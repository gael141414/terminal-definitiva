# Changelog

Todos los cambios relevantes de ValueQuant Terminal se documentan en este archivo.

El formato sigue una estructura práctica inspirada en Keep a Changelog y versionado semántico interno. Mientras el producto siga en prototipo local, las versiones se marcan como `internal`.

## [0.1.0-internal] - 2026-07-08

### Added

- Research Core como superficie principal de decisión.
- ValueQuant Score con payload estructurado, trazabilidad, quality gates, red flags, confidence diagnostics y decision guidance.
- Integración del score en informes, watchlist, briefings y superficies de evolución.
- Watchlist con snapshots de análisis y seguimiento operativo.
- Backtesting básico de señales históricas `BUY`, `WATCH` y `AVOID`.
- Calibración de confianza predictiva cuando existe muestra histórica suficiente.
- UX ejecutiva del Research Core con ruta de análisis recomendada.
- Exportación institucional desde Research Core: Markdown, HTML imprimible, memo ejecutivo, metadata JSON y ZIP.
- Healthcheck local para entorno, configuración, imports, runtime dirs y secretos locales.
- Smoke tests estrictos con contratos críticos del producto.
- Release readiness gate para validar preparación interna antes de fusionar o entregar.
- Documentación final de uso y runbook de release.

### Changed

- El producto pasa de prototipo disperso a terminal local estabilizado para research financiero.
- La lectura del score queda explícitamente condicionada por cobertura, confianza, quality gates y validación manual.
- El flujo operativo recomendado queda documentado como: datos, análisis fundamental, score, tesis, watchlist, backtesting, exportación y QA.

### Quality

- CI verde en los sprints de estabilización, exportación, QA y documentación.
- Contratos locales para scoring, data quality, reportes, watchlist, backtesting, confidence calibration, Research Core UX, exportación institucional, release readiness y documentación.

### Limitations

- No constituye asesoramiento financiero personalizado.
- No garantiza rentabilidad.
- El backtesting básico no sustituye una validación histórica robusta con costes, liquidez, slippage y ventanas múltiples.
- La confianza predictiva depende de la disponibilidad de snapshots históricos suficientes.

## [0.1.0-internal] - 2026-07-09 (resiliencia Yahoo/yfinance + consolidación de datos)

Esta sección documenta trabajo que ya estaba mergeado en `main` (sprints 11b–11g)
pero nunca se había reflejado en el changelog, más la auditoría de estabilización
de esta fecha que corrige el problema real detectado en producción: la capa de
resiliencia existía pero no estaba conectada a los módulos que la app realmente
usa.

### Added (sprints 11b–11g, retroactivo)

- `modulos/yahoo_resilience.py` y `modulos/yfinance_global_guard.py`: helpers de resiliencia ante rate limits de Yahoo/yfinance.
- `sitecustomize.py`: guarda global instalado al arranque del intérprete sobre `yf.download`.
- Limpieza de imports/bloques `main` duplicados en `screener.py` (sprint final cleanup).
- Contratos dedicados: `test_yahoo_resilience_contract`, `test_yfinance_helper_migration_contract`, `test_charts_yfinance_resilience_contract`, `test_final_cleanup_contract`.

### Fixed (auditoría de estabilización 2026-07-09)

- **Causa raíz real de "la barra superior no muestra precios" y "las herramientas no obtienen datos"**: la capa de resiliencia de los sprints 11c–11g se había conectado a `screener.py`/`backtester.py`/`data_provider.py` en la raíz del repo, que la app de Streamlit nunca importa. Los módulos que el router sí usa (`modulos/screener.py`, `modulos/backtester.py`, `modulos/watchlist.py`, `charts.py` y otros 14 módulos) seguían haciendo llamadas directas y desprotegidas a `yf.Ticker(...).info/.history/.financials`, con `except: pass` que ocultaba el fallo real (rate limit, ticker inválido, error de red mostraban el mismo "sin datos").
- `modulos/yahoo_resilience.py`: nuevo `safe_yfinance_fetch()` genérico con reintento corto (backoff) ante rate limit — antes un único 429 era definitivo para todo el rerun de Streamlit, sin reintento alguno.
- Nuevo `modulos/quotes.py`: proveedor centralizado de cotizaciones por lote (`fetch_quotes_with_fallback`) con fallback a FMP cuando Yahoo falla, y etiqueta explícita `unsupported_symbol` para futuros/índices (oro, petróleo, VIX, US10Y) que no tienen equivalente fiable en FMP — en vez de fingir un fallback inexistente.
- Ticker tape (`modulos/market_widgets.py`): antes no tenía ningún fallback a FMP — si Yahoo fallaba, cada símbolo desaparecía en silencio y la cinta caía a un placeholder estático. Ahora usa el proveedor centralizado, muestra un estado explícito por símbolo ("Rate limit temporal de Yahoo", "Fuente no disponible para este instrumento") y ya no bloquea 15 minutos completos de caché tras un fallo total puntual (auto-limpieza de caché en fallo total).
- `charts.py` (1931 líneas): no tenía ni un solo `@st.cache_data` pese a hacer ~24 llamadas directas a `yf.Ticker`. Ahora las funciones de descarga de datos están cacheadas (15 min precios, 24h fundamentales) y enrutadas por la capa de resiliencia; las funciones de solo-graficado quedan sin caché por ser baratas.
- `modulos/watchlist.py`: refrescaba precios en un bucle serie por ticker, sin caché, en cada rerun de la pestaña. Ahora usa el proveedor centralizado en lote con caché de 5 minutos.
- Otros 14 módulos con llamadas directas a `yf.Ticker`/`.info` migrados a la capa de resiliencia: `company_data_helpers.py`, `etf.py`, `insiders.py`, `predictor.py`, `radar.py`, `screener_avanzado.py`, `relative_comparison.py`, `scoring_engine.py`, `macro.py`, `derivados.py`, `proyeccion.py`, `utils.py`, `minero_smallcaps.py`, `opportunity_briefing.py`.
- Screener Avanzado (`modulos/screener_avanzado.py`): disparaba el universo FMP + enriquecimiento Yahoo automáticamente en cada cambio de slider, sin botón de ejecución. Ahora requiere pulsar "Ejecutar Screener Avanzado", igual que el resto de herramientas pesadas.

### Quality

- 3 contratos de comportamiento nuevos: `test_data_layer_consolidation_contract` (verifica que los módulos realmente usados por la app —no los huérfanos de la raíz— usan la capa de resiliencia), `test_ticker_tape_fallback_contract` (verifica fallback FMP y auto-recuperación de caché), `test_watchlist_price_cache_contract` (verifica lote + caché).
- Suite de smoke tests: 199 → 211 checks; contratos de comportamiento: 25 → 28.
