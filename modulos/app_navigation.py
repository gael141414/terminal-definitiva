from __future__ import annotations

import html

import streamlit as st

try:
    from streamlit_option_menu import option_menu
except Exception:
    option_menu = None

from modulos.app_assets import strip_visual_prefix
from modulos.html_markdown import escribir_html


BLOQUE_UI = {
    "🧩 Research Core": ("Research Core", "diagram-3"),
    "📊 Market Terminal": ("Market", "graph-up-arrow"),
    "🔎 Discovery Engine": ("Discovery", "search"),
    "⏳ Historical Lab": ("Lab", "hourglass-split"),
    "⚖️ Portfolio & Risk": ("Portfolio", "shield-lock"),
    "🤖 Automatización & Watchlist": ("Watchlist", "list-check"),
    "🧰 Utilidades & Post-MVP": ("Utilidades", "tools"),
}


TOOL_UI_ICONS = {
    "📊 Resumen Ejecutivo": "speedometer2",
    "🔎 Análisis Fundamental": "clipboard-data",
    "🧠 Auditoría Forense": "fingerprint",
    "🔮 Proyección Cuantitativa y Catalizadores": "stars",
    "🎓 Visor de Gurús (Estrategias)": "mortarboard",
    "📈 Técnico y Opciones": "graph-up",
    "🧮 Opciones Avanzadas (BSM)": "calculator",
    "🌍 Radar Macro y Sectores": "globe2",
    "🕰️ Reloj Económico (Regímenes)": "clock-history",
    "🚰 Monitor de Liquidez (FED)": "bank",
    "📊 Extremos de Volatilidad (Z-Score)": "activity",
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

    # Cuando el bloque y la herramienta se llaman igual (p. ej. Research Core),
    # imprimir ambos escribe el mismo texto dos veces, una encima de la otra.
    eyebrow = (
        f'<div class="vq-context-eyebrow">{html.escape(nombre_bloque)}</div>'
        if nombre_bloque.strip().lower() != nombre_herramienta.strip().lower()
        else ""
    )

    escribir_html(f"""
        <section class="vq-context-header">
            <div>
                {eyebrow}
                <h1 class="vq-context-title">{html.escape(nombre_herramienta)}</h1>
                <div class="vq-context-subtitle">{html.escape(descripcion)}</div>
            </div>
            <div class="vq-context-badges">
                {''.join(badges)}
            </div>
        </section>
        """)


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
            # streamlit-option-menu se pinta dentro de un iframe, así que el CSS
            # del tema NO le llega: su aspecto tiene que declararse aquí. El
            # azul seleccionado era el cian #00C0F2 del sistema antiguo, que
            # chocaba con la paleta nueva. "--hover-color" es la única vía que
            # ofrece el componente para un estado de hover.
            styles={
                "container": {
                    "padding": "5px",
                    "background-color": "#101827",
                    "border": "1px solid rgba(147,164,187,.20)",
                    "border-radius": "12px",
                    "overflow-x": "auto",
                    "white-space": "nowrap",
                },
                "icon": {"color": "#93a4bb", "font-size": "14px"},
                "nav-link": {
                    "font-family": "'Space Grotesk', Inter, sans-serif",
                    "font-size": "13.5px",
                    "font-weight": "600",
                    "text-align": "center",
                    "margin": "0 2px",
                    "padding": "9px 18px",
                    "color": "#93a4bb",
                    "background-color": "transparent",
                    "border": "1px solid transparent",
                    "border-radius": "9px",
                    "transition": "background-color .16s ease, color .16s ease",
                    "--hover-color": "rgba(59,130,246,.12)",
                },
                "nav-link-selected": {
                    "background": "linear-gradient(160deg, #3b82f6, #2f6fe0)",
                    "background-color": "#3b82f6",
                    "color": "#ffffff",
                    "font-weight": "700",
                    "box-shadow": "0 2px 10px rgba(59,130,246,.35)",
                },
            },
        )
    return st.radio(key, options, index=default_index, horizontal=True, label_visibility="collapsed")

