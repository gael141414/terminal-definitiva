"""Research Core consolidado de ValueQuant Terminal.

Este módulo integra las vistas nucleares de análisis de empresa en un único flujo:
score, tesis, resumen ejecutivo, análisis fundamental, auditoría forense,
proyección y earnings call NLP.

No sustituye todavía a los módulos originales. Los orquesta mediante lazy loading
para que cualquier fallo quede aislado dentro de la pestaña correspondiente.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from modulos.module_loader import safe_call


def _score_attr(valuequant_score: Any, attr: str, default: Any = None) -> Any:
    """Lee atributos del ValueQuantScore sin acoplarse a su implementación."""

    if valuequant_score is None:
        return default
    return getattr(valuequant_score, attr, default)


def _component_score(valuequant_score: Any, component_name: str) -> float | None:
    """Busca la puntuación de un componente por nombre parcial."""

    components = _score_attr(valuequant_score, "components", []) or []
    component_name = component_name.lower()
    for component in components:
        name = str(getattr(component, "name", "")).lower()
        if component_name in name:
            try:
                return float(getattr(component, "score"))
            except Exception:
                return None
    return None


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
    verdict, verdict_text = _veredicto(float(final_score) if final_score is not None else None)

    st.markdown(f"## 🧩 Research Core — {ticker_input}")
    st.caption(
        "Vista consolidada de análisis de empresa: score, tesis, fundamentales, valoración, "
        "forense, escenarios y narrativa directiva."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ValueQuant Score", _fmt_score(final_score))
    c2.metric("Buffett Quality", _fmt_score(nota_buffett))
    c3.metric("Cobertura datos", _fmt_pct(coverage))
    c4.metric("Confianza operativa", _fmt_pct(confidence))

    st.info(f"**Veredicto operativo:** {verdict}. {verdict_text}")
    if ticker_competidor:
        st.caption(f"Comparador activo: **{ticker_competidor}**")


def _render_investment_thesis(valuequant_score: Any, res_val: dict[str, Any]) -> None:
    """Panel de tesis inicial basado en el score y valoración disponible."""

    final_score = _score_attr(valuequant_score, "final_score")
    quality = _component_score(valuequant_score, "calidad")
    valuation = _component_score(valuequant_score, "valoración")
    risk = _component_score(valuequant_score, "riesgo")
    growth = _component_score(valuequant_score, "crecimiento")

    verdict, _ = _veredicto(float(final_score) if final_score is not None else None)

    st.markdown("### Tesis preliminar")
    st.caption("Esta tesis es un resumen cuantitativo inicial. No sustituye el análisis manual ni constituye recomendación financiera.")

    col_left, col_right = st.columns([1.1, 1])

    with col_left:
        st.markdown("#### Lectura ejecutiva")
        st.write(f"**Estado actual:** {verdict}")

        bullets: list[str] = []
        if quality is not None:
            bullets.append(
                "Calidad fundamental fuerte." if quality >= 75 else
                "Calidad fundamental aceptable, pero no excepcional." if quality >= 55 else
                "Calidad fundamental débil o incompleta."
            )
        if valuation is not None:
            bullets.append(
                "Valoración atractiva o razonable." if valuation >= 65 else
                "Valoración exigente; requiere más margen de seguridad." if valuation >= 35 else
                "Valoración muy penalizada por el modelo."
            )
        if risk is not None:
            bullets.append(
                "Riesgo financiero/forense controlado." if risk >= 70 else
                "Riesgo medio: revisar balance, deuda y calidad contable." if risk >= 45 else
                "Riesgo elevado: revisar banderas rojas antes de avanzar."
            )
        if growth is not None:
            bullets.append(
                "Crecimiento/catalizadores apoyan la tesis." if growth >= 65 else
                "Crecimiento o catalizadores todavía poco convincentes."
            )

        if not bullets:
            st.warning("No hay componentes suficientes para construir una tesis automática.")
        else:
            for bullet in bullets:
                st.write(f"- {bullet}")

    with col_right:
        st.markdown("#### Valoración disponible")
        precio_actual = res_val.get("precio_actual") if isinstance(res_val, dict) else None
        valor_intrinseco = (
            res_val.get("valor_intrinseco")
            or res_val.get("valor_intrinseco_dcf")
            or res_val.get("precio_objetivo")
        ) if isinstance(res_val, dict) else None

        st.metric("Precio actual", f"${float(precio_actual):,.2f}" if precio_actual else "N/D")
        st.metric("Valor / objetivo", f"${float(valor_intrinseco):,.2f}" if valor_intrinseco else "N/D")

        if precio_actual and valor_intrinseco:
            try:
                margen = (float(valor_intrinseco) / float(precio_actual)) - 1
                st.metric("Margen estimado", f"{margen * 100:+.1f}%")
            except Exception:
                st.metric("Margen estimado", "N/D")

    st.markdown("---")
    st.markdown("#### Checklist antes de decidir")
    st.write("- Confirmar que los datos financieros son completos y recientes.")
    st.write("- Validar si la valoración incorpora supuestos realistas de crecimiento y márgenes.")
    st.write("- Revisar deuda, recompras, dilución y generación de caja.")
    st.write("- Comparar contra competidor y sector antes de priorizar compra/vigilancia.")


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
    valuequant_score: Any = None,
) -> None:
    """Renderiza el flujo consolidado de análisis de empresa."""

    _render_research_header(ticker_input, ticker_competidor, nota_buffett, valuequant_score)

    tabs = st.tabs(
        [
            "🧭 Tesis",
            "📊 Resumen",
            "🔎 Fundamental",
            "🧠 Forense",
            "🔮 Proyección",
            "🧾 Earnings NLP",
        ]
    )

    with tabs[0]:
        _render_investment_thesis(valuequant_score, res_val)

    with tabs[1]:
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

    with tabs[2]:
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

    with tabs[3]:
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

    with tabs[4]:
        safe_call("modulos.proyeccion", "ejecutar_proyeccion", ticker_input)

    with tabs[5]:
        safe_call("modulos.nlp_analyzer", "render_nlp_dashboard", ticker_input)
