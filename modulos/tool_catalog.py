"""Catálogo central de herramientas de ValueQuant Terminal."""

from __future__ import annotations

TOOL_CATALOG = [
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
    {"label": "⚖️ Optimizador de Cartera", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Correlación, frontera eficiente y asignación óptima.", "strategic_group": "portfolio"},
    {"label": "🎲 Monte Carlo Cartera", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Proyección de cartera con percentiles y VaR.", "strategic_group": "portfolio"},
    {"label": "🤖 Robo-Advisor & Test Perfil", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Perfil inversor y asignación orientativa.", "strategic_group": "assistant"},
    {"label": "📲 Automatización Telegram", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Briefing diario y automatización operativa.", "strategic_group": "utility"},
    {"label": "🤖 Chatbot Inversor", "bloque": "🧠 IA y Mentoría", "input_mode": "standalone", "descripcion": "Asistente sobre conocimiento value y documentos locales.", "strategic_group": "assistant"},
    {"label": "🧠 Earnings Call NLP", "bloque": "🧠 IA y Mentoría", "input_mode": "company", "descripcion": "Transcripciones, tono directivo y guidance.", "strategic_group": "research"},
    {"label": "💡 Consejos y Mentoría", "bloque": "🧠 IA y Mentoría", "input_mode": "standalone", "descripcion": "Aprendizaje guiado y criterios de inversión.", "strategic_group": "assistant"},
]

BLOQUES_HERRAMIENTAS = tuple(dict.fromkeys(h["bloque"] for h in TOOL_CATALOG))
HERRAMIENTAS_POR_LABEL = {h["label"]: h for h in TOOL_CATALOG}


def obtener_herramientas_por_bloque(bloque: str):
    return [h for h in TOOL_CATALOG if h["bloque"] == bloque]


def obtener_herramientas_por_grupo_estrategico(grupo: str):
    return [h for h in TOOL_CATALOG if h.get("strategic_group") == grupo]
