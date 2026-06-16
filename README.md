# ValueQuant Terminal

ValueQuant Terminal es una plataforma Streamlit de análisis financiero orientada a research, valoración, scoring, screener, watchlist y seguimiento de carteras.

> Estado actual: prototipo avanzado en estabilización. No debe presentarse como asesor financiero automático ni como sistema que garantice rentabilidad.

## Objetivo del producto

El objetivo del proyecto es evolucionar hacia un terminal de apoyo a la decisión inversora:

```text
Datos -> Análisis -> ValueQuant Score -> Backtesting -> Screener -> Tesis -> Watchlist -> Alertas
```

## Instalación local

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Configuración

Copia los ejemplos de configuración y añade tus claves reales en local:

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

## Módulos principales

- Resumen Ejecutivo
- Análisis Fundamental
- ValueQuant Score
- Auditoría Forense
- Valoración
- Técnico y Opciones
- Macro y Liquidez
- Screener
- Watchlist
- Portfolio Manager
- Backtesting
- Monte Carlo

## ValueQuant Score

El `ValueQuant Score` es una nota institucional orientativa. Pondera:

- Calidad fundamental
- Valoración
- Riesgo y forense
- Crecimiento y catalizadores
- Asignación de capital e insiders
- Momentum y timing
- Macro, sector y liquidez
- Opciones, alt data y NLP

La confianza predictiva queda pendiente de validación mediante backtesting histórico. Hasta que exista esa validación, la nota debe usarse como herramienta de research, no como señal automática de compra o venta.

## Advertencia

Este proyecto no constituye asesoramiento financiero personalizado. Cualquier decisión de inversión debe ser validada por el usuario y contrastada con fuentes externas.

## Roadmap inmediato

1. Estabilización técnica y seguridad.
2. Reorganización/fusión de herramientas.
3. ValueQuant Score v1.1 trazable.
4. Backtesting transversal del score.
5. Screener y ranking de oportunidades.
6. Tesis de inversión exportable.
7. Watchlist, alertas y portfolio.
