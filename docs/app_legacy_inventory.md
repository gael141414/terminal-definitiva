# App legacy inventory

Inventario estático de funciones top-level restantes en `app.py`.

Este informe no borra código. Sirve para decidir el siguiente refactor con menor riesgo.

## Resumen

- Funciones top-level detectadas: 15
- Sin llamadas detectadas en el repositorio: 5
- Candidatas a extracción/revisión: 7

## Inventario

| Función | Líneas | Categoría | Llamadas en app.py | Llamadas repo | Recomendación |
|---|---:|---|---:|---:|---|
| `inyectar_atajo_teclado` | 78-117 | runtime/helper | 1 | 1 | mantener temporalmente |
| `load_lottieurl` | 119-125 | runtime/helper | 0 | 0 | candidata a revisar; sin llamadas detectadas |
| `obtener_secreto_streamlit` | 130-135 | runtime/helper | 0 | 0 | candidata a revisar; sin llamadas detectadas |
| `obtener_modelo_gemini` | 138-157 | runtime/helper | 0 | 7 | posible API usada fuera de app.py; no borrar |
| `obtener_transacciones_insiders` | 164-184 | data/helper | 0 | 1 | posible API usada fuera de app.py; no borrar |
| `obtener_tickers_filtrados` | 187-211 | data/helper | 1 | 1 | candidata a extracción modular posterior |
| `render_tradingview_widget` | 216-252 | ui/widget | 0 | 0 | candidata a revisar; sin llamadas detectadas |
| `renderizar_grafico_tradingview` | 254-287 | ui/widget | 0 | 2 | posible API usada fuera de app.py; no borrar |
| `obtener_valoracion_sectorial` | 289-337 | data/helper | 0 | 1 | posible API usada fuera de app.py; no borrar |
| `escanear_vulnerabilidades` | 339-370 | analysis/helper | 0 | 1 | posible API usada fuera de app.py; no borrar |
| `analizar_sentimiento_noticias` | 372-374 | analysis/helper | 0 | 4 | mantener como wrapper hasta confirmar consumidores |
| `generar_reporte_pdf` | 376-475 | export/helper | 0 | 0 | candidata a revisar; sin llamadas detectadas |
| `obtener_datos_directiva` | 478-487 | data/helper | 0 | 1 | posible API usada fuera de app.py; no borrar |
| `ultimo_ratio` | 489-498 | legacy/helper | 0 | 0 | candidata a revisar; sin llamadas detectadas |
| `render_company_empty_state` | 507-534 | ui/widget | 1 | 1 | candidata a extracción modular posterior |

## Lectura recomendada

- No eliminar funciones solo porque tengan pocas llamadas: algunas pueden ser entrypoints indirectos de Streamlit o rutas antiguas.
- Priorizar extracción de widgets/UI antes que lógica financiera.
- Convertir wrappers de compatibilidad en delegaciones explícitas cuando haya consumidores externos.
