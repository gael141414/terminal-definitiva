"""Research Core consolidado de ValueQuant Terminal.

Este módulo integra las vistas nucleares de análisis de empresa en un único flujo:
score, tesis, resumen ejecutivo, análisis fundamental, auditoría forense,
proyección, earnings call NLP e informe exportable.

No sustituye todavía a los módulos originales. Los orquesta mediante lazy loading
para que cualquier fallo quede aislado dentro de la pestaña correspondiente.
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from modulos.analysis_store import render_save_to_watchlist_panel
from modulos.investment_thesis import render_investment_thesis
from modulos.module_loader import safe_call
from modulos.research_report import render_research_report_export
from modulos.relative_comparison import render_relative_comparison
from modulos.scoring_engine import _score_linear
from modulos.ui_components import render_pillar_card


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


def _verdict_color(score: float | None) -> tuple[str, str, str]:
    """Color semántico del veredicto (color, bg, border), reutilizando los
    mismos umbrales que _veredicto() (80/50) consolidados a 3 colores en vez
    de 4 etiquetas de texto — el mockup usa un esquema de 3 colores
    (verde/ámbar/rojo), la app ya tenía 4 etiquetas de texto más matizadas;
    aquí se combinan sin inventar un umbral nuevo."""
    if score is None:
        return "#5b6a80", "rgba(147,164,187,0.1)", "rgba(147,164,187,0.3)"
    if score >= 80:
        return "#3ddc97", "rgba(61,220,151,0.12)", "rgba(61,220,151,0.35)"
    if score >= 50:
        return "#f5b04c", "rgba(245,176,76,0.12)", "rgba(245,176,76,0.35)"
    return "#f36c6c", "rgba(243,108,108,0.12)", "rgba(243,108,108,0.35)"


def _render_tier1_score_and_valuation(summary: dict[str, Any], res_val: dict[str, Any] | None) -> None:
    """Tier 1 del mockup (1c): score global circular + veredicto + valoración
    con barra de margen de seguridad, convención (fair_value - price) / price."""

    final_score = summary.get("final_score")
    color, bg, border = _verdict_color(final_score)
    score_display = f"{final_score:.0f}" if final_score is not None else "—"
    sweep_deg = (final_score / 100 * 360) if final_score is not None else 0.0

    col_score, col_val = st.columns([0.38, 0.62])

    with col_score:
        st.markdown(
            f"""
            <div style="background:rgba(18,25,38,0.92); border:1px solid rgba(147,164,187,0.12); border-radius:14px;
                        padding:26px 28px; display:flex; align-items:center; gap:26px; height:100%;">
                <div style="width:104px; height:104px; border-radius:50%; flex:none;
                            background:conic-gradient({color} 0 {sweep_deg:.0f}deg, rgba(147,164,187,0.12) {sweep_deg:.0f}deg 360deg);
                            display:flex; align-items:center; justify-content:center;">
                    <div style="width:82px; height:82px; border-radius:50%; background:#0d111a; display:flex;
                                flex-direction:column; align-items:center; justify-content:center; gap:1px;">
                        <span style="font-family:'JetBrains Mono',monospace; font-size:26px; font-weight:800;
                                    line-height:1; color:#eef4ff;">{html.escape(score_display)}</span>
                        <span style="font-size:9px; color:#5b6a80; letter-spacing:0.1em;">/ 100</span>
                    </div>
                </div>
                <div style="display:flex; flex-direction:column; gap:8px; min-width:0;">
                    <span style="font-size:10.5px; font-weight:700; letter-spacing:0.14em; color:#5b6a80;
                                text-transform:uppercase;">Score global</span>
                    <span style="font-size:12px; font-weight:800; letter-spacing:0.04em; color:{color}; background:{bg};
                                border:1px solid {border}; padding:5px 12px; border-radius:99px; text-transform:uppercase;
                                align-self:flex-start;">{html.escape(str(summary.get('verdict', 'Pendiente')))}</span>
                    <span style="font-size:11.5px; color:#93a4bb; line-height:1.5;">{html.escape(str(summary.get('verdict_text', '')))}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_val:
        v_justo = None
        precio = None
        if res_val:
            v_justo = res_val.get("dcf_value") or res_val.get("epv_value") or res_val.get("graham_value")
            precio = res_val.get("precio_actual")

        margin = None
        if v_justo and precio:
            # Convención unificada: (fair_value - price) / price. Positivo =
            # infravalorada (precio por debajo del valor razonable estimado).
            margin = (v_justo - precio) / precio

        # Reutiliza el mismo rango [-35%, +35%] que scoring_engine._valuation_component
        # usa para puntuar el margen de seguridad (línea `_score_linear(margin_safety, -0.35, 0.35)`),
        # para que la posición del marcador en la barra sea consistente con cómo el
        # score institucional interpreta ese mismo margen.
        bar_pct = _score_linear(margin, -0.35, 0.35) if margin is not None else 50.0
        margin_color = "#5b6a80" if margin is None else ("#3ddc97" if margin >= 0 else "#f36c6c")
        margin_display = f"{margin * 100:+.1f}%" if margin is not None else "n/d"
        v_justo_display = f"${v_justo:,.0f}" if v_justo else "n/d"
        precio_display = f"${precio:,.2f}" if precio else "n/d"

        st.markdown(
            f"""
            <div style="background:rgba(18,25,38,0.92); border:1px solid rgba(147,164,187,0.12); border-radius:14px;
                        padding:26px 28px; display:flex; flex-direction:column; gap:16px; height:100%;">
                <span style="font-size:10.5px; font-weight:700; letter-spacing:0.14em; color:#5b6a80;
                            text-transform:uppercase;">Valoración · margen de seguridad</span>
                <div style="display:flex; align-items:center; gap:36px; flex-wrap:wrap;">
                    <div style="display:flex; flex-direction:column; gap:2px;">
                        <span style="font-size:11px; color:#5b6a80;">Valor intrínseco</span>
                        <span style="font-family:'JetBrains Mono',monospace; font-size:24px; font-weight:800;
                                    color:#eef4ff;">{v_justo_display}</span>
                    </div>
                    <div style="display:flex; flex-direction:column; gap:2px;">
                        <span style="font-size:11px; color:#5b6a80;">Precio actual</span>
                        <span style="font-family:'JetBrains Mono',monospace; font-size:24px; font-weight:800;
                                    color:#93a4bb;">{precio_display}</span>
                    </div>
                    <div style="display:flex; flex-direction:column; gap:2px;">
                        <span style="font-size:11px; color:#5b6a80;">Margen de seguridad</span>
                        <span style="font-family:'JetBrains Mono',monospace; font-size:24px; font-weight:800;
                                    color:{margin_color};">{html.escape(margin_display)}</span>
                    </div>
                </div>
                <div style="display:flex; flex-direction:column; gap:6px;">
                    <div style="position:relative; height:10px; border-radius:99px;
                                background:linear-gradient(90deg, #f36c6c 0 30%, #f5b04c 30% 50%, rgba(147,164,187,0.25) 50% 70%, #3ddc97 70% 100%);">
                        <div style="position:absolute; left:{bar_pct:.0f}%; top:-4px; width:3px; height:18px; background:#eef4ff;
                                    border-radius:2px; box-shadow:0 0 8px rgba(238,244,255,0.6); transform:translateX(-50%);"></div>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:10.5px; color:#5b6a80;">
                        <span>Sobrevalorada</span><span>Precio justo</span><span>Infravalorada</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_tier2_data_confidence(valuequant_score: Any, summary: dict[str, Any]) -> None:
    """Tier 2 del mockup (1c): franja de "Confianza de datos".

    ALCANCE: el mockup asume un desglose por campo individual ("X de Y
    métricas con dato real", badges de fuente "FMP"/"SEC 10-K" por campo, "N
    campos estimados", "N sin dato"). ValueQuantScore no expone esa
    granularidad hoy — solo agrega ``data_coverage`` (cobertura ponderada de
    los 8 componentes) y ``confidence_label`` a nivel de score completo, y
    cada ScoreComponent trae una única ``confidence`` agregada por bloque, sin
    listar qué campos concretos están estimados/ausentes ni de qué proveedor
    viene cada uno. Mostrar esos números habría significado inventarlos, así
    que esta franja usa solo lo que sí es real: la cobertura ponderada y, si
    aplica, qué bloques tienen confianza reducida (mismo umbral <55% que
    scoring_engine._confidence_diagnostics). Exponer un desglose por campo con
    fuente (FMP/SEC) y estado (real/estimado/ausente) requeriría una tarea
    aparte para instrumentar esa granularidad en la capa de datos primero.
    """
    coverage = summary.get("coverage")
    confidence_label = str(_score_attr(valuequant_score, "confidence_label", "N/D") or "N/D")

    coverage_pct = coverage * 100 if coverage is not None else 0.0
    coverage_caption = (
        f"{coverage_pct:.0f}% de cobertura ponderada sobre los 8 componentes del score."
        if coverage is not None
        else "Cobertura no disponible todavía."
    )

    components = _score_attr(valuequant_score, "components", []) or []
    weak = sorted(
        [c for c in components if getattr(c, "confidence", 1.0) < 0.55],
        key=lambda c: c.confidence,
    )
    if weak:
        weak_text = ", ".join(f"{c.name} ({c.confidence * 100:.0f}%)" for c in weak[:4])
        weak_caption = f"Confianza reducida en: {weak_text}."
        weak_color = "#f5b04c"
    else:
        weak_caption = "Ningún bloque por debajo del umbral mínimo de confianza (55%)."
        weak_color = "#3ddc97"

    level_color = {"Alta": "#37c6e6", "Media": "#f5b04c", "Baja": "#f36c6c"}.get(confidence_label, "#5b6a80")

    st.markdown(
        f"""
        <div style="background:rgba(13,17,26,0.9); border:1px solid rgba(79,140,255,0.18); border-radius:12px;
                    padding:16px 24px; display:flex; align-items:center; gap:24px; flex-wrap:wrap;">
            <span style="font-size:10.5px; font-weight:700; letter-spacing:0.14em; color:#4f8cff; text-transform:uppercase;
                        flex:none;">Confianza de datos</span>
            <div style="flex:1; min-width:220px; display:flex; flex-direction:column; gap:5px;">
                <div style="height:7px; border-radius:99px; background:rgba(147,164,187,0.12); overflow:hidden;">
                    <div style="height:100%; width:{coverage_pct:.0f}%; background:linear-gradient(90deg,#4f8cff,#37c6e6);
                                border-radius:99px;"></div>
                </div>
                <span style="font-size:11px; color:#5b6a80;">{html.escape(coverage_caption)}</span>
            </div>
            <span style="font-size:11px; color:{weak_color}; max-width:420px;">{html.escape(weak_caption)}</span>
            <span style="font-size:11px; font-weight:700; letter-spacing:0.06em; color:{level_color};
                        border:1px solid {level_color}55; padding:4px 12px; border-radius:99px;
                        flex:none;">CONFIANZA {html.escape(confidence_label.upper())}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_tier3_pillars(valuequant_score: Any) -> None:
    """Tier 3 del mockup (1c): rejilla 4x2 con los 8 componentes reales del
    ValueQuant Score (peso, score/100, color semántico).

    ALCANCE: el mockup muestra "N métricas" bajo cada score (p. ej. "88/100 ·
    12 métricas"). ScoreComponent no cuenta métricas individuales:
    ``source_tools`` es una lista de HERRAMIENTAS de origen (típicamente 3 por
    componente), no de métricas subyacentes — usarla como "N métricas"
    habría mostrado "3 métricas" en los 8 pilares, un número fijo y sin
    relación real con la profundidad de cada bloque. En su lugar se muestra
    la confianza propia de cada componente (``component.confidence``), que sí
    es un dato real y distinto por pilar.
    """
    components = _score_attr(valuequant_score, "components", None)
    if not components:
        st.info("No hay componentes del ValueQuant Score disponibles todavía para desglosar en pilares.")
        return

    st.markdown("#### Componentes del ValueQuant Score")
    for row_start in range(0, len(components), 4):
        row = components[row_start:row_start + 4]
        cols = st.columns(4)
        for col, component in zip(cols, row):
            with col:
                score_value = float(component.score) if component.score is not None else None
                render_pillar_card(
                    component.name,
                    float(component.weight) * 100,
                    score_value,
                    detail=f"confianza {component.confidence * 100:.0f}%",
                )


def _render_tier4_thesis(valuequant_score: Any) -> None:
    """Tier 4 del mockup (1c): fortalezas y riesgos de la tesis lado a lado.

    Usa valuequant_score.positives/.negatives directamente — ya son listas
    reales calculadas por scoring_engine.calcular_valuequant_score, no texto
    inventado para esta pantalla.
    """
    positives = _score_attr(valuequant_score, "positives", []) or []
    negatives = _score_attr(valuequant_score, "negatives", []) or []

    col_pos, col_neg = st.columns(2)
    with col_pos:
        items = "".join(f"<span>{html.escape(str(p))}</span>" for p in positives[:6])
        if not items:
            items = "<span style='color:#5b6a80;'>Sin fortalezas destacadas todavía.</span>"
        st.markdown(
            f"""
            <div style="background:rgba(18,25,38,0.92); border:1px solid rgba(147,164,187,0.1); border-radius:12px;
                        padding:20px 24px; display:flex; flex-direction:column; gap:12px; height:100%;">
                <span style="font-size:10.5px; font-weight:700; letter-spacing:0.14em; color:#3ddc97;
                            text-transform:uppercase;">Fortalezas de la tesis</span>
                <div style="display:flex; flex-direction:column; gap:9px; font-size:13px; color:#93a4bb;
                            line-height:1.5;">{items}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_neg:
        items = "".join(f"<span>{html.escape(str(n))}</span>" for n in negatives[:6])
        if not items:
            items = "<span style='color:#5b6a80;'>Sin riesgos destacados todavía.</span>"
        st.markdown(
            f"""
            <div style="background:rgba(18,25,38,0.92); border:1px solid rgba(147,164,187,0.1); border-radius:12px;
                        padding:20px 24px; display:flex; flex-direction:column; gap:12px; height:100%;">
                <span style="font-size:10.5px; font-weight:700; letter-spacing:0.14em; color:#f36c6c;
                            text-transform:uppercase;">Riesgos vigilados</span>
                <div style="display:flex; flex-direction:column; gap:9px; font-size:13px; color:#93a4bb;
                            line-height:1.5;">{items}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_research_header(
    ticker_input: str,
    ticker_competidor: str,
    nota_buffett: float,
    valuequant_score: Any,
    res_val: dict[str, Any] | None = None,
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

    # Resumen ejecutivo en 4 niveles (mockup docs/design/research_core_navegacion_kpi.html, 1c):
    # (1) score + veredicto y valoración al mismo nivel visual, (2) franja de
    # confianza de datos, (3) pilares con color semántico, (4) tesis cualitativa.
    _render_tier1_score_and_valuation(summary, res_val)
    _render_tier2_data_confidence(valuequant_score, summary)
    _render_tier3_pillars(valuequant_score)
    _render_tier4_thesis(valuequant_score)

    predictive = summary.get("predictive_confidence")
    predictive_text = _fmt_pct(predictive) if predictive is not None else "pendiente"
    st.caption(
        f"Buffett Quality Score (histórico, solo calidad fundamental): {_fmt_score(summary['buffett_score'])} · "
        f"Confianza predictiva (backtesting): {predictive_text}."
    )

    st.divider()
    _render_action_card(summary)

    with st.expander("Ver ruta de análisis recomendada", expanded=False):
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

    _render_research_header(ticker_input, ticker_competidor, nota_buffett, valuequant_score, res_val)

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
