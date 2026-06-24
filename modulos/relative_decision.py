"""Veredicto relativo para comparación empresa vs competidor.

Este módulo transforma la comparativa cuantitativa de Research Core en una
conclusión accionable: preferencia relativa, ventaja por bloque y confianza.
No toma decisiones automáticas; prioriza qué empresa merece más análisis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st


@dataclass
class RelativeEdge:
    """Ventaja cuantitativa por dimensión."""

    name: str
    primary_value: float | None
    competitor_value: float | None
    edge: float | None
    winner: str
    reading: str


@dataclass
class RelativeDecision:
    """Conclusión estructurada de preferencia relativa."""

    action: str
    preferred: str
    relative_score: float | None
    confidence: float
    summary: str
    edges: list[RelativeEdge]
    primary_reasons: list[str]
    competitor_reasons: list[str]
    caveats: list[str]


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


def _fmt_score(value: Any) -> str:
    number = _as_float(value)
    return f"{number:.1f}/100" if number is not None else "N/D"


def _fmt_pct(value: Any, signed: bool = False) -> str:
    number = _as_float(value)
    if number is None:
        return "N/D"
    sign = "+" if signed else ""
    return f"{number * 100:{sign}.1f}%"


def _fmt_delta(value: Any) -> str:
    number = _as_float(value)
    return f"{number:+.1f} pts" if number is not None else "N/D"


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


def _winner_from_edge(edge: float | None, primary_label: str, competitor_label: str, threshold: float = 2.0) -> str:
    if edge is None:
        return "N/D"
    if abs(edge) < threshold:
        return "Empate práctico"
    return primary_label if edge > 0 else competitor_label


def _edge(
    name: str,
    primary_value: float | None,
    competitor_value: float | None,
    primary_label: str,
    competitor_label: str,
    reading: str,
    *,
    multiplier: float = 1.0,
    lower_is_better: bool = False,
    threshold: float = 2.0,
) -> RelativeEdge:
    if primary_value is None or competitor_value is None:
        edge_value = None
    else:
        raw = (competitor_value - primary_value) if lower_is_better else (primary_value - competitor_value)
        edge_value = raw * multiplier

    return RelativeEdge(
        name=name,
        primary_value=primary_value,
        competitor_value=competitor_value,
        edge=edge_value,
        winner=_winner_from_edge(edge_value, primary_label, competitor_label, threshold),
        reading=reading,
    )


def _build_edges(comparison: Any, valuequant_score: Any) -> list[RelativeEdge]:
    primary_label = comparison.primary.ticker
    competitor_label = comparison.competitor.ticker
    competitor_vq = (
        comparison.competitor_score.valuequant_score
        if comparison.competitor_score and comparison.competitor_score.data_available
        else None
    )

    return [
        _edge(
            "Score agregado",
            _as_float(_score_attr(valuequant_score, "final_score")),
            _as_float(_score_attr(competitor_vq, "final_score")),
            primary_label,
            competitor_label,
            "Ventaja global del modelo ValueQuant.",
            threshold=3.0,
        ),
        _edge(
            "Quality edge",
            _component_score(valuequant_score, "calidad"),
            _component_score(competitor_vq, "calidad"),
            primary_label,
            competitor_label,
            "Calidad de negocio, rentabilidad y consistencia fundamental.",
            threshold=3.0,
        ),
        _edge(
            "Valuation edge",
            _component_score(valuequant_score, "valoración"),
            _component_score(competitor_vq, "valoración"),
            primary_label,
            competitor_label,
            "Atractivo relativo de precio frente a valor razonable y múltiplos.",
            threshold=3.0,
        ),
        _edge(
            "Risk edge",
            _component_score(valuequant_score, "riesgo"),
            _component_score(competitor_vq, "riesgo"),
            primary_label,
            competitor_label,
            "Riesgo financiero, forense y estabilidad del perfil.",
            threshold=3.0,
        ),
        _edge(
            "Growth edge",
            _component_score(valuequant_score, "crecimiento"),
            _component_score(competitor_vq, "crecimiento"),
            primary_label,
            competitor_label,
            "Crecimiento cuantitativo y catalizadores incorporados al score.",
            threshold=3.0,
        ),
        _edge(
            "FCF Yield edge",
            _as_float(comparison.primary.fcf_yield),
            _as_float(comparison.competitor.fcf_yield),
            primary_label,
            competitor_label,
            "Mayor rentabilidad por flujo de caja libre sobre capitalización.",
            multiplier=100.0,
            threshold=0.5,
        ),
        _edge(
            "Momentum edge",
            _as_float(comparison.primary.perf_1y),
            _as_float(comparison.competitor.perf_1y),
            primary_label,
            competitor_label,
            "Comportamiento relativo de mercado durante el último año.",
            multiplier=100.0,
            threshold=3.0,
        ),
        _edge(
            "Beta/riesgo mercado",
            _as_float(comparison.primary.beta),
            _as_float(comparison.competitor.beta),
            primary_label,
            competitor_label,
            "Menor sensibilidad al mercado, si el resto de métricas acompaña.",
            multiplier=10.0,
            lower_is_better=True,
            threshold=1.0,
        ),
    ]


def _weighted_relative_score(edges: list[RelativeEdge]) -> tuple[float | None, int]:
    weights = {
        "Score agregado": 0.30,
        "Quality edge": 0.18,
        "Valuation edge": 0.22,
        "Risk edge": 0.10,
        "Growth edge": 0.08,
        "FCF Yield edge": 0.06,
        "Momentum edge": 0.04,
        "Beta/riesgo mercado": 0.02,
    }
    numerator = 0.0
    denominator = 0.0
    available = 0
    for edge in edges:
        value = _as_float(edge.edge)
        weight = weights.get(edge.name, 0.0)
        if value is None or weight <= 0:
            continue
        numerator += value * weight
        denominator += weight
        available += 1
    if denominator <= 0:
        return None, available
    return numerator / denominator, available


def build_relative_decision(
    comparison: Any,
    valuequant_score: Any,
    res_val: dict[str, Any] | None = None,
    nota_buffett: float | None = None,
) -> RelativeDecision:
    """Construye una conclusión relativa entre empresa principal y competidor."""

    primary_label = comparison.primary.ticker
    competitor_label = comparison.competitor.ticker
    edges = _build_edges(comparison, valuequant_score)
    relative_score, available_edges = _weighted_relative_score(edges)

    primary_final = _as_float(_score_attr(valuequant_score, "final_score"))
    competitor_vq = (
        comparison.competitor_score.valuequant_score
        if comparison.competitor_score and comparison.competitor_score.data_available
        else None
    )
    competitor_final = _as_float(_score_attr(competitor_vq, "final_score"))

    if relative_score is None:
        action = "Comparativa insuficiente"
        preferred = "N/D"
        summary = "No hay suficientes datos comparables para establecer una preferencia relativa."
    elif primary_final is not None and competitor_final is not None and primary_final < 50 and competitor_final < 50 and abs(relative_score) < 6:
        action = "Ninguna prioritaria"
        preferred = "N/D"
        summary = "Ambas compañías quedan por debajo de un umbral exigente o sin ventaja relativa suficiente."
    elif relative_score >= 8:
        action = f"Prefiero {primary_label}"
        preferred = primary_label
        summary = f"{primary_label} muestra una ventaja relativa suficiente para priorizar su análisis frente a {competitor_label}."
    elif relative_score <= -8:
        action = f"Prefiero {competitor_label}"
        preferred = competitor_label
        summary = f"{competitor_label} muestra una ventaja relativa suficiente para priorizarlo frente a {primary_label}."
    elif primary_final is not None and competitor_final is not None and primary_final >= 60 and competitor_final >= 60:
        action = "Ambas interesantes"
        preferred = "Empate práctico"
        summary = "Ambas compañías presentan calidad suficiente; la decisión debería depender de precio de entrada y cartera actual."
    else:
        action = "Sin preferencia fuerte"
        preferred = "Empate práctico"
        summary = "La diferencia relativa no es suficientemente amplia; conviene esperar mejor precio o más datos."

    primary_reasons: list[str] = []
    competitor_reasons: list[str] = []
    for edge in edges:
        if edge.winner == primary_label:
            primary_reasons.append(f"{edge.name}: ventaja de {_fmt_delta(edge.edge)}. {edge.reading}")
        elif edge.winner == competitor_label:
            competitor_reasons.append(f"{edge.name}: ventaja de {_fmt_delta(-edge.edge if edge.edge is not None else None)}. {edge.reading}")

    confidence = min(0.85, 0.35 + available_edges * 0.06)
    if comparison.competitor_score and comparison.competitor_score.data_available:
        confidence = min(0.85, confidence + 0.12)
    if comparison.competitor_score and comparison.competitor_score.error:
        confidence = max(0.25, confidence - 0.15)

    caveats = [
        "La preferencia relativa prioriza análisis, no ejecuta una recomendación automática de compra.",
        "El score del competidor se calcula bajo demanda y debe validarse con datos normalizados.",
        "La decisión final debe incorporar margen de seguridad, diversificación y horizonte temporal.",
    ]
    if comparison.competitor_score and comparison.competitor_score.error:
        caveats.insert(0, f"Score del competidor incompleto: {comparison.competitor_score.error}")

    return RelativeDecision(
        action=action,
        preferred=preferred,
        relative_score=relative_score,
        confidence=confidence,
        summary=summary,
        edges=edges,
        primary_reasons=primary_reasons[:5],
        competitor_reasons=competitor_reasons[:5],
        caveats=caveats,
    )


def relative_decision_table_rows(decision: RelativeDecision, primary_label: str, competitor_label: str) -> list[dict[str, str]]:
    """Filas compactas para insertar el veredicto relativo en el informe."""

    rows = [
        {
            "Bloque": "Preferencia relativa",
            primary_label: decision.action if decision.preferred == primary_label else "No preferente",
            competitor_label: decision.action if decision.preferred == competitor_label else "No preferente",
            "Lectura": decision.summary,
        },
        {
            "Bloque": "Relative edge score",
            primary_label: _fmt_delta(decision.relative_score),
            competitor_label: _fmt_delta(-decision.relative_score if decision.relative_score is not None else None),
            "Lectura": f"Confianza relativa: {_fmt_pct(decision.confidence)}.",
        },
    ]
    for edge in decision.edges[:6]:
        rows.append(
            {
                "Bloque": edge.name,
                primary_label: _fmt_delta(edge.edge),
                competitor_label: _fmt_delta(-edge.edge if edge.edge is not None else None),
                "Lectura": f"Ventaja: {edge.winner}. {edge.reading}",
            }
        )
    return rows


def render_relative_decision_panel(decision: RelativeDecision) -> None:
    """Renderiza el panel ejecutivo de decisión relativa."""

    st.markdown("#### Veredicto relativo final")
    c1, c2, c3 = st.columns(3)
    c1.metric("Conclusión", decision.action)
    c2.metric("Relative edge", _fmt_delta(decision.relative_score))
    c3.metric("Confianza relativa", _fmt_pct(decision.confidence))
    st.info(decision.summary)

    edge_rows = [
        {
            "Dimensión": edge.name,
            "Ventaja neta": _fmt_delta(edge.edge),
            "Ganador": edge.winner,
            "Lectura": edge.reading,
        }
        for edge in decision.edges
    ]
    st.dataframe(pd.DataFrame(edge_rows), use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        st.markdown("**Razones a favor de la empresa principal**")
        if decision.primary_reasons:
            for reason in decision.primary_reasons:
                st.write(f"- {reason}")
        else:
            st.write("- No hay ventaja clara suficiente.")
    with right:
        st.markdown("**Razones a favor del competidor**")
        if decision.competitor_reasons:
            for reason in decision.competitor_reasons:
                st.write(f"- {reason}")
        else:
            st.write("- No hay ventaja clara suficiente.")

    with st.expander("Limitaciones del veredicto relativo", expanded=False):
        for caveat in decision.caveats:
            st.write(f"- {caveat}")
