# App legacy inventory

Inventario estático de funciones top-level restantes en `app.py`.

Este informe no borra código. Sirve para decidir el siguiente refactor con menor riesgo.

## Resumen

- Funciones top-level detectadas: 0
- Sin llamadas detectadas en el repositorio: 0
- Candidatas a extracción/revisión: 0

## Inventario

| Función | Líneas | Categoría | Llamadas en app.py | Llamadas repo | Recomendación |
|---|---:|---|---:|---:|---|

## Lectura recomendada

- No eliminar funciones solo porque tengan pocas llamadas: algunas pueden ser entrypoints indirectos de Streamlit o rutas antiguas.
- Priorizar extracción de widgets/UI antes que lógica financiera.
- Convertir wrappers de compatibilidad en delegaciones explícitas cuando haya consumidores externos.
