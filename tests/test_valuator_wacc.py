"""WACC real en valuator.py (Fase 7, punto 3).

Cubre _calcular_wacc de forma aislada (todas las ramas: sin market_cap, sin
deuda, con deuda y coste de deuda real, con deuda pero sin interestExpense —
el caso que exige el proxy documentado en vez de un 0% artificial) y una
integración ligera con _valorar_empresa_fmp confirmando que wacc (no
tasa_descuento_capm) es lo que realmente alimenta dcf_value/epv_value.

La validación con datos reales de Apple/Microsoft/Coca-Cola (confirmando que
el WACC queda en el mismo orden de magnitud que el CAPM anterior) se hizo
aparte, en vivo, y se describe en el informe de la tarea — aquí solo la
lógica determinista, sin red.
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

from valuator import _calcular_wacc, _last_valid_allow_zero, valorar_empresa


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
    import valuator

    monkeypatch.setattr(valuator, "obtener_cotizacion_fmp", lambda ticker: 70.0)

    is_df, bs_df, cf_df, metrics_df = _fmp_frames_con_deuda()
    res = valorar_empresa(is_df, bs_df, cf_df, metrics_df, "TEST")

    assert res is not None
    assert "wacc" in res and "wacc_nota" in res and "tasa_descuento_capm" in res
    assert res["wacc"] != res["tasa_descuento_capm"]  # hay deuda real: WACC debe diferir del CAPM puro
    assert res["wacc"] < res["tasa_descuento_capm"]  # deuda post-impuestos más barata que el equity
    assert res["wacc_nota"] == ""  # interestExpense disponible: cálculo directo, sin proxy
    assert res["total_debt"] == pytest.approx(15e9)

    # dcf_value debe coincidir con calcular_dcf_fcf_por_accion usando wacc, no CAPM.
    from valuator import calcular_dcf_fcf_por_accion

    esperado = calcular_dcf_fcf_por_accion(
        res["fcf_per_share"], res["crecimiento_sostenible"], res["wacc"], res["terminal_growth"],
    )
    assert res["dcf_value"] == pytest.approx(esperado, rel=1e-6)


def test_valorar_empresa_legacy_expone_wacc_como_alias_de_capm_con_nota():
    """La ruta SEC/XBRL no tiene deuda/impuestos normalizados en esta tarea —
    wacc debe seguir presente (alias de CAPM) para que fundamental.py/
    app_pdf_export.py no caigan en un valor por defecto inventado."""
    years = ["2022", "2023", "2024"]
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
    res = valorar_empresa(is_df, bs_df, None, None, "TEST")
    assert res is not None
    assert res["wacc"] == res["tasa_descuento_capm"]
    assert "SEC/XBRL" in res["wacc_nota"]
