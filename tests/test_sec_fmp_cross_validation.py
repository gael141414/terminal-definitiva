"""Motor de comparación SEC↔FMP (Sub-fase 1): modulos/sec_fmp_cross_validation.py.

Dos niveles de cobertura:

1. Lógica de clasificación pura (``comparar_metricas``/``_comparar_valor``/
   ``_verificar_periodo``/``_diff_pct``) con DataFrames de ratios sintéticos
   pequeños: cubre exhaustivamente coincide/discrepancia/no_comparable/
   periodo_no_alineado y los casos borde (FMP=0, año o métrica no
   compartidos, fechas ausentes vs. fechas que no coinciden).

2. Extremo a extremo (``comparar_estados_financieros``) con datos reales:
   el lado SEC son los fixtures de Apple de la Sub-fase 0
   (tests/fixtures/sec_edgar/*.csv, con period_end_dates reconstruido tal
   cual lo dejó una ejecución real de downloader.py — ver
   AAPL_PERIOD_END_DATES más abajo); el lado FMP es un DataFrame con
   columnas FMP construido con los MISMOS valores reales (revenue, grossProfit,
   netIncome, totalAssets, totalStockholdersEquity, D&A, capex, dividendos,
   recompras) tomados de esos mismos fixtures, para que el caso "coincide"
   esté grounded en datos reales y no en un ejemplo inventado. La única
   excepción es ``interestExpense``: Apple no desglosa un interés explícito
   en su cuenta de resultados (va dentro de "Other income/(expense), net"),
   así que se usa un valor ilustrativo — su único propósito es ejercitar la
   ruta "no_comparable" cuando el lado SEC genuinamente no tiene ese dato
   para 2022-2025 (confirmado real: el XBRL de Apple solo reporta
   InterestPaidNet para 2021).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.sec_fmp_cross_validation import (
    DISCREPANCY,
    MATCH,
    NOT_COMPARABLE,
    PERIOD_MISALIGNED,
    comparar_estados_financieros,
    comparar_metricas,
    fmp_period_end_dates,
)

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "sec_edgar"


def _load_sec_fixture(name: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / name, index_col=0)


# ---------------------------------------------------------------------------
# Nivel 1: lógica de clasificación pura, con DataFrames de ratios sintéticos
# ---------------------------------------------------------------------------


def _ratios_df(data: dict[str, list[float]], years: list[str]) -> pd.DataFrame:
    return pd.DataFrame(data, index=years)


def test_coincide_dentro_de_tolerancia():
    fmp = _ratios_df({"Margen Bruto %": [46.21]}, ["2024"])
    sec = _ratios_df({"Margen Bruto %": [46.30]}, ["2024"])  # ~0.19% relativo
    resultado = comparar_metricas(fmp, sec)
    assert len(resultado) == 1
    assert resultado[0].classification == MATCH
    assert resultado[0].note == ""


def test_discrepancia_fuera_de_tolerancia():
    fmp = _ratios_df({"Margen Bruto %": [46.21]}, ["2024"])
    sec = _ratios_df({"Margen Bruto %": [55.0]}, ["2024"])  # ~19% relativo
    resultado = comparar_metricas(fmp, sec)
    assert resultado[0].classification == DISCREPANCY
    assert resultado[0].diff_pct == pytest.approx((55.0 - 46.21) / 46.21 * 100)
    assert "tolerancia" in resultado[0].note


def test_no_comparable_valor_ausente_en_sec_no_es_discrepancia_100():
    fmp = _ratios_df({"Intereses % (s/OpInc)": [5.0]}, ["2024"])
    sec = _ratios_df({"Intereses % (s/OpInc)": [float("nan")]}, ["2024"])
    resultado = comparar_metricas(fmp, sec)
    assert resultado[0].classification == NOT_COMPARABLE
    assert resultado[0].diff_pct is None  # nunca "100% de diferencia"
    assert "SEC" in resultado[0].note


def test_no_comparable_valor_ausente_en_fmp():
    fmp = _ratios_df({"Margen Bruto %": [float("nan")]}, ["2024"])
    sec = _ratios_df({"Margen Bruto %": [46.21]}, ["2024"])
    resultado = comparar_metricas(fmp, sec)
    assert resultado[0].classification == NOT_COMPARABLE
    assert "FMP" in resultado[0].note


def test_no_comparable_ambos_ausentes():
    fmp = _ratios_df({"Margen Bruto %": [float("nan")]}, ["2024"])
    sec = _ratios_df({"Margen Bruto %": [float("nan")]}, ["2024"])
    resultado = comparar_metricas(fmp, sec)
    assert resultado[0].classification == NOT_COMPARABLE


def test_fmp_cero_y_sec_cero_es_coincide():
    fmp = _ratios_df({"Recompras (B USD)": [0.0]}, ["2024"])
    sec = _ratios_df({"Recompras (B USD)": [0.0]}, ["2024"])
    resultado = comparar_metricas(fmp, sec)
    assert resultado[0].classification == MATCH
    assert resultado[0].diff_pct is None


def test_fmp_cero_y_sec_no_cero_es_discrepancia_sin_diff_relativo():
    fmp = _ratios_df({"Recompras (B USD)": [0.0]}, ["2024"])
    sec = _ratios_df({"Recompras (B USD)": [5.0]}, ["2024"])
    resultado = comparar_metricas(fmp, sec)
    assert resultado[0].classification == DISCREPANCY
    assert resultado[0].diff_pct is None
    assert "no definida" in resultado[0].note


def test_metrica_no_compartida_se_ignora():
    fmp = _ratios_df({"Margen Bruto %": [46.21], "Solo FMP": [1.0]}, ["2024"])
    sec = _ratios_df({"Margen Bruto %": [46.21], "Solo SEC": [2.0]}, ["2024"])
    resultado = comparar_metricas(fmp, sec)
    assert {r.metric for r in resultado} == {"Margen Bruto %"}


def test_anio_no_compartido_se_ignora():
    fmp = _ratios_df({"Margen Bruto %": [46.21, 40.0]}, ["2023", "2024"])
    sec = _ratios_df({"Margen Bruto %": [46.21]}, ["2024"])
    resultado = comparar_metricas(fmp, sec)
    assert {r.year for r in resultado} == {"2024"}


def test_periodo_no_verificado_si_falta_alguna_fecha():
    fmp = _ratios_df({"Margen Bruto %": [46.21]}, ["2024"])
    sec = _ratios_df({"Margen Bruto %": [46.21]}, ["2024"])
    resultado = comparar_metricas(fmp, sec, fmp_period_end={"2024": "2024-09-28"})  # falta sec_period_end
    assert resultado[0].period_verified is False
    assert resultado[0].classification == MATCH  # no bloquea la comparación, solo no la certifica
    assert resultado[0].note == ""


def test_periodo_verificado_si_fechas_dentro_de_tolerancia():
    fmp = _ratios_df({"Margen Bruto %": [46.21]}, ["2024"])
    sec = _ratios_df({"Margen Bruto %": [46.21]}, ["2024"])
    resultado = comparar_metricas(
        fmp, sec,
        fmp_period_end={"2024": "2024-09-28"},
        sec_period_end={"2024": "2024-09-25"},  # 3 dias de diferencia, dentro de la tolerancia
    )
    assert resultado[0].period_verified is True
    assert resultado[0].classification == MATCH


def test_restatement_mismo_anio_fechas_de_periodo_distintas():
    """Mismo año fiscal ('2023' en ambos lados) pero fechas de fin de periodo
    muy distintas: no se debe tratar como discrepancia real."""
    fmp = _ratios_df({"Margen Bruto %": [46.0]}, ["2023"])
    sec = _ratios_df({"Margen Bruto %": [61.0]}, ["2023"])  # diferencia grande, pero no es de fiar
    resultado = comparar_metricas(
        fmp, sec,
        fmp_period_end={"2023": "2023-09-30"},
        sec_period_end={"2023": "2022-12-31"},  # ~9 meses de diferencia: posible restatement/cambio fiscal
    )
    assert resultado[0].classification == PERIOD_MISALIGNED
    assert resultado[0].period_verified is False
    assert "restatement" in resultado[0].note
    assert resultado[0].fmp_period_end == "2023-09-30"
    assert resultado[0].sec_period_end == "2022-12-31"


def test_dataframes_vacios_o_none_no_generan_comparaciones():
    assert comparar_metricas(None, _ratios_df({"x": [1.0]}, ["2024"])) == []
    assert comparar_metricas(_ratios_df({"x": [1.0]}, ["2024"]), None) == []
    assert comparar_metricas(pd.DataFrame(), pd.DataFrame()) == []


# ---------------------------------------------------------------------------
# fmp_period_end_dates: deriva {año: fecha} de un DatetimeIndex real
# ---------------------------------------------------------------------------


def test_fmp_period_end_dates_deriva_del_indice_real():
    df = pd.DataFrame(
        {"revenue": [100.0, 200.0]},
        index=pd.to_datetime(["2023-09-30", "2024-09-28"]),
    )
    fechas = fmp_period_end_dates(df)
    assert fechas == {"2023": "2023-09-30", "2024": "2024-09-28"}


def test_fmp_period_end_dates_devuelve_vacio_sin_datetimeindex():
    df = pd.DataFrame({"revenue": [100.0]}, index=["2024"])
    assert fmp_period_end_dates(df) == {}


def test_fmp_period_end_dates_none_o_vacio():
    assert fmp_period_end_dates(None) == {}
    assert fmp_period_end_dates(pd.DataFrame()) == {}


# ---------------------------------------------------------------------------
# Nivel 2: extremo a extremo con datos reales de Apple
# ---------------------------------------------------------------------------

# Fechas reales de fin de periodo, tal como las capturó una ejecución real de
# downloader.obtener_estados_financieros("AAPL", años=5, usar_cache=False)
# tras la Sub-fase 1 (df.attrs["period_end_dates"]) — no sobreviven el
# roundtrip por CSV, así que se reconstruyen aquí explícitamente sobre los
# fixtures ya committeados en la Sub-fase 0.
AAPL_SEC_PERIOD_END = {
    "2021": "2021-09-25",
    "2022": "2022-09-24",
    "2023": "2023-09-30",
    "2024": "2024-09-28",
    "2025": "2025-09-27",
}


def _sec_fixture_con_attrs(name: str) -> pd.DataFrame:
    df = _load_sec_fixture(name)
    años_presentes = [c for c in df.columns if str(c).isdigit()]
    df.attrs["period_end_dates"] = {y: AAPL_SEC_PERIOD_END[y] for y in años_presentes if y in AAPL_SEC_PERIOD_END}
    return df


def _fmp_income_df() -> pd.DataFrame:
    # Mismos valores reales que tests/fixtures/sec_edgar/AAPL_is.csv, en
    # columnas FMP. interestExpense es ilustrativo (ver docstring del módulo).
    years = ["2021", "2022", "2023", "2024", "2025"]
    return pd.DataFrame(
        {
            "revenue": [365817e6, 394328e6, 383285e6, 391035e6, 416161e6],
            "costOfRevenue": [212981e6, 223546e6, 214137e6, 210352e6, 220960e6],
            "grossProfit": [152836e6, 170782e6, 169148e6, 180683e6, 195201e6],
            "researchAndDevelopmentExpenses": [21914e6, 26251e6, 29915e6, 31370e6, 34550e6],
            "sellingGeneralAndAdministrativeExpenses": [21973e6, 25094e6, 24932e6, 26097e6, 27601e6],
            "operatingIncome": [108949e6, 119437e6, 114301e6, 123216e6, 133050e6],
            "netIncome": [94680e6, 99803e6, 96995e6, 93736e6, 112010e6],
            "interestExpense": [2687e6, 3000e6, 3000e6, 3000e6, 3000e6],
        },
        index=pd.to_datetime(["2021-09-25", "2022-09-24", "2023-09-30", "2024-09-28", "2025-09-27"]),
    )


def _fmp_cashflow_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "depreciationAndAmortization": [11284e6, 11104e6, 11519e6, 11445e6, 11698e6],
            "capitalExpenditure": [-11085e6, -10708e6, -10959e6, -9447e6, -12715e6],
            "commonStockRepurchased": [-85971e6, -89402e6, -77550e6, -94949e6, -90711e6],
            "operatingCashFlow": [104038e6, 122151e6, 110543e6, 118254e6, 111482e6],
            "dividendsPaid": [-14467e6, -14841e6, -15025e6, -15234e6, -15421e6],
        },
        index=pd.to_datetime(["2021-09-25", "2022-09-24", "2023-09-30", "2024-09-28", "2025-09-27"]),
    )


def _fmp_balance_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "totalAssets": [352755e6, 352583e6, 364980e6, 359241e6],
            "totalStockholdersEquity": [50672e6, 62146e6, 56950e6, 73733e6],
        },
        index=pd.to_datetime(["2022-09-24", "2023-09-30", "2024-09-28", "2025-09-27"]),
    )


def test_e2e_metricas_clave_coinciden_con_datos_reales_de_apple():
    df_is_sec = _sec_fixture_con_attrs("AAPL_is.csv")
    df_cf_sec = _sec_fixture_con_attrs("AAPL_cf.csv")
    df_bs_sec = _sec_fixture_con_attrs("AAPL_bs.csv")

    resultados = comparar_estados_financieros(
        df_is_fmp=_fmp_income_df(), df_cf_fmp=_fmp_cashflow_df(), df_bs_fmp=_fmp_balance_df(),
        df_is_sec=df_is_sec, df_cf_sec=df_cf_sec, df_bs_sec=df_bs_sec,
    )
    assert resultados  # no vacío

    por_metrica_2024 = {r.metric: r for r in resultados if r.year == "2024"}
    for metrica in ("Margen Bruto %", "Margen Neto %", "SG&A % (s/MB)"):
        comp = por_metrica_2024[metrica]
        assert comp.classification == MATCH, f"{metrica}: {comp}"
        assert comp.period_verified is True

    roe = por_metrica_2024["ROE %"]
    assert roe.classification == MATCH
    assert roe.sec_value == pytest.approx(157.41, abs=0.01)


def test_e2e_concepto_ausente_en_sec_intereses_es_no_comparable_no_discrepancia():
    df_is_sec = _sec_fixture_con_attrs("AAPL_is.csv")
    df_cf_sec = _sec_fixture_con_attrs("AAPL_cf.csv")

    resultados = comparar_estados_financieros(
        df_is_fmp=_fmp_income_df(), df_cf_fmp=_fmp_cashflow_df(), df_bs_fmp=None,
        df_is_sec=df_is_sec, df_cf_sec=df_cf_sec, df_bs_sec=None,
    )
    intereses_2024 = next(r for r in resultados if r.metric == "Intereses % (s/OpInc)" and r.year == "2024")
    assert intereses_2024.classification == NOT_COMPARABLE
    assert intereses_2024.diff_pct is None
    assert "SEC" in intereses_2024.note


def test_e2e_discrepancia_fabricada_modificando_revenue_fmp():
    df_is_sec = _sec_fixture_con_attrs("AAPL_is.csv")
    df_cf_sec = _sec_fixture_con_attrs("AAPL_cf.csv")

    df_is_fmp_alterado = _fmp_income_df()
    # Se infla el revenue de 2024 un 20% a propósito: revienta Margen Bruto %
    # y Margen Neto % muy por encima de la banda de tolerancia (±2%).
    df_is_fmp_alterado.loc[df_is_fmp_alterado.index[3], "revenue"] *= 1.20

    resultados = comparar_estados_financieros(
        df_is_fmp=df_is_fmp_alterado, df_cf_fmp=_fmp_cashflow_df(), df_bs_fmp=None,
        df_is_sec=df_is_sec, df_cf_sec=df_cf_sec, df_bs_sec=None,
    )
    margen_bruto_2024 = next(r for r in resultados if r.metric == "Margen Bruto %" and r.year == "2024")
    assert margen_bruto_2024.classification == DISCREPANCY
    assert abs(margen_bruto_2024.diff_pct) > 2.0
    assert "tolerancia" in margen_bruto_2024.note


def test_e2e_sin_period_end_dates_degrada_a_alineacion_solo_por_anio():
    """Si el SEC viene de un cache en disco (sin .attrs), la comparación sigue
    funcionando, solo que sin certificar el periodo."""
    df_is_sec = _load_sec_fixture("AAPL_is.csv")  # sin .attrs adjuntos
    df_cf_sec = _load_sec_fixture("AAPL_cf.csv")

    resultados = comparar_estados_financieros(
        df_is_fmp=_fmp_income_df(), df_cf_fmp=_fmp_cashflow_df(), df_bs_fmp=None,
        df_is_sec=df_is_sec, df_cf_sec=df_cf_sec, df_bs_sec=None,
    )
    margen_bruto_2024 = next(r for r in resultados if r.metric == "Margen Bruto %" and r.year == "2024")
    assert margen_bruto_2024.classification == MATCH
    assert margen_bruto_2024.period_verified is False
    assert margen_bruto_2024.sec_period_end is None
