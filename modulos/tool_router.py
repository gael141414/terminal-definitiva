"""Router central de herramientas de ValueQuant Terminal.

Este módulo concentra el enrutado entre etiquetas de navegación y funciones reales.
El objetivo es adelgazar app.py y poder fusionar/renombrar herramientas sin tocar
la lógica principal de la aplicación.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import streamlit as st

from modulos.module_loader import safe_call


@dataclass(slots=True)
class CompanyToolContext:
    """Contexto ya calculado para herramientas dependientes de empresa."""

    ticker: str
    competitor: str
    years: int
    is_df: Any
    bs_df: Any
    cf_df: Any
    metrics_df: Any
    res_is: dict[str, Any]
    res_bs: dict[str, Any]
    res_cf: dict[str, Any]
    res_val: dict[str, Any]
    nota_buffett: float
    valuequant_score: Any
    sector_rotation_fn: Callable[[], Any] | None = None


INDEPENDENT_TOOL_ROUTES: dict[str, tuple[str, str]] = {
    "🧭 Mapa del Producto": ("modulos.product_dashboard", "render_product_dashboard"),
    "🕰️ Reloj Económico (Regímenes)": ("modulos.reloj_macro", "ejecutar_reloj_macro"),
    "📋 Mi Watchlist (Cartera)": ("modulos.watchlist", "ejecutar_watchlist"),
    "⚖️ Optimizador de Cartera": ("modulos.portfolio", "render_portfolio_manager"),
    "🎲 Monte Carlo Cartera": ("modulos.montecarlo", "render_montecarlo"),
    "🤖 Robo-Advisor & Test Perfil": ("modulos.roboadvisor", "ejecutar_roboadvisor"),
    "📲 Automatización Telegram": ("modulos.automatizacion", "ejecutar_panel_automatizacion"),
    "🌐 Escáner Global (Screener)": ("modulos.screener", "ejecutar_escaner_global"),
    "🌐 Screener Avanzado (Multi-Factor)": ("modulos.screener_avanzado", "render_screener_avanzado"),
    "🚰 Monitor de Liquidez (FED)": ("modulos.liquidez", "ejecutar_monitor_liquidez"),
    "🤖 Chatbot Inversor": ("modulos.chatbot", "render_chatbot"),
    "💡 Consejos y Mentoría": ("modulos.consejos", "ejecutar_apartado_consejos"),
    "⛏️ Minero de Small Caps": ("modulos.minero_smallcaps", "ejecutar_visor_smallcaps"),
}


COMPANY_TOOL_ROUTES: dict[str, tuple[str, str]] = {
    "📈 Técnico y Opciones": ("modulos.tecnico", "ejecutar_tecnico_y_opciones"),
    "🧮 Opciones Avanzadas (BSM)": ("modulos.derivados", "render_derivados"),
    "🧠 Auditoría Forense": ("modulos.forense", "ejecutar_auditoria_forense"),
    "🔭 Predictor de Techos/Suelos": ("modulos.predictor", "ejecutar_predictor_techos_suelos"),
    "🔮 Proyección IA y Catalizadores": ("modulos.proyeccion", "ejecutar_proyeccion"),
    "⏳ Máquina del Tiempo (Backtest)": ("modulos.backtest", "ejecutar_maquina_del_tiempo"),
    "🧪 Backtesting Estrategias": ("modulos.backtester", "render_backtesting_engine"),
    "🧠 Earnings Call NLP": ("modulos.nlp_analyzer", "render_nlp_dashboard"),
    "🚀 Radar Multibaggers (Small/Mid Caps)": ("modulos.radar", "ejecutar_radar_multibagger"),
    "🕵️‍♂️ Rastreador de Insiders (SEC)": ("modulos.insiders", "ejecutar_rastreador_insiders"),
    "🕵️ Alt Data & Congreso": ("modulos.alt_data", "render_alt_data"),
    "🦢 Test Cisnes Negros (Crisis)": ("modulos.cisnes_negros", "ejecutar_simulador_crisis"),
    "🛡️ Radar de Coberturas (Hedging)": ("modulos.coberturas", "ejecutar_radar_coberturas"),
}


def render_independent_tool(seccion_actual: str, *, etf_input: str = "SPY") -> Any:
    """Renderiza herramientas que no requieren estados financieros previos."""

    if seccion_actual == "🩻 Radiografía de ETFs (X-Ray)":
        return safe_call("modulos.etf", "ejecutar_radiografia_etf", etf_input)

    route = INDEPENDENT_TOOL_ROUTES.get(seccion_actual)
    if route is None:
        st.info("Esta herramienta independiente todavía no tiene ruta registrada en el router.")
        return None

    module_path, callable_name = route
    return safe_call(module_path, callable_name)


def render_company_tool(seccion_actual: str, context: CompanyToolContext) -> Any:
    """Renderiza herramientas que requieren datos financieros de una empresa."""

    if seccion_actual == "🧩 Research Core":
        return safe_call(
            "modulos.research_core",
            "ejecutar_research_core",
            context.ticker,
            context.is_df,
            context.bs_df,
            context.cf_df,
            context.res_is,
            context.res_bs,
            context.res_cf,
            context.res_val,
            context.nota_buffett,
            context.competitor,
            context.valuequant_score,
        )

    if seccion_actual == "📊 Resumen Ejecutivo":
        return safe_call(
            "modulos.resumen",
            "ejecutar_resumen_ejecutivo",
            context.ticker,
            context.is_df,
            context.bs_df,
            context.cf_df,
            context.res_is,
            context.res_bs,
            context.res_cf,
            context.res_val,
            context.nota_buffett,
            context.valuequant_score,
        )

    if seccion_actual == "🔎 Análisis Fundamental":
        return safe_call(
            "modulos.fundamental",
            "ejecutar_analisis_fundamental",
            context.ticker,
            context.is_df,
            context.bs_df,
            context.cf_df,
            context.res_is,
            context.res_bs,
            context.res_cf,
            context.res_val,
            context.nota_buffett,
            context.competitor,
            context.valuequant_score,
        )

    if seccion_actual == "🌍 Radar Macro y Sectores":
        df_sectores = context.sector_rotation_fn() if context.sector_rotation_fn else None
        return safe_call(
            "modulos.macro",
            "ejecutar_radar_macro",
            context.ticker,
            context.competitor,
            df_sectores,
        )

    if seccion_actual == "🧠 Auditoría Forense":
        return safe_call(
            "modulos.forense",
            "ejecutar_auditoria_forense",
            context.ticker,
            context.is_df,
            context.bs_df,
            context.cf_df,
            context.res_val,
            context.res_bs,
        )

    if seccion_actual == "🎓 Visor de Gurús (Estrategias)":
        return safe_call(
            "modulos.gurus",
            "ejecutar_visor_gurus",
            context.ticker,
            context.res_is,
            context.res_bs,
            context.res_cf,
            context.res_val,
        )

    route = COMPANY_TOOL_ROUTES.get(seccion_actual)
    if route is None:
        st.info("Esta herramienta de empresa todavía no tiene ruta registrada en el router.")
        return None

    module_path, callable_name = route
    return safe_call(module_path, callable_name, context.ticker)
