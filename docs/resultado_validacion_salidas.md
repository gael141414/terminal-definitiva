# Resultado: las reglas de salida sobre entradas reales

Ejecución del pre-registro de `docs/preregistro_validacion_salidas.md`, que se
commiteó **antes** de correr nada (commit `5ac928b`).

Universo A (alfabético, defectuoso — ver abajo): 110 valores de 121 solicitados · 10 años · **7.212 entradas
reales** generadas por el catálogo de estrategias · 36.060 cierres simulados ·
coste 0,1% por lado aplicado por igual a las cinco reglas.

---

## Un defecto de universo que encontré a mitad de camino, y cómo lo corregí

La primera ejecución usó `_universo_mercado(120)`, que **no devuelve los 120
valores mayores**: devuelve los 120 primeros de una lista **alfabética** — A, AA,
AACG, AADX, AAGH… Un corte dominado por microcaps y sociedades vacías, que no se
parece a lo que se analiza con esta aplicación y donde además el coste real de
operar es muy superior al 0,1% que asume el backtest.

Lo detecté al ver nombres como «Antiaging Quantum Living» y «Prevention
Insurance» en los registros de la SEC. **Es un defecto mío, no del código
existente**, y afectaba a los dos estudios de esta sesión.

Así que repetí todo sobre `screener_avanzado.FALLBACK_UNIVERSE`: 119 grandes
capitalizaciones en 11 sectores. **La conclusión no solo sobrevive: se refuerza**,
porque la muestra pasa de 7.212 a 27.541 entradas. Se publican las dos.

---

## MEDIDO

| Regla | Retorno medio | IC95 | Expectativa (R) | Acierto | Días | Salidas anticipadas |
|---|---|---|---|---|---|---|
| **Aguantar** | **+1,44%** | [0,92 · 2,03] | **+0,199** | 51,9% | 23,3 | 0% |
| Técnica | +1,44% | [0,92 · 2,02] | +0,200 | 52,0% | 23,1 | **0,7%** |
| Stop fijo −8% | +0,78% | [0,43 · 1,16] | +0,142 | 43,3% | 16,3 | 40,4% |
| Compuesta | +0,79% | [0,44 · 1,17] | +0,144 | 43,5% | 16,2 | 40,9% |
| Aleatoria | +0,34% | [0,05 · 0,64] | +0,074 | 50,0% | 12,1 | 94,2% |

### Universo de grandes capitalizaciones (119 valores, 27.541 entradas)

| Regla | Retorno medio | IC95 | Expectativa (R) | Acierto | Días | Salidas anticipadas |
|---|---|---|---|---|---|---|
| **Aguantar** | **+1,12%** | [1,01 · 1,22] | **+0,276** | 55,6% | 22,8 | 0% |
| Técnica | +1,10% | [1,00 · 1,21] | +0,275 | 55,7% | 22,7 | 0,6% |
| Stop fijo −8% | +0,83% | [0,74 · 0,93] | +0,237 | 52,2% | 19,5 | 23,4% |
| Compuesta | +0,82% | [0,73 · 0,92] | +0,236 | 52,3% | 19,4 | 23,9% |
| Aleatoria | +0,43% | [0,35 · 0,50] | +0,135 | 53,0% | 11,9 | 94,6% |

Con este universo, **todas las reglas son significativamente peores que
aguantar**, incluida la técnica (−0,013 pts, IC [−0,027, −0,002]). Su daño es
minúsculo, pero con 27.541 operaciones el intervalo ya excluye el cero.

Por régimen: bajista **−0,880** frente a alcista −0,221. La hipótesis de
Kaminski-Lo vuelve a salir **invertida**, ahora con más muestra.

Por estrategia: peor en `ruptura_maximos` (−0,556) y `squeeze_disparo` (−0,563);
menos malo en `reversion_rsi2` (−0,085). La hipótesis 3 también vuelve a salir
invertida.

**Walk-forward: nueve de diez años negativos y significativos.** El único
positivo es **2020 (+0,464 pts)**, el año del desplome del COVID. Ese matiz
importa y es lo más cerca que está el resultado de rescatar la intuición del
stop: en el desplome más rápido de la década, salir pagó. En los otros nueve
años costó dinero. Un seguro que se cobra una vez cada diez años tiene que
compensar nueve de primas, y aquí no lo hace.

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
