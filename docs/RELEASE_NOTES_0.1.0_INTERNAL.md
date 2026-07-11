# Release notes — ValueQuant Terminal 0.1.0-internal

Fecha: 2026-07-08
Estado: release interna para uso local de research.

> Esta release no constituye asesoramiento financiero personalizado. Es una herramienta de apoyo analítico y requiere validación manual antes de cualquier decisión real.

## Resumen ejecutivo

`0.1.0-internal` consolida ValueQuant Terminal como una versión local estabilizada para research financiero. El producto queda organizado alrededor de Research Core, ValueQuant Score, watchlist, backtesting básico, exportación institucional y QA final.

## Superficie funcional incluida

### Research Core

- Panel central de análisis por empresa.
- Ruta ejecutiva de análisis recomendada.
- Tesis, seguimiento, informe, resumen, fundamental, forense, proyección, NLP y comparativa.

### ValueQuant Score

- Score final y score bruto.
- Diagnóstico de confianza.
- Quality gates.
- Red flags.
- Guía de decisión.
- Payload estructurado para integraciones.

### Watchlist y seguimiento

- Guardado de análisis.
- Snapshots de score y tesis.
- Base para seguimiento histórico posterior.

### Backtesting básico

- Evaluación simple de señales `BUY`, `WATCH` y `AVOID`.
- Calibración de confianza predictiva si existe muestra suficiente.
- Lectura orientativa; no sustituye backtesting profesional.

### Exportación institucional

Desde `Research Core -> Informe`:

- Informe Markdown.
- HTML imprimible.
- Memo ejecutivo de comité.
- Metadata JSON.
- ZIP institucional.

### QA y release readiness

- `python scripts/run_healthcheck.py`
- `python scripts/run_smoke_tests.py --strict`
- `python scripts/run_release_readiness.py`
- `python scripts/run_release_readiness.py --json`

## Criterios de uso prudente

Antes de usar cualquier salida como base de decisión:

- Validar manualmente estados financieros.
- Revisar noticias recientes no incorporadas.
- Comparar con competidores directos.
- Revisar sensibilidad de valoración.
- Revisar red flags y quality gates.
- Confirmar que la tesis no depende solo del escenario optimista.

## Limitaciones conocidas

- No hay garantía de rentabilidad.
- La calidad del análisis depende de la calidad y cobertura de datos.
- La confianza predictiva requiere histórico suficiente.
- El backtesting básico no contempla todos los costes ni restricciones reales de mercado.
- El sistema debe interpretarse como herramienta de research, no como motor automático de inversión.

## Comandos de verificación

```bash
python scripts/test_documentation_contract.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
python scripts/run_release_readiness.py
streamlit run app.py
```

## Actualización 2026-07-09 — consolidación de la capa de datos Yahoo/FMP

Auditoría de estabilización que corrige por qué, pese a que `0.1.0-internal` ya
incluía una capa de resiliencia ante rate limits de Yahoo (sprints 11c–11g), la
barra de precios y varias herramientas seguían mostrando "sin datos" en uso
real: esa capa estaba conectada a archivos huérfanos en la raíz del repo que la
app de Streamlit no ejecuta, no a los módulos reales del router.

- Nuevo proveedor centralizado `modulos/quotes.py` con fallback Yahoo → FMP para cotizaciones por lote.
- Ticker tape, watchlist, snapshot y treemap de mercado migrados a este proveedor; muestran estado explícito por símbolo (rate limit, sin fallback, sin datos) en vez de desaparecer en silencio.
- `charts.py` (antes sin ninguna caché) y otros 15 módulos con llamadas directas a `yf.Ticker` migrados a la capa de resiliencia con reintento corto ante rate limit.
- Screener Avanzado ahora requiere un botón de ejecución explícito, en línea con el resto de herramientas pesadas del catálogo.
- 3 contratos de comportamiento nuevos (`test_data_layer_consolidation_contract`, `test_ticker_tape_fallback_contract`, `test_watchlist_price_cache_contract`) para evitar que esta regresión — resiliencia construida pero no conectada al camino real de ejecución — vuelva a ocurrir.

**Limitación conocida no resuelta por esta actualización**: la clave FMP configurada en este entorno devolvía `403` (rechazada) durante la auditoría, y Yahoo Finance devolvía `429` de forma intermitente. El código ahora degrada con estados explícitos en vez de fallar en silencio, pero una clave FMP funcional sigue siendo necesaria para que el fallback tenga efecto real.
