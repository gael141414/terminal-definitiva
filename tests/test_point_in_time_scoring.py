"""Motor de scoring point-in-time (Sub-fase 3, calibración del score).

Cubre lo que se puede probar de forma determinista, sin red: el reshape
"as reported" -> forma "_legacy", el filtro por filing_date (la pieza que
evita el look-ahead bias, con un caso real -- el restatement de Bitcoin de
RIOT confirmado en la Sub-fase 1), la inyección/restauración de precio y
snapshot de mercado históricos, y la persistencia. La ejecución real con
empresas reales (FMP + yfinance en vivo) se hizo aparte y se describe en el
informe de la tarea -- mismo criterio que el resto de la suite desde la
Fase 7 (sin red en pytest).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import financials.valuator as valuator
import modulos.scoring_engine as scoring_engine
from modulos import point_in_time_scoring as pits


# ---------------------------------------------------------------------------
# _as_reported_a_forma_legacy: reshape fecha=índice/concepto=columna -> forma
# concepto=fila (columna "concept") / año=columna
# ---------------------------------------------------------------------------


def test_as_reported_a_forma_legacy_transpone_correctamente():
    df = pd.DataFrame(
        {
            "netincomeloss": [10.0, 12.0],
            "revenuefromcontractwithcustomerexcludingassessedtax": [100.0, 110.0],
            "fiscalYear": [2023, 2024],
            "period": ["FY", "FY"],
        },
        index=pd.to_datetime(["2023-12-31", "2024-12-31"]),
    )
    df.attrs["filing_dates"] = {"2023": "2024-02-01", "2024": "2025-02-01"}
    df.attrs["accepted_dates"] = {"2023": "2024-02-01 10:00:00", "2024": "2025-02-01 10:00:00"}

    resultado = pits._as_reported_a_forma_legacy(df)

    assert resultado is not None
    assert set(resultado["concept"]) == {"netincomeloss", "revenuefromcontractwithcustomerexcludingassessedtax"}
    fila = resultado[resultado["concept"] == "netincomeloss"].iloc[0]
    assert fila["2023"] == 10.0
    assert fila["2024"] == 12.0
    # metadata (fiscalYear/period) no debe colarse como "concepto".
    assert "fiscalYear" not in set(resultado["concept"])
    assert resultado.attrs["filing_dates"] == {"2023": "2024-02-01", "2024": "2025-02-01"}
    assert resultado.attrs["accepted_dates"] == {"2023": "2024-02-01 10:00:00", "2024": "2025-02-01 10:00:00"}


def test_as_reported_a_forma_legacy_none_si_vacio_o_none():
    assert pits._as_reported_a_forma_legacy(None) is None
    assert pits._as_reported_a_forma_legacy(pd.DataFrame()) is None


# ---------------------------------------------------------------------------
# _filtrar_columnas_por_filing_date: la pieza que evita el look-ahead bias
# ---------------------------------------------------------------------------


def _df_legacy(years_values: dict[str, float], filing_dates: dict[str, str]) -> pd.DataFrame:
    df = pd.DataFrame({"concept": ["NetIncomeLoss"], **{y: [v] for y, v in years_values.items()}})
    df.attrs["filing_dates"] = filing_dates
    return df


def test_filtrar_excluye_anio_con_filing_posterior_a_as_of():
    df = _df_legacy({"2022": 100.0, "2023": 110.0}, {"2022": "2023-02-01", "2023": "2024-02-01"})

    resultado = pits._filtrar_columnas_por_filing_date(df, "2023-06-01")

    assert "2022" in resultado.columns
    assert "2023" not in resultado.columns  # filed 2024-02-01, posterior a as_of


def test_filtrar_incluye_anio_con_filing_el_mismo_dia_del_as_of():
    df = _df_legacy({"2022": 100.0}, {"2022": "2023-02-01"})

    resultado = pits._filtrar_columnas_por_filing_date(df, "2023-02-01")

    assert "2022" in resultado.columns


def test_filtrar_excluye_anio_sin_fecha_de_filing_conocida():
    """Un año sin fecha de filing conocida nunca se asume disponible --
    mismo principio de "nunca dato artificial" que el resto del proyecto."""
    df = _df_legacy({"2022": 100.0, "2023": 110.0}, {"2022": "2023-02-01"})  # 2023 sin fecha

    resultado = pits._filtrar_columnas_por_filing_date(df, "2025-01-01")

    assert "2022" in resultado.columns
    assert "2023" not in resultado.columns


def test_filtrar_devuelve_none_si_ningun_anio_pasa_el_filtro():
    df = _df_legacy({"2023": 110.0}, {"2023": "2024-02-01"})

    assert pits._filtrar_columnas_por_filing_date(df, "2023-01-01") is None


def test_no_look_ahead_bitcoin_impairment_riot_caso_real():
    """Caso real confirmado en la Sub-fase 1: RIOT restató el impairment de
    Bitcoin de FY2021 de $36,462,000 (10-K original, filed 2022-03-16) a
    $43,973,000 (comparativa del 10-K de FY2022, filed 2023-03-02) -- el
    valor corregido ni siquiera existe en esta fuente hasta ese filing."""
    df = pd.DataFrame({"concept": ["riot_ImpairmentGainLossOnCryptocurrencies"], "2021": [36462000.0]})
    df.attrs["filing_dates"] = {"2021": "2022-03-16"}

    # Antes del filing original: 2021 no debe estar disponible en absoluto.
    assert pits._filtrar_columnas_por_filing_date(df, "2022-01-01") is None

    # Justo después del filing original: disponible, con el valor ORIGINAL.
    despues = pits._filtrar_columnas_por_filing_date(df, "2022-03-17")
    assert despues is not None
    assert despues.loc[0, "2021"] == 36462000.0


# ---------------------------------------------------------------------------
# construir_fundamentales_point_in_time_fmp: integración (extraer_datos_as_reported_fmp mockeado)
# ---------------------------------------------------------------------------


def test_construir_fundamentales_fmp_excluye_anio_futuro(monkeypatch):
    df_is = pd.DataFrame(
        {"netincomeloss": [10.0, 12.0], "fiscalYear": [2023, 2024], "period": ["FY", "FY"]},
        index=pd.to_datetime(["2023-12-31", "2024-12-31"]),
    )
    df_is.attrs["filing_dates"] = {"2023": "2024-02-01", "2024": "2025-02-01"}
    monkeypatch.setattr(pits, "extraer_datos_as_reported_fmp", lambda ticker, limite: (df_is, None, None))

    is_df, bs_df, cf_df = pits.construir_fundamentales_point_in_time_fmp("TEST", "2024-06-01")

    assert is_df is not None
    assert sorted(c for c in is_df.columns if str(c).isdigit()) == ["2023"]  # 2024 excluido
    assert bs_df is None
    assert cf_df is None


# ---------------------------------------------------------------------------
# _inyectar_datos_historicos: inyecta y restaura, incluso ante excepción
# ---------------------------------------------------------------------------


def test_inyectar_datos_historicos_inyecta_y_restaura(monkeypatch):
    monkeypatch.setattr(pits, "_historical_price", lambda t, d: 123.45)
    monkeypatch.setattr(pits, "_historical_market_snapshot", lambda t, d: {"beta": None, "rsi": 55.0})

    precio_original = valuator.obtener_cotizacion_fmp
    snapshot_original = scoring_engine._market_data_snapshot

    with pits._inyectar_datos_historicos("TEST", "2024-01-01") as precio:
        assert precio == 123.45
        assert valuator.obtener_cotizacion_fmp("TEST") == 123.45
        assert scoring_engine._market_data_snapshot("TEST") == {"beta": None, "rsi": 55.0}

    assert valuator.obtener_cotizacion_fmp is precio_original
    assert scoring_engine._market_data_snapshot is snapshot_original


def test_inyectar_datos_historicos_restaura_incluso_si_el_bloque_lanza(monkeypatch):
    monkeypatch.setattr(pits, "_historical_price", lambda t, d: None)
    monkeypatch.setattr(pits, "_historical_market_snapshot", lambda t, d: {})
    precio_original = valuator.obtener_cotizacion_fmp

    with pytest.raises(RuntimeError):
        with pits._inyectar_datos_historicos("TEST", "2024-01-01"):
            raise RuntimeError("boom")

    assert valuator.obtener_cotizacion_fmp is precio_original


def test_inyectar_datos_historicos_usa_0_0_si_no_hay_precio_mismo_contrato_que_el_real(monkeypatch):
    """obtener_cotizacion_fmp real devuelve 0.0 (nunca None) si no hay
    cotización -- la versión inyectada debe seguir el mismo contrato."""
    monkeypatch.setattr(pits, "_historical_price", lambda t, d: None)
    monkeypatch.setattr(pits, "_historical_market_snapshot", lambda t, d: {})

    with pits._inyectar_datos_historicos("TEST", "2024-01-01"):
        assert valuator.obtener_cotizacion_fmp("TEST") == 0.0


# ---------------------------------------------------------------------------
# Persistencia: dominio propio, separado de analysis_store.py
# ---------------------------------------------------------------------------


def _score_de_prueba(identificador="TEST", final_score=72.5) -> pits.FrozenScore:
    return pits.FrozenScore(
        identificador=identificador, fuente="fmp", as_of_date="2024-01-01",
        fiscal_year_mas_reciente_incluido="2023", final_score=final_score, confidence=0.8,
        verdict="Comprar", data_coverage=0.9,
        componentes=[{"name": "Calidad fundamental", "score": 80.0, "weight": 0.30, "confidence": 0.9}],
        precio_historico=123.45, red_flags=[],
    )


def test_guardar_y_cargar_scores_congelados_roundtrip(tmp_path):
    path = tmp_path / "scores.json"
    pits.guardar_score_congelado(_score_de_prueba(), path=path)

    cargados = pits.cargar_scores_congelados(path=path)

    assert len(cargados) == 1
    assert cargados[0]["identificador"] == "TEST"
    assert cargados[0]["final_score"] == 72.5
    assert cargados[0]["componentes"][0]["name"] == "Calidad fundamental"


def test_guardar_hace_append_no_sobrescribe(tmp_path):
    path = tmp_path / "scores.json"

    pits.guardar_score_congelado(_score_de_prueba("A", final_score=1.0), path=path)
    pits.guardar_score_congelado(_score_de_prueba("B", final_score=2.0), path=path)

    cargados = pits.cargar_scores_congelados(path=path)
    assert [c["identificador"] for c in cargados] == ["A", "B"]


def test_cargar_scores_congelados_vacio_si_no_existe_el_archivo(tmp_path):
    assert pits.cargar_scores_congelados(path=tmp_path / "no_existe.json") == []


# ---------------------------------------------------------------------------
# Extremo a extremo: congelar_score_fmp sobre fundamentales sintéticos
# (reshape + filtro + analizadores reales + scoring_engine real, sin red)
# ---------------------------------------------------------------------------


def _as_reported_sintetico_multi_anio() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    idx = pd.to_datetime(["2022-12-31", "2023-12-31", "2024-12-31"])
    df_is = pd.DataFrame(
        {
            "revenuefromcontractwithcustomerexcludingassessedtax": [200e9, 210e9, 220e9],
            "costofgoodsandservicessold": [120e9, 124e9, 128e9],
            "netincomeloss": [40e9, 42e9, 45e9],
            "operatingincomeloss": [55e9, 58e9, 62e9],
            "fiscalYear": [2022, 2023, 2024], "period": ["FY", "FY", "FY"],
        },
        index=idx,
    )
    df_bs = pd.DataFrame(
        {
            "stockholdersequity": [60e9, 65e9, 70e9],
            "assets": [300e9, 310e9, 320e9],
            "longtermdebtnoncurrent": [20e9, 20e9, 20e9],
            "retainedearningsaccumulateddeficit": [30e9, 35e9, 40e9],
            "fiscalYear": [2022, 2023, 2024], "period": ["FY", "FY", "FY"],
        },
        index=idx,
    )
    df_cf = pd.DataFrame(
        {
            "netcashprovidedbyoperatingactivities": [50e9, 52e9, 55e9],
            "paymentstoacquirepropertyplantandequipment": [10e9, 11e9, 12e9],
            "fiscalYear": [2022, 2023, 2024], "period": ["FY", "FY", "FY"],
        },
        index=idx,
    )
    filing_dates = {"2022": "2023-02-15", "2023": "2024-02-15", "2024": "2025-02-15"}
    for df in (df_is, df_bs, df_cf):
        df.attrs["filing_dates"] = filing_dates
        df.attrs["accepted_dates"] = {}
    return df_is, df_bs, df_cf


def test_congelar_score_fmp_extremo_a_extremo_sin_red(monkeypatch):
    df_is, df_bs, df_cf = _as_reported_sintetico_multi_anio()
    monkeypatch.setattr(pits, "extraer_datos_as_reported_fmp", lambda ticker, limite: (df_is, df_bs, df_cf))
    monkeypatch.setattr(pits, "_historical_price", lambda t, d: 150.0)
    monkeypatch.setattr(
        pits, "_historical_market_snapshot",
        lambda t, d: {"beta": None, "market_cap": None, "sector": None, "rsi": 50.0, "ret_6m": 0.05,
                       "ret_1y": 0.10, "vol_1y": 0.2, "max_drawdown_1y": -0.1, "sma50_above_sma200": True,
                       "price_above_sma200": True, "sector_rel_3m": None, "insider_pct": None,
                       "inst_pct": None, "short_ratio": None},
    )

    resultado = pits.congelar_score_fmp("TEST", "2024-06-01", limite_anios=5)

    assert resultado is not None
    assert resultado.fuente == "fmp"
    assert resultado.fiscal_year_mas_reciente_incluido == "2023"  # 2024 (filed 2025-02-15) no debe verse
    assert resultado.final_score is not None
    assert 0 <= resultado.final_score <= 100
    assert len(resultado.componentes) == 8
    assert resultado.precio_historico == 150.0


def test_congelar_score_fmp_none_si_no_hay_fundamentales(monkeypatch):
    monkeypatch.setattr(pits, "extraer_datos_as_reported_fmp", lambda ticker, limite: (None, None, None))

    assert pits.congelar_score_fmp("TEST", "2024-06-01") is None
