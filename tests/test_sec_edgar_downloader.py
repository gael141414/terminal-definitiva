"""SEC EDGAR (edgartools) resiliencia: downloader.py + rutas "_legacy" de los analyzers.

Cubre lo que quedaba sin probar del bloque SEC↔FMP (Sub-fase 0, fundamentos
antes del motor de comparación cruzada):

1. downloader.py clasifica errores de edgartools/httpx con la jerarquía común
   de modulos/data_provider_errors.py en vez de tragarlos con un
   ``except Exception`` amplio.
2. El bug de ``años=1`` (``.latest(1)`` de edgartools devuelve un
   ``EntityFiling`` suelto no iterable en vez de una colección) está
   corregido: no debe propagar ``TypeError``.
3. Un fallo de red/rate-limit de SEC EDGAR mantiene el contrato externo
   (``(None, None, None)``) pero queda clasificado y logueado, no silenciado.
4. Las rutas "_legacy" (income/balance/cashflow_analyzer.py) siguen
   funcionando contra la forma real que produce edgartools — fixtures reales
   de Apple (``tests/fixtures/sec_edgar/``), las mismas obtenidas y
   verificadas contra FMP en el diagnóstico previo (Margen Bruto/Neto, ROE).
5. Un concepto XBRL no encontrado en ``extraer_dato_robusto`` devuelve NaN,
   nunca un cero artificial ni un ``TypeError``.

Ninguno de estos tests toca la red real: ``Company``/``get_filings`` se
sustituyen por dobles mínimos (mismo criterio que ``test_data_provider_errors.py``
mockeando ``requests.get``), y las rutas _legacy se prueban con CSVs reales
pre-descargados, sin invocar a edgartools en absoluto.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import httpx
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import downloader
from balance_analyzer import analizar_balance
from cashflow_analyzer import analizar_flujo_efectivo
from edgar import CompanyNotFoundError
from edgar.httprequests import TooManyRequestsError
from income_analyzer import analizar_cuenta_resultados, extraer_dato_robusto

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "sec_edgar"


def _load_fixture(name: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / name, index_col=0)


# ---------------------------------------------------------------------------
# downloader._fetch_filings: normalización de años=1 + clasificación de errores
# ---------------------------------------------------------------------------


class _FakeFiling:
    """Doble mínimo de edgar.entity.filings.EntityFiling."""

    def __init__(self, xbrl_obj=None, fail: bool = False):
        self._xbrl_obj = xbrl_obj
        self._fail = fail

    def xbrl(self):
        if self._fail:
            raise RuntimeError("xbrl parse failure")
        return self._xbrl_obj


class _FakeFilings(list):
    """Colección iterable: simula EntityFilings (años>=2)."""


class _FakeFilingsQuery:
    def __init__(self, result):
        self._result = result

    def latest(self, n):
        return self._result


class _FakeCompany:
    """Doble de edgar.Company: get_filings(form=...).latest(n)."""

    def __init__(self, filings_result=None, raise_on_get_filings: Exception | None = None):
        self._filings_result = filings_result
        self._raise = raise_on_get_filings

    def get_filings(self, form):
        if self._raise is not None:
            raise self._raise
        return _FakeFilingsQuery(self._filings_result)


def test_latest_1_devuelve_filing_suelto_envuelto_en_lista():
    filing = _FakeFiling()
    empresa = _FakeCompany(filings_result=filing)  # no iterable, como EntityFiling real
    resultado = downloader._fetch_filings(empresa, "10-K", 1, context="test")
    assert resultado == [filing]


def test_latest_n_devuelve_coleccion_iterable_tal_cual():
    filings = _FakeFilings([_FakeFiling(), _FakeFiling(), _FakeFiling()])
    empresa = _FakeCompany(filings_result=filings)
    resultado = downloader._fetch_filings(empresa, "10-K", 3, context="test")
    assert len(resultado) == 3


def test_filings_none_se_clasifica_como_no_data_error():
    empresa = _FakeCompany(filings_result=None)
    with pytest.raises(downloader.NoDataError):
        downloader._fetch_filings(empresa, "10-K", 5, context="test")


def test_company_not_found_se_clasifica_invalid_ticker():
    empresa = _FakeCompany(raise_on_get_filings=CompanyNotFoundError("ZZZZINVALID"))
    with pytest.raises(downloader.InvalidTickerError):
        downloader._fetch_filings(empresa, "10-K", 5, context="test")


def test_too_many_requests_se_clasifica_rate_limited():
    empresa = _FakeCompany(raise_on_get_filings=TooManyRequestsError("https://sec.gov/x"))
    with pytest.raises(downloader.RateLimitedError):
        downloader._fetch_filings(empresa, "10-K", 5, context="test")


def test_httpx_timeout_se_clasifica_data_timeout_error():
    empresa = _FakeCompany(raise_on_get_filings=httpx.ReadTimeout("timed out"))
    with pytest.raises(downloader.DataTimeoutError):
        downloader._fetch_filings(empresa, "10-K", 5, context="test")


def test_httpx_error_generico_se_clasifica_provider_error():
    empresa = _FakeCompany(raise_on_get_filings=httpx.ConnectError("conn refused"))
    with pytest.raises(downloader.ProviderError):
        downloader._fetch_filings(empresa, "10-K", 5, context="test")


def test_error_generico_no_tipado_se_clasifica_provider_error():
    empresa = _FakeCompany(raise_on_get_filings=RuntimeError("algo raro"))
    with pytest.raises(downloader.ProviderError):
        downloader._fetch_filings(empresa, "10-K", 5, context="test")


# ---------------------------------------------------------------------------
# obtener_estados_financieros: contrato externo end-to-end (Company mockeada)
# ---------------------------------------------------------------------------


class _FakeStatement:
    def __init__(self, df):
        self.to_dataframe = lambda: df


class _FakeStatements:
    def __init__(self, is_df, bs_df, cf_df):
        self.income_statement = _FakeStatement(is_df)
        self.balance_sheet = _FakeStatement(bs_df)
        self.cashflow_statement = _FakeStatement(cf_df)


class _FakeXbrl:
    def __init__(self, is_df, bs_df, cf_df):
        self.statements = _FakeStatements(is_df, bs_df, cf_df)


def _single_year_frames(year: str):
    is_df = pd.DataFrame({
        "concept": ["us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap_NetIncomeLoss"],
        year: [391035000000.0, 93736000000.0],
    })
    bs_df = pd.DataFrame({
        "concept": ["us-gaap_Assets", "us-gaap_StockholdersEquity"],
        year: [364980000000.0, 56950000000.0],
    })
    cf_df = pd.DataFrame({
        "concept": ["us-gaap_DepreciationDepletionAndAmortization"],
        year: [11445000000.0],
    })
    return is_df, bs_df, cf_df


@pytest.fixture
def _no_disk_cache(tmp_path, monkeypatch):
    """Aísla cache_datos/ en un directorio temporal: nunca escribe en el repo real."""
    monkeypatch.chdir(tmp_path)


def test_anos_1_no_propaga_typeerror_y_devuelve_dataframes(_no_disk_cache, monkeypatch):
    is_df, bs_df, cf_df = _single_year_frames("2024-09-28")
    filing = _FakeFiling(xbrl_obj=_FakeXbrl(is_df, bs_df, cf_df))
    monkeypatch.setattr(downloader, "Company", lambda ticker: _FakeCompany(filings_result=filing))
    monkeypatch.setattr(downloader.time, "sleep", lambda _s: None)

    df_is, df_bs, df_cf = downloader.obtener_estados_financieros("TESTX", años=1, usar_cache=False)

    assert df_is is not None and not df_is.empty
    assert df_bs is not None and not df_bs.empty
    assert df_cf is not None and not df_cf.empty
    assert "2024" in df_is.columns


def test_anos_multiple_consolida_varios_filings(_no_disk_cache, monkeypatch):
    filing_2023 = _FakeFiling(xbrl_obj=_FakeXbrl(*_single_year_frames("2023-09-30")))
    filing_2024 = _FakeFiling(xbrl_obj=_FakeXbrl(*_single_year_frames("2024-09-28")))
    monkeypatch.setattr(
        downloader, "Company",
        lambda ticker: _FakeCompany(filings_result=_FakeFilings([filing_2024, filing_2023])),
    )
    monkeypatch.setattr(downloader.time, "sleep", lambda _s: None)

    df_is, df_bs, df_cf = downloader.obtener_estados_financieros("TESTX", años=2, usar_cache=False)

    assert sorted(c for c in df_is.columns if c.isdigit()) == ["2023", "2024"]


def test_fallo_de_red_devuelve_contrato_none_y_loggea_clasificado(_no_disk_cache, monkeypatch, caplog):
    def _raise_connect_error(ticker):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(downloader, "Company", _raise_connect_error)

    with caplog.at_level(logging.WARNING, logger="downloader"):
        resultado = downloader.obtener_estados_financieros("TESTX", años=3, usar_cache=False)

    assert resultado == (None, None, None)
    assert any("provider_error" in record.message for record in caplog.records)


def test_rate_limit_devuelve_contrato_none_y_loggea_clasificado(_no_disk_cache, monkeypatch, caplog):
    def _raise_rate_limited(ticker):
        raise TooManyRequestsError("https://sec.gov/x")

    monkeypatch.setattr(downloader, "Company", _raise_rate_limited)

    with caplog.at_level(logging.WARNING, logger="downloader"):
        resultado = downloader.obtener_estados_financieros("TESTX", años=3, usar_cache=False)

    assert resultado == (None, None, None)
    assert any("rate_limited" in record.message for record in caplog.records)


def test_un_filing_roto_no_tumba_el_resto(_no_disk_cache, monkeypatch):
    """Un filing individual que falla al parsear xbrl() se omite (logueado en
    debug) sin abortar la consolidación de los demás años."""
    filing_ok = _FakeFiling(xbrl_obj=_FakeXbrl(*_single_year_frames("2024-09-28")))
    filing_roto = _FakeFiling(fail=True)
    monkeypatch.setattr(
        downloader, "Company",
        lambda ticker: _FakeCompany(filings_result=_FakeFilings([filing_ok, filing_roto])),
    )
    monkeypatch.setattr(downloader.time, "sleep", lambda _s: None)

    df_is, df_bs, df_cf = downloader.obtener_estados_financieros("TESTX", años=2, usar_cache=False)

    assert df_is is not None and "2024" in df_is.columns


# ---------------------------------------------------------------------------
# extraer_dato_robusto: concepto XBRL ausente -> NaN, nunca cero ni TypeError
# ---------------------------------------------------------------------------


def test_extraer_dato_robusto_concepto_ausente_devuelve_nan_no_cero():
    df = pd.DataFrame({
        "concept": ["us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax"],
        "2024": [391035000000.0],
    })
    resultado = extraer_dato_robusto(df, ["InterestExpense", "InterestAndDebtExpense"], ["2024"])
    assert resultado.isna().all()
    assert not (resultado == 0).any()


def test_extraer_dato_robusto_sobre_fixture_real_aapl_is():
    df = _load_fixture("AAPL_is.csv")
    ventas = extraer_dato_robusto(
        df,
        ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
        ["2024"],
    )
    assert ventas["2024"] == pytest.approx(391035000000.0)


# ---------------------------------------------------------------------------
# Rutas _legacy end-to-end: fixtures reales de Apple (income/balance/cashflow)
# ---------------------------------------------------------------------------


def test_analizar_cuenta_resultados_legacy_con_fixture_real_aapl():
    df_is = _load_fixture("AAPL_is.csv")
    df_cf = _load_fixture("AAPL_cf.csv")

    resultado = analizar_cuenta_resultados(df_is, df_cf)

    assert resultado is not None
    ratios = resultado["ratios"]
    # Valores cruzados contra FMP en el diagnóstico previo: coinciden exactos.
    assert ratios.loc["2024", "Margen Bruto %"] == pytest.approx(46.21, abs=0.01)
    assert ratios.loc["2024", "Margen Neto %"] == pytest.approx(23.97, abs=0.01)
    assert ratios.loc["2024", "SG&A % (s/MB)"] == pytest.approx(14.44, abs=0.01)


def test_analizar_balance_legacy_con_fixture_real_aapl():
    df_bs = _load_fixture("AAPL_bs.csv")
    df_is = _load_fixture("AAPL_is.csv")

    resultado = analizar_balance(df_bs, df_is)

    assert resultado is not None
    ratios = resultado["ratios"]
    assert ratios.loc["2024", "ROE %"] == pytest.approx(157.41, abs=0.01)
    assert resultado["flags"] == []


def test_analizar_flujo_efectivo_legacy_con_fixture_real_aapl():
    df_cf = _load_fixture("AAPL_cf.csv")
    df_is = _load_fixture("AAPL_is.csv")

    resultado = analizar_flujo_efectivo(df_cf, df_is)

    assert resultado is not None
    ratios = resultado["ratios"]
    assert ratios.loc["2024", "Free Cash Flow (B USD)"] == pytest.approx(108.81, abs=0.01)
