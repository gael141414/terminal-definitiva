from __future__ import annotations

import html

import streamlit as st

from modulos.app_assets import strip_visual_prefix
from modulos.app_navigation import TOOL_UI_ICONS
from modulos.tool_catalog import TOOL_CATALOG


def render_module_showcase(limit: int = 9) -> None:
    """Muestra módulos principales en la home como tarjetas de producto."""
    destacados = TOOL_CATALOG[:limit]

    cards = ""
    for tool in destacados:
        label_original = tool["label"]
        label = strip_visual_prefix(label_original)
        icon = TOOL_UI_ICONS.get(label_original, "grid")
        bloque = strip_visual_prefix(tool["bloque"])
        desc = tool["descripcion"]
        input_mode = tool["input_mode"]

        if input_mode == "company":
            mode_label = "Empresa"
        elif input_mode == "standalone":
            mode_label = "Autónomo"
        elif input_mode == "etf":
            mode_label = "ETF / Fondo"
        else:
            mode_label = "Módulo"

        # HTML Compactado sin saltos de línea para evitar el Bug de Streamlit
        cards += f"<article class='vq-module-card'><div class='vq-module-icon'><i class='bi bi-{html.escape(icon)}'></i></div><div class='vq-module-eyebrow'>{html.escape(bloque)} · {html.escape(mode_label)}</div><div class='vq-module-title'>{html.escape(label)}</div><div class='vq-module-desc'>{html.escape(desc)}</div></article>"

    st.markdown(
        "<div class='vq-section-title'><i class='bi bi-grid-1x2'></i> Módulos principales</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div class='vq-module-grid'>{cards}</div>",
        unsafe_allow_html=True,
    )
