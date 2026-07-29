"""Suite de guards financieros: patrimonio negativo, ceros sintéticos, ROIC y caja neta.

Cubre los bugs corregidos en income_analyzer.py, balance_analyzer.py,
cashflow_analyzer.py y modulos/utils.py:

1. Patrimonio <= 0 debe bloquear ROE / Deuda-Capital / ROIC (no un número con
   signo espurio) y debe emitir un flag de riesgo explícito.
2. Un dato ausente (deuda, caja, CAPEX) nunca debe mostrarse como 0 sintético;
   debe seguir siendo NaN. Un dato real igual a 0 sí debe conservarse como 0.
3. El capital invertido usa una única fórmula (Deuda + Patrimonio - Caja); si
   no es positivo, ROIC es NaN, nunca se recalcula con una fórmula alternativa.
4. La "Caja Neta" no debe sumar automáticamente inversiones a largo plazo.
5. escanear_vulnerabilidades / calcular_score_buffett deben distinguir un 0.0
   real de un dato ausente (sin usar `if valor and ...`).
6. COGS/SG&A/I+D ausentes (income_analyzer.py) y recompras/dividendos ausentes
   (cashflow_analyzer.py) no deben mostrarse/sumarse como 0 sintético.
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

from financials.balance_analyzer import analizar_balance
from financials.cashflow_analyzer import analizar_flujo_efectivo
from financials.income_analyzer import _safe_ratio, analizar_cuenta_resultados
from modulos.utils import calcular_score_buffett, escanear_vulnerabilidades


def _idx(years: list[int]) -> pd.DatetimeIndex:
    return pd.to_datetime([f"{y}-09-30" for y in years])


# ---------------------------------------------------------------------------
# Bug 1: _safe_ratio con positive_denominator (nivel unitario, sin balance_analyzer)
# ---------------------------------------------------------------------------


def test_safe_ratio_legacy_deja_pasar_denominador_negativo():
    """Comportamiento histórico: solo el cero exacto se neutraliza."""
    numerator = pd.Series([10.0, -10.0, 5.0])
    denominator = pd.Series([-5.0, -5.0, 0.0])

    legacy = _safe_ratio(numerator, denominator)

    assert legacy.iloc[0] == pytest.approx(-2.0)
    assert legacy.iloc[1] == pytest.approx(2.0)  # negativo/negativo -> positivo espurio
    assert pd.isna(legacy.iloc[2])


def test_safe_ratio_positive_denominator_bloquea_negativo_y_cero():
    numerator = pd.Series([10.0, -10.0, 5.0])
    denominator = pd.Series([-5.0, -5.0, 0.0])

    guarded = _safe_ratio(numerator, denominator, positive_denominator=True)

    assert guarded.isna().all()


# ---------------------------------------------------------------------------
# Bug 1 (integración): patrimonio negativo / cero en balance_analyzer
# ---------------------------------------------------------------------------


def test_patrimonio_negativo_bloquea_roe_deuda_capital_y_emite_flag():
    years = [2023, 2024]
    bs_df = pd.DataFrame(
        {
            "totalStockholdersEquity": [50e9, -200e9],
            "totalDebt": [100e9, 100e9],
            "cashAndShortTermInvestments": [10e9, 10e9],
            "retainedEarnings": [30e9, -50e9],
            "propertyPlantEquipmentNet": [40e9, 40e9],
            "longTermDebt": [80e9, 80e9],
        },
        index=_idx(years),
    )
    is_df = pd.DataFrame(
        {
            "revenue": [500e9, 500e9],
            "netIncome": [40e9, -60e9],
            "operatingIncome": [60e9, 60e9],
            "incomeTaxExpense": [10e9, np.nan],
            "incomeBeforeTax": [50e9, np.nan],
            "grossProfit": [200e9, 200e9],
            "costOfRevenue": [300e9, 300e9],
        },
        index=_idx(years),
    )

    resultado = analizar_balance(bs_df, is_df)
    ratios = resultado["ratios"]

    # 2023: patrimonio positivo -> ratios normales
    assert ratios.loc["2023", "ROE %"] == pytest.approx(80.0)
    assert ratios.loc["2023", "Deuda / Capital"] == pytest.approx(2.0)

    # 2024: patrimonio negativo -> None explícito, no ROE positivo espurio
    # (netIncome también negativo: -60e9 / -200e9 daría un ROE de +30% si no
    # se guardara, ocultando exactamente el riesgo que se quiere señalar)
    assert pd.isna(ratios.loc["2024", "ROE %"])
    assert pd.isna(ratios.loc["2024", "Deuda / Capital"])
    assert pd.isna(ratios.loc["2024", "ROIC %"])

    assert resultado["flags"], "Debe emitir un flag de riesgo por patrimonio negativo"
    assert "Patrimonio neto negativo" in resultado["flags"][0]
    assert "2024" in resultado["flags"][0]


def test_patrimonio_exactamente_cero_tambien_bloquea():
    years = [2023, 2024]
    bs_df = pd.DataFrame(
        {
            "totalStockholdersEquity": [50e9, 0.0],
            "totalDebt": [100e9, 100e9],
            "cashAndShortTermInvestments": [10e9, 10e9],
            "retainedEarnings": [30e9, 30e9],
        },
        index=_idx(years),
    )

    resultado = analizar_balance(bs_df, None)
    ratios = resultado["ratios"]

    assert ratios.loc["2023", "Deuda / Capital"] == pytest.approx(2.0)
    assert pd.isna(ratios.loc["2024", "Deuda / Capital"]), (
        "patrimonio == 0 debe tratarse igual que negativo, no solo detectarse "
        "el caso 'denominator.replace(0, np.nan)'"
    )
    assert resultado["flags"]


# ---------------------------------------------------------------------------
# Bug 2: sin ceros sintéticos para dato ausente; el 0 real se conserva
# ---------------------------------------------------------------------------


def test_empresa_sin_deuda_conserva_el_cero_real():
    years = [2023, 2024]
    bs_df = pd.DataFrame(
        {
            "totalStockholdersEquity": [80e9, 90e9],
            "totalDebt": [0.0, 0.0],  # dato real reportado, no ausente
            "cashAndShortTermInvestments": [30e9, 35e9],
            "retainedEarnings": [40e9, 45e9],
        },
        index=_idx(years),
    )

    resultado = analizar_balance(bs_df, None)
    ratios = resultado["ratios"]

    assert ratios.loc["2024", "Deuda / Capital"] == pytest.approx(0.0)
    assert ratios.loc["2024", "Caja Neta (B USD)"] == pytest.approx(35.0)
    assert not resultado["flags"], "Patrimonio positivo: no debe haber flags"


def test_capex_ausente_no_se_muestra_como_cero_por_ciento():
    years = [2023, 2024]
    cf_df = pd.DataFrame(
        {
            "operatingCashFlow": [50e9, 55e9],
            "freeCashFlow": [40e9, 45e9],
            # Sin capitalExpenditure ni investmentsInPropertyPlantAndEquipment:
            # CAPEX es un dato ausente, no cero.
            "commonStockRepurchased": [5e9, 5e9],
            "dividendsPaid": [3e9, 3e9],
        },
        index=_idx(years),
    )
    is_df = pd.DataFrame(
        {"revenue": [200e9, 210e9], "netIncome": [40e9, 42e9]},
        index=_idx(years),
    )

    resultado = analizar_flujo_efectivo(cf_df, is_df)
    ratios = resultado["ratios"]

    assert ratios["CAPEX % sobre Beneficio"].isna().all(), (
        "CAPEX desconocido no debe indistinguirse de un negocio asset-light real (0%)"
    )
    assert ratios["CAPEX (B USD)"].isna().all()
    assert resultado["veredicto"] == "Sin datos de CAPEX suficientes"


# ---------------------------------------------------------------------------
# Bug 3: fórmula única de capital invertido / ROIC, sin rama alternativa
# ---------------------------------------------------------------------------


def test_capital_invertido_no_positivo_bloquea_roic_sin_formula_alternativa():
    years = [2023, 2024]
    # patrimonio + deuda - caja = 10e9 + 5e9 - 30e9 = -15e9 (<= 0) en ambos años.
    # La fórmula alternativa retirada (patrimonio + deuda, sin restar caja)
    # habría dado 15e9 (positivo) y un ROIC calculado silenciosamente distinto.
    bs_df = pd.DataFrame(
        {
            "totalStockholdersEquity": [10e9, 10e9],
            "totalDebt": [5e9, 5e9],
            "cashAndShortTermInvestments": [30e9, 30e9],
            "retainedEarnings": [5e9, 5e9],
        },
        index=_idx(years),
    )
    is_df = pd.DataFrame(
        {
            "revenue": [50e9, 50e9],
            "netIncome": [3e9, 3e9],
            "operatingIncome": [4e9, 4e9],
            "incomeTaxExpense": [1e9, 1e9],
            "incomeBeforeTax": [5e9, 5e9],
        },
        index=_idx(years),
    )

    resultado = analizar_balance(bs_df, is_df)
    ratios = resultado["ratios"]

    assert ratios["ROIC %"].isna().all()


# ---------------------------------------------------------------------------
# Bug 4: Caja Neta no suma inversiones a largo plazo automáticamente
# ---------------------------------------------------------------------------


def test_caja_neta_no_suma_inversiones_largo_plazo():
    bs_df = pd.DataFrame(
        {
            "totalStockholdersEquity": [100e9],
            "totalDebt": [20e9],
            # Sin "cashAndShortTermInvestments": fuerza el camino de fallback.
            "cashAndCashEquivalents": [10e9],
            "shortTermInvestments": [5e9],
            "longTermInvestments": [50e9],  # no debe sumarse a la caja
            "retainedEarnings": [40e9],
        },
        index=_idx([2024]),
    )

    resultado = analizar_balance(bs_df, None)
    ratios = resultado["ratios"]

    # Caja Neta = (10 + 5 - 20) / 1e9 = -5.0. Si sumara longTermInvestments
    # (50e9) daría +45.0: una lectura de liquidez completamente distinta.
    assert ratios.loc["2024", "Caja Neta (B USD)"] == pytest.approx(-5.0)


# ---------------------------------------------------------------------------
# Bug 5: truthiness -> comparaciones explícitas (0.0 real dispara alertas)
# ---------------------------------------------------------------------------


def test_margen_neto_y_roic_cero_real_disparan_alertas():
    res_is = {"ratios": pd.DataFrame({"Margen Neto %": [0.0]}, index=["2024"])}
    res_bs = {
        "ratios": pd.DataFrame({"Deuda / Capital": [0.5], "ROIC %": [0.0]}, index=["2024"]),
        "flags": [],
    }
    res_cf = {"ratios": pd.DataFrame({"Free Cash Flow (B USD)": [0.0]}, index=["2024"])}

    alertas = escanear_vulnerabilidades(res_is, res_bs, res_cf)
    texto = " ".join(alertas)

    assert "Márgenes Críticos" in texto, "margen_neto == 0.0 (< 5) debe disparar, no tratarse como ausente"
    assert "Destrucción de Capital" in texto, "roic == 0.0 (< 7) debe disparar, no tratarse como ausente"
    # FCF == 0.0 no es "< 0": no debe disparar Quema de Caja (ni con la versión antigua ni la nueva)
    assert "Quema de Caja" not in texto


def test_flag_patrimonio_negativo_llega_a_escanear_vulnerabilidades():
    years = [2023, 2024]
    bs_df = pd.DataFrame(
        {
            "totalStockholdersEquity": [30e9, -40e9],
            "totalDebt": [50e9, 50e9],
            "cashAndShortTermInvestments": [10e9, 10e9],
            "retainedEarnings": [20e9, -10e9],
        },
        index=_idx(years),
    )
    is_df = pd.DataFrame(
        {"revenue": [100e9, 90e9], "netIncome": [8e9, -12e9]},
        index=_idx(years),
    )

    res_bs = analizar_balance(bs_df, is_df)
    res_is = {"ratios": pd.DataFrame({"Margen Neto %": [8.0, -13.3]}, index=["2023", "2024"])}
    res_cf = {"ratios": pd.DataFrame({"Free Cash Flow (B USD)": [1.0, -2.0]}, index=["2023", "2024"])}

    alertas = escanear_vulnerabilidades(res_is, res_bs, res_cf)

    assert any("Patrimonio neto negativo" in a for a in alertas)


def test_calcular_score_buffett_no_confunde_cero_real_con_ausente():
    df_is = pd.DataFrame({"Margen Bruto %": [0.0], "Margen Neto %": [0.0]}, index=["2024"])
    df_bs = pd.DataFrame({"ROE %": [0.0], "ROIC %": [0.0], "Deuda / Capital": [0.5]}, index=["2024"])
    df_cf = pd.DataFrame(
        {"CAPEX % sobre Beneficio": [0.0], "Free Cash Flow (B USD)": [0.0], "Recompras (B USD)": [0.0]},
        index=["2024"],
    )

    # No debe lanzar excepción (None comparado con operadores). Un 0.0 real en
    # fcf/buybacks no debe sumar puntos (0 > 0 es False), pero capex == 0.0 sí
    # cumple "< 25" (asset-light real) y sí debe puntuar: si el truthiness
    # tratara ese 0.0 como "sin dato", perdería silenciosamente esos puntos.
    score = calcular_score_buffett(df_is, df_bs, df_cf)

    # Deuda/Capital < 0.8 (15 pts) + CAPEX < 25% (10 pts) = 25; mb/mn/roe/roic/
    # fcf/buybacks en 0.0 real no cruzan sus umbrales ">" y no puntúan.
    assert score == 25
    assert score == calcular_score_buffett(df_is, df_bs, df_cf)  # determinista


def test_calcular_score_buffett_ignora_columnas_ausentes_sin_lanzar():
    df_is = pd.DataFrame({"Margen Bruto %": [np.nan]}, index=["2024"])
    df_bs = pd.DataFrame({"Deuda / Capital": [0.5]}, index=["2024"])
    df_cf = pd.DataFrame({"Free Cash Flow (B USD)": [np.nan]}, index=["2024"])

    score = calcular_score_buffett(df_is, df_bs, df_cf)

    assert score == 15  # Igual que arriba: solo Deuda/Capital puntúa


# ---------------------------------------------------------------------------
# Caso pedido explícitamente: serie de un solo año
# ---------------------------------------------------------------------------


def test_serie_de_un_solo_anio_no_rompe_y_calcula_lo_calculable():
    bs_df = pd.DataFrame(
        {
            "totalStockholdersEquity": [80e9],
            "totalDebt": [20e9],
            "cashAndShortTermInvestments": [15e9],
            "retainedEarnings": [40e9],
            "propertyPlantEquipmentNet": [10e9],
            "longTermDebt": [15e9],
        },
        index=_idx([2024]),
    )
    is_df = pd.DataFrame(
        {
            "revenue": [300e9],
            "netIncome": [50e9],
            "operatingIncome": [70e9],
            "incomeTaxExpense": [12e9],
            "incomeBeforeTax": [62e9],
        },
        index=_idx([2024]),
    )

    resultado = analizar_balance(bs_df, is_df)
    ratios = resultado["ratios"]

    assert not ratios.empty
    assert ratios.loc["2024", "ROE %"] == pytest.approx((50e9 / 80e9) * 100, rel=1e-6)
    assert ratios.loc["2024", "Deuda / Capital"] == pytest.approx(0.25)
    # Sin año previo no hay crecimiento de ganancias retenidas calculable.
    assert pd.isna(ratios.loc["2024", "Crecimiento Gan. Retenidas %"])


def test_serie_de_un_solo_anio_flujo_efectivo_no_rompe():
    cf_df = pd.DataFrame(
        {
            "operatingCashFlow": [50e9],
            "capitalExpenditure": [-10e9],
            "freeCashFlow": [40e9],
            "commonStockRepurchased": [5e9],
            "dividendsPaid": [3e9],
        },
        index=_idx([2024]),
    )
    is_df = pd.DataFrame({"revenue": [200e9], "netIncome": [40e9]}, index=_idx([2024]))

    resultado = analizar_flujo_efectivo(cf_df, is_df)

    assert resultado is not None
    assert resultado["ratios"].loc["2024", "CAPEX % sobre Beneficio"] == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# Extensión: COGS / SG&A / I+D ausentes (income_analyzer.py) no son 0 sintético
# ---------------------------------------------------------------------------


def test_cogs_ausente_no_infla_margen_bruto_al_100_por_ciento():
    # Sin "grossProfit" ni "costOfRevenue": el margen bruto no es derivable y
    # debe quedar NaN, no "ventas - 0 = ventas" (100% de margen, falso).
    is_df = pd.DataFrame(
        {"revenue": [100e9], "netIncome": [20e9], "operatingIncome": [25e9]},
        index=_idx([2024]),
    )

    resultado = analizar_cuenta_resultados(is_df, None)
    ratios = resultado["ratios"]

    assert pd.isna(ratios.loc["2024", "Margen Bruto %"])


def test_sga_e_id_ausentes_no_se_muestran_como_cero_por_ciento():
    is_df = pd.DataFrame(
        {
            "revenue": [100e9],
            "grossProfit": [40e9],
            "netIncome": [10e9],
            "operatingIncome": [15e9],
            # Sin sellingGeneralAndAdministrativeExpenses/generalAndAdministrativeExpenses/
            # sellingAndMarketingExpenses ni researchAndDevelopmentExpenses.
        },
        index=_idx([2024]),
    )

    resultado = analizar_cuenta_resultados(is_df, None)
    ratios = resultado["ratios"]

    assert pd.isna(ratios.loc["2024", "SG&A % (s/MB)"])
    assert pd.isna(ratios.loc["2024", "I+D % (s/MB)"])


def test_sga_e_id_cero_real_se_conserva():
    is_df = pd.DataFrame(
        {
            "revenue": [100e9],
            "grossProfit": [40e9],
            "netIncome": [10e9],
            "operatingIncome": [15e9],
            "sellingGeneralAndAdministrativeExpenses": [0.0],  # dato real reportado
            "researchAndDevelopmentExpenses": [0.0],  # dato real reportado
        },
        index=_idx([2024]),
    )

    resultado = analizar_cuenta_resultados(is_df, None)
    ratios = resultado["ratios"]

    assert ratios.loc["2024", "SG&A % (s/MB)"] == pytest.approx(0.0)
    assert ratios.loc["2024", "I+D % (s/MB)"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Extensión: Recompras / Dividendos ausentes (cashflow_analyzer.py) no son 0 sintético
# ---------------------------------------------------------------------------


def test_recompras_y_dividendos_ausentes_no_se_muestran_como_cero():
    cf_df = pd.DataFrame(
        {
            "operatingCashFlow": [50e9],
            "freeCashFlow": [45e9],
            # Sin commonStockRepurchased/repurchasesOfStock ni dividendsPaid/commonDividendsPaid.
        },
        index=_idx([2024]),
    )
    is_df = pd.DataFrame({"revenue": [100e9], "netIncome": [20e9]}, index=_idx([2024]))

    resultado = analizar_flujo_efectivo(cf_df, is_df)
    ratios = resultado["ratios"]

    assert pd.isna(ratios.loc["2024", "Recompras (B USD)"])
    assert pd.isna(ratios.loc["2024", "Dividendos (B USD)"])


def test_recompras_y_dividendos_cero_real_se_conserva():
    cf_df = pd.DataFrame(
        {
            "operatingCashFlow": [50e9],
            "freeCashFlow": [45e9],
            "commonStockRepurchased": [0.0],  # dato real: no recompró acciones
            "dividendsPaid": [0.0],  # dato real: no repartió dividendo
        },
        index=_idx([2024]),
    )
    is_df = pd.DataFrame({"revenue": [100e9], "netIncome": [20e9]}, index=_idx([2024]))

    resultado = analizar_flujo_efectivo(cf_df, is_df)
    ratios = resultado["ratios"]

    assert ratios.loc["2024", "Recompras (B USD)"] == pytest.approx(0.0)
    assert ratios.loc["2024", "Dividendos (B USD)"] == pytest.approx(0.0)


def test_recompras_ausente_habria_roto_el_patron_viejo_de_buyback_yield():
    """Reproduce por qué modulos/fundamental.py necesitó tocarse en esta tarea.

    Antes del fix, "Recompras (B USD)" ausente siempre traía un 0.0 sintético,
    así que `.dropna().iloc[-1]` (usado para Buyback Yield / FCF+Buyback Yield)
    nunca se topaba con una serie vacía. Con el guard aplicado, una empresa con
    la columna de recompras totalmente ausente en FMP produce una serie
    íntegramente NaN, y ese patrón sin comprobar `.empty` explota.
    """
    cf_df = pd.DataFrame(
        {
            "operatingCashFlow": [50e9],
            "freeCashFlow": [45e9],
            "dividendsPaid": [3e9],
        },
        index=_idx([2024]),
    )
    is_df = pd.DataFrame({"revenue": [100e9], "netIncome": [20e9]}, index=_idx([2024]))

    resultado = analizar_flujo_efectivo(cf_df, is_df)
    recompras_series = resultado["ratios"]["Recompras (B USD)"]

    assert recompras_series.isna().all()

    with pytest.raises(IndexError):
        recompras_series.dropna().iloc[-1]  # patrón viejo, sin comprobar .empty

    # Patrón corregido (el que ahora usa modulos/fundamental.py): degrada a None.
    dropped = recompras_series.dropna()
    ultimas_recompras = dropped.iloc[-1] if not dropped.empty else None
    assert ultimas_recompras is None
