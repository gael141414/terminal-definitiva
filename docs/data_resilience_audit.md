# Data Resilience Audit

Auditoría estática ligera de módulos críticos de datos.

## Resumen

- Archivos auditados: 3
- Fallos: 0
- Avisos: 4

## Superficie auditada

| Archivo | Funciones | Requests | Requests sin timeout | Yahoo Ticker | Except amplios | Except silenciosos | Return None | Guards detectados |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| modulos/fmp_api.py | 11 | 2 | 0 | 0 | 5 | 2 | 8 | .empty, .columns, dropna, pd.to_numeric, pd.to_datetime, isinstance, validate_dataframe |
| modulos/company_data_helpers.py | 6 | 1 | 0 | 3 | 5 | 1 | 6 | .empty, .columns, dropna, pd.to_datetime, isinstance, validate_dataframe |
| modulos/scoring_engine.py | 24 | 0 | 0 | 3 | 4 | 1 | 6 | .empty, .columns, dropna, pd.to_numeric, isinstance, np.isfinite, replace([np.inf, -np.inf] |

## Incidencias

| Severidad | Código | Archivo | Detalle |
|---|---|---|---|
| WARN | silent_broad_except | modulos/fmp_api.py | Except amplio y silencioso cerca de línea 48. |
| WARN | silent_broad_except | modulos/fmp_api.py | Except amplio y silencioso cerca de línea 136. |
| WARN | silent_broad_except | modulos/company_data_helpers.py | Except amplio y silencioso cerca de línea 65. |
| WARN | silent_broad_except | modulos/scoring_engine.py | Except amplio y silencioso cerca de línea 250. |

## Recomendaciones Sprint 4B

- Crear un helper común para validar DataFrames obligatorios antes de calcular ratios.
- Diferenciar explícitamente entre `sin datos`, `API caída`, `ticker inválido` y `cobertura insuficiente`.
- Elevar avisos de baja cobertura cuando el score se calcule con demasiados defaults neutrales.
- Evitar que errores de Yahoo/FMP/SEC terminen como ceros silenciosos si esos ceros afectan a valoración o riesgo.
