# Pre-registro: ¿queda selección después de descontar el riesgo?

**Escrito y commiteado ANTES de ejecutar nada.** Tercer pre-registro de esta
línea, tras `preregistro_validacion_salidas.md` (`5ac928b`) y
`preregistro_eje_riesgo.md` (`1a664f4`).

## Qué pregunta responde

`rendimiento_cartera` midió que la cartera bate al índice en bruto (+30%) pero
**no en riesgo-ajustado**: Sharpe 1,214 frente a 1,266 del índice, casi el doble
de volatilidad (25,8% frente a 13,6%) y el **89% del exceso concentrado en una
sola posición**.

Un exceso de retorno se puede conseguir de dos maneras muy distintas: eligiendo
mejor (alfa) o asumiendo más riesgo de mercado (beta). Un +30% con beta 1,8 no es
selección: es el índice apalancado. Esta sesión separa las dos cosas.

## Dónde vive

**Módulo compañero `modulos/rendimiento_riesgo.py`**, no una extensión de
`rendimiento_cartera`. Tres razones: aquel ya ronda las 700 líneas y hace un
trabajo distinto; este consume su salida, así que la dependencia va en una sola
dirección; y mantiene intacto el módulo ya validado con su test de aceptación.

## Tipo libre de riesgo

**`XEON.DE`** (Xtrackers €STR, de acumulación, cotizado en EUR). Su serie de
precio *es* el retorno libre de riesgo en euros, con la misma convención de
retorno total que el resto. Verificado antes de fijarlo: 763 sesiones, 2,86%
anualizado y **0,237% de volatilidad anualizada** — efectivamente sin riesgo.

No se usa `^TNX` pese a existir ya en `charts.obtener_risk_free_real`: es el bono
estadounidense a 10 años, en dólares y con duración. Aplicarlo a una cartera en
euros sería el mismo desajuste de divisa que ya nos costó una corrección en el FX.

**El mismo tipo se aplica a los dos lados**, así que en la comparación de excesos
se cancela casi por completo y la conclusión no depende de haberlo elegido bien.

## Métricas

- **Vol-matched**: `k = σ_cartera / σ_benchmark` sobre retornos de exceso;
  `r_vm(t) = r_f(t) + k·(r_bench(t) − r_f(t))`. Comparación en CAGR y valor
  terminal. **Es una lente analítica, no una estrategia**: un ETF no se apalanca
  al tipo libre de riesgo sin coste ni margen.
- **CAPM**: `r_p − r_f = α + β·(r_b − r_f) + ε`. Alfa anualizado, beta, R².
- **Information Ratio**: retorno activo / tracking error, ambos anualizados.
- **Descomposición** del exceso en beta, alfa e idiosincrático, que debe sumar
  el exceso total.
- **Concentración**: Herfindahl sobre el |alfa| por posición, y recálculo
  completo excluyendo la mayor.

## Intervalos de confianza

**Bootstrap por bloques móviles**, no t de Student. Los retornos diarios están
autocorrelacionados y tienen colas gordas; un IC gaussiano sería artificialmente
estrecho justo donde más importa no engañarse.

- Longitud de bloque: **10 sesiones** (dos semanas de mercado). Regla habitual
  n^(1/3); con ~670 sesiones da 8,7, y se redondea a 10.
- **10.000 remuestreos**, IC del 95% por percentiles.

## Criterio de evidencia (fijado ahora, no se mueve)

Hay **evidencia de selección** solo si se cumplen **las tres**:

- **(a)** El alfa anualizado tiene su **IC del 95% por bootstrap enteramente por
  encima de 0**.
- **(b)** El benchmark **vol-matched rinde MENOS** que la cartera (CAGR).
- **(c)** La conclusión **sobrevive a excluir la mayor posición**: el alfa
  puntual sigue siendo positivo y el vol-matched sigue rindiendo menos.

Si falla cualquiera → **«insuficiente evidencia»**, y se dirá con esas palabras.
No «casi», no «tendencia favorable».

## Lo que ya espero encontrar, dicho antes

Con **3 posiciones** y **~2 años**, la beta será alta y el IC del alfa muy ancho.
**Es casi seguro que cruce cero**, y entonces la respuesta será «insuficiente
evidencia» aunque el alfa puntual salga grande y positivo. Eso no es un fallo del
método: es la muestra que hay. Dejarlo escrito de antemano evita la tentación de
leer un alfa puntual bonito como si fuera un hallazgo.

## Compromisos

- No se cambia el tipo libre de riesgo, ni la longitud de bloque, ni la ventana,
  después de ver resultados.
- Todos los retornos salen de la **serie unitizada (TWR)**. Sobre la serie de
  valor, cada aportación parecería un retorno gigante y contaminaría regresión,
  volatilidad y bootstrap a la vez.
- El resultado se publica sea cual sea. **«No hay evidencia» es un entregable
  válido**, y con esta muestra es el desenlace más probable.

## Límites conocidos de antemano

- **n = 3 posiciones.** Cualquier estadístico de sección cruzada sobre tres
  nombres es anecdótico.
- **~2 años y un solo régimen** mayoritariamente alcista.
- **Sesgo de supervivencia del propio inversor**: la cartera contiene lo que se
  compró y se mantuvo, no lo que se vendió por el camino.
- El vol-matched **ignora costes de financiación reales** y el efecto del
  rebalanceo diario del apalancamiento (*volatility drag*).

---

Fecha de pre-registro: 2026-09-06 · Rama: `rediseno-ui-tecnologica`
