"""Catálogo central de herramientas de ValueQuant Terminal."""

from __future__ import annotations

from modulos.tool_consolidation import (
    CONSOLIDATION_GROUPS,
    get_tool_consolidation,
)


_RAW_TOOL_CATALOG = [
    {"label": "🧭 Mapa del Producto", "bloque": "🧭 Producto", "input_mode": "standalone", "descripcion": "Panel interno de arquitectura, MVP, consolidación y priorización del terminal.", "strategic_group": "utility"},
    {"label": "🧩 Research Core", "bloque": "📌 Núcleo Empresa", "input_mode": "company", "descripcion": "Flujo integrado de tesis, resumen, fundamentales, forense, proyección y earnings NLP.", "strategic_group": "research"},
    {"label": "📊 Resumen Ejecutivo", "bloque": "📌 Núcleo Empresa", "input_mode": "company", "descripcion": "Vista de mando con precio, score, riesgos y gráfico institucional.", "strategic_group": "research"},
    {"label": "🔎 Análisis Fundamental", "bloque": "📌 Núcleo Empresa", "input_mode": "company", "descripcion": "Estados financieros, ratios, valoración y comparador.", "strategic_group": "research"},
    {"label": "🧠 Auditoría Forense", "bloque": "📌 Núcleo Empresa", "input_mode": "company", "descripcion": "Banderas rojas contables y calidad de beneficios.", "strategic_group": "research"},
    {"label": "🔮 Proyección IA y Catalizadores", "bloque": "📌 Núcleo Empresa", "input_mode": "company", "descripcion": "Escenarios futuros, catalizadores y narrativa de crecimiento.", "strategic_group": "research"},
    {"label": "🎓 Visor de Gurús (Estrategias)", "bloque": "📌 Núcleo Empresa", "input_mode": "company", "descripcion": "Lectura de la empresa con marcos de inversión value.", "strategic_group": "assistant"},
    {"label": "📈 Técnico y Opciones", "bloque": "📈 Mercado y Timing", "input_mode": "company", "descripcion": "Tendencia, volumen, opciones y contexto técnico.", "strategic_group": "market"},
    {"label": "🧮 Opciones Avanzadas (BSM)", "bloque": "📈 Mercado y Timing", "input_mode": "company", "descripcion": "Black-Scholes, griegas y volatility smile.", "strategic_group": "market"},
    {"label": "🌍 Radar Macro y Sectores", "bloque": "📈 Mercado y Timing", "input_mode": "company", "descripcion": "Rotación sectorial y comparación con el mercado.", "strategic_group": "market"},
    {"label": "🕰️ Reloj Económico (Regímenes)", "bloque": "📈 Mercado y Timing", "input_mode": "standalone", "descripcion": "Lectura del ciclo económico por regímenes.", "strategic_group": "market"},
    {"label": "🚰 Monitor de Liquidez (FED)", "bloque": "📈 Mercado y Timing", "input_mode": "standalone", "descripcion": "Condiciones de liquidez, tipos y presión monetaria.", "strategic_group": "market"},
    {"label": "🔭 Predictor de Techos/Suelos", "bloque": "📈 Mercado y Timing", "input_mode": "company", "descripcion": "Indicadores cuantitativos de exceso o agotamiento.", "strategic_group": "market"},
    {"label": "🦢 Test Cisnes Negros (Crisis)", "bloque": "🛡️ Riesgo y Defensa", "input_mode": "company", "descripcion": "Stress test ante escenarios extremos.", "strategic_group": "risk"},
    {"label": "🛡️ Radar de Coberturas (Hedging)", "bloque": "🛡️ Riesgo y Defensa", "input_mode": "company", "descripcion": "Ideas de cobertura y protección de posiciones.", "strategic_group": "risk"},
    {"label": "⏳ Máquina del Tiempo (Backtest)", "bloque": "🛡️ Riesgo y Defensa", "input_mode": "company", "descripcion": "Simulación histórica para evaluar robustez.", "strategic_group": "lab"},
    {"label": "🧪 Backtesting Estrategias", "bloque": "🛡️ Riesgo y Defensa", "input_mode": "company", "descripcion": "Prueba estrategias históricas contra buy and hold.", "strategic_group": "lab"},
    {"label": "⛏️ Minero de Small Caps", "bloque": "🔎 Descubrimiento", "input_mode": "standalone", "descripcion": "Explorador de small caps con señales de calidad.", "strategic_group": "discovery"},
    {"label": "🚀 Radar Multibaggers (Small/Mid Caps)", "bloque": "🔎 Descubrimiento", "input_mode": "company", "descripcion": "Diagnóstico de potencial multibagger.", "strategic_group": "discovery"},
    {"label": "🕵️‍♂️ Rastreador de Insiders (SEC)", "bloque": "🔎 Descubrimiento", "input_mode": "company", "descripcion": "Compras y ventas de directivos.", "strategic_group": "discovery"},
    {"label": "🕵️ Alt Data & Congreso", "bloque": "🔎 Descubrimiento", "input_mode": "company", "descripcion": "Operaciones políticas y sentimiento mediático.", "strategic_group": "discovery"},
    {"label": "🩻 Radiografía de ETFs (X-Ray)", "bloque": "🔎 Descubrimiento", "input_mode": "etf", "descripcion": "Análisis de fondos y ETFs.", "strategic_group": "discovery"},
    {"label": "🌐 Escáner Global (Screener)", "bloque": "🔎 Descubrimiento", "input_mode": "standalone", "descripcion": "Filtro global por criterios cuantitativos.", "strategic_group": "discovery"},
    {"label": "🌐 Screener Avanzado (Multi-Factor)", "bloque": "🔎 Descubrimiento", "input_mode": "standalone", "descripcion": "Buscador con filtros dinámicos y ranking multifactor.", "strategic_group": "discovery"},
    {"label": "📋 Mi Watchlist (Cartera)", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Seguimiento de cartera y prioridades de análisis.", "strategic_group": "portfolio"},
    {"label": "📌 Briefing de Oportunidades", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Vista ejecutiva de oportunidades: revisar hoy, vigilar caída, recalcular y descartar.", "strategic_group": "portfolio"},
    {"label": "⚙️ Centro de Automatización", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Panel de control para payloads, estado de configuración y envío manual confirmado.", "strategic_group": "utility"},
    {"label": "📚 Análisis Guardados", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Histórico de snapshots guardados desde Research Core.", "strategic_group": "portfolio"},
    {"label": "⚖️ Optimizador de Cartera", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Correlación, frontera eficiente y asignación óptima.", "strategic_group": "portfolio"},
    {"label": "🎲 Monte Carlo Cartera", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Proyección de cartera con percentiles y VaR.", "strategic_group": "portfolio"},
    {"label": "🤖 Robo-Advisor & Test Perfil", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Perfil inversor y asignación orientativa.", "strategic_group": "assistant"},
    {"label": "📲 Automatización Telegram", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Briefing diario y automatización operativa.", "strategic_group": "utility"},
    {"label": "🤖 Chatbot Inversor", "bloque": "🧠 IA y Mentoría", "input_mode": "standalone", "descripcion": "Asistente sobre conocimiento value y documentos locales.", "strategic_group": "assistant"},
    {"label": "🧠 Earnings Call NLP", "bloque": "🧠 IA y Mentoría", "input_mode": "company", "descripcion": "Transcripciones, tono directivo y guidance.", "strategic_group": "research"},
    {"label": "💡 Consejos y Mentoría", "bloque": "🧠 IA y Mentoría", "input_mode": "standalone", "descripcion": "Aprendizaje guiado y criterios de inversión.", "strategic_group": "assistant"},
]


NAVIGATION_MODES = {
    "mvp": {
        "key": "mvp",
        "label": "MVP",
        "caption": "Solo herramientas nucleares para research, discovery, cartera y validación.",
        "badge": "Producto",
    },
    "consolidated": {
        "key": "consolidated",
        "label": "Consolidado",
        "caption": "Herramientas agrupadas por arquitectura objetivo; oculta utilidades accesorias.",
        "badge": "Arquitectura",
    },
    "complete": {
        "key": "complete",
        "label": "Completo",
        "caption": "Todas las herramientas actuales, incluidas utilidades experimentales y post-MVP.",
        "badge": "Full terminal",
    },
}

_NAVIGATION_MODE_ORDER = ("mvp", "consolidated", "complete")


def _enrich_tool(tool: dict[str, object]) -> dict[str, object]:
    """Añade metadatos de consolidación a una herramienta del catálogo."""

    enriched = dict(tool)
    metadata = get_tool_consolidation(str(tool["label"]))
    group_key = str(metadata.get("group", "unassigned"))
    group = CONSOLIDATION_GROUPS.get(group_key)

    enriched.update(
        {
            "consolidation_group": group_key,
            "consolidation_name": group.name if group else "Sin asignar",
            "consolidation_status": metadata.get("status", "merge"),
            "consolidation_order": metadata.get("order", 999),
            "visible_in_mvp": bool(metadata.get("visible_in_mvp", False)),
        }
    )
    return enriched


TOOL_CATALOG = [_enrich_tool(tool) for tool in _RAW_TOOL_CATALOG]

BLOQUES_HERRAMIENTAS = tuple(dict.fromkeys(h["bloque"] for h in TOOL_CATALOG))
HERRAMIENTAS_POR_LABEL = {h["label"]: h for h in TOOL_CATALOG}


def _sort_tools_for_product(tools: list[dict[str, object]]) -> list[dict[str, object]]:
    """Ordena herramientas por grupo consolidado y prioridad interna."""

    def sort_key(tool: dict[str, object]) -> tuple[int, int, str]:
        group_key = str(tool.get("consolidation_group", "unassigned"))
        group = CONSOLIDATION_GROUPS.get(group_key)
        group_priority = group.priority if group else 999
        tool_order = int(tool.get("consolidation_order", 999))
        return group_priority, tool_order, str(tool.get("label", ""))

    return sorted(tools, key=sort_key)


def obtener_modos_navegacion() -> list[dict[str, str]]:
    """Devuelve los modos de navegación disponibles en orden de producto."""

    return [dict(NAVIGATION_MODES[key]) for key in _NAVIGATION_MODE_ORDER]


def _tool_visible_in_mode(tool: dict[str, object], mode: str) -> bool:
    """Decide si una herramienta aparece en un modo de navegación."""

    if mode == "complete":
        return True
    if mode == "mvp":
        return bool(tool.get("visible_in_mvp"))
    if mode == "consolidated":
        return str(tool.get("consolidation_status")) in {"core", "merge"}
    return True


def obtener_catalogo_por_modo(mode: str) -> list[dict[str, object]]:
    """Devuelve el catálogo filtrado por modo de navegación."""

    return _sort_tools_for_product([tool for tool in TOOL_CATALOG if _tool_visible_in_mode(tool, mode)])


def obtener_bloques_por_modo(mode: str) -> tuple[str, ...]:
    """Devuelve los bloques visibles para el modo seleccionado."""

    tools = obtener_catalogo_por_modo(mode)
    return tuple(dict.fromkeys(str(tool["bloque"]) for tool in tools))


def obtener_herramientas_por_bloque(bloque: str):
    return [h for h in TOOL_CATALOG if h["bloque"] == bloque]


def obtener_herramientas_por_bloque_y_modo(bloque: str, mode: str):
    """Devuelve herramientas de un bloque filtradas por modo de navegación."""

    tools = [
        h for h in TOOL_CATALOG
        if h["bloque"] == bloque and _tool_visible_in_mode(h, mode)
    ]
    return _sort_tools_for_product(tools)


def obtener_herramientas_por_grupo_estrategico(grupo: str):
    return [h for h in TOOL_CATALOG if h.get("strategic_group") == grupo]


def obtener_herramientas_por_grupo_consolidado(grupo: str):
    return [h for h in TOOL_CATALOG if h.get("consolidation_group") == grupo]


def obtener_catalogo_mvp():
    """Devuelve solo herramientas candidatas a MVP comercial."""

    return _sort_tools_for_product([h for h in TOOL_CATALOG if h.get("visible_in_mvp")])
