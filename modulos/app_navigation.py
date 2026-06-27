from __future__ import annotations

import html

import streamlit as st

try:
    from streamlit_option_menu import option_menu
except Exception:
    option_menu = None

from modulos.app_assets import strip_visual_prefix


BLOQUE_UI = {
    "📌 Núcleo Empresa": ("Empresa", "bar-chart-line"),
    "📈 Mercado y Timing": ("Mercado", "graph-up-arrow"),
    "🛡️ Riesgo y Defensa": ("Riesgo", "shield-lock"),
    "🔎 Descubrimiento": ("Descubrimiento", "search"),
    "💼 Cartera y Decisión": ("Cartera", "briefcase"),
    "🧠 IA y Mentoría": ("IA", "cpu"),
}


TOOL_UI_ICONS = {
    "📊 Resumen Ejecutivo": "speedometer2",
    "🔎 Análisis Fundamental": "clipboard-data",
    "🧠 Auditoría Forense": "fingerprint",
    "🔮 Proyección IA y Catalizadores": "stars",
    "🎓 Visor de Gurús (Estrategias)": "mortarboard",
    "📈 Técnico y Opciones": "graph-up",
    "🧮 Opciones Avanzadas (BSM)": "calculator",
    "🌍 Radar Macro y Sectores": "globe2",
    "🕰️ Reloj Económico (Regímenes)": "clock-history",
    "🚰 Monitor de Liquidez (FED)": "bank",
    "🔭 Predictor de Techos/Suelos": "bullseye",
    "🦢 Test Cisnes Negros (Crisis)": "exclamation-triangle",
    "🛡️ Radar de Coberturas (Hedging)": "shield-check",
    "⏳ Máquina del Tiempo (Backtest)": "hourglass-split",
    "🧪 Backtesting Estrategias": "bezier2",
    "⛏️ Minero de Small Caps": "gem",
    "🚀 Radar Multibaggers (Small/Mid Caps)": "rocket-takeoff",
    "🕵️‍♂️ Rastreador de Insiders (SEC)": "person-badge",
    "🕵️ Alt Data & Congreso": "building-lock",
    "🩻 Radiografía de ETFs (X-Ray)": "diagram-3",
    "🌐 Escáner Global (Screener)": "filter-square",
    "🌐 Screener Avanzado (Multi-Factor)": "sliders",
    "📋 Mi Watchlist (Cartera)": "list-check",
    "⚖️ Optimizador de Cartera": "diagram-2",
    "🎲 Monte Carlo Cartera": "bounding-box-circles",
    "🤖 Robo-Advisor & Test Perfil": "robot",
    "📲 Automatización Telegram": "send",
    "🤖 Chatbot Inversor": "chat-dots",
    "🧠 Earnings Call NLP": "soundwave",
    "💡 Consejos y Mentoría": "lightbulb",
}


def render_context_header(
    bloque: str,
    herramienta: dict,
    ticker: str | None = None,
    competidor: str | None = None,
    años: int | None = None,
) -> None:
    """Cabecera contextual para que cada módulo parezca una pantalla de research."""
    nombre_bloque = strip_visual_prefix(bloque)
    nombre_herramienta = strip_visual_prefix(herramienta.get("label", "Módulo"))
    descripcion = herramienta.get("descripcion", "")

    badges = [
        "<span class='vq-badge vq-badge-primary'><i class='bi bi-grid'></i> Workspace activo</span>"
    ]

    if herramienta.get("input_mode") == "company" and ticker:
        badges.append(f"<span class='vq-badge'><i class='bi bi-building'></i> {html.escape(ticker)}</span>")

    if competidor:
        badges.append(f"<span class='vq-badge'><i class='bi bi-arrow-left-right'></i> vs {html.escape(competidor)}</span>")

    if años:
        badges.append(f"<span class='vq-badge'><i class='bi bi-calendar3'></i> {años} años</span>")

    if herramienta.get("input_mode") == "standalone":
        badges.append("<span class='vq-badge vq-badge-success'><i class='bi bi-lightning-charge'></i> Módulo autónomo</span>")

    if herramienta.get("input_mode") == "etf":
        badges.append("<span class='vq-badge vq-badge-warning'><i class='bi bi-diagram-3'></i> ETF / Fondo</span>")

    st.markdown(
        f"""
        <section class="vq-context-header">
            <div>
                <div class="vq-context-eyebrow">{html.escape(nombre_bloque)}</div>
                <h1 class="vq-context-title">{html.escape(nombre_herramienta)}</h1>
                <div class="vq-context-subtitle">{html.escape(descripcion)}</div>
            </div>
            <div class="vq-context-badges">
                {''.join(badges)}
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_option_menu_safe(options: list[str], icons: list[str], key: str, default_index: int = 0) -> str:
    """Renderiza streamlit-option-menu y usa radio horizontal como fallback."""
    if option_menu is not None:
        return option_menu(
            menu_title=None,
            options=options,
            icons=icons,
            default_index=default_index,
            orientation="horizontal",
            key=key,
            styles={
                "container": {"padding": "0", "background-color": "transparent", "overflow-x": "auto", "white-space": "nowrap"},
                "icon": {"color": "#96A3B8", "font-size": "14px"},
                "nav-link": {
                    "font-size": "13px",
                    "font-weight": "700",
                    "text-align": "center",
                    "margin": "0 3px",
                    "padding": "8px 12px",
                    "color": "#B7C2D6",
                    "background-color": "#111827",
                    "border": "1px solid rgba(34,48,71,.85)",
                    "border-radius": "7px",
                },
                "nav-link-selected": {"background-color": "#00C0F2", "color": "#051018", "font-weight": "800"},
            },
        )
    return st.radio(key, options, index=default_index, horizontal=True, label_visibility="collapsed")

