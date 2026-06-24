"""Mapa de consolidación de herramientas de ValueQuant Terminal.

Este módulo define la arquitectura de producto objetivo sin borrar todavía módulos
existentes. Sirve como capa intermedia para pasar de una colección amplia de
herramientas a un producto organizado por capacidades reales.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ToolStatus = Literal["core", "merge", "assistant", "utility", "deprecated"]


@dataclass(frozen=True, slots=True)
class ConsolidationGroup:
    """Grupo funcional al que se asignan herramientas relacionadas."""

    key: str
    name: str
    strategic_area: str
    description: str
    target_module: str | None
    priority: int


CONSOLIDATION_GROUPS: dict[str, ConsolidationGroup] = {
    "product_ops": ConsolidationGroup(
        key="product_ops",
        name="Product Operations",
        strategic_area="Product",
        description="Mapa interno de producto, priorización MVP, arquitectura objetivo y control de consolidación.",
        target_module="modulos.product_dashboard",
        priority=0,
    ),
    "research_core": ConsolidationGroup(
        key="research_core",
        name="Research Core",
        strategic_area="Research",
        description="Análisis central de empresa: resumen, fundamentales, valoración, forense, tesis y NLP.",
        target_module="modulos.research_terminal",
        priority=1,
    ),
    "market_timing": ConsolidationGroup(
        key="market_timing",
        name="Market Timing & Derivatives",
        strategic_area="Market",
        description="Técnico, opciones, derivados, predictor de techos/suelos y contexto macro-timing.",
        target_module="modulos.market_terminal",
        priority=3,
    ),
    "macro_liquidity": ConsolidationGroup(
        key="macro_liquidity",
        name="Macro & Liquidity Monitor",
        strategic_area="Market",
        description="Régimen económico, liquidez, tipos y presión monetaria.",
        target_module="modulos.macro_terminal",
        priority=4,
    ),
    "risk_shield": ConsolidationGroup(
        key="risk_shield",
        name="Risk Shield",
        strategic_area="Risk",
        description="Stress testing, cisnes negros y coberturas de cartera o posición.",
        target_module="modulos.risk_terminal",
        priority=5,
    ),
    "historical_lab": ConsolidationGroup(
        key="historical_lab",
        name="Historical Lab",
        strategic_area="Lab",
        description="Backtesting, máquina del tiempo, validación histórica de estrategias y score.",
        target_module="modulos.historical_lab",
        priority=2,
    ),
    "discovery_engine": ConsolidationGroup(
        key="discovery_engine",
        name="Discovery Engine",
        strategic_area="Discovery",
        description="Screeners, small caps, multibaggers, insiders, alt data y ETF discovery.",
        target_module="modulos.discovery_engine",
        priority=2,
    ),
    "portfolio_decision": ConsolidationGroup(
        key="portfolio_decision",
        name="Portfolio & Decision Center",
        strategic_area="Portfolio",
        description="Watchlist, cartera, optimización, Monte Carlo, alertas y decisión asistida.",
        target_module="modulos.portfolio_center",
        priority=2,
    ),
    "investor_assistant": ConsolidationGroup(
        key="investor_assistant",
        name="Investor Assistant & Academy",
        strategic_area="Assistant",
        description="Chatbot, mentoría, marcos de gurús y perfil inversor educativo.",
        target_module="modulos.investor_assistant",
        priority=6,
    ),
    "automation_utility": ConsolidationGroup(
        key="automation_utility",
        name="Automation Utilities",
        strategic_area="Utility",
        description="Automatizaciones, Telegram y utilidades no nucleares.",
        target_module="modulos.automation_center",
        priority=7,
    ),
}


TOOL_CONSOLIDATION: dict[str, dict[str, str | int | bool]] = {
    "🧭 Mapa del Producto": {"group": "product_ops", "status": "core", "order": 1, "visible_in_mvp": True},

    "📊 Resumen Ejecutivo": {"group": "research_core", "status": "core", "order": 10, "visible_in_mvp": True},
    "🔎 Análisis Fundamental": {"group": "research_core", "status": "core", "order": 20, "visible_in_mvp": True},
    "🧠 Auditoría Forense": {"group": "research_core", "status": "core", "order": 30, "visible_in_mvp": True},
    "🔮 Proyección IA y Catalizadores": {"group": "research_core", "status": "merge", "order": 40, "visible_in_mvp": True},
    "🧠 Earnings Call NLP": {"group": "research_core", "status": "merge", "order": 50, "visible_in_mvp": True},

    "📈 Técnico y Opciones": {"group": "market_timing", "status": "core", "order": 10, "visible_in_mvp": True},
    "🧮 Opciones Avanzadas (BSM)": {"group": "market_timing", "status": "merge", "order": 20, "visible_in_mvp": False},
    "🔭 Predictor de Techos/Suelos": {"group": "market_timing", "status": "merge", "order": 30, "visible_in_mvp": False},
    "🌍 Radar Macro y Sectores": {"group": "market_timing", "status": "merge", "order": 40, "visible_in_mvp": True},

    "🕰️ Reloj Económico (Regímenes)": {"group": "macro_liquidity", "status": "core", "order": 10, "visible_in_mvp": True},
    "🚰 Monitor de Liquidez (FED)": {"group": "macro_liquidity", "status": "merge", "order": 20, "visible_in_mvp": True},

    "🦢 Test Cisnes Negros (Crisis)": {"group": "risk_shield", "status": "merge", "order": 10, "visible_in_mvp": False},
    "🛡️ Radar de Coberturas (Hedging)": {"group": "risk_shield", "status": "merge", "order": 20, "visible_in_mvp": False},

    "⏳ Máquina del Tiempo (Backtest)": {"group": "historical_lab", "status": "merge", "order": 10, "visible_in_mvp": True},
    "🧪 Backtesting Estrategias": {"group": "historical_lab", "status": "core", "order": 20, "visible_in_mvp": True},

    "🌐 Escáner Global (Screener)": {"group": "discovery_engine", "status": "merge", "order": 10, "visible_in_mvp": True},
    "🌐 Screener Avanzado (Multi-Factor)": {"group": "discovery_engine", "status": "core", "order": 20, "visible_in_mvp": True},
    "⛏️ Minero de Small Caps": {"group": "discovery_engine", "status": "merge", "order": 30, "visible_in_mvp": True},
    "🚀 Radar Multibaggers (Small/Mid Caps)": {"group": "discovery_engine", "status": "merge", "order": 40, "visible_in_mvp": True},
    "🕵️‍♂️ Rastreador de Insiders (SEC)": {"group": "discovery_engine", "status": "merge", "order": 50, "visible_in_mvp": True},
    "🕵️ Alt Data & Congreso": {"group": "discovery_engine", "status": "merge", "order": 60, "visible_in_mvp": False},
    "🩻 Radiografía de ETFs (X-Ray)": {"group": "discovery_engine", "status": "merge", "order": 70, "visible_in_mvp": False},

    "📋 Mi Watchlist (Cartera)": {"group": "portfolio_decision", "status": "core", "order": 10, "visible_in_mvp": True},
    "⚖️ Optimizador de Cartera": {"group": "portfolio_decision", "status": "merge", "order": 20, "visible_in_mvp": True},
    "🎲 Monte Carlo Cartera": {"group": "portfolio_decision", "status": "merge", "order": 30, "visible_in_mvp": True},

    "🤖 Chatbot Inversor": {"group": "investor_assistant", "status": "assistant", "order": 10, "visible_in_mvp": False},
    "💡 Consejos y Mentoría": {"group": "investor_assistant", "status": "assistant", "order": 20, "visible_in_mvp": False},
    "🎓 Visor de Gurús (Estrategias)": {"group": "investor_assistant", "status": "assistant", "order": 30, "visible_in_mvp": False},
    "🤖 Robo-Advisor & Test Perfil": {"group": "investor_assistant", "status": "assistant", "order": 40, "visible_in_mvp": False},

    "📲 Automatización Telegram": {"group": "automation_utility", "status": "utility", "order": 10, "visible_in_mvp": False},
}


def get_tool_consolidation(label: str) -> dict[str, str | int | bool]:
    """Devuelve metadatos de consolidación de una herramienta."""

    return TOOL_CONSOLIDATION.get(
        label,
        {"group": "unassigned", "status": "merge", "order": 999, "visible_in_mvp": False},
    )


def get_group_for_tool(label: str) -> ConsolidationGroup | None:
    """Devuelve el grupo funcional de una herramienta."""

    metadata = get_tool_consolidation(label)
    group_key = metadata.get("group")
    if not isinstance(group_key, str):
        return None
    return CONSOLIDATION_GROUPS.get(group_key)


def get_consolidation_groups_ordered() -> list[ConsolidationGroup]:
    """Devuelve los grupos funcionales ordenados por prioridad de producto."""

    return sorted(CONSOLIDATION_GROUPS.values(), key=lambda group: group.priority)
