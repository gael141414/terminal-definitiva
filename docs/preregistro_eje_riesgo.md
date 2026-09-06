# Pre-registro: el eje de riesgo de las reglas de salida

**Escrito y commiteado ANTES de ejecutar nada.** Segundo pre-registro de esta
línea de trabajo; el primero (`preregistro_validacion_salidas.md`, commit
`5ac928b`) cubría el eje de retorno.

## Qué pregunta responde

La Tarea 1 ya dictaminó sobre la media: ninguna regla de salida bate a aguantar.
Pero nueve de diez años negativos y **solo 2020 positivo** apunta a que las
salidas se comportan como una **cobertura de cola**: pagan en el desplome y
restan el resto del tiempo.

La media no decide eso. Hace falta el otro eje: si la prima que se cede compra
suficiente reducción de caída. El objetivo es convertir *«las salidas pierden de
media»* en *«las salidas cuestan X puntos al año y a cambio recortan Y puntos de
drawdown»*, y emitir un veredicto.

## Construcción de cartera (pre-declarada)

Drawdown y volatilidad exigen una curva de equity, no una media por operación.
Construcción **idéntica para las cinco reglas**; lo único que cambia es cuándo
sale cada posición:

- **Equiponderada por posición abierta.** En cada sesión, el retorno de la
  cartera es la media simple de los retornos diarios de las posiciones abiertas
  ese día.
- **Sin apalancamiento.** Las sesiones sin ninguna posición abierta rinden 0
  (efectivo), no se rellenan con el índice.
- **Marcada a mercado a diario**, no solo al cierre de la operación.
- **Costes ya incluidos**: 0,1% por lado, los mismos de la Tarea 1, aplicados en
  la sesión de entrada y en la de salida.
- **Sensibilidad**: se reporta también con peso fijo del 2% por operación. Si
  las dos construcciones dan veredictos distintos, el veredicto es «depende de
  la construcción» y se dice así.

## Métricas de riesgo

**Curva y caída**: máximo drawdown (profundidad y duración en sesiones),
volatilidad anualizada, downside deviation.

**Ratios ajustados**: Sharpe, Sortino, Calmar (CAGR/maxDD), Ulcer Index.

**Cola**: percentiles 5 y 1 de la distribución de retorno por operación,
CVaR al 5% (Expected Shortfall), peor operación, y MAE — máxima excursión
adversa dentro de la operación.

**Forma completa**: media, mediana, asimetría y curtosis.

Todas con **intervalo de confianza del 95% por bootstrap**.

## Criterio de decisión (fijado ahora, no se mueve)

La regla compuesta —o el stop fijo— se declara **seguro que merece la pena** si
cumple **al menos una** de estas dos condiciones frente a aguantar:

**(A) Dominancia ajustada a riesgo.** Mejoran **a la vez**: Calmar, Sortino y
CVaR al 5%, y además el maxDD es menor.

**(B) Canje aceptable.** Recorta **≥ 3 puntos de maxDD por cada punto de retorno
medio anualizado cedido**, y además el CVaR al 5% mejora.

Si no cumple ninguna, se declara **seguro caro** y así se escribe.

*Por qué 3:1.* Un inversor averso a caídas con aversión al riesgo típica cambia
en torno a 2-4 puntos de reducción de caída por cada punto de retorno esperado.
3:1 está en el centro de ese rango y es defendible en ambas direcciones. Se fija
ahora, antes de ver ningún número, precisamente para no poder elegirlo después.

**Sub-veredicto de evento, separado**: cuánto recortó exactamente la compuesta el
drawdown durante el episodio COVID de 2020. Ahí está toda la tesis del seguro, y
se reporta aparte del veredicto agregado para que no se contaminen.

## Compromisos

- **Ni un parámetro de salida tocado.** Ni el stop, ni el múltiplo del
  chandelier, ni los umbrales del sell score.
- Mismas entradas, mismas reglas y mismos costes que la Tarea 1.
- El resultado se reporta sea cual sea. **Que la compuesta tampoco gane en
  riesgo-ajustado es un entregable válido**, no un fracaso.
- Todas las métricas con y sin 2020, para que se vea qué parte del resultado
  depende de un solo año.

## Límites conocidos de antemano

- **Sesgo de supervivencia.** Universo de empresas vivas hoy. Va EN CONTRA de
  las salidas, así que un resultado favorable a ellas sería un suelo.
- **Operaciones solapadas y no independientes.** El bootstrap sobre operaciones
  asume independencia; los intervalos reales son más anchos.
- **Una sola década**, mayoritariamente alcista, y un solo episodio de crash
  severo. El sub-veredicto COVID descansa sobre **n=1 evento**: no puede
  generalizarse por muchos datos diarios que tenga dentro.

---

Fecha de pre-registro: 2026-09-06 · Rama: `rediseno-ui-tecnologica`
