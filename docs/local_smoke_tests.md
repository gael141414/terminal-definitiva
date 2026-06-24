# ValueQuant Terminal — Smoke tests locales

Estos smoke tests son pruebas rápidas para validar que el proyecto sigue arrancable a nivel técnico antes de ejecutar Streamlit, el runner de briefings o una futura automatización.

No descargan datos financieros pesados, no envían Telegram y no lanzan la app.

## Ejecución básica

Desde la raíz del proyecto:

```bash
python scripts/run_smoke_tests.py
```

Resultado esperado:

```text
=== ValueQuant Local Smoke Tests ===
[OK   ] file:app.py — exists
[OK   ] compile:modulos/config.py — compiled
[OK   ] import:modulos.tool_catalog — imported
...
Resultado: OK (... checks)
```

## Modo estricto

Para usarlo en scripts o CI local:

```bash
python scripts/run_smoke_tests.py --strict
```

En modo estricto:

- devuelve `0` si todo pasa;
- devuelve `1` si hay algún fallo.

## Qué comprueba

- Existencia de archivos críticos.
- Compilación de módulos críticos con `py_compile`.
- Importación de módulos core.
- Registro de herramientas clave en `TOOL_CATALOG`.
- Registro de rutas clave en `tool_router`.
- Versión del modelo `ValueQuant Score`.
- Límite de confianza del score.

## Qué no comprueba

- No valida datos reales de FMP.
- No ejecuta análisis financiero completo.
- No prueba la UI de Streamlit.
- No envía Telegram.
- No garantiza que todos los módulos secundarios funcionen a nivel funcional.

## Uso recomendado antes de trabajar

```bash
git pull origin sprint-1-stabilization
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
```

Después de modificar código:

```bash
python -m compileall -q .
python scripts/run_smoke_tests.py --strict
```

## Interpretación

Si falla un import o compilación, corrige eso antes de seguir añadiendo funcionalidades. Estos tests no sustituyen tests unitarios reales, pero sirven como red mínima para detectar errores de sintaxis, imports rotos y rutas críticas ausentes.
