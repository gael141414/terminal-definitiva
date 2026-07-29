"""Convención unificada de margen de seguridad: (fair_value - price) / price.

Antes de este fix, modulos/resumen.py y modulos/fundamental.py (Graham, Lynch,
DCF) usaban la convención contraria — (price - fair_value) / fair_value —
mientras que modulos/scoring_engine.py (el score institucional) y
modulos/investment_thesis.py (Tesis, de donde Watchlist lee el valor guardado
sin recalcularlo) ya usaban la convención correcta. Este archivo fija esa
propiedad: para el mismo par (precio, valor razonable), el SIGNO debe
coincidir en las 4 rutas de cálculo, y las funciones ya "correctas" no deben
haber cambiado.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.investment_thesis import _margin


def _scoring_engine_margin(fair_value: float, price: float) -> float:
    """Replica exacta de la fórmula en modulos/scoring_engine.py::_valuation_component."""
    return (float(fair_value) - float(price)) / float(price)


def _resumen_margin(fair_value: float, price: float) -> float:
    """Replica exacta de la fórmula corregida en modulos/resumen.py (tras el fix)."""
    return ((fair_value - price) / price) * 100


def _fundamental_margin(fair_value: float, price: float) -> float:
    """Replica exacta de la fórmula corregida en modulos/fundamental.py (Graham/Lynch/DCF, tras el fix)."""
    return ((fair_value - price) / price) * 100


# ---------------------------------------------------------------------------
# El signo (y el sentido "infravalorada/sobrevalorada") coincide en las 4 rutas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fair_value,price,expect_positive",
    [
        (150.0, 100.0, True),   # infravalorada: precio por debajo del valor razonable
        (100.0, 150.0, False),  # sobrevalorada: precio por encima del valor razonable
        (100.0, 100.0, None),   # precio justo: signo no importa (cero)
    ],
)
def test_las_4_rutas_coinciden_en_signo(fair_value, price, expect_positive):
    thesis_margin = _margin(price, fair_value)  # firma: (current_price, intrinsic_value)
    scoring_margin = _scoring_engine_margin(fair_value, price)
    resumen_margin = _resumen_margin(fair_value, price)
    fundamental_margin = _fundamental_margin(fair_value, price)

    # Las 4 fórmulas deben ser algebraicamente equivalentes (salvo el *100 de
    # resumen/fundamental, que son puntos porcentuales en vez de fracción).
    assert thesis_margin == pytest.approx(scoring_margin, rel=1e-9)
    assert resumen_margin == pytest.approx(scoring_margin * 100, rel=1e-9)
    assert fundamental_margin == pytest.approx(scoring_margin * 100, rel=1e-9)

    if expect_positive is True:
        assert thesis_margin > 0 and scoring_margin > 0 and resumen_margin > 0 and fundamental_margin > 0
    elif expect_positive is False:
        assert thesis_margin < 0 and scoring_margin < 0 and resumen_margin < 0 and fundamental_margin < 0
    else:
        assert thesis_margin == pytest.approx(0.0) and scoring_margin == pytest.approx(0.0)


def test_investment_thesis_margin_no_cambio_ya_estaba_correcto():
    """modulos/investment_thesis.py (Tesis, de donde Watchlist lee el valor
    guardado) ya usaba (fair_value - price) / price antes de este fix — no se
    tocó, y esta prueba fija que sigue siendo así."""
    # intrinsic_value/current_price - 1.0 == (intrinsic_value - current_price) / current_price
    assert _margin(100.0, 150.0) == pytest.approx((150.0 - 100.0) / 100.0)
    assert _margin(150.0, 100.0) == pytest.approx((100.0 - 150.0) / 150.0)


# ---------------------------------------------------------------------------
# Verificación estática: el código fuente ya no contiene la fórmula vieja
# ---------------------------------------------------------------------------


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_resumen_ya_no_usa_la_convencion_contraria():
    source = _read("modulos/resumen.py")
    assert "(precio_mercado - v_justo) / v_justo" not in source
    assert "(v_justo - precio_mercado) / precio_mercado" in source


def test_fundamental_ya_no_usa_la_convencion_contraria():
    source = _read("modulos/fundamental.py")
    # Las 3 fórmulas viejas (Graham, Lynch, DCF) no deben quedar.
    assert "(p_actual_seguro - v_graham) / v_graham" not in source
    assert "(p_actual_seguro - v_lynch) / v_lynch" not in source
    assert "(precio_actual - v_dcf) / v_dcf" not in source
    # Las 3 fórmulas nuevas sí.
    assert "(v_graham - p_actual_seguro) / p_actual_seguro" in source
    assert "(v_lynch - p_actual_seguro) / p_actual_seguro" in source
    assert "(v_dcf - precio_actual) / precio_actual" in source
    # margen_seguridad_usr / precio_compra es un concepto DISTINTO (el
    # descuento objetivo elegido por el usuario para calcular un precio de
    # compra, no la lectura infravalorada/sobrevalorada) y no debe tocarse.
    assert "precio_compra = v_dcf * (1 - (margen_seguridad_usr / 100))" in source


def test_scoring_engine_margin_no_cambio_ya_estaba_correcto():
    source = _read("modulos/scoring_engine.py")
    assert "(float(fair_value) - float(price)) / float(price)" in source
