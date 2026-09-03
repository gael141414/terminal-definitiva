# Pre-registro: validación de las reglas de salida sobre entradas reales

**Escrito y commiteado ANTES de ejecutar nada.** Si el resultado no sale como se
espera, se publica igual. Este documento existe para que eso sea comprobable en
el historial de git, no solo prometido.

## Por qué se repite la validación

El backtest anterior (`scripts/backtest_decision_venta.py`) usó **entradas
sintéticas**: comprar el primer día hábil de cada mes. Ese diseño está sesgado
en contra de las salidas por construcción. Entradas arbitrarias se aproximan a
un paseo aleatorio, y bajo paseo aleatorio una regla de stop tiene esperanza
negativa: corta la cola izquierda pero también la derecha, y paga el coste
(Kaminski y Lo, *When Do Stop-Loss Rules Stop Losses?*, 2014).

Una regla de salida solo puede ganarse el sueldo sobre una población que
contenga **posiciones genuinamente malas que cortar**. Esta validación se monta
sobre las entradas que genera la propia aplicación.

## Hipótesis pre-registrada

1. **Principal.** Sobre entradas reales, al menos una regla de salida supera a
   aguantar hasta el horizonte en expectativa por operación.
2. **Kaminski-Lo.** El beneficio de salir se concentra en regímenes bajistas y
   de corrección, y desaparece o se invierte en régimen lateral/alcista.
3. **Por calidad de entrada.** El beneficio es mayor sobre estrategias con
   expectativa fuera de muestra negativa (`ruptura_maximos`, cortas) que sobre
   las validadas (`canslim`, `pullback_tendencia`, `pead`).

Si las tres se refutan, la conclusión es que la gestión activa de salida no
aporta en este sistema, y se dirá con esas palabras.

## Población

Las **8 estrategias** del catálogo (`modulos/swing_estrategias.py`), reportadas
por separado y agregadas. Se incluyen a propósito las tres no validadas: son la
población de entradas malas donde la hipótesis 3 se juega.

Las entradas las genera `swing_backtest.backtest_estrategia`, que ya existe y
está probado. No se crea un generador nuevo.

## Los cinco benchmarks

Todos sobre **exactamente las mismas entradas**, mismo horizonte y mismo coste:

| # | Regla | Definición |
|---|---|---|
| 1 | Aguantar | Cerrar al horizonte fijo, sin tocar nada. Es el listón real. |
| 2 | Aleatoria | Cerrar en una sesión al azar, con la **misma distribución de duraciones** que la regla técnica. Controla que salir a menudo no parezca bueno solo por reducir tiempo en mercado. |
| 3 | Stop fijo | Cerrar si el precio cae un 8% desde la entrada. |
| 4 | Regla técnica | `swing_salidas.evaluar_salida`. |
| 5 | Decisión compuesta | `decision_venta.evaluar_posicion`, con overrides. |

## Métricas

Retorno medio · CAGR · hit rate · expectancy por operación (en R y en %) ·
max drawdown · Sharpe · Sortino · días medios en posición · turnover anualizado.
Coste de transacción **0,1% por lado**, aplicado a todas las reglas por igual.

**Intervalos de confianza del 95% por bootstrap** (10.000 remuestreos sobre las
operaciones). Una diferencia cuyo IC cruza el cero **no se declara diferencia**.

## Partición temporal

Walk-forward: el histórico se divide en ventanas consecutivas. Los parámetros de
salida **no se ajustan en ninguna**: son los que ya están en `config.py` desde
antes de esta validación. La partición sirve para comprobar estabilidad, no para
seleccionar.

## Compromisos anti-overfitting

- **No se toca ningún parámetro de salida** para mejorar el resultado. Ni el
  stop, ni el múltiplo del chandelier, ni los umbrales del sell score.
- No se prueban variantes y se reporta la mejor.
- No se cambia el horizonte ni el coste después de ver resultados.
- Si la conclusión es negativa, se escribe en el README y en la pantalla.

## Límites conocidos de antemano

- **Sesgo de supervivencia.** El universo es de empresas que hoy cotizan.
  `modulos/survivorship_universe.py` tiene 3 casos curados (BBBY, SHLD, TOYS)
  pero sin precios fiables de deslistadas — ya documentado en
  `return_crossing.py`. Las quiebras son justo donde una salida ayudaría, así
  que **este sesgo va en contra de las salidas** y cualquier resultado positivo
  es un suelo, no un techo.
- **Solo pilares técnicos.** Los pilares de valoración y fundamentales de
  `decision_venta` no se pueden reconstruir sin datos point-in-time por cada
  fecha de entrada. La decisión compuesta se evalúa con el pilar técnico y los
  overrides de precio.
- **Correlación entre operaciones.** Varias entradas del mismo mes comparten
  régimen de mercado; el bootstrap sobre operaciones independientes subestima
  la incertidumbre real.

---

Fecha de pre-registro: 2026-09-03 · Rama: `rediseno-ui-tecnologica`
