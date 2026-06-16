import html
import streamlit as st


def render_kpi_card(label: str, value: str, detail: str = "", status: str = "neutral") -> None:
    """Tarjeta KPI visual para métricas ejecutivas."""
    status_class = {
        "positive": "vq-badge-success",
        "warning": "vq-badge-warning",
        "negative": "",
        "neutral": "",
    }.get(status, "")

    badge_text = {
        "positive": "Favorable",
        "warning": "Vigilancia",
        "negative": "Riesgo",
        "neutral": "Neutral",
    }.get(status, "Neutral")

    st.markdown(
        f"""
        <article class="vq-market-card">
            <div class="vq-market-label">{html.escape(str(label))}</div>
            <div class="vq-market-value">{html.escape(str(value))}</div>
            <div style="display:flex; align-items:center; justify-content:space-between; gap:.75rem; margin-top:.75rem;">
                <span style="color:var(--vq-muted); font-size:.82rem;">{html.escape(str(detail))}</span>
                <span class="vq-badge {status_class}">{html.escape(str(badge_text))}</span>
            </div>
        </article>
        """,
        unsafe_allow_html=True,
    )