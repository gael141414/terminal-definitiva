"""WACC real en valuator.py (Fase 7, punto 3) y CAPM real (Fase 8, punto 1).

Cubre _calcular_wacc de forma aislada (todas las ramas: sin market_cap, sin
deuda, con deuda y coste de deuda real, con deuda pero sin interestExpense —
el caso que exige el proxy documentado en vez de un 0% artificial), y
_obtener_capm_inputs de forma aislada (risk-free/beta reales, y cada
combinación de fallback cuando Yahoo no da datos). También una integración
ligera con _valorar_empresa_fmp/_valorar_empresa_legacy confirmando que wacc
(no tasa_descuento_capm) es lo que realmente alimenta dcf_value/epv_value, y
que el CAPM real (o su fallback declarado) llega hasta ahí.

La validación con datos reales de Apple/Microsoft/Coca-Cola (confirmando que
el WACC queda en el mismo orden de magnitud que el CAPM anterior) se hizo
aparte, en vivo, y se describe en el informe de la tarea — aquí solo la
lógica determinista, sin red (obtener_risk_free_real/obtener_beta_real van
siempre mockeados: no tocan Yahoo en esta suite).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from financials.valuator import (
    CAPM_BETA_FALLBACK,
    CAPM_RISK_FREE_FALLBACK,
    _calcular_wacc,
    _last_valid_allow_zero,
    _obtener_capm_inputs,
    valorar_empresa,
)


# ---------------------------------------------------------------------------
# _calcular_wacc: lógica pura
# ---------------------------------------------------------------------------


def test_sin_market_cap_devuelve_capm_puro_con_nota():
    wacc, nota = _calcular_wacc(
        market_cap=None, total_debt=1e9, interest_expense=5e7, tax_rate=0.21, costo_capital_propio=0.10,
    )
    assert wacc == 0.10
    assert "market_cap no disponible" in nota


def test_empresa_sin_deuda_wacc_igual_a_capm_sin_nota():
    wacc, nota = _calcular_wacc(
        market_cap=1e12, total_debt=0.0, interest_expense=None, tax_rate=0.21, costo_capital_propio=0.10,
    )
    assert wacc == 0.10
    assert nota == ""


def test_empresa_sin_deuda_none_equivale_a_cero():
    wacc, nota = _calcular_wacc(
        market_cap=1e12, total_debt=None, interest_expense=None, tax_rate=0.21, costo_capital_propio=0.10,
    )
    assert wacc == 0.10
    assert nota == ""


def test_con_deuda_e_interes_real_calcula_blend_sin_nota():
    # E=800, D=200, rE=10%, rD=1000/200=5%, T=20% -> WACC = 0.8*0.10 + 0.2*0.05*0.8 = 0.088
    wacc, nota = _calcular_wacc(
        market_cap=800.0, total_debt=200.0, interest_expense=10.0, tax_rate=0.20, costo_capital_propio=0.10,
    )
    assert wacc == pytest.approx(0.088, abs=1e-9)
    assert nota == ""
    assert wacc < 0.10  # la deuda barata post-impuestos siempre baja el WACC frente al CAPM puro


def test_deuda_sin_interest_expense_usa_proxy_documentado_no_cero_artificial():
    """Sin interestExpense (dato ausente, no un cero real) con deuda>0: no se
    debe asumir rD=0% (eso infundiría el WACC hacia abajo artificialmente)."""
    wacc, nota = _calcular_wacc(
        market_cap=800.0, total_debt=200.0, interest_expense=None, tax_rate=0.20, costo_capital_propio=0.10,
    )
    # rD proxy = 0.10 * 0.6 = 0.06 -> WACC = 0.8*0.10 + 0.2*0.06*0.8 = 0.0896
    assert wacc == pytest.approx(0.0896, abs=1e-9)
    assert "proxy" in nota
    assert "interestExpense no disponible" in nota
    # el proxy nunca debe coincidir con "coste de deuda = 0%"
    wacc_si_fuera_cero, _ = _calcular_wacc(
        market_cap=800.0, total_debt=200.0, interest_expense=1e-9, tax_rate=0.20, costo_capital_propio=0.10,
    )
    assert wacc != pytest.approx(wacc_si_fuera_cero, abs=1e-6)


def test_interest_expense_exactamente_cero_tambien_usa_proxy():
    """Un interestExpense reportado como 0 exacto con deuda>0 es implausible
    como coste de deuda real (nadie se financia gratis) — se trata igual que
    'dato ausente', no como '0% de coste real'."""
    wacc, nota = _calcular_wacc(
        market_cap=800.0, total_debt=200.0, interest_expense=0.0, tax_rate=0.20, costo_capital_propio=0.10,
    )
    assert "proxy" in nota


def test_coste_de_deuda_absurdo_se_topa_al_25_por_ciento():
    # interestExpense/D = 500/100 = 500% -> debe toparse a 25%
    wacc, nota = _calcular_wacc(
        market_cap=900.0, total_debt=100.0, interest_expense=500.0, tax_rate=0.21, costo_capital_propio=0.10,
    )
    # E/V=0.9, D/V=0.1, rD topado=0.25 -> WACC = 0.9*0.10 + 0.1*0.25*0.79 = 0.10975
    assert wacc == pytest.approx(0.9 * 0.10 + 0.1 * 0.25 * 0.79, abs=1e-9)


# ---------------------------------------------------------------------------
# obtener_risk_free_real (charts.py) y obtener_beta_real (scoring_engine.py):
# las funciones reutilizables (Fase 8) que _obtener_capm_inputs consume.
# ---------------------------------------------------------------------------


def test_obtener_risk_free_real_convierte_tnx_a_fraccion(monkeypatch):
    import charts

    monkeypatch.setattr(
        charts, "_cached_history", lambda ticker, period="1y", **kw: pd.DataFrame({"Close": [4.20, 4.35]})
    )

    # ^TNX en Yahoo ya viene en puntos porcentuales directos -> /100 para fracción.
    assert charts.obtener_risk_free_real() == pytest.approx(0.0435)


def test_obtener_risk_free_real_none_si_tnx_vacio(monkeypatch):
    import charts

    monkeypatch.setattr(charts, "_cached_history", lambda ticker, period="1y", **kw: pd.DataFrame({"Close": []}))

    assert charts.obtener_risk_free_real() is None


def test_obtener_risk_free_real_none_si_fallo_total_sin_columnas(monkeypatch):
    """safe_yfinance_fetch devuelve pd.DataFrame() (sin ninguna columna, ni
    siquiera 'Close') en fallo total -- indexar ['Close'] a ciegas antes de
    comprobar la columna lanzaría KeyError en vez de degradar a None."""
    import charts

    monkeypatch.setattr(charts, "_cached_history", lambda ticker, period="1y", **kw: pd.DataFrame())

    assert charts.obtener_risk_free_real() is None


def test_obtener_beta_real_lee_del_snapshot_de_mercado(monkeypatch):
    import modulos.scoring_engine as scoring_engine

    monkeypatch.setattr(scoring_engine, "_market_data_snapshot", lambda ticker: {"beta": 1.42})

    assert scoring_engine.obtener_beta_real("AAPL") == 1.42


def test_obtener_beta_real_none_si_snapshot_no_trae_beta(monkeypatch):
    import modulos.scoring_engine as scoring_engine

    monkeypatch.setattr(scoring_engine, "_market_data_snapshot", lambda ticker: {"beta": None})

    assert scoring_engine.obtener_beta_real("AAPL") is None


# ---------------------------------------------------------------------------
# _obtener_capm_inputs: risk-free/beta reales, con fallback declarado y nota
# ---------------------------------------------------------------------------


def test_capm_inputs_usa_datos_reales_sin_nota_si_ambos_disponibles(monkeypatch):
    import financials.valuator as valuator

    monkeypatch.setattr(valuator, "obtener_risk_free_real", lambda: 0.038)
    monkeypatch.setattr(valuator, "obtener_beta_real", lambda ticker: 1.25)

    risk_free, beta, nota = _obtener_capm_inputs("AAPL")
    assert risk_free == 0.038
    assert beta == 1.25
    assert nota == ""


def test_capm_inputs_fallback_risk_free_si_yahoo_no_da_dato(monkeypatch):
    import financials.valuator as valuator

    monkeypatch.setattr(valuator, "obtener_risk_free_real", lambda: None)
    monkeypatch.setattr(valuator, "obtener_beta_real", lambda ticker: 1.25)

    risk_free, beta, nota = _obtener_capm_inputs("AAPL")
    assert risk_free == CAPM_RISK_FREE_FALLBACK  # el mismo 4.5% de la Fase 7, pero declarado
    assert beta == 1.25
    assert "Risk-free real (^TNX) no disponible" in nota
    assert "Beta" not in nota  # beta sí estaba disponible: no debe mezclar notas que no tocan


def test_capm_inputs_fallback_beta_si_yahoo_no_da_dato(monkeypatch):
    import financials.valuator as valuator

    monkeypatch.setattr(valuator, "obtener_risk_free_real", lambda: 0.038)
    monkeypatch.setattr(valuator, "obtener_beta_real", lambda ticker: None)

    risk_free, beta, nota = _obtener_capm_inputs("AAPL")
    assert risk_free == 0.038
    assert beta == CAPM_BETA_FALLBACK  # el mismo 1.0 de la Fase 7, pero declarado
    assert "Beta real no disponible" in nota
    assert "Risk-free" not in nota


def test_capm_inputs_fallback_ambos_si_yahoo_falla_del_todo(monkeypatch):
    import financials.valuator as valuator

    monkeypatch.setattr(valuator, "obtener_risk_free_real", lambda: None)
    monkeypatch.setattr(valuator, "obtener_beta_real", lambda ticker: None)

    risk_free, beta, nota = _obtener_capm_inputs("AAPL")
    assert risk_free == CAPM_RISK_FREE_FALLBACK
    assert beta == CAPM_BETA_FALLBACK
    assert "Risk-free real (^TNX) no disponible" in nota
    assert "Beta real no disponible" in nota


def test_capm_inputs_sin_ticker_no_intenta_beta_y_usa_fallback(monkeypatch):
    """Sin ticker no hay forma de pedir beta a Yahoo -- debe degradar al
    fallback declarado sin ni siquiera intentar la llamada (nunca None
    silencioso ni una excepción por ticker vacío)."""
    import financials.valuator as valuator

    monkeypatch.setattr(valuator, "obtener_risk_free_real", lambda: 0.038)

    def _beta_no_deberia_llamarse(ticker):
        raise AssertionError("obtener_beta_real no debe llamarse sin ticker")

    monkeypatch.setattr(valuator, "obtener_beta_real", _beta_no_deberia_llamarse)

    risk_free, beta, nota = _obtener_capm_inputs(None)
    assert beta == CAPM_BETA_FALLBACK
    assert "Beta real no disponible" in nota


def test_last_valid_allow_zero_conserva_cero_real():
    serie = pd.Series([np.nan, 0.0])
    assert _last_valid_allow_zero(serie) == 0.0


def test_last_valid_allow_zero_none_si_todo_nan():
    serie = pd.Series([np.nan, np.nan])
    assert _last_valid_allow_zero(serie) is None


def test_last_valid_allow_zero_none_si_serie_none():
    assert _last_valid_allow_zero(None) is None


# ---------------------------------------------------------------------------
# Integración ligera: valorar_empresa (rama FMP) usa wacc, no CAPM, para DCF
# ---------------------------------------------------------------------------


def _fmp_frames_con_deuda():
    years_idx = pd.to_datetime(["2022-12-31", "2023-12-31", "2024-12-31"])
    is_df = pd.DataFrame(
        {
            "netIncome": [8e9, 9e9, 10e9],
            "revenue": [50e9, 55e9, 60e9],
            "epsdiluted": [4.0, 4.5, 5.0],
            "weightedAverageShsOutDil": [2e9, 2e9, 2e9],
            "interestExpense": [3e8, 3.2e8, 3.5e8],
            "incomeTaxExpense": [1.8e9, 2.0e9, 2.2e9],
            "incomeBeforeTax": [9.8e9, 11.0e9, 12.2e9],
        },
        index=years_idx,
    )
    bs_df = pd.DataFrame(
        {
            "totalStockholdersEquity": [40e9, 44e9, 48e9],
            "totalDebt": [15e9, 15e9, 15e9],
        },
        index=years_idx,
    )
    cf_df = pd.DataFrame(
        {
            "freeCashFlow": [7e9, 8e9, 9e9],
            "dividendsPaid": [-1e9, -1e9, -1e9],
        },
        index=years_idx,
    )
    metrics_df = pd.DataFrame({"marketCap": [120e9, 130e9, 140e9]}, index=years_idx)
    return is_df, bs_df, cf_df, metrics_df


def test_valorar_empresa_fmp_expone_wacc_y_lo_usa_para_dcf(monkeypatch):
    import financials.valuator as valuator

    monkeypatch.setattr(valuator, "obtener_cotizacion_fmp", lambda ticker: 70.0)
    monkeypatch.setattr(valuator, "obtener_risk_free_real", lambda: 0.038)
    monkeypatch.setattr(valuator, "obtener_beta_real", lambda ticker: 1.25)

    is_df, bs_df, cf_df, metrics_df = _fmp_frames_con_deuda()
    res = valorar_empresa(is_df, bs_df, cf_df, metrics_df, "TEST")

    assert res is not None
    assert "wacc" in res and "wacc_nota" in res and "tasa_descuento_capm" in res
    assert res["wacc"] != res["tasa_descuento_capm"]  # hay deuda real: WACC debe diferir del CAPM puro
    assert res["wacc"] < res["tasa_descuento_capm"]  # deuda post-impuestos más barata que el equity
    assert res["wacc_nota"] == ""  # risk-free/beta reales e interestExpense disponible: sin proxy ni fallback
    assert res["total_debt"] == pytest.approx(15e9)
    assert res["tasa_libre_riesgo"] == 0.038  # el dato real mockeado, no el 0.045 hardcodeado de la Fase 7
    assert res["beta"] == 1.25  # el dato real mockeado, no el 1.0 hardcodeado de la Fase 7
    assert res["tasa_descuento_capm"] == pytest.approx(max(0.038 + 1.25 * 0.055, 0.07))

    # dcf_value debe coincidir con calcular_dcf_fcf_por_accion usando wacc, no CAPM.
    from financials.valuator import calcular_dcf_fcf_por_accion

    esperado = calcular_dcf_fcf_por_accion(
        res["fcf_per_share"], res["crecimiento_sostenible"], res["wacc"], res["terminal_growth"],
    )
    assert res["dcf_value"] == pytest.approx(esperado, rel=1e-6)


def test_valorar_empresa_fmp_capm_fallback_declarado_si_yahoo_falla(monkeypatch):
    """Sin risk-free ni beta reales (Yahoo caído, sin red, o histórico
    insuficiente): debe caer al mismo 4.5%/1.0 que la Fase 7 usaba siempre,
    pero ahora como fallback declarado y visible en wacc_nota -- nunca un
    valor real silencioso ni una excepción."""
    import financials.valuator as valuator

    monkeypatch.setattr(valuator, "obtener_cotizacion_fmp", lambda ticker: 70.0)
    monkeypatch.setattr(valuator, "obtener_risk_free_real", lambda: None)
    monkeypatch.setattr(valuator, "obtener_beta_real", lambda ticker: None)

    is_df, bs_df, cf_df, metrics_df = _fmp_frames_con_deuda()
    res = valorar_empresa(is_df, bs_df, cf_df, metrics_df, "TEST")

    assert res is not None
    assert res["tasa_libre_riesgo"] == CAPM_RISK_FREE_FALLBACK
    assert res["beta"] == CAPM_BETA_FALLBACK
    # mismo resultado numérico que la Fase 7 (comportamiento por defecto de siempre)...
    assert res["tasa_descuento_capm"] == pytest.approx(max(0.045 + 1.0 * 0.055, 0.07))
    # ...pero ahora explícito en la nota que se muestra en la UI (fundamental.py), no silencioso.
    assert "Risk-free real (^TNX) no disponible" in res["wacc_nota"]
    assert "Beta real no disponible" in res["wacc_nota"]


def _legacy_frames():
    is_df = pd.DataFrame(
        {
            "concept": ["NetIncomeLoss", "Revenues", "WeightedAverageNumberOfDilutedSharesOutstanding"],
            "2022": [8e9, 50e9, 2e9],
            "2023": [9e9, 55e9, 2e9],
            "2024": [10e9, 60e9, 2e9],
        }
    )
    bs_df = pd.DataFrame(
        {
            "concept": ["StockholdersEquity"],
            "2022": [40e9],
            "2023": [44e9],
            "2024": [48e9],
        }
    )
    return is_df, bs_df


def test_valorar_empresa_legacy_expone_wacc_como_alias_de_capm_con_nota(monkeypatch):
    """La ruta SEC/XBRL no tiene deuda/impuestos normalizados en esta tarea —
    wacc debe seguir presente (alias de CAPM) para que fundamental.py no
    caiga en un valor por defecto inventado. El CAPM real llega igual que en
    la ruta FMP; la nota de "Ruta SEC/XBRL" se conserva junto a la del CAPM
    si hiciera falta."""
    import financials.valuator as valuator

    monkeypatch.setattr(valuator, "obtener_risk_free_real", lambda: 0.038)
    monkeypatch.setattr(valuator, "obtener_beta_real", lambda ticker: 1.25)

    is_df, bs_df = _legacy_frames()
    res = valorar_empresa(is_df, bs_df, None, None, "TEST")
    assert res is not None
    assert res["wacc"] == res["tasa_descuento_capm"]
    assert res["tasa_libre_riesgo"] == 0.038
    assert res["beta"] == 1.25
    assert "SEC/XBRL" in res["wacc_nota"]


def test_valorar_empresa_legacy_capm_fallback_se_combina_con_nota_sec_xbrl(monkeypatch):
    import financials.valuator as valuator

    monkeypatch.setattr(valuator, "obtener_risk_free_real", lambda: None)
    monkeypatch.setattr(valuator, "obtener_beta_real", lambda ticker: None)

    is_df, bs_df = _legacy_frames()
    res = valorar_empresa(is_df, bs_df, None, None, "TEST")
    assert res is not None
    assert res["tasa_libre_riesgo"] == CAPM_RISK_FREE_FALLBACK
    assert res["beta"] == CAPM_BETA_FALLBACK
    # las dos notas conviven en el mismo string, igual que ya se hacía con el proxy de deuda de la Fase 7.
    assert "Risk-free real (^TNX) no disponible" in res["wacc_nota"]
    assert "Beta real no disponible" in res["wacc_nota"]
    assert "SEC/XBRL" in res["wacc_nota"]
