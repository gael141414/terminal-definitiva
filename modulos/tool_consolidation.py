"""Mapa de consolidación de herramientas de ValueQuant Terminal.

Agrupación final validada contra el mockup docs/design/research_core_navegacion_kpi.html
(sección 1a): Research Core es la puerta de entrada jerárquicamente superior (no es un
"grupo" con herramientas propias) y las 34 herramientas restantes se reparten en 5 grupos
visibles + 1 grupo de utilidades oculto por defecto (solo visible en modo "Completo").

Nota de conteo: el mockup dice "35 herramientas · 6 grupos" con las tarjetas de grupo
sumando 5+8+4+6+7+5=35. El catálogo real tiene 35 herramientas EN TOTAL, incluyendo
Research Core, que no aparece como tarjeta de grupo — así que las 5 herramientas
visibles + el grupo de utilidades solo pueden repartirse 34 herramientas reales, no 35.
El hueco se resta del grupo "Utilidades & Post-MVP" (4 en vez de 5): Automatización &
Watchlist coincide exacto con el mockup (7) porque absorbe Resumen Ejecutivo y Análisis
Fundamental (mantenidos visibles a propósito, no degradados a utilidad — el paso 2 de
esta misma tarea los prioriza explícitamente para la tarjeta KPI nueva) más Earnings
Call NLP; Utilidades & Post-MVP se queda con las 4 herramientas restantes que ya eran
no-MVP/asistente antes de este cambio (Mapa del Producto, Visor de Gurús, Chatbot
Inversor, Consejos y Mentoría).
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
    is_hub: bool = False
    hidden_unless_complete: bool = False


CONSOLIDATION_GROUPS: dict[str, ConsolidationGroup] = {
    "research_core": ConsolidationGroup(
        key="research_core",
        name="Research Core",
        strategic_area="Research",
        description="Puerta de entrada principal: análisis central de una empresa (score, valoración, calidad, riesgo, veredicto).",
        target_module="modulos.research_core",
        priority=0,
        is_hub=True,
    ),
    "market_terminal": ConsolidationGroup(
        key="market_terminal",
        name="Market Terminal",
        strategic_area="Market",
        description="Técnico, opciones, rotación sectorial, régimen económico y liquidez — contexto de mercado y timing.",
        target_module="modulos.market_terminal",
        priority=1,
    ),
    "discovery_engine": ConsolidationGroup(
        key="discovery_engine",
        name="Discovery Engine",
        strategic_area="Discovery",
        description="Screeners, small caps, multibaggers, insiders, alt data, ETFs y catalizadores — encontrar oportunidades.",
        target_module="modulos.discovery_engine",
        priority=2,
    ),
    "historical_lab": ConsolidationGroup(
        key="historical_lab",
        name="Historical Lab",
        strategic_area="Lab",
        description="Backtesting, máquina del tiempo, stress test de crisis y predictor de techos/suelos — validación histórica.",
        target_module="modulos.historical_lab",
        priority=3,
    ),
    "portfolio_risk": ConsolidationGroup(
        key="portfolio_risk",
        name="Portfolio & Risk",
        strategic_area="Portfolio",
        description="Optimización de cartera, Monte Carlo, robo-advisor, coberturas, auditoría forense y análisis guardados.",
        target_module="modulos.portfolio_risk",
        priority=4,
    ),
    "automation_watchlist": ConsolidationGroup(
        key="automation_watchlist",
        name="Automatización & Watchlist",
        strategic_area="Operations",
        description="Watchlist, briefing de oportunidades, automatización, Telegram y las vistas de empresa de mayor uso diario.",
        target_module="modulos.automation_watchlist",
        priority=5,
    ),
    "utilities_postmvp": ConsolidationGroup(
        key="utilities_postmvp",
        name="Utilidades & Post-MVP",
        strategic_area="Utility",
        description="Herramientas accesorias/experimentales, ocultas por defecto y visibles solo en modo «Completo».",
        target_module=None,
        priority=6,
        hidden_unless_complete=True,
    ),
}


TOOL_CONSOLIDATION: dict[str, dict[str, str | int | bool]] = {
    "🧩 Research Core": {"group": "research_core", "status": "core", "order": 1, "visible_in_mvp": True},

    # Market Terminal (5)
    "📈 Técnico y Opciones": {"group": "market_terminal", "status": "core", "order": 10, "visible_in_mvp": True},
    "⚡ Swing Trading (Estrategias)": {"group": "market_terminal", "status": "core", "order": 5, "visible_in_mvp": True},
    "🧮 Opciones Avanzadas (BSM)": {"group": "market_terminal", "status": "merge", "order": 20, "visible_in_mvp": False},
    "🌍 Radar Macro y Sectores": {"group": "market_terminal", "status": "merge", "order": 30, "visible_in_mvp": True},
    "🕰️ Reloj Económico (Regímenes)": {"group": "market_terminal", "status": "core", "order": 40, "visible_in_mvp": True},
    "🚰 Monitor de Liquidez (FED)": {"group": "market_terminal", "status": "merge", "order": 50, "visible_in_mvp": True},

    # Discovery Engine (8)
    "🌐 Escáner Global (Screener)": {"group": "discovery_engine", "status": "merge", "order": 10, "visible_in_mvp": True},
    "🌐 Screener Avanzado (Multi-Factor)": {"group": "discovery_engine", "status": "core", "order": 20, "visible_in_mvp": True},
    "⛏️ Minero de Small Caps": {"group": "discovery_engine", "status": "merge", "order": 30, "visible_in_mvp": True},
    "🚀 Radar Multibaggers (Small/Mid Caps)": {"group": "discovery_engine", "status": "merge", "order": 40, "visible_in_mvp": True},
    "🕵️‍♂️ Rastreador de Insiders (SEC)": {"group": "discovery_engine", "status": "merge", "order": 50, "visible_in_mvp": True},
    "🕵️ Alt Data & Congreso": {"group": "discovery_engine", "status": "merge", "order": 60, "visible_in_mvp": False},
    "🩻 Radiografía de ETFs (X-Ray)": {"group": "discovery_engine", "status": "merge", "order": 70, "visible_in_mvp": False},
    "🔮 Proyección Cuantitativa y Catalizadores": {"group": "discovery_engine", "status": "merge", "order": 80, "visible_in_mvp": True},

    # Historical Lab (3 — Predictor de Techos/Suelos se renombró y pasó a
    # Utilidades & Post-MVP, ver Fase 7: su texto prometía una probabilidad de
    # reversión que no estaba respaldada por ningún backtest real)
    "⏳ Máquina del Tiempo (Backtest)": {"group": "historical_lab", "status": "merge", "order": 10, "visible_in_mvp": True},
    "🧪 Backtesting Estrategias": {"group": "historical_lab", "status": "core", "order": 20, "visible_in_mvp": True},
    "🦢 Test Cisnes Negros (Crisis)": {"group": "historical_lab", "status": "merge", "order": 30, "visible_in_mvp": False},

    # Portfolio & Risk (6)
    "🚪 Decisión de Venta": {"group": "portfolio_risk", "status": "core", "order": 26, "visible_in_mvp": True},
    "📓 Diario de Decisiones": {"group": "automation_watchlist", "status": "core", "order": 25, "visible_in_mvp": True},
    "📚 Análisis Guardados": {"group": "portfolio_risk", "status": "core", "order": 10, "visible_in_mvp": True},
    "⚖️ Optimizador de Cartera": {"group": "portfolio_risk", "status": "merge", "order": 20, "visible_in_mvp": True},
    "🎲 Monte Carlo Cartera": {"group": "portfolio_risk", "status": "merge", "order": 30, "visible_in_mvp": True},
    "🤖 Robo-Advisor & Test Perfil": {"group": "portfolio_risk", "status": "assistant", "order": 40, "visible_in_mvp": False},
    "🛡️ Radar de Coberturas (Hedging)": {"group": "portfolio_risk", "status": "merge", "order": 50, "visible_in_mvp": False},
    "🧠 Auditoría Forense": {"group": "portfolio_risk", "status": "merge", "order": 60, "visible_in_mvp": True},

    # Automatización & Watchlist (7)
    "📋 Mi Watchlist (Cartera)": {"group": "automation_watchlist", "status": "core", "order": 10, "visible_in_mvp": True},
    "📌 Briefing de Oportunidades": {"group": "automation_watchlist", "status": "core", "order": 15, "visible_in_mvp": True},
    "⚙️ Centro de Automatización": {"group": "automation_watchlist", "status": "core", "order": 20, "visible_in_mvp": True},
    "📲 Automatización Telegram": {"group": "automation_watchlist", "status": "utility", "order": 30, "visible_in_mvp": False},
    "📊 Resumen Ejecutivo": {"group": "automation_watchlist", "status": "merge", "order": 40, "visible_in_mvp": True},
    "🔎 Análisis Fundamental": {"group": "automation_watchlist", "status": "merge", "order": 50, "visible_in_mvp": True},
    "🧠 Earnings Call NLP": {"group": "automation_watchlist", "status": "merge", "order": 60, "visible_in_mvp": True},

    # Utilidades & Post-MVP (5 — el mockup pedía 5 para este grupo; ver nota de
    # conteo original en el docstring del módulo. Chatbot Inversor se promovió
    # de vuelta a "merge" en la Fase 7 — sigue agrupado aquí visualmente, pero
    # ya es visible en modo Consolidado: es el módulo con más sustancia real
    # de los cuatro históricamente "post-MVP" (corpus RAG real + LLM
    # configurado), no tenía sentido mantenerlo tan escondido como los demás.
    "🧭 Mapa del Producto": {"group": "utilities_postmvp", "status": "utility", "order": 10, "visible_in_mvp": False},
    "🎓 Visor de Gurús (Estrategias)": {"group": "utilities_postmvp", "status": "assistant", "order": 20, "visible_in_mvp": False},
    "🤖 Chatbot Inversor": {"group": "utilities_postmvp", "status": "merge", "order": 30, "visible_in_mvp": False},
    "💡 Consejos y Mentoría": {"group": "utilities_postmvp", "status": "assistant", "order": 40, "visible_in_mvp": False},
    "📊 Extremos de Volatilidad (Z-Score)": {"group": "utilities_postmvp", "status": "assistant", "order": 50, "visible_in_mvp": False},
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


def get_navigation_groups_ordered() -> list[ConsolidationGroup]:
    """Grupos de la rejilla de navegación (excluye Research Core, que es jerárquicamente superior)."""

    return [group for group in get_consolidation_groups_ordered() if not group.is_hub]
