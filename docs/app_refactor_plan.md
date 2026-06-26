# App refactor plan

## Contexto

`app.py` concentra demasiadas responsabilidades: configuración de página, assets, CSS, navegación, carga de datos, widgets externos, lógica de análisis y renderizado de herramientas. Esto dificulta el mantenimiento y aumenta el riesgo de romper la app con cambios pequeños.

El refactor debe ser incremental. Cada paso tiene que mantener:

- `streamlit run app.py` operativo.
- `python scripts/run_smoke_tests.py --strict` en verde.
- CI en verde.
- Sin mover secretos, datos runtime ni archivos locales al repositorio.

## Regla crítica de Streamlit

`st.set_page_config()` debe ejecutarse una única vez y debe ser el primer comando Streamlit del archivo. Por eso la llamada debe permanecer al inicio de `app.py`, justo después de `import streamlit as st`.

Se permite mover las constantes de configuración a `modulos/app_runtime.py`, pero no la llamada efectiva a `st.set_page_config()`.

## Orden propuesto de extracción

### Sprint 2A - Runtime y mapa de refactor

- Añadir `modulos/app_runtime.py`.
- Documentar el plan de extracción.
- No modificar todavía el flujo principal de `app.py`.

### Sprint 2B - Limpieza segura de imports

- Eliminar imports duplicados.
- Convertir dependencias opcionales a imports tolerantes a fallo.
- Mantener imports críticos explícitos.
- Aplicar la migración con `scripts/apply_sprint_2b_import_cleanup.py`.

El script de Sprint 2B debe:

- mantener `st.set_page_config()` al inicio de `app.py`,
- quitar el segundo `from modulos.config import CONFIG`,
- convertir `google.generativeai`, `fpdf`, `TextBlob` y `streamlit_lottie` en imports tolerantes a fallo,
- añadir guardas para Gemini y exportación PDF.

Validación específica:

```bash
python scripts/apply_sprint_2b_import_cleanup.py
python -m py_compile app.py scripts/apply_sprint_2b_import_cleanup.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

### Sprint 2C - Assets y helpers visuales

Extraer de `app.py`:

- `asset_to_data_uri`
- rutas de logo y fondo
- helpers de formato visual

Destino sugerido:

- `modulos/app_assets.py`

### Sprint 2D - Tema visual y CSS

Extraer:

- `inject_terminal_theme`
- CSS largo del terminal
- helpers relacionados con layout visual

Destino sugerido:

- `modulos/app_theme.py`

### Sprint 2E - Navegación superior

Extraer:

- navbar
- selector de modo de producto
- selector de bloque/herramienta
- cabeceras de contexto

Destino sugerido:

- `modulos/app_navigation.py`

### Sprint 2F - Home/dashboard inicial

Extraer:

- pantalla inicial
- tarjetas de bloques
- resumen de producto

Destino sugerido:

- `modulos/app_home.py`

### Sprint 2G - Datos externos genéricos

Extraer:

- Yahoo search ETF
- ticker tape
- rotación sectorial
- TradingView helpers

Destino sugerido:

- `modulos/market_widgets.py`

### Sprint 2H - Compatibilidad legacy

Revisar funciones antiguas que ya delegan en módulos nuevos y decidir si:

- se eliminan,
- se convierten en wrappers explícitos,
- o se mantienen temporalmente por compatibilidad.

## Criterio de aceptación por sprint

Cada sprint debe cumplir:

```bash
python -m py_compile app.py modulos/<nuevo_modulo>.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

## No hacer todavía

- No reescribir `app.py` completo de golpe.
- No cambiar scoring en el mismo PR que refactor visual.
- No mover datos de `data/` ni runtime files.
- No subir `.env` ni `.streamlit/secrets.toml`.
- No hacer `git add .`.
