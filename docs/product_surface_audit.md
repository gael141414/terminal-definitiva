# Product surface audit

Auditoría estática del catálogo de herramientas y su cobertura real en `tool_router`.

## Resumen

- Rutas auditadas: 35
- Rutas OK: 35
- Fallos: 0
- Avisos: 0

## Herramientas por modo

| Modo | Herramientas visibles |
| --- | ---: |
| complete | 35 |
| consolidated | 30 |
| mvp | 24 |

## Incidencias

Sin incidencias detectadas.

## Cobertura de rutas

| Estado | Herramienta | Modo | Módulo | Callable |
| --- | --- | --- | --- | --- |
| OK | ⏳ Máquina del Tiempo (Backtest) | company | modulos.backtest | ejecutar_maquina_del_tiempo |
| OK | 🌍 Radar Macro y Sectores | company | modulos.macro | ejecutar_radar_macro |
| OK | 🎓 Visor de Gurús (Estrategias) | company | modulos.gurus | ejecutar_visor_gurus |
| OK | 📈 Técnico y Opciones | company | modulos.tecnico | ejecutar_tecnico_y_opciones |
| OK | 📊 Resumen Ejecutivo | company | modulos.resumen | ejecutar_resumen_ejecutivo |
| OK | 🔎 Análisis Fundamental | company | modulos.fundamental | ejecutar_analisis_fundamental |
| OK | 🔭 Predictor de Techos/Suelos | company | modulos.predictor | ejecutar_predictor_techos_suelos |
| OK | 🔮 Proyección IA y Catalizadores | company | modulos.proyeccion | ejecutar_proyeccion |
| OK | 🕵️ Alt Data & Congreso | company | modulos.alt_data | render_alt_data |
| OK | 🕵️‍♂️ Rastreador de Insiders (SEC) | company | modulos.insiders | ejecutar_rastreador_insiders |
| OK | 🚀 Radar Multibaggers (Small/Mid Caps) | company | modulos.radar | ejecutar_radar_multibagger |
| OK | 🛡️ Radar de Coberturas (Hedging) | company | modulos.coberturas | ejecutar_radar_coberturas |
| OK | 🦢 Test Cisnes Negros (Crisis) | company | modulos.cisnes_negros | ejecutar_simulador_crisis |
| OK | 🧠 Auditoría Forense | company | modulos.forense | ejecutar_auditoria_forense |
| OK | 🧠 Earnings Call NLP | company | modulos.nlp_analyzer | render_nlp_dashboard |
| OK | 🧩 Research Core | company | modulos.research_core | ejecutar_research_core |
| OK | 🧪 Backtesting Estrategias | company | modulos.backtester | render_backtesting_engine |
| OK | 🧮 Opciones Avanzadas (BSM) | company | modulos.derivados | render_derivados |
| OK | 🩻 Radiografía de ETFs (X-Ray) | etf | modulos.etf | ejecutar_radiografia_etf |
| OK | ⚖️ Optimizador de Cartera | standalone | modulos.portfolio | render_portfolio_manager |
| OK | ⚙️ Centro de Automatización | standalone | modulos.automation_center | render_automation_center |
| OK | ⛏️ Minero de Small Caps | standalone | modulos.minero_smallcaps | ejecutar_visor_smallcaps |
| OK | 🌐 Escáner Global (Screener) | standalone | modulos.screener | ejecutar_escaner_global |
| OK | 🌐 Screener Avanzado (Multi-Factor) | standalone | modulos.screener_avanzado | render_screener_avanzado |
| OK | 🎲 Monte Carlo Cartera | standalone | modulos.montecarlo | render_montecarlo |
| OK | 💡 Consejos y Mentoría | standalone | modulos.consejos | ejecutar_apartado_consejos |
| OK | 📋 Mi Watchlist (Cartera) | standalone | modulos.watchlist | ejecutar_watchlist |
| OK | 📌 Briefing de Oportunidades | standalone | modulos.opportunity_briefing | render_opportunity_briefing |
| OK | 📚 Análisis Guardados | standalone | modulos.analysis_store | render_saved_research_dashboard |
| OK | 📲 Automatización Telegram | standalone | modulos.automatizacion | ejecutar_panel_automatizacion |
| OK | 🕰️ Reloj Económico (Regímenes) | standalone | modulos.reloj_macro | ejecutar_reloj_macro |
| OK | 🚰 Monitor de Liquidez (FED) | standalone | modulos.liquidez | ejecutar_monitor_liquidez |
| OK | 🤖 Chatbot Inversor | standalone | modulos.chatbot | render_chatbot |
| OK | 🤖 Robo-Advisor & Test Perfil | standalone | modulos.roboadvisor | ejecutar_roboadvisor |
| OK | 🧭 Mapa del Producto | standalone | modulos.product_dashboard | render_product_dashboard |

## Lectura recomendada

- Un fallo `missing_route` implica que una herramienta aparece en navegación pero cae en mensaje genérico del router.
- Un fallo `missing_callable` implica que el router apunta a una función inexistente o renombrada.
- Los avisos `orphan_route` no rompen la app, pero señalan rutas que ya no son visibles desde el catálogo.
- Esta auditoría no ejecuta herramientas ni llama APIs externas; solo comprueba coherencia estática.
