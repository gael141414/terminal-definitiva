# Resultado: las reglas de salida sobre entradas reales

Ejecución del pre-registro de `docs/preregistro_validacion_salidas.md`, que se
commiteó **antes** de correr nada (commit `5ac928b`).

Universo: 110 valores con datos de 121 solicitados · 10 años · **7.212 entradas
reales** generadas por el catálogo de estrategias · 36.060 cierres simulados ·
coste 0,1% por lado aplicado por igual a las cinco reglas.

---

## MEDIDO

| Regla | Retorno medio | IC95 | Expectativa (R) | Acierto | Días | Salidas anticipadas |
|---|---|---|---|---|---|---|
| **Aguantar** | **+1,44%** | [0,92 · 2,03] | **+0,199** | 51,9% | 23,3 | 0% |
| Técnica | +1,44% | [0,92 · 2,02] | +0,200 | 52,0% | 23,1 | **0,7%** |
| Stop fijo −8% | +0,78% | [0,43 · 1,16] | +0,142 | 43,3% | 16,3 | 40,4% |
| Compuesta | +0,79% | [0,44 · 1,17] | +0,144 | 43,5% | 16,2 | 40,9% |
| Aleatoria | +0,34% | [0,05 · 0,64] | +0,074 | 50,0% | 12,1 | 94,2% |

### Diferencia frente a aguantar, emparejada por operación

| Regla | Diferencia | IC95 | Veredicto |
|---|---|---|---|
| Técnica | −0,004 pts | [−0,042 · +0,031] | **no significativa** |
| Compuesta | −0,658 pts | [−1,110 · −0,290] | **significativa, peor** |
| Stop fijo | −0,660 pts | [−1,112 · −0,290] | **significativa, peor** |
| Aleatoria | −1,105 pts | [−1,530 · −0,731] | significativa, peor |

Emparejada porque las cinco reglas se aplican a las mismas entradas: la
diferencia por operación tiene mucha menos varianza que la diferencia de medias.

### Las tres hipótesis pre-registradas

| # | Hipótesis | Resultado |
|---|---|---|
| 1 | Alguna regla supera a aguantar | **REFUTADA.** Ninguna. La técnica empata; el resto pierde. |
| 2 | El beneficio se concentra en régimen bajista (Kaminski-Lo) | **REFUTADA, y del revés.** La compuesta pierde −0,59 pts en alcista y **−1,24 en bajista**. |
| 3 | Aporta más sobre entradas malas | **REFUTADA, y del revés.** Donde más daño hace es en `ruptura_maximos` (−1,93 pts), la entrada con peor expectativa fuera de muestra. |

### Walk-forward por año de entrada

Siete de diez años en negativo; los tres positivos (2017, 2022, 2025) no son
significativos. **No hay estabilidad temporal en ninguna dirección.**

---

## INTERPRETACIÓN

**La regla técnica no es mala: es inerte.** Se dispara en el **0,7%** de las
operaciones. No puede batir a aguantar porque prácticamente nunca actúa. Esto
replica exactamente lo que ya documentaba `swing_salidas.RESULTADO_VALIDACION`
(0,9% de activación) sobre otras 2.377 operaciones y con otro diseño. Dos
mediciones independientes llegando al mismo sitio.

**Todo el daño viene del stop de −8%**, que corta el 40% de las operaciones. La
compuesta y el stop fijo dan resultados casi idénticos porque, en la práctica,
la compuesta *es* el stop.

**Por qué la hipótesis de Kaminski-Lo sale invertida.** Interpretación, no
medición: en régimen bajista las caídas del 8% son en buena medida movimiento
del índice, no deterioro del valor. El stop cristaliza la pérdida justo cuando
la recuperación viene con el mercado. Kaminski y Lo describen el beneficio del
stop bajo momentum con autocorrelación positiva; este universo y este periodo
—diez años de mercado alcista estadounidense— tienen deriva positiva y reversión
en los retrocesos, que es el régimen contrario.

**Este backtest ya no está sesgado contra las salidas por el motivo anterior**
(entradas sintéticas ≈ paseo aleatorio) porque las entradas son las que genera
la aplicación. Pero sigue teniendo la deriva alcista del periodo en contra.

---

## Lo que esto cambia en el producto

1. El stop duro **ya no fuerza la venta en perfil de largo plazo** desde la
   sesión anterior; esta medición lo confirma con entradas reales y con IC.
2. La pantalla de decisión de venta mantiene su advertencia. Es un panel de
   diagnóstico, no una orden.
3. **No se toca ningún parámetro de salida** para mejorar estos números. Era el
   compromiso del pre-registro y se cumple.

---

## Límites, con nombre y apellidos

- **Sesgo de supervivencia.** El universo son empresas que hoy cotizan.
  `survivorship_universe` tiene 3 casos curados (BBBY, SHLD, TOYS) pero **sin
  precios fiables de deslistadas** — ya documentado en `return_crossing.py:257`.
  Las quiebras son justo donde una salida ayudaría, así que este sesgo va EN
  CONTRA de las salidas: el resultado negativo es un suelo, no un techo. Si se
  consiguieran precios de deslistadas, las salidas podrían mejorar.
- **Dos métricas retiradas.** CAGR y max drawdown estaban en el pre-registro y
  **no son computables con este diseño**: anualizar el retorno de una operación
  de tres días eleva a la 84 y da 1e11; encadenar 7.000 operaciones solapadas
  como una cuenta reinvertida da −100% siempre. Publicar esos números habría
  sido peor que no publicarlos. Es un defecto de la medición, no del resultado,
  y se declara aquí porque estaban pre-registrados.
- **Solo el pilar técnico.** Valoración y fundamentales no se pueden reconstruir
  en cada fecha de entrada sin datos point-in-time por fecha. La "compuesta" de
  este backtest es técnica + stop.
- **Operaciones no independientes.** Varias entradas del mismo mes comparten
  régimen; el bootstrap sobre operaciones asume independencia y por tanto los
  IC reales son **más anchos** que los publicados.
- **Solo posiciones largas.** Las tres estrategias cortas del catálogo quedan
  fuera: las reglas comparadas están definidas para largos.

---

## Qué sigue sin estar validado

Los pilares de **valoración (A)** y **fundamentales (B)** de `decision_venta`.
La vía correcta está montada y comprobada (ver `docs/` y el Paso 0 de esta
sesión): `point_in_time_scoring` reconstruye fundamentales por fecha de filing
real, y se verificó en vivo que FMP y SEC EDGAR devuelven las mismas fechas.
Queda pendiente ejecutarlo a escala.

Mientras tanto, la vía principal es el **registro forward**
(`jobs/congelar_decisiones.py`), iniciado el **2026-09-06**, que guarda cada
decisión y sus tres sub-scores antes de conocer el retorno posterior. Ninguna
reconstrucción del pasado puede ofrecer esa garantía.
