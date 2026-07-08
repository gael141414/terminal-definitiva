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
