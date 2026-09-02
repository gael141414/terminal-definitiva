"""Consolidación de navegación (Paso 1): grupos, conteos y rutas.

Verifica contra el mockup docs/design/research_core_navegacion_kpi.html
(sección 1a) y la nota de conteo documentada en modulos/tool_consolidation.py:
Research Core no es una de las 6 tarjetas de grupo (es la puerta de entrada
jerárquicamente superior), y las 34 herramientas restantes se reparten en
Market Terminal (5), Discovery Engine (8), Historical Lab (3), Portfolio &
Risk (6), Automatización & Watchlist (7) y Utilidades & Post-MVP (5).

Historical Lab pasó de 4 a 3 y Utilidades & Post-MVP de 4 a 5 en la Fase 7:
"Predictor de Techos/Suelos" se renombró a "Extremos de Volatilidad (Z-Score)"
(su texto original prometía una probabilidad de reversión sin backtest real
detrás) y se trasladó ahí, con el mismo status oculto que sus vecinos.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.tool_catalog import TOOL_CATALOG, obtener_catalogo_por_modo
from modulos.tool_consolidation import (
    CONSOLIDATION_GROUPS,
    TOOL_CONSOLIDATION,
    get_navigation_groups_ordered,
)
from modulos.tool_router import COMPANY_TOOL_ROUTES, INDEPENDENT_TOOL_ROUTES

EXPECTED_GROUP_COUNTS = {
    "market_terminal": 6,  # +1: Swing Trading
    "discovery_engine": 8,
    "historical_lab": 3,  # Predictor de Techos/Suelos se trasladó a utilities_postmvp (Fase 7)
    "portfolio_risk": 6,
    "automation_watchlist": 8,  # +1: Diario de Decisiones
    "utilities_postmvp": 5,  # +1 tras el traslado anterior; mockup original pedía 5 aquí
}


def test_catalogo_tiene_37_herramientas():
    # 35 originales de la consolidación + Swing Trading + Diario de Decisiones.
    assert len(TOOL_CATALOG) == 37


def test_todas_las_herramientas_del_catalogo_tienen_metadatos_de_consolidacion():
    catalog_labels = {str(t["label"]) for t in TOOL_CATALOG}
    assert catalog_labels == set(TOOL_CONSOLIDATION.keys())


def test_research_core_no_es_uno_de_los_grupos_de_navegacion():
    nav_groups = {g.key for g in get_navigation_groups_ordered()}
    assert "research_core" not in nav_groups
    research_core_group = CONSOLIDATION_GROUPS["research_core"]
    assert research_core_group.is_hub is True


def test_conteo_por_grupo_coincide_con_lo_documentado():
    from collections import Counter

    counts = Counter(str(meta["group"]) for meta in TOOL_CONSOLIDATION.values())
    counts.pop("research_core", None)

    assert dict(counts) == EXPECTED_GROUP_COUNTS
    assert sum(EXPECTED_GROUP_COUNTS.values()) == 36  # 34 consolidadas + Swing Trading + Diario
    assert sum(EXPECTED_GROUP_COUNTS.values()) + 1 == len(TOOL_CATALOG)  # +1 = Research Core


def test_utilidades_postmvp_oculto_salvo_modo_completo():
    """Oculto por defecto en Consolidado, con una excepción desde la Fase 7:
    el Chatbot Inversor se promovió a status="merge" (era, de los cuatro
    módulos históricamente post-MVP, el que tenía más sustancia real: corpus
    RAG real + LLM configurado) — sigue agrupado aquí visualmente, pero ya
    es visible en Consolidado, a diferencia de sus vecinos."""
    mvp_labels = {str(t["label"]) for t in obtener_catalogo_por_modo("mvp")}
    consolidated_labels = {str(t["label"]) for t in obtener_catalogo_por_modo("consolidated")}
    complete_labels = {str(t["label"]) for t in obtener_catalogo_por_modo("complete")}

    utilities_labels = {
        label for label, meta in TOOL_CONSOLIDATION.items() if meta["group"] == "utilities_postmvp"
    }
    assert len(utilities_labels) == 5

    promoted_label = "🤖 Chatbot Inversor"
    still_hidden_labels = utilities_labels - {promoted_label}

    assert not (utilities_labels & mvp_labels), "Utilidades & Post-MVP no debe verse en modo MVP"
    assert not (still_hidden_labels & consolidated_labels), "Utilidades & Post-MVP (salvo el Chatbot promovido) no debe verse en modo Consolidado"
    assert promoted_label in consolidated_labels, "El Chatbot Inversor debe verse en modo Consolidado tras su promoción (Fase 7)"
    assert utilities_labels <= complete_labels, "Utilidades & Post-MVP debe verse completo en modo Completo"


def test_las_35_rutas_siguen_siendo_validas():
    """Cada herramienta del catálogo resuelve a una ruta real (independiente o de empresa)."""
    from scripts.print_product_surface_audit import SPECIAL_COMPANY_ROUTES, SPECIAL_INDEPENDENT_ROUTES, resolve_route

    unresolved = []
    for tool in TOOL_CATALOG:
        label = str(tool["label"])
        input_mode = str(tool["input_mode"])
        route = resolve_route(label, input_mode, INDEPENDENT_TOOL_ROUTES, COMPANY_TOOL_ROUTES)
        if route is None:
            unresolved.append(label)

    assert not unresolved, f"Herramientas sin ruta resuelta: {unresolved}"


def test_no_hay_funcionalidad_eliminada_respecto_al_catalogo_original():
    """Ninguna de las 35 etiquetas originales desapareció al reagrupar."""
    original_labels = {
        "🧭 Mapa del Producto", "🧩 Research Core", "📊 Resumen Ejecutivo", "🔎 Análisis Fundamental",
        "🧠 Auditoría Forense", "🔮 Proyección Cuantitativa y Catalizadores", "🎓 Visor de Gurús (Estrategias)",
        "📈 Técnico y Opciones", "🧮 Opciones Avanzadas (BSM)", "🌍 Radar Macro y Sectores",
        "🕰️ Reloj Económico (Regímenes)", "🚰 Monitor de Liquidez (FED)", "📊 Extremos de Volatilidad (Z-Score)",
        "🦢 Test Cisnes Negros (Crisis)", "🛡️ Radar de Coberturas (Hedging)", "⏳ Máquina del Tiempo (Backtest)",
        "🧪 Backtesting Estrategias", "⛏️ Minero de Small Caps", "🚀 Radar Multibaggers (Small/Mid Caps)",
        "🕵️‍♂️ Rastreador de Insiders (SEC)", "🕵️ Alt Data & Congreso", "🩻 Radiografía de ETFs (X-Ray)",
        "🌐 Escáner Global (Screener)", "🌐 Screener Avanzado (Multi-Factor)", "📋 Mi Watchlist (Cartera)",
        "📌 Briefing de Oportunidades", "⚙️ Centro de Automatización", "📚 Análisis Guardados",
        "⚖️ Optimizador de Cartera", "🎲 Monte Carlo Cartera", "🤖 Robo-Advisor & Test Perfil",
        "📲 Automatización Telegram", "🤖 Chatbot Inversor", "🧠 Earnings Call NLP", "💡 Consejos y Mentoría",
    }
    assert len(original_labels) == 35
    catalog_labels = {str(t["label"]) for t in TOOL_CATALOG}

    # Subconjunto, no igualdad: lo que este test protege es que la reagrupación
    # no haga DESAPARECER funcionalidad. Escrito como igualdad exacta prohibía
    # además añadir herramientas nuevas, que es un cambio legítimo y no una
    # regresión.
    faltantes = original_labels - catalog_labels
    assert not faltantes, f"Herramientas desaparecidas del catálogo: {faltantes}"


@pytest.mark.parametrize("module_name", [
    "modulos.market_terminal", "modulos.discovery_engine", "modulos.historical_lab",
    "modulos.portfolio_risk", "modulos.automation_watchlist",
])
def test_modulos_de_grupo_existen_y_exponen_render_group_card(module_name):
    import importlib

    module = importlib.import_module(module_name)
    assert hasattr(module, "GROUP_KEY")
    assert callable(getattr(module, "render_group_card"))
    assert module.GROUP_KEY in CONSOLIDATION_GROUPS
    assert module.GROUP_KEY in EXPECTED_GROUP_COUNTS
