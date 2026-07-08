"""Research Core consolidado de ValueQuant Terminal.

Este módulo integra las vistas nucleares de análisis de empresa en un único flujo:
score, tesis, resumen ejecutivo, análisis fundamental, auditoría forense,
proyección, earnings call NLP e informe exportable.

No sustituye todavía a los módulos originales. Los orquesta mediante lazy loading
para que cualquier fallo quede aislado dentro de la pestaña correspondiente.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from modulos.analysis_store import render_save_to_watchlist_panel
from modulos.investment_thesis import render_investment_thesis
from modulos.module_loader import safe_call
from modulos.research_report import render_research_report_export
from modulos.relative_comparison import render_relative_comparison


def _score_attr(valuequant_score: Any, attr: str, default: Any = None) -> Any:
    """Lee atributos del ValueQuantScore sin acoplarse a su implementación."""

    if valuequant_score is None:
        return default
    return getattr(valuequant_score, attr, default)


def _fmt_score(value: Any) -> str:
    try:
        return f"{float(value):.1f}/100"
    except Exception:
        return "N/D"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except Exception:
        return "N/D"


def _veredicto(score: float | None) -> tuple[str, str]:
    """Devuelve etiqueta y mensaje operativo para el score global."""

    if score is None:
        return "Pendiente", "No hay score suficiente para formular una tesis cuantitativa."
    if score >= 80:
        return "Alta calidad", "Empresa candidata a análisis profundo. Requiere validar valoración y riesgos antes de comprar."
    if score >= 65:
        return "Vigilar / estudiar", "Perfil razonable, pero necesita margen de seguridad o catalizadores adicionales."
    if score >= 50:
        return "Neutral", "No hay ventaja clara. Mantener en observación salvo que la tesis cualitativa sea fuerte."
    return "Evitar por ahora", "La combinación de calidad, valoración y riesgo no justifica prioridad de análisis."



def _as_float(value: Any, default: float | None = None) -> float | None:
    """Convierte valores numéricos sin romper la UI."""

    try:
        if value is None:
            return default
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return default
        return number
    except Exception:
        return default


def _score_bucket(score: float | None) -> tuple[str, str, str]:
    """Clasifica el score en una banda accionable de producto."""

    if score is None:
        return "Pendiente", "Sin datos suficientes", "Revisar cobertura antes de tomar decisiones."
    if score >= 80:
        return "Excelente", "Alta prioridad", "Profundizar tesis, valoración y riesgos antes de entrada."
    if score >= 65:
        return "Invertible", "Prioridad media", "Candidato razonable; exigir margen de seguridad y confirmar catalizadores."
    if score >= 50:
        return "Observación", "Baja prioridad", "Mantener en seguimiento salvo mejora clara de score o precio."
    return "Débil", "Descartar / recalcular", "No dedicar tiempo adicional salvo cambio material en datos o tesis."


def _red_flags_count(valuequant_score: Any) -> int:
    """Cuenta banderas rojas del score sin acoplarse a la implementación interna."""

    explicit = _score_attr(valuequant_score, "red_flags_count")
    try:
        if explicit is not None:
            return max(0, int(explicit))
    except Exception:
        pass

    flags = _score_attr(valuequant_score, "red_flags", [])
    if isinstance(flags, list):
        return len(flags)
    if isinstance(flags, tuple):
        return len(flags)
    return 0


def build_research_ux_summary(
    ticker_input: str,
    ticker_competidor: str,
    nota_buffett: float,
    valuequant_score: Any,
) -> dict[str, Any]:
    """Construye el payload de UX del panel principal de Research Core."""

    final_score = _as_float(_score_attr(valuequant_score, "final_score"))
    raw_score = _as_float(_score_attr(valuequant_score, "raw_score"))
    coverage = _as_float(_score_attr(valuequant_score, "data_coverage"))
    confidence = _as_float(_score_attr(valuequant_score, "confidence"))
    predictive_confidence = _as_float(_score_attr(valuequant_score, "predictive_confidence"))
    model_version = _score_attr(valuequant_score, "model_version", "N/D")
    decision_action = str(_score_attr(valuequant_score, "decision_action", "") or "").strip()
    quality_adjusted = bool(_score_attr(valuequant_score, "quality_adjusted", False))
    quality_gate_reason = str(_score_attr(valuequant_score, "quality_gate_reason", "") or "").strip()
    red_flags = _red_flags_count(valuequant_score)

    verdict, verdict_text = _veredicto(final_score)
    score_bucket, priority_label, priority_detail = _score_bucket(final_score)

    if red_flags > 0 or quality_adjusted:
        risk_state = "Alerta"
        risk_detail = quality_gate_reason or f"{red_flags} bandera(s) roja(s) detectada(s)."
    elif final_score is not None and final_score >= 65:
        risk_state = "Controlado"
        risk_detail = "Sin ajustes críticos detectados en el score."
    else:
        risk_state = "Pendiente"
        risk_detail = "Conviene validar fundamentales, valoración y narrativa antes de priorizar."

    if decision_action:
        primary_action = decision_action
    elif final_score is not None and final_score >= 80:
        primary_action = "Analizar entrada con prioridad"
    elif final_score is not None and final_score >= 65:
        primary_action = "Estudiar con margen de seguridad"
    elif final_score is not None and final_score >= 50:
        primary_action = "Mantener en observación"
    else:
        primary_action = "Evitar por ahora"

    return {
        "ticker": str(ticker_input or "").upper(),
        "competitor": str(ticker_competidor or "").upper(),
        "final_score": final_score,
        "raw_score": raw_score,
        "buffett_score": _as_float(nota_buffett),
        "coverage": coverage,
        "confidence": confidence,
        "predictive_confidence": predictive_confidence,
        "model_version": model_version,
        "verdict": verdict,
        "verdict_text": verdict_text,
        "score_bucket": score_bucket,
        "priority_label": priority_label,
        "priority_detail": priority_detail,
        "primary_action": primary_action,
        "risk_state": risk_state,
        "risk_detail": risk_detail,
        "quality_adjusted": quality_adjusted,
        "quality_gate_reason": quality_gate_reason or "-",
        "red_flags": red_flags,
    }


def build_research_workflow_steps(summary: dict[str, Any]) -> list[dict[str, str]]:
    """Devuelve los pasos de lectura recomendados para el análisis principal."""

    final_score = _as_float(summary.get("final_score"))
    coverage = _as_float(summary.get("coverage"))
    confidence = _as_float(summary.get("confidence"))
    predictive_confidence = _as_float(summary.get("predictive_confidence"))
    red_flags = int(summary.get("red_flags") or 0)
    quality_adjusted = bool(summary.get("quality_adjusted"))

    score_status = "OK" if final_score is not None else "Pendiente"
    data_status = "OK" if coverage is not None and coverage >= 0.70 else "Revisar"
    confidence_status = "OK" if confidence is not None and confidence >= 0.60 else "Revisar"
    prediction_status = "OK" if predictive_confidence is not None and predictive_confidence >= 0.55 else "Pendiente"
    risk_status = "Alerta" if red_flags > 0 or quality_adjusted else "OK"

    return [
        {
            "Paso": "1. Score institucional",
            "Estado": score_status,
            "Lectura": "Confirmar score final, score bruto y acción recomendada.",
        },
        {
            "Paso": "2. Calidad de datos",
            "Estado": data_status,
            "Lectura": "Validar cobertura antes de confiar en conclusiones automáticas.",
        },
        {
            "Paso": "3. Confianza operativa",
            "Estado": confidence_status,
            "Lectura": "Medir si la señal tiene suficiente fiabilidad para priorizar tiempo.",
        },
        {
            "Paso": "4. Confianza predictiva",
            "Estado": prediction_status,
            "Lectura": "Contrastar fiabilidad esperada frente a backtesting histórico.",
        },
        {
            "Paso": "5. Riesgos y quality gates",
            "Estado": risk_status,
            "Lectura": "Revisar banderas rojas, ajustes de calidad y razones de gate.",
        },
        {
            "Paso": "6. Tesis, valoración y seguimiento",
            "Estado": "Acción",
            "Lectura": "Completar tesis, margen de seguridad, comparativa y guardado en watchlist.",
        },
    ]


def _state_badge(status: str) -> str:
    status = str(status or "").lower()
    if status == "ok":
        return "✅ OK"
    if status == "alerta":
        return "⚠️ Alerta"
    if status == "acción":
        return "➡️ Acción"
    return "🟡 Revisar"


def _render_workflow_steps(summary: dict[str, Any]) -> None:
    """Renderiza un workflow compacto de decisión."""

    steps = build_research_workflow_steps(summary)
    st.markdown("#### Ruta recomendada de análisis")

    for step in steps:
        c1, c2, c3 = st.columns([1.2, 0.8, 3.0])
        c1.markdown(f"**{step['Paso']}**")
        c2.markdown(_state_badge(step["Estado"]))
        c3.caption(step["Lectura"])


def _render_action_card(summary: dict[str, Any]) -> None:
    """Tarjeta ejecutiva de decisión."""

    st.markdown("#### Decisión ejecutiva")

    c1, c2, c3 = st.columns([1.3, 1.0, 1.0])
    c1.metric("Acción sugerida", summary["primary_action"])
    c2.metric("Prioridad", summary["priority_label"])
    c3.metric("Riesgo", summary["risk_state"])

    if summary["risk_state"] == "Alerta":
        st.warning(summary["risk_detail"])
    elif summary["priority_label"] == "Alta prioridad":
        st.success(summary["priority_detail"])
    else:
        st.info(summary["priority_detail"])


def _render_research_header(
    ticker_input: str,
    ticker_competidor: str,
    nota_buffett: float,
    valuequant_score: Any,
) -> None:
    """Cabecera ejecutiva del flujo Research Core."""

    summary = build_research_ux_summary(
        ticker_input=ticker_input,
        ticker_competidor=ticker_competidor,
        nota_buffett=nota_buffett,
        valuequant_score=valuequant_score,
    )

    st.markdown(f"## 🧩 Research Core — {summary['ticker']}")
    st.caption(
        "Panel principal de decisión: score, confianza, riesgos, tesis, seguimiento e informe en una sola ruta."
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("ValueQuant", _fmt_score(summary["final_score"]))
    c2.metric("Buffett", _fmt_score(summary["buffett_score"]))
    c3.metric("Cobertura", _fmt_pct(summary["coverage"]))
    c4.metric("Confianza", _fmt_pct(summary["confidence"]))
    c5.metric(
        "Predictiva",
        _fmt_pct(summary["predictive_confidence"]) if summary["predictive_confidence"] is not None else "Pendiente",
    )

    _render_action_card(summary)

    with st.expander("Ver ruta de análisis recomendada", expanded=True):
        _render_workflow_steps(summary)

    st.caption(f"Modelo: **{summary['model_version']}**")
    if summary["competitor"]:
        st.caption(f"Comparador activo: **{summary['competitor']}**")


def ejecutar_research_core(
    ticker_input: str,
    is_df: Any,
    bs_df: Any,
    cf_df: Any,
    res_is: dict[str, Any],
    res_bs: dict[str, Any],
    res_cf: dict[str, Any],
    res_val: dict[str, Any],
    nota_buffett: float,
    ticker_competidor: str,
    years: int = 5,
    valuequant_score: Any = None,
) -> None:
    """Renderiza el flujo consolidado de análisis de empresa."""

    _render_research_header(ticker_input, ticker_competidor, nota_buffett, valuequant_score)

    tabs = st.tabs(
        [
            "🧭 Tesis",
            "💾 Seguimiento",
            "📄 Informe",
            "📊 Resumen",
            "🔎 Fundamental",
            "🧠 Forense",
            "🔮 Proyección",
            "🧾 Earnings NLP",
            "⚖️ Comparativa",
        ]
    )

    with tabs[0]:
        render_investment_thesis(
            ticker=ticker_input,
            valuequant_score=valuequant_score,
            res_val=res_val,
            nota_buffett=nota_buffett,
            ticker_competidor=ticker_competidor,
        )

    with tabs[1]:
        render_save_to_watchlist_panel(
            ticker=ticker_input,
            competitor=ticker_competidor,
            valuequant_score=valuequant_score,
            res_val=res_val,
            nota_buffett=nota_buffett,
        )

    with tabs[2]:
        render_research_report_export(
            ticker=ticker_input,
            ticker_competidor=ticker_competidor,
            valuequant_score=valuequant_score,
            res_val=res_val,
            nota_buffett=nota_buffett,
            res_is=res_is,
            res_bs=res_bs,
            res_cf=res_cf,
        )

    with tabs[3]:
        safe_call(
            "modulos.resumen",
            "ejecutar_resumen_ejecutivo",
            ticker_input,
            is_df,
            bs_df,
            cf_df,
            res_is,
            res_bs,
            res_cf,
            res_val,
            nota_buffett,
            valuequant_score,
        )

    with tabs[4]:
        safe_call(
            "modulos.fundamental",
            "ejecutar_analisis_fundamental",
            ticker_input,
            is_df,
            bs_df,
            cf_df,
            res_is,
            res_bs,
            res_cf,
            res_val,
            nota_buffett,
            ticker_competidor,
            valuequant_score,
        )

    with tabs[5]:
        safe_call(
            "modulos.forense",
            "ejecutar_auditoria_forense",
            ticker_input,
            is_df,
            bs_df,
            cf_df,
            res_val,
            res_bs,
        )

    with tabs[6]:
        safe_call("modulos.proyeccion", "ejecutar_proyeccion", ticker_input)

    with tabs[7]:
        safe_call("modulos.nlp_analyzer", "render_nlp_dashboard", ticker_input)

    with tabs[8]:
        render_relative_comparison(
            ticker=ticker_input,
            competitor=ticker_competidor,
            valuequant_score=valuequant_score,
            res_val=res_val,
            nota_buffett=nota_buffett,
            years=years,
        )
