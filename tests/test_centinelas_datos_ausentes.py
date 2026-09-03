"""Ningún dato ausente puede convertirse en una métrica que afirme algo.

El patrón: sustituir un dato que falta por un número pequeño "para evitar
dividir por cero", o por un valor medio "para no romper el cálculo". El
resultado no es un error visible, es una métrica que MIENTE con la misma cara
que una buena. Aquí se fija que cada sitio donde se detectó degrada con
transparencia en vez de rellenar.
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


# ==========================================================================
# MONTE CARLO: volatilidad cero
# ==========================================================================


def test_sin_volatilidad_no_se_simula_en_vez_de_proyectar_una_certeza():
    """Elevar la volatilidad a 0,0001 producía P5, P50 y P95 casi idénticos:
    un abanico sin incertidumbre presentado como si tuviera precisión."""
    from modulos.montecarlo import extract_percentiles, simulate_monte_carlo

    for volatilidad in (0.0, -0.1, float("nan")):
        rutas = simulate_monte_carlo(
            initial_portfolio_value=10_000.0, expected_return=0.08,
            volatility=volatilidad, years=3, num_simulations=200,
        )
        assert rutas.size == 0, f"con volatilidad {volatilidad} no debe simular"
        assert extract_percentiles(rutas) is None


def test_con_volatilidad_real_la_simulacion_tiene_dispersion():
    from modulos.montecarlo import extract_percentiles, simulate_monte_carlo

    rutas = simulate_monte_carlo(
        initial_portfolio_value=10_000.0, expected_return=0.08,
        volatility=0.18, years=3, num_simulations=500,
    )
    percentiles = extract_percentiles(rutas)

    assert percentiles is not None
    assert percentiles.p95[-1] > percentiles.p50[-1] > percentiles.p5[-1], (
        "sin dispersión entre percentiles el abanico no informa de nada"
    )


# ==========================================================================
# OPTIMIZADOR DE CARTERA: varianza cero
# ==========================================================================


def test_una_cartera_sin_varianza_no_tiene_sharpe_infinito():
    """Con el suelo de 1e-12 el Sharpe se disparaba a ~1e6. Como el optimizador
    MAXIMIZA el Sharpe, ese suelo creaba un óptimo artificial hacia el que
    empujar: no era un detalle numérico inofensivo."""
    fuente = (PROJECT_ROOT / "modulos" / "portfolio.py").read_text(encoding="utf-8")

    assert "max(variance, 1e-12)" not in fuente
    assert 'return expected, 0.0, float("-inf")' in fuente, (
        "una varianza no positiva debe descartarse, no convertirse en un óptimo"
    )


# ==========================================================================
# ESTOCÁSTICO DEL RSI: rango cero
# ==========================================================================


def test_un_rsi_plano_no_produce_una_señal_de_sobreventa():
    """max == min significa 0/0. Con 1e-10 salía StochRSI = 0, que se lee como
    SOBREVENTA EXTREMA: una señal alcista inventada desde la quietud."""
    rsi = pd.Series([50.0] * 30)
    minimo = rsi.rolling(window=14).min()
    maximo = rsi.rolling(window=14).max()

    rango_malo = (maximo - minimo).replace(0, 1e-10)
    stoch_malo = ((rsi - minimo) / rango_malo) * 100
    assert stoch_malo.dropna().eq(0).all(), "así se comportaba antes: 0 = sobreventa"

    rango_bueno = (maximo - minimo).replace(0, np.nan)
    stoch_bueno = ((rsi - minimo) / rango_bueno) * 100
    assert stoch_bueno.dropna().empty, "sin rango no hay estocástico que dar"

    fuente = (PROJECT_ROOT / "charts.py").read_text(encoding="utf-8")
    assert "rango.replace(0, np.nan)" in fuente
    assert "rango.replace(0, 1e-10)" not in fuente


# ==========================================================================
# VEREDICTO DEL RESUMEN: confianza sin modelo
# ==========================================================================


def test_sin_valuequant_score_no_se_declara_una_confianza_del_cien_por_cien():
    """Se imprimía «Confianza del modelo: 100%» justo cuando no había modelo."""
    fuente = (PROJECT_ROOT / "modulos" / "resumen.py").read_text(encoding="utf-8")

    assert "if valuequant_score is not None else 1.0" not in fuente
    assert "if valuequant_score is not None else None" in fuente
    assert "sin confianza asociada" in fuente


# ==========================================================================
# SCORE: un dato ausente no puede contar como observación
# ==========================================================================


def test_un_dividendo_ausente_no_puntua_ni_infla_la_cobertura():
    """_weighted_mean salta los None. Un 50 fijo fabricaba una observación con
    peso completo, incoherente con buyback_score y fcf_yield justo al lado."""
    from modulos.scoring_engine import _weighted_mean

    con_dato = _weighted_mean([(65.0, 0.10), (80.0, 0.90)])
    sin_dato = _weighted_mean([(None, 0.10), (80.0, 0.90)])

    assert sin_dato == pytest.approx(80.0), "el peso del ausente se redistribuye"
    assert con_dato != sin_dato

    fuente = (PROJECT_ROOT / "modulos" / "scoring_engine.py").read_text(encoding="utf-8")
    assert "dividend_score = 65 if _is_valid(dividends) and dividends > 0 else 50" not in fuente


def test_un_dividendo_de_cero_si_es_un_dato_y_puntua_neutral():
    """No repartir dividendo es información; no saberlo, no."""
    fuente = (PROJECT_ROOT / "modulos" / "scoring_engine.py").read_text(encoding="utf-8")
    assert "dividend_score = 65 if dividends > 0 else 50" in fuente


# ==========================================================================
# LO QUE SIGUE SIENDO CORRECTO
# ==========================================================================


def test_el_ayudante_de_ratios_de_los_analizadores_usa_nan_no_un_centinela():
    """_safe_ratio es el modelo a seguir: neutraliza con NaN, no con un número."""
    from financials.income_analyzer import _safe_ratio

    resultado = _safe_ratio(pd.Series([100.0, 200.0]), pd.Series([0.0, 50.0]))
    assert pd.isna(resultado.iloc[0]), "denominador cero -> NaN, nunca un número"
    assert resultado.iloc[1] == pytest.approx(4.0)


def test_el_score_sin_cobertura_queda_capado_y_con_bandera_roja():
    """El 50.0 por defecto sí está justificado: la quality gate lo capa a 49 y
    añade una bandera roja explícita, así que degrada de forma visible."""
    from modulos.scoring_engine import _apply_quality_gates

    banderas: list[str] = []
    capado, motivo = _apply_quality_gates(
        final_score=50.0, data_coverage=0.0, confidence=0.0,
        components=[], red_flags=banderas, negatives=[],
    )
    assert capado <= 49.0
    assert motivo and "insuficientes" in motivo.lower()
    assert banderas


def test_el_plan_de_riesgo_bloquea_el_stop_en_cero():
    """calcular_stop devuelve 0.0 sin ATR válido, pero construir_plan lo frena:
    un stop en cero significaría arriesgar el 100% por acción."""
    from modulos.swing_riesgo import calcular_stop, construir_plan

    assert calcular_stop(entrada=100.0, atr=0.0) == 0.0
    plan = construir_plan(entrada=100.0, atr=0.0)
    assert not plan.operable
    assert any("BLOQUEO" in aviso for aviso in plan.avisos)
