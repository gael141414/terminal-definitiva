# Guía de uso — ValueQuant Terminal

Esta guía describe el flujo operativo recomendado para usar ValueQuant Terminal como herramienta local de research financiero.

> ValueQuant Terminal no es asesor financiero automático. La salida del sistema debe tratarse como apoyo analítico y no como recomendación individualizada.

## 1. Arranque

Desde la raíz del proyecto:

```bash
source .venv/bin/activate
streamlit run app.py
```

Antes de una sesión importante conviene ejecutar:

```bash
python scripts/run_healthcheck.py
```

Si faltan directorios runtime, se pueden crear con:

```bash
python scripts/run_healthcheck.py --fix
```

## 2. Configuración mínima

Archivos locales esperados:

```text
.env
.streamlit/secrets.toml
```

Variables más relevantes:

```text
FMP_API_KEY
GEMINI_API_KEY
GOOGLE_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

`FMP_API_KEY` es crítica para datos financieros. Telegram es opcional si no se van a usar entregas manuales o alertas.

## 3. Flujo recomendado de análisis

```text
Seleccionar ticker
-> Research Core
-> revisar score y cobertura
-> revisar tesis y valoración
-> revisar riesgos
-> comparar con competidor
-> guardar en watchlist si procede
-> exportar informe
-> validar manualmente
```

## 4. Research Core

Research Core es el centro principal de decisión.

Incluye pestañas como:

- **Tesis**: acción operativa, detalle, valoración, margen de seguridad y riesgos.
- **Seguimiento**: guardado en watchlist y snapshots.
- **Informe**: exportación Markdown, HTML, memo, JSON y ZIP institucional.
- **Resumen**: visión agregada del análisis.
- **Fundamental**: estados financieros y ratios.
- **Forense**: señales de riesgo contable o financiero.
- **Proyección**: escenarios y sensibilidad.
- **Earnings NLP**: lectura cualitativa si hay datos disponibles.
- **Comparativa**: contraste relativo con competidor.

## 5. Interpretación del ValueQuant Score

El score debe interpretarse con cuatro capas:

1. **Score final**: nota agregada ajustada.
2. **Score bruto**: lectura antes de penalizaciones o gates.
3. **Cobertura de datos**: fiabilidad de la información disponible.
4. **Confianza operativa/predictiva**: nivel de fiabilidad del score y de señales históricas.

Lectura prudente:

```text
Score alto + cobertura alta + confianza alta + pocos red flags = candidato a estudiar.
Score alto + cobertura baja = estudiar manualmente antes de decidir.
Score bajo + red flags = evitar o mantener fuera de watchlist prioritaria.
```

## 6. Quality gates y red flags

Los quality gates reducen o matizan la lectura del score cuando detectan problemas de calidad, cobertura o riesgo.

Ejemplos de interpretación:

- `quality_adjusted = Sí`: el score ha sido penalizado o ajustado.
- `quality_gate_reason`: explica el motivo del ajuste.
- `red_flags`: enumera riesgos relevantes que deben revisarse manualmente.

Nunca se debe ignorar un quality gate por tener un score final atractivo.

## 7. Watchlist

La watchlist sirve para guardar análisis y hacer seguimiento posterior.

Uso recomendado:

1. Analizar empresa en Research Core.
2. Revisar score, tesis, riesgos y valoración.
3. Guardar snapshot si merece seguimiento.
4. Usar la watchlist para comparar evolución de señales, score y decisiones.

La watchlist no es una cartera real. Es un registro operativo de seguimiento.

## 8. Backtesting básico

El backtesting básico evalúa señales históricas guardadas:

- `BUY`: acierta si el retorno posterior es positivo.
- `AVOID`: acierta si el retorno posterior no es positivo.
- `WATCH`: se trata como observación y no como señal fuerte.

Limitaciones:

- Depende de tener suficientes snapshots históricos.
- No sustituye un backtesting robusto con costes, slippage, liquidez y ventanas múltiples.
- Sirve para validar disciplina y calibrar confianza, no para prometer rentabilidad.

## 9. Confianza predictiva

La confianza predictiva se calibra cuando hay muestra histórica suficiente.

Interpretación:

- **Alta y bien calibrada**: las señales históricas han sido razonablemente consistentes.
- **Media o aceptable**: útil como apoyo, pero requiere revisión manual.
- **Baja o insuficiente**: no debe usarse como base decisoria.
- **Pendiente**: falta histórico suficiente.

## 10. Exportación institucional

Desde `Research Core -> Informe` se pueden descargar:

```text
research_report.md
research_report_print.html
committee_memo.md
metadata.json
institutional_export_pack.zip
```

Uso recomendado:

- Markdown: revisión rápida y versionado textual.
- HTML imprimible: abrir en navegador y guardar como PDF.
- Memo comité: resumen ejecutivo para decisión.
- Metadata JSON: trazabilidad del análisis.
- ZIP: paquete completo para archivar.

## 11. QA antes de entregar

Ejecutar:

```bash
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
python scripts/run_release_readiness.py
```

Una versión local puede considerarse preparada si:

```text
Healthcheck: sin errores bloqueantes
Smoke tests: 0 fallos
Release readiness: READY
```

## 12. Criterio de uso prudente

Antes de tomar cualquier decisión real:

- Contrastar estados financieros con fuentes oficiales.
- Revisar noticias recientes no incorporadas.
- Revisar valoración y sensibilidad de supuestos.
- Comparar con competidores directos.
- Revisar deuda, dilución, recompras, márgenes y FCF.
- Confirmar que la tesis no depende solo del escenario optimista.
