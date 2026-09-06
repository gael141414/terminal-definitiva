# Changelog

Todos los cambios relevantes de ValueQuant Terminal se documentan en este archivo.

El formato sigue una estructura práctica inspirada en Keep a Changelog y versionado semántico interno. Mientras el producto siga en prototipo local, las versiones se marcan como `internal`.

## [0.5.0-internal] - 2026-09-06

### Added

- Eje de riesgo de las reglas de salida (`modulos/riesgo_salidas.py`,
  `scripts/riesgo_salidas_informe.py`): construcción de cartera a partir de operaciones
  solapadas, maxDD con duración, Sortino, Calmar, Ulcer, CVaR5, MAE, asimetría y curtosis,
  todo con IC por bootstrap. No existía ninguna de estas primitivas en el repositorio.
- Tres gráficas en `docs/img/`: curvas de capital, curvas de drawdown con el episodio COVID
  marcado, y distribución por operación con la cola señalada.

### Evidencia

- **Veredicto según criterio pre-registrado: las salidas son un seguro caro.** El canje sale
  NEGATIVO en la construcción principal (−0,89 puntos de maxDD por punto de CAGR cedido): se
  paga la prima y además se recibe más caída.
- **En el episodio COVID, donde el seguro debía pagar, cobró**: la compuesta casi dobló la
  pérdida (−23,1% frente a −12,8% de aguantar) y cayó más hondo.
- Hallazgo metodológico: **cortar la cola por operación no es cortar el drawdown de cartera.**
  El CVaR5 de la compuesta mejora a la mitad y su peor operación pasa de −71% a −15%, y aun así
  el drawdown de la cartera empeora.
- Con peso fijo del 2% el criterio B pasa por dos centésimas (3,08 frente a 3,00), por un efecto
  de construcción de cartera —el capital liberado va a efectivo— y no por acierto de la regla.

## [0.4.0-internal] - 2026-09-06

### Added

- Validación point-in-time de los pilares fundamentales (`modulos/validacion_pilares.py`,
  `scripts/validar_pilares_point_in_time.py`): 740 observaciones sobre 79 grandes
  capitalizaciones, situadas el día siguiente a la fecha de presentación real ante la SEC.
- Vocabulario XBRL en `forense_scores`, para que las tres métricas funcionen sobre datos
  as-reported además de sobre los esquemas de yfinance y FMP.

### Fixed

- **`_universo_mercado(N)` devuelve los N primeros de una lista alfabética**, no los N mayores.
  Los estudios se repitieron sobre 119 grandes capitalizaciones; la conclusión sobre las salidas
  se refuerza (27.541 entradas, todas las reglas significativamente peores que aguantar).
- La reconstrucción point-in-time no leía nada, por tres fallos encadenados: `usar_cache=True`
  perdía los `filing_dates` (viajan en `.attrs`), las columnas de metadatos de EDGAR se colaban
  al convertir a número, y EDGAR y FMP nombran el mismo concepto distinto
  (`us-gaap_AssetsCurrent` frente a `assetscurrent`).

### Evidencia

- **Altman Z'' predice el retorno posterior** entre grandes capitalizaciones: signo correcto en los
  tres horizontes y reparto monótono por quintiles (16,8% a 26,7% anual). Es un criterio de
  SELECCIÓN, no de venta.
- **Piotroski no predice**, y el quintil más alto es el de peor retorno.
- Beneish es inconsistente entre horizontes: por el criterio pre-declarado, ruido.

## [0.3.0-internal] - 2026-09-06

### Added

- Validación de reglas de salida sobre **entradas reales** (`modulos/backtest_salidas.py`,
  `scripts/backtest_salidas_entradas_reales.py`), pre-registrada en
  `docs/preregistro_validacion_salidas.md` y con resultado en `docs/resultado_validacion_salidas.md`.
- Registro **forward** de decisiones (`modulos/congelado_forward.py`, `jobs/congelar_decisiones.py`),
  iniciado el 2026-09-06: guarda cada decisión y sus tres sub-scores antes de conocer el retorno.
- `forense_scores.normalizar_estados`, que acepta las dos orientaciones de estados financieros
  que conviven en el repositorio.

### Fixed

- **El pilar de fundamentales no se calculaba nunca en producción.** El respaldo de yfinance
  entrega las fechas en el índice y los conceptos en columnas, al revés de lo que espera
  `forense_scores`. No fallaba nada: las métricas salían no evaluables y el pilar se omitía en
  silencio.
- **El pilar de valoración tampoco.** `reunir_datos` no rellenaba `fair_value`, margen de
  seguridad ni múltiplos, así que quedaba permanentemente sin evaluar.
- Choque de zona horaria entre precios (con tz) y fechas contables (sin tz) en el cálculo de
  múltiplos históricos, que afloró al ejecutarse ese camino por primera vez.

### Evidencia

- Sobre **7.212 entradas reales**: aguantar +1,44%, técnica +1,44% (diferencia −0,004 pts, IC95
  [−0,042, +0,031], **no significativa**), compuesta y stop fijo −0,66 pts (**significativamente
  peores**). Las tres hipótesis pre-registradas quedan **refutadas**, dos de ellas del revés.
- La regla técnica se dispara en el 0,7% de las operaciones: es inerte, no dañina. Replica lo que
  ya medía `swing_salidas` (0,9%) con otro diseño y otra muestra.
- CAGR y max drawdown se retiran por no ser computables con este diseño; el motivo se documenta.

## [0.2.0-internal] - 2026-09-03

### Added

- **Decisión de venta sobre posiciones abiertas** (`modulos/decision_venta.py`): dada una acción con
  precio y fecha de entrada, devuelve MANTENER / REDUCIR / VENDER, cuánto reducir y precios objetivo,
  combinando valoración, deterioro fundamental y técnica en un *sell score* con pesos por perfil.
- Métricas forenses como funciones puras (`modulos/forense_scores.py`): Altman Z y Z'', Beneish M y
  F-Score de Piotroski, que antes no existía. Estaban entrelazadas con el dibujo dentro de `charts.py`.
- Múltiplos en el percentil de su propia historia (`modulos/multiplos_historicos.py`), con retardo de
  publicación de 75 días para no contaminar la serie con información futura.
- Backtest honesto de la regla de salida (`scripts/backtest_decision_venta.py`) contra aguantar, venta
  aleatoria de igual frecuencia y solo-stop-fijo.
- Alertas de watchlist derivadas del veredicto de venta.

### Changed

- El stop duro de −8% deja de forzar la venta en el perfil de largo plazo y pasa a ser solo un aviso.
  **Medido**: aplicado a posiciones de un año rindió 11,03% frente al 36,31% de aguantar, con un 17,1%
  de acierto. Sigue decidiendo en swing, que es el horizonte para el que la regla se diseñó.

### Fixed

- Los datos contables ausentes se sustituían por `0.001` "para evitar divisiones por cero". Dividir
  entre 0,001 produce ratios de miles que se presentaban como puntuaciones legítimas: una empresa sin
  el dato de activos totales salía con un Altman Z enorme, es decir, **en zona segura**. Ahora devuelve
  `None` y enumera los campos que faltan.

### Evidencia

- La regla de salida bate a la venta aleatoria por 15,5 puntos sobre 4.199 operaciones (lleva
  información) pero **no bate a aguantar** (−0,55). Los pilares de valoración y fundamentales quedan
  **sin validar**: reconstruirlos sin look-ahead exige datos point-in-time que el repositorio no tiene.

## [0.1.0-internal] - 2026-07-08

### Added

- Research Core como superficie principal de decisión.
- ValueQuant Score con payload estructurado, trazabilidad, quality gates, red flags, confidence diagnostics y decision guidance.
- Integración del score en informes, watchlist, briefings y superficies de evolución.
- Watchlist con snapshots de análisis y seguimiento operativo.
- Backtesting básico de señales históricas `BUY`, `WATCH` y `AVOID`.
- Calibración de confianza predictiva cuando existe muestra histórica suficiente.
- UX ejecutiva del Research Core con ruta de análisis recomendada.
- Exportación institucional desde Research Core: Markdown, HTML imprimible, memo ejecutivo, metadata JSON y ZIP.
- Healthcheck local para entorno, configuración, imports, runtime dirs y secretos locales.
- Smoke tests estrictos con contratos críticos del producto.
- Release readiness gate para validar preparación interna antes de fusionar o entregar.
- Documentación final de uso y runbook de release.

### Changed

- El producto pasa de prototipo disperso a terminal local estabilizado para research financiero.
- La lectura del score queda explícitamente condicionada por cobertura, confianza, quality gates y validación manual.
- El flujo operativo recomendado queda documentado como: datos, análisis fundamental, score, tesis, watchlist, backtesting, exportación y QA.

### Quality

- CI verde en los sprints de estabilización, exportación, QA y documentación.
- Contratos locales para scoring, data quality, reportes, watchlist, backtesting, confidence calibration, Research Core UX, exportación institucional, release readiness y documentación.

### Limitations

- No constituye asesoramiento financiero personalizado.
- No garantiza rentabilidad.
- El backtesting básico no sustituye una validación histórica robusta con costes, liquidez, slippage y ventanas múltiples.
- La confianza predictiva depende de la disponibilidad de snapshots históricos suficientes.

## [0.1.0-internal] - 2026-07-09 (resiliencia Yahoo/yfinance + consolidación de datos)

Esta sección documenta trabajo que ya estaba mergeado en `main` (sprints 11b–11g)
pero nunca se había reflejado en el changelog, más la auditoría de estabilización
de esta fecha que corrige el problema real detectado en producción: la capa de
resiliencia existía pero no estaba conectada a los módulos que la app realmente
usa.

### Added (sprints 11b–11g, retroactivo)

- `modulos/yahoo_resilience.py` y `modulos/yfinance_global_guard.py`: helpers de resiliencia ante rate limits de Yahoo/yfinance.
- `sitecustomize.py`: guarda global instalado al arranque del intérprete sobre `yf.download`.
- Limpieza de imports/bloques `main` duplicados en `screener.py` (sprint final cleanup).
- Contratos dedicados: `test_yahoo_resilience_contract`, `test_yfinance_helper_migration_contract`, `test_charts_yfinance_resilience_contract`, `test_final_cleanup_contract`.

### Fixed (auditoría de estabilización 2026-07-09)

- **Causa raíz real de "la barra superior no muestra precios" y "las herramientas no obtienen datos"**: la capa de resiliencia de los sprints 11c–11g se había conectado a `screener.py`/`backtester.py`/`data_provider.py` en la raíz del repo, que la app de Streamlit nunca importa. Los módulos que el router sí usa (`modulos/screener.py`, `modulos/backtester.py`, `modulos/watchlist.py`, `charts.py` y otros 14 módulos) seguían haciendo llamadas directas y desprotegidas a `yf.Ticker(...).info/.history/.financials`, con `except: pass` que ocultaba el fallo real (rate limit, ticker inválido, error de red mostraban el mismo "sin datos").
- `modulos/yahoo_resilience.py`: nuevo `safe_yfinance_fetch()` genérico con reintento corto (backoff) ante rate limit — antes un único 429 era definitivo para todo el rerun de Streamlit, sin reintento alguno.
- Nuevo `modulos/quotes.py`: proveedor centralizado de cotizaciones por lote (`fetch_quotes_with_fallback`) con fallback a FMP cuando Yahoo falla, y etiqueta explícita `unsupported_symbol` para futuros/índices (oro, petróleo, VIX, US10Y) que no tienen equivalente fiable en FMP — en vez de fingir un fallback inexistente.
- Ticker tape (`modulos/market_widgets.py`): antes no tenía ningún fallback a FMP — si Yahoo fallaba, cada símbolo desaparecía en silencio y la cinta caía a un placeholder estático. Ahora usa el proveedor centralizado, muestra un estado explícito por símbolo ("Rate limit temporal de Yahoo", "Fuente no disponible para este instrumento") y ya no bloquea 15 minutos completos de caché tras un fallo total puntual (auto-limpieza de caché en fallo total).
- `charts.py` (1931 líneas): no tenía ni un solo `@st.cache_data` pese a hacer ~24 llamadas directas a `yf.Ticker`. Ahora las funciones de descarga de datos están cacheadas (15 min precios, 24h fundamentales) y enrutadas por la capa de resiliencia; las funciones de solo-graficado quedan sin caché por ser baratas.
- `modulos/watchlist.py`: refrescaba precios en un bucle serie por ticker, sin caché, en cada rerun de la pestaña. Ahora usa el proveedor centralizado en lote con caché de 5 minutos.
- Otros 14 módulos con llamadas directas a `yf.Ticker`/`.info` migrados a la capa de resiliencia: `company_data_helpers.py`, `etf.py`, `insiders.py`, `predictor.py`, `radar.py`, `screener_avanzado.py`, `relative_comparison.py`, `scoring_engine.py`, `macro.py`, `derivados.py`, `proyeccion.py`, `utils.py`, `minero_smallcaps.py`, `opportunity_briefing.py`.
- Screener Avanzado (`modulos/screener_avanzado.py`): disparaba el universo FMP + enriquecimiento Yahoo automáticamente en cada cambio de slider, sin botón de ejecución. Ahora requiere pulsar "Ejecutar Screener Avanzado", igual que el resto de herramientas pesadas.

### Quality

- 3 contratos de comportamiento nuevos: `test_data_layer_consolidation_contract` (verifica que los módulos realmente usados por la app —no los huérfanos de la raíz— usan la capa de resiliencia), `test_ticker_tape_fallback_contract` (verifica fallback FMP y auto-recuperación de caché), `test_watchlist_price_cache_contract` (verifica lote + caché).
- Suite de smoke tests: 199 → 211 checks; contratos de comportamiento: 25 → 28.
