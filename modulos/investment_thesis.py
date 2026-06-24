"""Motor de tesis de inversión para ValueQuant Terminal.

Este módulo convierte el ValueQuant Score, la valoración y las banderas rojas en
una tesis operativa estructurada. No ejecuta órdenes ni constituye asesoramiento
financiero personalizado; genera un marco de análisis para revisión humana.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import streamlit as st


@dataclass
class ThesisSection:
    """Bloque textual dentro de la tesis."""

    title: str
    bullets: list[str] = field(default_factory=list)


@dataclass
class InvestmentThesis:
    """Resultado estructurado de tesis operativa."""

    ticker: str
    action: str
    action_detail: str
    final_score: float | None
    quality_score: float | None
    valuation_score: float | None
    risk_score: float | None
    growth_score: float | None
    buffett_score: float | None
    current_price: float | None
    intrinsic_value: float | None
    margin_of_safety: float | None
    conservative_entry_price: float | None
    reasonable_entry_price: float | None
    positives: list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    sections: list[ThesisSection] = field(default_factory=list)


def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _score_attr(valuequant_score: Any, attr: str, default: Any = None) -> Any:
    if valuequant_score is None:
        return default
    return getattr(valuequant_score, attr, default)


def _component_score(valuequant_score: Any, component_name: str) -> float | None:
    components = _score_attr(valuequant_score, "components", []) or []
    target = component_name.lower()
    for component in components:
        name = str(getattr(component, "name", "")).lower()
        if target in name:
            return _as_float(getattr(component, "score", None))
    return None


def _extract_price_and_value(res_val: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not isinstance(res_val, dict):
        return None, None

    current_price = _as_float(
        res_val.get("precio_actual")
        or res_val.get("current_price")
        or res_val.get("price")
        or res_val.get("precio")
    )

    intrinsic_value = _as_float(
        res_val.get("valor_intrinseco")
        or res_val.get("valor_intrinseco_dcf")
        or res_val.get("precio_objetivo")
        or res_val.get("target_price")
        or res_val.get("fair_value")
    )

    return current_price, intrinsic_value


def _margin(current_price: float | None, intrinsic_value: float | None) -> float | None:
    if current_price is None or intrinsic_value is None or current_price <= 0:
        return None
    return intrinsic_value / current_price - 1.0


def _fmt_score(value: float | None) -> str:
    return f"{value:.1f}/100" if value is not None else "N/D"


def _fmt_money(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "N/D"


def _fmt_pct(value: float | None) -> str:
    return f"{value * 100:+.1f}%" if value is not None else "N/D"


def _decision(
    final_score: float | None,
    quality_score: float | None,
    valuation_score: float | None,
    risk_score: float | None,
    margin_of_safety: float | None,
    red_flags: list[str],
) -> tuple[str, str]:
    """Clasificación operativa: Comprar / Vigilar / Mantener / Evitar.

    La decisión es deliberadamente exigente: una empresa de calidad puede quedar
    en Vigilar si la valoración no ofrece margen de seguridad.
    """

    score = final_score if final_score is not None else 0.0
    quality = quality_score if quality_score is not None else 50.0
    valuation = valuation_score if valuation_score is not None else 50.0
    risk = risk_score if risk_score is not None else 50.0
    margin = margin_of_safety if margin_of_safety is not None else -1.0

    severe_red_flags = len(red_flags) >= 3 or risk < 35

    if severe_red_flags:
        return (
            "Evitar",
            "El perfil de riesgo o las banderas rojas obligan a descartar la operación hasta revisar la calidad de datos y balance.",
        )

    if score >= 78 and quality >= 75 and risk >= 60 and valuation >= 45 and margin >= 0.10:
        return (
            "Comprar / estudiar compra",
            "La combinación de calidad, riesgo y margen de seguridad justifica análisis final de entrada.",
        )

    if score >= 65 and quality >= 70 and risk >= 50:
        if margin >= 0.0 or valuation >= 45:
            return (
                "Vigilar",
                "La empresa es interesante, pero la entrada debe esperar mejor precio, catalizador claro o mayor margen de seguridad.",
            )
        return (
            "Mantener / neutral",
            "La calidad puede ser alta, pero la valoración no ofrece todavía una ventaja clara.",
        )

    if score >= 50:
        return (
            "Mantener / neutral",
            "El modelo no detecta una ventaja suficiente para priorizar compra; conviene observar evolución de fundamentales y precio.",
        )

    return (
        "Evitar",
        "La puntuación agregada no compensa el riesgo, la valoración o la falta de calidad detectada.",
    )


def build_investment_thesis(
    ticker: str,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None = None,
) -> InvestmentThesis:
    """Construye una tesis estructurada desde los outputs del análisis."""

    final_score = _as_float(_score_attr(valuequant_score, "final_score"))
    quality_score = _component_score(valuequant_score, "calidad")
    valuation_score = _component_score(valuequant_score, "valoración")
    risk_score = _component_score(valuequant_score, "riesgo")
    growth_score = _component_score(valuequant_score, "crecimiento")
    buffett_score = _as_float(nota_buffett)

    positives = list(_score_attr(valuequant_score, "positives", []) or [])[:6]
    negatives = list(_score_attr(valuequant_score, "negatives", []) or [])[:6]
    red_flags = list(_score_attr(valuequant_score, "red_flags", []) or [])[:6]

    current_price, intrinsic_value = _extract_price_and_value(res_val)
    margin_of_safety = _margin(current_price, intrinsic_value)

    conservative_entry_price = intrinsic_value * 0.75 if intrinsic_value is not None else None
    reasonable_entry_price = intrinsic_value * 0.85 if intrinsic_value is not None else None

    action, action_detail = _decision(
        final_score,
        quality_score,
        valuation_score,
        risk_score,
        margin_of_safety,
        red_flags,
    )

    bull_case: list[str] = []
    bear_case: list[str] = []
    entry_conditions: list[str] = []
    exit_conditions: list[str] = []

    if quality_score is not None:
        bull_case.append("Calidad fundamental elevada." if quality_score >= 75 else "Calidad fundamental mejorable; requiere validación manual.")
    if growth_score is not None:
        bull_case.append("Crecimiento/catalizadores favorables." if growth_score >= 65 else "Catalizadores todavía poco concluyentes.")
    if valuation_score is not None:
        if valuation_score >= 65:
            bull_case.append("Valoración razonable según el modelo.")
        elif valuation_score < 35:
            bear_case.append("Valoración exigente o margen de seguridad insuficiente.")
    if risk_score is not None:
        if risk_score >= 70:
            bull_case.append("Riesgo financiero/forense contenido.")
        elif risk_score < 50:
            bear_case.append("Riesgo financiero o contable relevante.")

    if positives:
        bull_case.extend(positives[:3])
    if negatives:
        bear_case.extend(negatives[:3])
    if red_flags:
        bear_case.extend([f"Bandera roja: {flag}" for flag in red_flags[:3]])

    if reasonable_entry_price is not None:
        entry_conditions.append(f"Zona razonable de estudio: por debajo de {_fmt_money(reasonable_entry_price)}.")
    if conservative_entry_price is not None:
        entry_conditions.append(f"Zona conservadora: por debajo de {_fmt_money(conservative_entry_price)}.")
    if margin_of_safety is not None and margin_of_safety < 0:
        entry_conditions.append("Esperar caída de precio o revisión al alza del valor intrínseco.")
    entry_conditions.append("Confirmar que el DCF/valor intrínseco usa supuestos prudentes de crecimiento, margen y WACC.")

    exit_conditions.extend(
        [
            "Deterioro persistente de FCF, márgenes o ROIC.",
            "Aumento material de deuda neta o dilución no justificada.",
            "ValueQuant Score cae por debajo de 50 o aparecen nuevas banderas rojas.",
            "La cotización supera claramente el valor razonable sin mejora equivalente en fundamentales.",
        ]
    )

    sections = [
        ThesisSection("Tesis alcista", bull_case or ["No hay suficientes argumentos alcistas automáticos."]),
        ThesisSection("Tesis bajista / riesgos", bear_case or ["No se han detectado riesgos destacados en el resumen automático."]),
        ThesisSection("Condiciones de entrada", entry_conditions),
        ThesisSection("Condiciones de salida o revisión", exit_conditions),
    ]

    return InvestmentThesis(
        ticker=ticker,
        action=action,
        action_detail=action_detail,
        final_score=final_score,
        quality_score=quality_score,
        valuation_score=valuation_score,
        risk_score=risk_score,
        growth_score=growth_score,
        buffett_score=buffett_score,
        current_price=current_price,
        intrinsic_value=intrinsic_value,
        margin_of_safety=margin_of_safety,
        conservative_entry_price=conservative_entry_price,
        reasonable_entry_price=reasonable_entry_price,
        positives=positives,
        negatives=negatives,
        red_flags=red_flags,
        sections=sections,
    )


def thesis_to_markdown(thesis: InvestmentThesis, competitor: str | None = None) -> str:
    """Exporta la tesis a Markdown para informe."""

    lines = [
        f"# Tesis de inversión — {thesis.ticker}",
        "",
        "> Documento generado automáticamente por ValueQuant Terminal. No constituye asesoramiento financiero personalizado.",
        "",
        f"**Acción operativa:** {thesis.action}",
        f"**Detalle:** {thesis.action_detail}",
    ]
    if competitor:
        lines.append(f"**Comparador:** {competitor}")
    lines.extend(
        [
            "",
            "## Métricas principales",
            f"- ValueQuant Score: {_fmt_score(thesis.final_score)}",
            f"- Buffett Quality: {_fmt_score(thesis.buffett_score)}",
            f"- Calidad: {_fmt_score(thesis.quality_score)}",
            f"- Valoración: {_fmt_score(thesis.valuation_score)}",
            f"- Riesgo: {_fmt_score(thesis.risk_score)}",
            f"- Crecimiento: {_fmt_score(thesis.growth_score)}",
            f"- Precio actual: {_fmt_money(thesis.current_price)}",
            f"- Valor intrínseco / objetivo: {_fmt_money(thesis.intrinsic_value)}",
            f"- Margen de seguridad estimado: {_fmt_pct(thesis.margin_of_safety)}",
            f"- Zona razonable de entrada: {_fmt_money(thesis.reasonable_entry_price)}",
            f"- Zona conservadora de entrada: {_fmt_money(thesis.conservative_entry_price)}",
            "",
        ]
    )

    for section in thesis.sections:
        lines.append(f"## {section.title}")
        for bullet in section.bullets:
            lines.append(f"- {bullet}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_investment_thesis(
    ticker: str,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None = None,
    ticker_competidor: str | None = None,
) -> InvestmentThesis:
    """Renderiza la tesis profesional dentro de Streamlit."""

    thesis = build_investment_thesis(ticker, valuequant_score, res_val, nota_buffett)

    st.markdown("### Tesis de inversión")
    st.caption(
        "Lectura operativa generada desde fundamentales, valoración, riesgo y score. "
        "Debe validarse manualmente antes de cualquier decisión real."
    )

    st.info(f"**Acción operativa:** {thesis.action}. {thesis.action_detail}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ValueQuant", _fmt_score(thesis.final_score))
    c2.metric("Calidad", _fmt_score(thesis.quality_score))
    c3.metric("Valoración", _fmt_score(thesis.valuation_score))
    c4.metric("Riesgo", _fmt_score(thesis.risk_score))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Precio actual", _fmt_money(thesis.current_price))
    c6.metric("Valor razonable", _fmt_money(thesis.intrinsic_value))
    c7.metric("Margen seguridad", _fmt_pct(thesis.margin_of_safety))
    c8.metric("Entrada razonable", _fmt_money(thesis.reasonable_entry_price))

    tabs = st.tabs(["Tesis", "Entrada/Salida", "Riesgos", "Exportar"])

    with tabs[0]:
        col_a, col_b = st.columns(2)
        with col_a:
            section = thesis.sections[0]
            st.markdown(f"#### {section.title}")
            for bullet in section.bullets:
                st.write(f"- {bullet}")
        with col_b:
            section = thesis.sections[1]
            st.markdown(f"#### {section.title}")
            for bullet in section.bullets:
                st.write(f"- {bullet}")

    with tabs[1]:
        col_a, col_b = st.columns(2)
        with col_a:
            section = thesis.sections[2]
            st.markdown(f"#### {section.title}")
            for bullet in section.bullets:
                st.write(f"- {bullet}")
        with col_b:
            section = thesis.sections[3]
            st.markdown(f"#### {section.title}")
            for bullet in section.bullets:
                st.write(f"- {bullet}")

    with tabs[2]:
        if thesis.red_flags:
            st.error("Banderas rojas detectadas")
            for flag in thesis.red_flags:
                st.write(f"- {flag}")
        else:
            st.success("No hay banderas rojas principales en el score agregado.")

        if thesis.negatives:
            st.markdown("#### Puntos débiles")
            for item in thesis.negatives:
                st.write(f"- {item}")

    with tabs[3]:
        markdown = thesis_to_markdown(thesis, ticker_competidor)
        st.download_button(
            "Descargar tesis en Markdown",
            data=markdown,
            file_name=f"tesis_{ticker.lower()}.md",
            mime="text/markdown",
        )
        st.code(markdown, language="markdown")

    return thesis
