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
- `strip_visual_prefix`
- rutas de logo y fondo mediante `build_runtime_paths()`

Destino:

- `modulos/app_assets.py`
- reutilización de `modulos/app_runtime.py`

Aplicar la migración con:

```bash
python scripts/apply_sprint_2c_extract_assets.py
```

Validación específica:

```bash
python scripts/apply_sprint_2c_extract_assets.py
python -m py_compile app.py modulos/app_assets.py scripts/apply_sprint_2c_extract_assets.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

### Sprint 2D - Tema visual y CSS

Extraer de `app.py`:

- `inject_terminal_theme()`
- bloque CSS largo del terminal

Destino:

- `modulos/app_theme.py`

La migración usa AST para localizar la función y moverla completa, evitando copiar manualmente cientos de líneas de CSS.

Aplicar con:

```bash
python scripts/apply_sprint_2d_extract_theme.py
```

Validación específica:

```bash
python scripts/apply_sprint_2d_extract_theme.py
python -m py_compile app.py modulos/app_theme.py scripts/apply_sprint_2d_extract_theme.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

### Sprint 2E - Navegación superior

Extraer de `app.py`:

- `render_context_header()`
- `render_option_menu_safe()`
- `BLOQUE_UI`
- `TOOL_UI_ICONS`

Destino:

- `modulos/app_navigation.py`

No se mueve todavía el bloque principal de selección de empresa/herramienta porque mezcla navegación, estado de sesión y controles de análisis. Ese bloque se abordará después de aislar helpers y constantes.

Aplicar con:

```bash
python scripts/apply_sprint_2e_extract_navigation.py
```

Validación específica:

```bash
python scripts/apply_sprint_2e_extract_navigation.py
python -m py_compile app.py modulos/app_navigation.py scripts/apply_sprint_2e_extract_navigation.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

### Sprint 2F - Home/dashboard inicial

Primera extracción segura:

- `render_module_showcase()`

Destino:

- `modulos/app_home.py`

No se mueve todavía `render_home_page()` completo porque depende de funciones de mercado, noticias, treemap y rotación sectorial que siguen residiendo en `app.py`. Ese movimiento debe hacerse después de aislar los widgets/datos de mercado.

Aplicar con:

```bash
python scripts/apply_sprint_2f_extract_home_showcase.py
```

Validación específica:

```bash
python scripts/apply_sprint_2f_extract_home_showcase.py
python -m py_compile app.py modulos/app_home.py scripts/apply_sprint_2f_extract_home_showcase.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

### Sprint 2G - Datos externos y widgets de mercado

Extraer de `app.py`:

- `buscar_etf_yahoo()`
- `obtener_datos_ticker_tape()`
- `render_ticker_tape()`
- `analizar_rotacion_sectores()`
- `obtener_market_snapshot()`
- `_normalizar_url_imagen_noticia()`
- `obtener_market_treemap_data()`
- `obtener_ultimas_noticias()`

Destino:

- `modulos/market_widgets.py`

No se mueve todavía `render_home_page()` completo. Tras extraer estos widgets/datos, `render_home_page()` queda como una capa de composición que podremos mover en el siguiente sprint con menor riesgo.

Aplicar con:

```bash
python scripts/apply_sprint_2g_extract_market_widgets.py
```

Validación específica:

```bash
python scripts/apply_sprint_2g_extract_market_widgets.py
python -m py_compile app.py modulos/market_widgets.py scripts/apply_sprint_2g_extract_market_widgets.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

### Sprint 2H - Home completo

Extraer de `app.py`:

- `render_home_page()`

Destino:

- `modulos/app_home.py`

La función se adapta para recibir las rutas visuales como parámetros:

```python
render_home_page(LOGO_PATH, HOME_BG_PATH)
```

Así evitamos que `modulos/app_home.py` dependa de variables globales definidas en `app.py`.

Aplicar con:

```bash
python scripts/apply_sprint_2h_extract_home_page.py
```

Validación específica:

```bash
python scripts/apply_sprint_2h_extract_home_page.py
python -m py_compile app.py modulos/app_home.py scripts/apply_sprint_2h_extract_home_page.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

### Sprint 2I - Limpieza runtime de Home

Limpieza segura después de mover Home:

- quitar de `app.py` imports de mercado que ya solo usa `modulos/app_home.py`,
- añadir `render_market_treemap()` en `modulos/app_home.py` para que el mapa de calor quede autocontenido,
- mantener sin tocar todavía funciones legacy financieras grandes.

Aplicar con:

```bash
python scripts/apply_sprint_2i_home_runtime_cleanup.py
```

Validación específica:

```bash
python scripts/apply_sprint_2i_home_runtime_cleanup.py
python -m py_compile app.py modulos/app_home.py scripts/apply_sprint_2i_home_runtime_cleanup.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

### Sprint 2J - Limpieza de imports legacy

Limpieza conservadora de `app.py`:

- detectar imports no usados mediante AST,
- quitar solo imports residuales inequívocos,
- eliminar `render_module_showcase` del import de `modulos.app_home` si ya no se usa directamente en `app.py`,
- mantener intactas las funciones financieras legacy hasta tener un inventario específico.

Aplicar con:

```bash
python scripts/apply_sprint_2j_legacy_import_cleanup.py
```

Validación específica:

```bash
python scripts/apply_sprint_2j_legacy_import_cleanup.py
python -m py_compile app.py scripts/apply_sprint_2j_legacy_import_cleanup.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

### Sprint 2K - Inventario legacy funcional

Añadir herramienta de auditoría estática:

- listar funciones top-level restantes en `app.py`,
- contar llamadas internas en `app.py`,
- contar llamadas detectadas en el repositorio,
- clasificar cada función como `runtime/helper`, `ui/widget`, `data/helper`, `analysis/helper`, `export/helper` o `legacy/helper`,
- generar opcionalmente `docs/app_legacy_inventory.md`.

Este sprint no modifica `app.py`; solo añade una herramienta para decidir los siguientes cortes con evidencia.

Ejecutar con:

```bash
python scripts/print_app_legacy_inventory.py
python scripts/print_app_legacy_inventory.py --write
```

Validación específica:

```bash
python -m py_compile scripts/print_app_legacy_inventory.py
python scripts/print_app_legacy_inventory.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

### Sprint 2L - Extraer widgets TradingView

Primera extracción legacy por grupo:

- `render_tradingview_widget()`
- `renderizar_grafico_tradingview()`

Destino:

- `modulos/tradingview_widgets.py`

Motivo: son widgets UI autocontenidos, de bajo riesgo y sin lógica financiera. Se mantienen importados desde `app.py` para preservar compatibilidad con llamadas existentes.

Aplicar con:

```bash
python scripts/apply_sprint_2l_extract_tradingview_widgets.py
```

Validación específica:

```bash
python scripts/apply_sprint_2l_extract_tradingview_widgets.py
python -m py_compile app.py modulos/tradingview_widgets.py scripts/apply_sprint_2l_extract_tradingview_widgets.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
streamlit run app.py
```

### Sprint 2M - Siguiente extracción legacy por grupo

Usar el inventario para decidir entre:

- helpers de datos SEC/yfinance,
- exportación PDF,
- wrappers de compatibilidad,
- funciones sin llamadas detectadas.

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
