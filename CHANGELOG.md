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
