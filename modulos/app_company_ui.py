from __future__ import annotations

import html

import streamlit as st

from modulos.app_assets import strip_visual_prefix


def render_company_empty_state(ticker: str, herramienta: dict) -> None:
    """Estado vacío premium para módulos que requieren ejecutar análisis."""
    nombre_herramienta = strip_visual_prefix(herramienta.get("label", "Módulo"))

    # Blindamos el HTML concatenando en una sola línea lógica para evitar bugs de Markdown
    html_state = (
        f"<section class='vq-empty-state' style='padding:1.15rem 1.25rem; margin-top:.85rem;'>"
        f"<div style='display:flex; align-items:flex-start; justify-content:space-between; gap:1rem;'>"
        f"<div>"
        f"<div class='vq-context-eyebrow'>Pendiente de ejecución</div>"
        f"<h3 style='margin:.2rem 0 .45rem; font-size:1.35rem;'>"
        f"Genera el análisis para activar {html.escape(nombre_herramienta)}"
        f"</h3>"
        f"<p style='color:var(--vq-muted); margin:0; line-height:1.6; max-width:900px;'>"
        f"Selecciona la compañía, define el histórico y ejecuta el análisis para cargar ratios, valoración, señales de riesgo y visualizaciones del módulo."
        f"</p>"
        f"</div>"
        f"<span class='vq-badge vq-badge-primary'><i class='bi bi-play-circle'></i> Esperando análisis</span>"
        f"</div>"
        f"<div style='display:flex; gap:.5rem; flex-wrap:wrap; margin-top:1.2rem;'>"
        f"<span class='vq-badge'><i class='bi bi-building'></i> Ticker actual: {html.escape(ticker)}</span>"
        f"<span class='vq-badge'><i class='bi bi-database'></i> Datos financieros</span>"
        f"<span class='vq-badge'><i class='bi bi-graph-up'></i> Visualización institucional</span>"
        f"</div>"
        f"</section>"
    )

    st.markdown(html_state, unsafe_allow_html=True)

