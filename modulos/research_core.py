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


def _render_research_header(
    ticker_input: str,
    ticker_competidor: str,
    nota_buffett: float,
    valuequant_score: Any,
) -> None:
    """Cabecera sintética del flujo Research Core."""

    final_score = _score_attr(valuequant_score, "final_score")
    coverage = _score_attr(valuequant_score, "data_coverage")
    confidence = _score_attr(valuequant_score, "confidence")
    predictive_confidence = _score_attr(valuequant_score, "predictive_confidence")
    model_version = _score_attr(valuequant_score, "model_version", "N/D")
    verdict, verdict_text = _veredicto(float(final_score) if final_score is not None else None)

    st.markdown(f"## 🧩 Research Core — {ticker_input}")
    st.caption(
        "Vista consolidada de análisis de empresa: score, tesis, fundamentales, valoración, "
        "forense, escenarios, narrativa directiva e informe exportable."
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("ValueQuant Score", _fmt_score(final_score))
    c2.metric("Buffett Quality", _fmt_score(nota_buffett))
    c3.metric("Cobertura datos", _fmt_pct(coverage))
    c4.metric("Confianza operativa", _fmt_pct(confidence))
    c5.metric("Confianza predictiva", _fmt_pct(predictive_confidence) if predictive_confidence is not None else "Pendiente")

    st.info(f"**Veredicto operativo:** {verdict}. {verdict_text}")
    st.caption(f"Modelo: **{model_version}**")
    if ticker_competidor:
        st.caption(f"Comparador activo: **{ticker_competidor}**")


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
