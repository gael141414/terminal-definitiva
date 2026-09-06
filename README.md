# ValueQuant Terminal

ValueQuant Terminal es una plataforma Streamlit de análisis financiero orientada a research, valoración, scoring, tesis de inversión, watchlist, backtesting básico de señales, exportación institucional y control de calidad local.

> Estado actual: prototipo avanzado estabilizado para uso local de research. No constituye asesoramiento financiero personalizado ni garantiza rentabilidad.

## Qué permite hacer

```text
Datos -> Análisis Fundamental -> ValueQuant Score -> Tesis -> Watchlist -> Backtesting -> Exportación -> QA
```

Capacidades principales:

- **Research Core**: centro operativo para analizar una empresa con score, tesis, seguimiento, informe, comparativa y módulos financieros.
- **ValueQuant Score**: score institucional orientativo con componentes, confidence diagnostics, quality gates, decision guidance y payload trazable.
- **Tesis de inversión**: lectura estructurada de acción operativa, valoración, margen de seguridad, riesgos y próximos pasos.
- **Watchlist**: guardado de análisis y seguimiento de snapshots.
- **Decisión de venta**: para una posición YA abierta, con su precio y fecha de entrada, devuelve
  MANTENER / REDUCIR / VENDER, cuánto reducir y precios objetivo, combinando valoración, deterioro
  del negocio y técnica. Ver la advertencia de evidencia más abajo.
- **Backtesting básico de señales**: evaluación histórica simple de señales BUY / WATCH / AVOID guardadas.
- **Calibración de confianza predictiva**: lectura de fiabilidad de la confianza cuando hay muestra histórica suficiente.
- **Exportación institucional**: informes Markdown, HTML imprimible, memo ejecutivo, metadata JSON y ZIP institucional.
- **QA final**: healthcheck, smoke tests estrictos y release readiness gate.

## Instalación local

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Configuración

Copia los ejemplos de configuración y añade tus claves reales solo en local:

```bash
cp .env.example .env
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
```

Variables principales:

```text
FMP_API_KEY
GEMINI_API_KEY
GOOGLE_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Nunca subas `.env` ni `.streamlit/secrets.toml` reales al repositorio.

## Ejecución

```bash
streamlit run app.py
```

## QA local recomendado

Antes de entregar, fusionar o usar una versión como estable:

```bash
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
python scripts/run_release_readiness.py
python scripts/run_release_readiness.py --json
```

El release gate debe terminar con:

```text
Estado: READY
Resultado: OK para merge/release interno.
```

## Guías

- [Guía de uso](docs/USER_GUIDE.md)
- [Runbook de release y QA](docs/RELEASE_RUNBOOK.md)

## Módulos principales

- Research Core
- Resumen Ejecutivo
- Análisis Fundamental
- ValueQuant Score
- Auditoría Forense
- Decisión de Venta
- Valoración
- Comparativa relativa
- Watchlist
- Briefing de Oportunidades
- Centro de Automatización
- Backtesting básico de señales
- Exportación institucional
- Release Readiness

## ValueQuant Score

El `ValueQuant Score` es una nota institucional orientativa. Pondera, entre otros bloques:

- Calidad fundamental
- Valoración
- Riesgo y forense
- Crecimiento y catalizadores
- Asignación de capital e insiders
- Momentum y timing
- Macro, sector y liquidez
- Opciones, alt data y NLP

El score no debe usarse como señal automática de compra o venta. Debe interpretarse junto con cobertura de datos, confianza operativa, quality gates, red flags, backtesting y validación manual.

## Exportación institucional

Desde `Research Core -> Informe` se puede descargar:

- Informe completo en Markdown.
- HTML imprimible para guardar como PDF.
- Memo ejecutivo de comité.
- Metadata JSON estructurada.
- ZIP institucional con todos los artefactos.

## Qué está validado y qué no

La decisión de venta se midió sobre 4.199 operaciones (57 valores, 10 años, coste del 0,1% por lado)
con `scripts/backtest_decision_venta.py`, comparándola contra tres listones:

| Regla | Retorno medio | Acierto | Días en mercado |
|---|---|---|---|
| Aguantar hasta el horizonte | **+36,31%** | 47,7% | 252 |
| Regla técnica de salida | +35,76% | 48,2% | 242 |
| Venta aleatoria de igual frecuencia | +20,22% | 47,6% | 126 |
| Solo stop fijo a −8% | +11,03% | 17,1% | 78 |

Lectura honesta: la regla **bate a la venta aleatoria por 15,5 puntos**, así que lleva información y
no es azar. Pero **no bate a limitarse a aguantar**. Y el stop fijo a −8% aplicado a posiciones de un
año es destructivo, porque corta caídas normales de valores que luego se recuperan; por eso solo
decide en el perfil de swing.

### Actualización 2026-09-06: revalidación sobre entradas reales

El backtest anterior usaba entradas sintéticas mensuales, un diseño sesgado contra las salidas por
construcción. Se repitió sobre **7.212 entradas reales** generadas por el catálogo de estrategias:

| Regla | Retorno medio | Diferencia vs aguantar (IC95) |
|---|---|---|
| Aguantar | **+1,44%** | — |
| Regla técnica | +1,44% | −0,004 pts [−0,042, +0,031] · **no significativa** |
| Stop fijo −8% | +0,78% | −0,660 pts [−1,112, −0,290] · **peor** |
| Compuesta | +0,79% | −0,658 pts [−1,110, −0,290] · **peor** |

Las tres hipótesis pre-registradas quedaron refutadas, dos de ellas **en dirección contraria** a lo
esperado: las salidas hacen más daño en régimen bajista y sobre las entradas de peor calidad. Detalle
completo en [docs/resultado_validacion_salidas.md](docs/resultado_validacion_salidas.md).

Los pilares de **valoración y fundamentales quedan sin validar**: reconstruirlos sin look-ahead exige
las cuentas tal y como se conocían en cada fecha pasada, y el repositorio no tiene esos datos
point-in-time generados. Trata la herramienta como un panel de diagnóstico, no como una orden.

## Advertencia

Este proyecto no constituye asesoramiento financiero personalizado. Cualquier decisión de inversión debe ser validada por el usuario y contrastada con fuentes externas.
