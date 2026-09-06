# Resultado: ¿predicen algo los pilares fundamentales?

La pregunta cambió a mitad de sesión, y con motivo. La validación de salidas
(`docs/resultado_validacion_salidas.md`) dejó claro dos veces, con universos y
diseños distintos, que ninguna regla de salida bate a aguantar. Reconstruir los
pilares para alimentar una regla de venta ya no tenía sentido.

La pregunta útil es la contraria: **¿sirven para SELECCIONAR?**

## Cómo se midió

**740 observaciones point-in-time** sobre **79 grandes capitalizaciones**, cada
una situada el día siguiente a la **fecha de presentación real** del informe
anual ante la SEC — que es cuando el mercado supo el dato, no el cierre del
ejercicio, que es entre uno y tres meses antes.

`_filtrar_columnas_por_filing_date` descarta además los ejercicios cuya fecha de
presentación se desconoce, en lugar de asumir que ya estaban disponibles.

Los signos esperados se declararon **antes** de mirar los resultados
(`validacion_pilares.SIGNO_ESPERADO`), para no poder celebrar cualquier
correlación mirando después qué signo salió.

---

## MEDIDO · correlación de Spearman con el retorno posterior

| Pilar | Signo esperado | 63 días | 126 días | 252 días |
|---|---|---|---|---|
| **Altman Z''** | positivo | +0,047 ✓ | +0,087 ✓ | **+0,119 ✓** |
| Beneish M | negativo | −0,098 ✓ | +0,027 ✗ | −0,170 ✓ |
| Piotroski (bruto) | positivo | −0,017 ✗ | −0,032 ✗ | −0,045 ✗ |
| Piotroski (normalizado) | positivo | +0,002 ✓ | −0,055 ✗ | −0,034 ✗ |
| Percentil de múltiplos | negativo | n/d | n/d | n/d |

### Retorno a 252 sesiones por quintil de Altman Z''

| Quintil | n | Altman medio | Retorno medio | Retorno mediano |
|---|---|---|---|---|
| 1 (peor) | 60 | 0,64 | 16,79% | 15,85% |
| 2 | 59 | 1,88 | 15,00% | 10,74% |
| 3 | 59 | 3,05 | 19,67% | 18,70% |
| 4 | 59 | 5,40 | 23,99% | 17,40% |
| **5 (mejor)** | 60 | 9,09 | **26,66%** | **27,20%** |

### Retorno a 252 sesiones por quintil de Piotroski

| Grupo | n | Piotroski medio | Retorno medio |
|---|---|---|---|
| 1 | 149 | 42,2 | 20,20% |
| 2 | 153 | 62,6 | 20,82% |
| 3 | 105 | 73,7 | 20,63% |
| **4 (mejor)** | 256 | 92,8 | **15,79%** |

---

## INTERPRETACIÓN

**Altman Z'' es el único pilar con poder predictivo limpio.** Signo correcto en
los tres horizontes, creciendo con el plazo —lo que se espera de una señal
fundamental, que tarda en reflejarse— y un reparto por quintiles **monótono**:
casi 10 puntos de diferencia anual entre el quintil más solvente y el menos.
Esto no es una regla de venta: es un criterio de **selección**, y ahí sí aporta.

**Piotroski no predice nada, y si acaso va al revés.** El quintil de F-Score más
alto es el de PEOR retorno posterior (15,79% frente a 20,20% del más bajo). Una
lectura posible: entre grandes capitalizaciones, un F-Score alto identifica
empresas cuya solidez el mercado **ya ha puesto en precio**. Es interpretación,
no medición.

**Beneish es inconsistente.** Signo correcto a 63 y 252 días, invertido a 126.
Mi propio criterio pre-declarado dice que un efecto que aparece en un horizonte
y no en los vecinos es ruido, así que **no se declara hallazgo**.

**El percentil de múltiplos nunca fue computable**: exige cinco ejercicios de
histórico reconstruido, y tras filtrar por fecha de presentación rara vez quedan
cinco.

---

## Límites

- **Tamaño del efecto pequeño.** Un rho de 0,12 explica muy poca varianza. Lo
  que sostiene el hallazgo de Altman no es la correlación sino la **monotonía
  del reparto por quintiles**, que es lo operativamente útil.
- **Observaciones no independientes.** 740 observaciones son ~9 por empresa, y
  todas las grandes capitalizaciones de una misma década comparten beta de
  mercado. Spearman asume independencia: **los intervalos reales son bastante
  más anchos** que lo que sugiere la n.
- **Sesgo de supervivencia.** Son empresas que llegaron vivas al final de la
  década. Justo el tipo de sesgo que favorece a un indicador de solvencia como
  Altman: las que quebraron no están.
- **Una sola década, un solo mercado**, y mayoritariamente alcista.
- **Sin corrección por comparaciones múltiples.** Se miraron 5 pilares × 3
  horizontes = 15 contrastes. A ese nivel, encontrar uno con signo consistente
  por azar no es improbable. **Altman merece confirmación en el registro
  forward antes de darlo por bueno.**

---

## Qué hacer con esto

1. **No** convertirlo en una regla automática. El tamaño del efecto y el número
   de contrastes no lo justifican.
2. Sí tratarlo como hipótesis con apoyo: la solvencia medida por Altman Z''
   parece ordenar el retorno a un año entre grandes capitalizaciones.
3. La confirmación llega del **registro forward** (`jobs/congelar_decisiones.py`),
   iniciado el 2026-09-06, que guarda estos mismos sub-scores antes de conocer
   el retorno. Es la única vía sin sospecha de contaminación.
