"""Validación de reglas de salida sobre entradas REALES del sistema.

Por qué existe además de scripts/backtest_decision_venta.py
------------------------------------------------------------
Aquel backtest usaba entradas sintéticas (comprar el primer día hábil de cada
mes). Ese diseño está sesgado contra las salidas por construcción: entradas
arbitrarias se aproximan a un paseo aleatorio, y bajo paseo aleatorio una regla
de stop tiene esperanza negativa — corta la cola izquierda pero también la
derecha, y encima paga el coste (Kaminski y Lo, 2014).

Una regla de salida solo puede ganarse el sueldo sobre una población que
contenga posiciones genuinamente malas que cortar. Aquí las entradas las genera
el propio catálogo de estrategias, incluidas las tres NO validadas, que son
precisamente donde la hipótesis se juega.

Ver docs/preregistro_validacion_salidas.md: métricas, benchmarks e hipótesis
quedaron escritos y commiteados antes de ejecutar nada.

Convenciones, heredadas de swing_backtest para que los números sean comparables
--------------------------------------------------------------------------------
- Entrada en la APERTURA de la sesión siguiente a la señal.
- Riesgo por acción = 2·ATR (MULTIPLO_ATR_STOP), que define la unidad R.
- El stop gana los empates: sin datos intradía no se sabe el orden real dentro
  de la vela, y suponer lo contrario infla los resultados.
- Coste de transacción aplicado por igual a las cinco reglas.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import pandas as pd

from modulos.config import STOP_DURO_PCT, UMBRAL_VENDER
from modulos.decision_venta import COL_RSI, COL_SMA50, COL_SMA200
from modulos.indicadores import enriquecer_ohlcv
from modulos.swing_estrategias import ESTRATEGIAS_POR_ID, Estrategia
from modulos.swing_riesgo import MULTIPLO_ATR_STOP

LOGGER = logging.getLogger("valuequant.backtest_salidas")

__all__ = [
    "AGUANTAR", "ALEATORIA", "STOP_FIJO", "TECNICA", "COMPUESTA", "REGLAS",
    "Entrada", "Cierre", "Metricas",
    "generar_entradas", "aplicar_reglas", "calcular_metricas", "comparar_reglas",
    "COSTE_POR_LADO", "SEMILLA",
]

AGUANTAR = "aguantar"
ALEATORIA = "aleatoria"
STOP_FIJO = "stop_fijo"
TECNICA = "tecnica"
COMPUESTA = "compuesta"

# El orden es el del pre-registro. No se añaden reglas después de ver resultados.
REGLAS = (AGUANTAR, ALEATORIA, STOP_FIJO, TECNICA, COMPUESTA)

COSTE_POR_LADO = 0.001
SEMILLA = 20260903
REMUESTREOS_BOOTSTRAP = 10_000
CALENTAMIENTO = 210


# ==========================================================================
# POBLACIÓN DE ENTRADAS
# ==========================================================================


@dataclass(slots=True)
class Entrada:
    """Una posición abierta por una estrategia real, antes de decidir su salida."""

    ticker: str
    estrategia: str
    indice_entrada: int
    fecha_entrada: Any
    precio_entrada: float
    riesgo_accion: float          # 2·ATR: la unidad R
    horizonte: int
    direccion: str = "largo"

    @property
    def stop_atr(self) -> float:
        return self.precio_entrada - self.riesgo_accion


def generar_entradas(
    precios: dict[str, pd.DataFrame],
    estrategias: Sequence[Estrategia] | None = None,
    *,
    separacion_minima_dias: int = 5,
    desde: pd.Timestamp | None = None,
    hasta: pd.Timestamp | None = None,
) -> list[Entrada]:
    """Recorre el histórico buscando señales con las estrategias del catálogo.

    Solo se generan entradas LARGAS: las reglas de salida que se comparan están
    definidas para posiciones largas, y mezclarlas con cortas compararía cosas
    distintas bajo el mismo nombre.
    """
    from modulos.swing_estrategias import ESTRATEGIAS

    catalogo = list(estrategias) if estrategias is not None else list(ESTRATEGIAS)
    entradas: list[Entrada] = []

    for ticker, df in precios.items():
        if df is None or len(df) < CALENTAMIENTO + 40:
            continue
        try:
            enriquecido = df if COL_SMA200 in df.columns else enriquecer_ohlcv(df)
        except Exception as exc:
            LOGGER.debug("No se pudo enriquecer %s: %s", ticker, exc)
            continue

        for estrategia in catalogo:
            if estrategia.direccion != "largo":
                continue
            ultima = -10_000
            for i in range(CALENTAMIENTO, len(enriquecido) - 2):
                if i - ultima < separacion_minima_dias:
                    continue
                fecha = enriquecido.index[i]
                if desde is not None and fecha < desde:
                    continue
                if hasta is not None and fecha > hasta:
                    break
                # Misma interfaz que usa swing_backtest: evaluar(df, None, i)
                # devuelve una Senal con su propio ATR, o None. Se reutiliza tal
                # cual para que la población de entradas sea EXACTAMENTE la que
                # genera la aplicación, no una reimplementación parecida.
                try:
                    señal = estrategia.evaluar(enriquecido, None, i)
                except Exception:
                    continue
                if señal is None:
                    continue

                atr = getattr(señal, "atr", None)
                if atr is None or pd.isna(atr) or float(atr) <= 0:
                    continue
                apertura = enriquecido["Open"].iloc[i + 1]
                if pd.isna(apertura) or float(apertura) <= 0:
                    continue

                entradas.append(Entrada(
                    ticker=ticker,
                    estrategia=estrategia.id,
                    indice_entrada=i + 1,
                    fecha_entrada=enriquecido.index[i + 1],
                    precio_entrada=float(apertura),
                    riesgo_accion=MULTIPLO_ATR_STOP * float(atr),
                    horizonte=estrategia.horizonte_dias[1],
                ))
                ultima = i

    return entradas


# ==========================================================================
# LAS CINCO REGLAS DE SALIDA
# ==========================================================================


@dataclass(slots=True)
class Cierre:
    """Resultado de aplicar una regla a una entrada."""

    regla: str
    ticker: str
    estrategia: str
    fecha_entrada: Any
    retorno_neto: float           # fracción, coste ya descontado
    resultado_r: float
    dias: int
    motivo: str
    anticipada: bool
    # Necesarios para el eje de riesgo: la curva de equity exige saber cuándo
    # está abierta cada posición, y el MAE exige mirar dentro de la operación.
    fecha_salida: Any = None
    mae: float | None = None      # máxima excursión adversa, fracción negativa


def puntuacion_tecnica(df: pd.DataFrame, indice: int, regimen_favorable: bool | None = None) -> float | None:
    """Pilar técnico de decision_venta, evaluado en un índice concreto.

    Se calcula aquí y no llamando a ``decision_venta.evaluar_tecnico`` porque
    aquella recibe un DatosPosicion con el histórico recortado, y construir uno
    por cada barra de cada operación sería O(n²). Las reglas son las mismas y un
    test comprueba que ambas coinciden (test_backtest_salidas.py).
    """
    if indice >= len(df) or indice < 0:
        return None
    cierre = float(df["Close"].iloc[indice])
    if not np.isfinite(cierre):
        return None

    señales: list[float] = []
    for columna, castigo in ((COL_SMA50, 55.0), (COL_SMA200, 80.0)):
        if columna not in df.columns:
            continue
        media = df[columna].iloc[indice]
        if not pd.isna(media):
            señales.append(castigo if cierre < float(media) else 15.0)

    if COL_RSI in df.columns:
        rsi = df[COL_RSI].iloc[indice]
        if not pd.isna(rsi):
            señales.append(float(min(100.0, max(0.0, (float(rsi) - 45.0) / 40.0 * 100))))

    if COL_SMA50 in df.columns and indice > 60:
        distancia = (df["Close"] - df[COL_SMA50]) / df[COL_SMA50]
        ventana = distancia.iloc[max(0, indice - 250):indice + 1]
        desviacion = float(ventana.std())
        if desviacion and not pd.isna(desviacion):
            z = float(distancia.iloc[indice]) / desviacion
            señales.append(float(min(100.0, max(0.0, z / 3.0 * 100))))

    if not señales:
        return None

    puntuacion = sum(señales) / len(señales)
    if regimen_favorable is False:
        from modulos.config import FACTOR_REGIMEN_ADVERSO
        puntuacion = min(100.0, puntuacion * FACTOR_REGIMEN_ADVERSO)
    elif regimen_favorable is True:
        from modulos.config import FACTOR_REGIMEN_FAVORABLE
        puntuacion *= FACTOR_REGIMEN_FAVORABLE
    return puntuacion


def _cerrar(entrada: Entrada, regla: str, df: pd.DataFrame, indice_salida: int,
            precio_salida: float, motivo: str, fin: int) -> Cierre:
    bruto = (precio_salida - entrada.precio_entrada) / entrada.precio_entrada
    neto = bruto - 2 * COSTE_POR_LADO
    movimiento = precio_salida - entrada.precio_entrada

    # MAE: lo más en contra que llegó a ir la posición ANTES de cerrarse. Se mide
    # sobre el mínimo intradía, no sobre el cierre: es la pérdida que el inversor
    # llegó a ver en pantalla, que es la que hace vender por nervios.
    mae = None
    if indice_salida > entrada.indice_entrada:
        try:
            minimo = float(df["Low"].iloc[entrada.indice_entrada : indice_salida + 1].min())
            if np.isfinite(minimo) and entrada.precio_entrada > 0:
                mae = min(0.0, (minimo - entrada.precio_entrada) / entrada.precio_entrada)
        except Exception:
            mae = None

    return Cierre(
        regla=regla, ticker=entrada.ticker, estrategia=entrada.estrategia,
        fecha_entrada=entrada.fecha_entrada,
        retorno_neto=float(neto),
        resultado_r=float(movimiento / entrada.riesgo_accion) if entrada.riesgo_accion else 0.0,
        dias=int(indice_salida - entrada.indice_entrada),
        motivo=motivo,
        anticipada=indice_salida < fin,
        fecha_salida=df.index[indice_salida],
        mae=mae,
    )


def aplicar_reglas(df: pd.DataFrame, entrada: Entrada, *,
                   aleatorio: random.Random,
                   regimen_favorable: bool | None = None) -> dict[str, Cierre]:
    """Aplica las cinco reglas pre-registradas a la MISMA entrada."""
    inicio = entrada.indice_entrada
    fin = min(inicio + entrada.horizonte, len(df) - 1)
    if fin <= inicio:
        return {}

    cierres_precio = df["Close"].to_numpy(dtype=float)
    minimos = df["Low"].to_numpy(dtype=float)
    resultado: dict[str, Cierre] = {}

    # 1. Aguantar hasta el horizonte.
    resultado[AGUANTAR] = _cerrar(entrada, AGUANTAR, df, fin, cierres_precio[fin], "horizonte", fin)

    # 3. Stop fijo: se comprueba contra el MÍNIMO, no contra el cierre; un stop
    #    real se ejecuta intradía.
    umbral = entrada.precio_entrada * (1 - STOP_DURO_PCT / 100)
    i_stop = fin
    for i in range(inicio, fin + 1):
        if minimos[i] <= umbral:
            i_stop = i
            break
    precio_stop = umbral if i_stop < fin else cierres_precio[fin]
    resultado[STOP_FIJO] = _cerrar(entrada, STOP_FIJO, df, i_stop, precio_stop,
                                   "stop" if i_stop < fin else "horizonte", fin)

    # 4. Regla técnica: primera sesión en la que el pilar supera el umbral.
    i_tec = fin
    for i in range(inicio + 1, fin + 1):
        punto = puntuacion_tecnica(df, i, regimen_favorable)
        if punto is not None and punto >= UMBRAL_VENDER:
            i_tec = i
            break
    resultado[TECNICA] = _cerrar(entrada, TECNICA, df, i_tec, cierres_precio[i_tec],
                                 "señal" if i_tec < fin else "horizonte", fin)

    # 5. Decisión compuesta: la técnica MÁS los overrides de precio. Sin datos
    #    point-in-time no se pueden reconstruir los pilares de valoración y
    #    fundamentales en cada fecha pasada, así que aquí la compuesta es
    #    técnica + stop, y el informe lo dice.
    i_comp = min(i_tec, i_stop)
    precio_comp = precio_stop if i_comp == i_stop and i_stop < fin else cierres_precio[i_comp]
    motivo_comp = ("stop" if i_comp == i_stop and i_stop < fin
                   else "señal" if i_comp < fin else "horizonte")
    resultado[COMPUESTA] = _cerrar(entrada, COMPUESTA, df, i_comp, precio_comp, motivo_comp, fin)

    # 2. Aleatoria: misma duración que la técnica, en un punto al azar. Controla
    #    que salir pronto no parezca bueno solo por reducir tiempo en mercado.
    duracion = resultado[TECNICA].dias
    i_azar = min(inicio + (aleatorio.randint(1, duracion) if duracion > 0 else 0), fin)
    resultado[ALEATORIA] = _cerrar(entrada, ALEATORIA, df, i_azar, cierres_precio[i_azar],
                                   "azar" if i_azar < fin else "horizonte", fin)

    return resultado


# ==========================================================================
# MÉTRICAS CON INTERVALO DE CONFIANZA
# ==========================================================================


@dataclass(slots=True)
class Metricas:
    regla: str
    operaciones: int
    retorno_medio_pct: float
    ic_retorno: tuple[float, float]
    expectativa_r: float
    ic_expectativa_r: tuple[float, float]
    acierto_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    sharpe: float
    sortino: float
    dias_medios: float
    rotacion_anual: float
    salidas_anticipadas_pct: float

    def como_fila(self) -> dict[str, Any]:
        return {
            "regla": self.regla, "ops": self.operaciones,
            "retorno_medio_%": round(self.retorno_medio_pct, 2),
            "IC95_retorno": f"[{self.ic_retorno[0]:.2f}, {self.ic_retorno[1]:.2f}]",
            "expectativa_R": round(self.expectativa_r, 4),
            "IC95_R": f"[{self.ic_expectativa_r[0]:.3f}, {self.ic_expectativa_r[1]:.3f}]",
            "acierto_%": round(self.acierto_pct, 1),
            "sharpe": round(self.sharpe, 3),
            "sortino": round(self.sortino, 3),
            "días": round(self.dias_medios, 1),
            "rotación": round(self.rotacion_anual, 2),
            "salidas_antic_%": round(self.salidas_anticipadas_pct, 1),
        }


def _bootstrap_ic(valores: np.ndarray, *, remuestreos: int = REMUESTREOS_BOOTSTRAP,
                  semilla: int = SEMILLA) -> tuple[float, float]:
    """IC del 95% de la media por bootstrap percentil.

    Se remuestrea sobre operaciones. Es una cota OPTIMISTA de la precisión: las
    operaciones del mismo mes comparten régimen de mercado y no son
    independientes, así que el intervalo real es más ancho que este.
    """
    if len(valores) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(semilla)
    indices = rng.integers(0, len(valores), size=(remuestreos, len(valores)))
    medias = valores[indices].mean(axis=1)
    return (float(np.percentile(medias, 2.5)), float(np.percentile(medias, 97.5)))


def calcular_metricas(cierres: Sequence[Cierre], regla: str) -> Metricas | None:
    propios = [c for c in cierres if c.regla == regla]
    if not propios:
        return None

    r = np.array([c.retorno_neto for c in propios], dtype=float)
    er = np.array([c.resultado_r for c in propios], dtype=float)
    dias = np.array([max(c.dias, 1) for c in propios], dtype=float)

    # CAGR y max drawdown NO son computables con este diseño, y publicar el
    # número que sale sería peor que no publicarlo:
    #
    # - CAGR: anualizar el retorno de una operación de 3 días eleva a la 84.
    #   Con miles de operaciones cortas la media explota a 1e11 y parece una
    #   rentabilidad. No mide nada.
    # - Max drawdown: encadenar 7.000 operaciones SOLAPADAS como si fueran una
    #   sola cuenta reinvertida al 100% no es una cartera; da −100% siempre.
    #   Un drawdown real exige simular una cartera con reglas de tamaño, que es
    #   otro experimento.
    #
    # Se dejan a NaN y el informe lo explica. Estaban en el pre-registro, así
    # que la retirada se declara: es un defecto de la medición, no del resultado.
    max_dd = float("nan")

    desv = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    bajistas = r[r < 0]
    desv_bajista = float(bajistas.std(ddof=1)) if len(bajistas) > 1 else 0.0

    return Metricas(
        regla=regla,
        operaciones=len(propios),
        retorno_medio_pct=float(r.mean() * 100),
        ic_retorno=tuple(x * 100 for x in _bootstrap_ic(r)),
        expectativa_r=float(er.mean()),
        ic_expectativa_r=_bootstrap_ic(er),
        acierto_pct=float((r > 0).mean() * 100),
        cagr_pct=float("nan"),
        max_drawdown_pct=max_dd,
        sharpe=float(r.mean() / desv) if desv else 0.0,
        sortino=float(r.mean() / desv_bajista) if desv_bajista else 0.0,
        dias_medios=float(dias.mean()),
        rotacion_anual=float(252 / dias.mean()) if dias.mean() else 0.0,
        salidas_anticipadas_pct=float(np.mean([c.anticipada for c in propios]) * 100),
    )


def comparar_reglas(cierres: Sequence[Cierre]) -> dict[str, Metricas]:
    salida: dict[str, Metricas] = {}
    for regla in REGLAS:
        m = calcular_metricas(cierres, regla)
        if m is not None:
            salida[regla] = m
    return salida


def diferencia_significativa(cierres: Sequence[Cierre], regla_a: str, regla_b: str,
                             *, semilla: int = SEMILLA) -> dict[str, Any]:
    """IC de la diferencia de medias EMPAREJADA por operación.

    Emparejar importa: las dos reglas se aplican a las mismas entradas, así que
    la diferencia por operación tiene mucha menos varianza que la diferencia de
    las medias por separado. Si el intervalo cruza el cero, no hay diferencia
    que declarar.
    """
    por_clave: dict[tuple, dict[str, float]] = {}
    for c in cierres:
        if c.regla not in (regla_a, regla_b):
            continue
        clave = (c.ticker, c.estrategia, pd.Timestamp(c.fecha_entrada).value)
        por_clave.setdefault(clave, {})[c.regla] = c.retorno_neto

    pares = [(v[regla_a], v[regla_b]) for v in por_clave.values()
             if regla_a in v and regla_b in v]
    if len(pares) < 2:
        return {"n": len(pares), "diferencia_pct": None, "ic": (None, None), "significativa": False}

    diferencias = np.array([a - b for a, b in pares], dtype=float)
    bajo, alto = _bootstrap_ic(diferencias, semilla=semilla)
    return {
        "n": len(pares),
        "diferencia_pct": float(diferencias.mean() * 100),
        "ic": (bajo * 100, alto * 100),
        "significativa": bool(bajo > 0 or alto < 0),
    }
