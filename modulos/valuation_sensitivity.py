"""Matriz de sensibilidad de valoración para Research Core.

El objetivo no es sustituir un DCF completo, sino convertir el valor razonable
actual en un rango defendible ante cambios de crecimiento y tasa de descuento.
La matriz debe leerse como análisis de sensibilidad, no como precio objetivo
oficial ni asesoramiento financiero personalizado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import streamlit as st


@dataclass
class SensitivityCell:
    """Celda individual de la matriz de sensibilidad."""

    growth_rate: float
    discount_rate: float
    fair_value: float | None
    margin_of_safety: float | None
    reading: str


@dataclass
class ValuationSensitivity:
    """Resultado completo de sensibilidad de valoración."""

    base_value: float | None
    current_price: float | None
    base_growth_rate: float
    base_discount_rate: float
    growth_rates: list[float] = field(default_factory=list)
    discount_rates: list[float] = field(default_factory=list)
    cells: list[SensitivityCell] = field(default_factory=list)
    available: bool = False
    comment: str = ""


def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number
    except Exception:
        return None


def _fmt_money(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "N/D"


def _fmt_pct(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "N/D"
    sign = "+" if signed else ""
    return f"{value * 100:{sign}.1f}%"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _infer_base_growth(thesis: Any) -> float:
    """Infiera un supuesto de crecimiento base desde el score de crecimiento."""

    growth_score = _as_float(getattr(thesis, "growth_score", None))
    quality_score = _as_float(getattr(thesis, "quality_score", None))

    if growth_score is None:
        growth_score = 50.0
    if quality_score is None:
        quality_score = 50.0

    if growth_score >= 75 and quality_score >= 70:
        return 0.06
    if growth_score >= 60:
        return 0.045
    if growth_score >= 45:
        return 0.035
    return 0.02


def _infer_base_discount_rate(thesis: Any) -> float:
    """Infiera una tasa de descuento base desde riesgo/calidad."""

    risk_score = _as_float(getattr(thesis, "risk_score", None))
    quality_score = _as_float(getattr(thesis, "quality_score", None))

    if risk_score is None:
        risk_score = 50.0
    if quality_score is None:
        quality_score = 50.0

    base = 0.10
    if risk_score >= 75 and quality_score >= 75:
        base -= 0.01
    elif risk_score < 45:
        base += 0.015
    elif risk_score < 60:
        base += 0.005

    return _clamp(base, 0.075, 0.125)


def _base_value_from_thesis(thesis: Any) -> float | None:
    """Obtiene valor base desde valor intrínseco o escenarios disponibles."""

    intrinsic = _as_float(getattr(thesis, "intrinsic_value", None))
    if intrinsic is not None and intrinsic > 0:
        return intrinsic

    values: list[float] = []
    current_price = _as_float(getattr(thesis, "current_price", None))
    for scenario in getattr(thesis, "valuation_scenarios", []) or []:
        name = str(getattr(scenario, "name", "")).lower()
        price = _as_float(getattr(scenario, "price", None))
        if price is None or price <= 0:
            continue
        if "precio actual" in name and current_price is not None and abs(price - current_price) < 0.01:
            continue
        values.append(price)

    if not values:
        return None

    values = sorted(values)
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def _sensitivity_factor(growth_rate: float, discount_rate: float, base_growth_rate: float, base_discount_rate: float) -> float:
    """Convierte cambios de supuestos en factor de valoración.

    Regla deliberadamente prudente:
    - Cada +1 pp de crecimiento respecto al caso base aumenta valor ~5.5%.
    - Cada +1 pp de tasa de descuento respecto al caso base reduce valor ~6.5%.
    """

    growth_delta = growth_rate - base_growth_rate
    discount_delta = discount_rate - base_discount_rate
    factor = 1.0 + (growth_delta / 0.01) * 0.055 - (discount_delta / 0.01) * 0.065
    return _clamp(factor, 0.50, 1.70)


def _reading(margin_of_safety: float | None) -> str:
    if margin_of_safety is None:
        return "Sin lectura"
    if margin_of_safety >= 0.25:
        return "Margen amplio"
    if margin_of_safety >= 0.10:
        return "Zona interesante"
    if margin_of_safety >= -0.10:
        return "Valor razonable"
    if margin_of_safety >= -0.25:
        return "Precio exigente"
    return "Muy exigente"


def build_valuation_sensitivity(thesis: Any) -> ValuationSensitivity:
    """Construye matriz crecimiento x tasa de descuento desde una tesis."""

    base_value = _base_value_from_thesis(thesis)
    current_price = _as_float(getattr(thesis, "current_price", None))
    base_growth = _infer_base_growth(thesis)
    base_discount = _infer_base_discount_rate(thesis)

    if base_value is None or base_value <= 0:
        return ValuationSensitivity(
            base_value=None,
            current_price=current_price,
            base_growth_rate=base_growth,
            base_discount_rate=base_discount,
            available=False,
            comment="No hay valor intrínseco o escenarios suficientes para construir sensibilidad.",
        )

    growth_rates = [max(0.0, base_growth - 0.02), base_growth, base_growth + 0.02]
    discount_rates = [max(0.06, base_discount - 0.01), base_discount, base_discount + 0.01]

    cells: list[SensitivityCell] = []
    for growth in growth_rates:
        for discount in discount_rates:
            fair_value = base_value * _sensitivity_factor(growth, discount, base_growth, base_discount)
            margin = fair_value / current_price - 1.0 if current_price and current_price > 0 else None
            cells.append(
                SensitivityCell(
                    growth_rate=growth,
                    discount_rate=discount,
                    fair_value=fair_value,
                    margin_of_safety=margin,
                    reading=_reading(margin),
                )
            )

    return ValuationSensitivity(
        base_value=base_value,
        current_price=current_price,
        base_growth_rate=base_growth,
        base_discount_rate=base_discount,
        growth_rates=growth_rates,
        discount_rates=discount_rates,
        cells=cells,
        available=True,
        comment=(
            "Matriz orientativa construida a partir del valor razonable actual. "
            "No sustituye un DCF formal; muestra sensibilidad ante supuestos clave."
        ),
    )


def sensitivity_to_dataframe(sensitivity: ValuationSensitivity) -> pd.DataFrame:
    """Devuelve DataFrame largo para visualización/depuración."""

    rows: list[dict[str, str]] = []
    for cell in sensitivity.cells:
        rows.append(
            {
                "Crecimiento": _fmt_pct(cell.growth_rate, signed=False),
                "Tasa descuento": _fmt_pct(cell.discount_rate, signed=False),
                "Valor razonable": _fmt_money(cell.fair_value),
                "Margen vs precio": _fmt_pct(cell.margin_of_safety),
                "Lectura": cell.reading,
            }
        )
    return pd.DataFrame(rows)


def sensitivity_matrix_dataframe(sensitivity: ValuationSensitivity) -> pd.DataFrame:
    """Devuelve matriz ancha crecimiento x descuento."""

    rows: list[dict[str, str]] = []
    for growth in sensitivity.growth_rates:
        row: dict[str, str] = {"Crecimiento": _fmt_pct(growth, signed=False)}
        for discount in sensitivity.discount_rates:
            cell = next(
                (
                    item
                    for item in sensitivity.cells
                    if abs(item.growth_rate - growth) < 1e-9 and abs(item.discount_rate - discount) < 1e-9
                ),
                None,
            )
            label = _fmt_pct(discount, signed=False)
            if cell is None:
                row[label] = "N/D"
            else:
                row[label] = f"{_fmt_money(cell.fair_value)} ({_fmt_pct(cell.margin_of_safety)})"
        rows.append(row)
    return pd.DataFrame(rows)


def sensitivity_markdown_rows(sensitivity: ValuationSensitivity) -> list[dict[str, str]]:
    """Filas listas para tabla Markdown del informe."""

    if not sensitivity.available:
        return []

    rows: list[dict[str, str]] = []
    for cell in sensitivity.cells:
        rows.append(
            {
                "Crecimiento": _fmt_pct(cell.growth_rate, signed=False),
                "Descuento": _fmt_pct(cell.discount_rate, signed=False),
                "Valor": _fmt_money(cell.fair_value),
                "Margen": _fmt_pct(cell.margin_of_safety),
                "Lectura": cell.reading,
            }
        )
    return rows


def render_valuation_sensitivity(thesis: Any) -> ValuationSensitivity:
    """Renderiza la matriz dentro de Streamlit."""

    sensitivity = build_valuation_sensitivity(thesis)

    st.markdown("#### Sensibilidad crecimiento vs tasa de descuento")
    st.caption(
        "Matriz orientativa para comprobar si la tesis depende demasiado de supuestos optimistas. "
        "Cada celda muestra valor razonable estimado y margen frente al precio actual."
    )

    if not sensitivity.available:
        st.warning(sensitivity.comment)
        return sensitivity

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valor base", _fmt_money(sensitivity.base_value))
    c2.metric("Precio actual", _fmt_money(sensitivity.current_price))
    c3.metric("Crecimiento base", _fmt_pct(sensitivity.base_growth_rate, signed=False))
    c4.metric("Descuento base", _fmt_pct(sensitivity.base_discount_rate, signed=False))

    st.dataframe(sensitivity_matrix_dataframe(sensitivity), use_container_width=True, hide_index=True)

    with st.expander("Ver tabla detallada de sensibilidad", expanded=False):
        st.dataframe(sensitivity_to_dataframe(sensitivity), use_container_width=True, hide_index=True)

    st.caption(sensitivity.comment)
    return sensitivity
