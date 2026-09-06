"""Eje de riesgo de las reglas de salida: curva, caída y cola.

La Tarea 1 midió la media por operación y dictaminó que ninguna regla de salida
bate a aguantar. Pero nueve de diez años negativos y solo 2020 positivo apunta a
que las salidas se comportan como una **cobertura de cola**: pagan en el desplome
y restan el resto del tiempo. Eso la media no lo puede decidir.

Aquí se mide el otro eje. Ver docs/preregistro_eje_riesgo.md: métricas,
construcción de cartera y criterio de decisión quedaron escritos y commiteados
antes de ejecutar nada.

Por qué hace falta una cartera
-------------------------------
El drawdown y la volatilidad no existen "por operación": exigen una curva de
capital. Y como las operaciones se solapan, encadenarlas como si fueran
secuenciales da −100% siempre (es lo que obligó a retirar el maxDD de la
Tarea 1). La construcción pre-declarada es equiponderada por posición abierta:
en cada sesión el retorno de la cartera es la media simple de los retornos
diarios de lo que está abierto, y 0 cuando no hay nada.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from modulos.backtest_salidas import COSTE_POR_LADO, REGLAS, SEMILLA, Cierre

LOGGER = logging.getLogger("valuequant.riesgo_salidas")

__all__ = [
    "MetricasRiesgo", "PESO_FIJO_SENSIBILIDAD",
    "retornos_diarios_cartera", "curva_equity", "serie_drawdown",
    "metricas_riesgo", "comparar_riesgo", "canje_maxdd_por_retorno",
    "veredicto_seguro", "CRITERIO",
]

SESIONES_ANIO = 252
PESO_FIJO_SENSIBILIDAD = 0.02      # 2% por operación, para la sensibilidad
REMUESTREOS = 5_000

# Criterio pre-registrado en docs/preregistro_eje_riesgo.md. NO se modifica.
CRITERIO = {
    "A": "Mejoran a la vez Calmar, Sortino y CVaR5, con menor maxDD.",
    "B": "Recorta >=3 puntos de maxDD por cada punto de retorno anualizado cedido, y mejora el CVaR5.",
    "canje_minimo": 3.0,
}


# ==========================================================================
# CONSTRUCCIÓN DE CARTERA
# ==========================================================================


def retornos_diarios_cartera(
    cierres: Sequence[Cierre],
    precios: dict[str, pd.DataFrame],
    *,
    peso_fijo: float | None = None,
) -> pd.Series:
    """Serie de retornos diarios de la cartera para UNA regla.

    ``peso_fijo=None`` reparte a partes iguales entre las posiciones abiertas
    ese día (la construcción principal). Con un valor, cada posición pesa esa
    fracción fija del capital y el resto es efectivo: es la sensibilidad
    pre-declarada.

    Los costes se cargan en la sesión de entrada y en la de salida, no
    prorrateados: es cuando realmente se pagan.
    """
    if not cierres:
        return pd.Series(dtype=float)

    aportaciones: dict[pd.Timestamp, list[float]] = defaultdict(list)

    for cierre in cierres:
        df = precios.get(cierre.ticker)
        if df is None or df.empty or cierre.fecha_salida is None:
            continue
        try:
            tramo = df.loc[cierre.fecha_entrada : cierre.fecha_salida, "Close"].dropna()
        except (KeyError, TypeError):
            continue
        if len(tramo) < 2:
            continue

        diarios = tramo.pct_change().dropna()
        if diarios.empty:
            continue
        # Coste de entrada en la primera sesión con retorno y de salida en la
        # última: dos veces COSTE_POR_LADO en total, igual que en la Tarea 1.
        ajustados = diarios.copy()
        ajustados.iloc[0] -= COSTE_POR_LADO
        ajustados.iloc[-1] -= COSTE_POR_LADO

        for fecha, valor in ajustados.items():
            if np.isfinite(valor):
                aportaciones[pd.Timestamp(fecha)].append(float(valor))

    if not aportaciones:
        return pd.Series(dtype=float)

    fechas = sorted(aportaciones)
    if peso_fijo is None:
        # Equiponderada: media de lo abierto. Sin posiciones, efectivo al 0%.
        valores = [float(np.mean(aportaciones[f])) for f in fechas]
    else:
        # Peso fijo por posición; el exceso sobre 1 se recorta para no
        # apalancar, que estaba excluido en el pre-registro.
        valores = []
        for f in fechas:
            lista = aportaciones[f]
            expuesto = min(1.0, peso_fijo * len(lista))
            peso_real = expuesto / len(lista) if lista else 0.0
            valores.append(float(sum(v * peso_real for v in lista)))

    return pd.Series(valores, index=pd.DatetimeIndex(fechas)).sort_index()


def curva_equity(retornos: pd.Series, inicial: float = 1.0) -> pd.Series:
    if retornos is None or retornos.empty:
        return pd.Series(dtype=float)
    return inicial * (1 + retornos).cumprod()


def serie_drawdown(equity: pd.Series) -> pd.Series:
    if equity is None or equity.empty:
        return pd.Series(dtype=float)
    return equity / equity.cummax() - 1.0


# ==========================================================================
# MÉTRICAS
# ==========================================================================


@dataclass(slots=True)
class MetricasRiesgo:
    regla: str
    # Curva
    cagr_pct: float
    max_drawdown_pct: float
    duracion_drawdown_dias: int
    volatilidad_pct: float
    downside_pct: float
    # Ratios
    sharpe: float
    sortino: float
    calmar: float
    ulcer: float
    # Cola, sobre la distribución por operación
    p5_pct: float
    p1_pct: float
    cvar5_pct: float
    peor_operacion_pct: float
    mae_medio_pct: float
    # Forma
    media_pct: float
    mediana_pct: float
    asimetria: float
    curtosis: float
    operaciones: int
    ic_cvar5: tuple[float, float] = (float("nan"), float("nan"))

    def como_fila(self) -> dict[str, Any]:
        return {
            "regla": self.regla, "ops": self.operaciones,
            "CAGR_%": round(self.cagr_pct, 2),
            "maxDD_%": round(self.max_drawdown_pct, 2),
            "durDD_d": self.duracion_drawdown_dias,
            "vol_%": round(self.volatilidad_pct, 2),
            "downside_%": round(self.downside_pct, 2),
            "Sharpe": round(self.sharpe, 3),
            "Sortino": round(self.sortino, 3),
            "Calmar": round(self.calmar, 3),
            "Ulcer": round(self.ulcer, 2),
            "P5_%": round(self.p5_pct, 2),
            "P1_%": round(self.p1_pct, 2),
            "CVaR5_%": round(self.cvar5_pct, 2),
            "peor_%": round(self.peor_operacion_pct, 2),
            "MAE_%": round(self.mae_medio_pct, 2),
            "asimetría": round(self.asimetria, 3),
            "curtosis": round(self.curtosis, 2),
        }


def _duracion_maxima_drawdown(drawdown: pd.Series) -> int:
    """Sesiones más largas que la curva pasó sin recuperar su máximo previo."""
    if drawdown is None or drawdown.empty:
        return 0
    bajo_agua = (drawdown < -1e-12).to_numpy()
    mejor = actual = 0
    for valor in bajo_agua:
        actual = actual + 1 if valor else 0
        mejor = max(mejor, actual)
    return int(mejor)


def _bootstrap_ic(valores: np.ndarray, funcion, *, remuestreos: int = REMUESTREOS,
                  semilla: int = SEMILLA) -> tuple[float, float]:
    if len(valores) < 5:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(semilla)
    indices = rng.integers(0, len(valores), size=(remuestreos, len(valores)))
    muestras = np.array([funcion(valores[fila]) for fila in indices])
    return (float(np.percentile(muestras, 2.5)), float(np.percentile(muestras, 97.5)))


def _cvar(valores: np.ndarray, alfa: float = 0.05) -> float:
    """Pérdida media en el alfa peor de los casos (Expected Shortfall).

    Es más informativo que el VaR: el VaR dice dónde está el corte, el CVaR
    dice cuánto se pierde una vez cruzado.
    """
    if len(valores) == 0:
        return float("nan")
    umbral = float(np.percentile(valores, alfa * 100))
    cola = valores[valores <= umbral]
    return float(cola.mean()) if len(cola) else umbral


def metricas_riesgo(regla: str, cierres: Sequence[Cierre],
                    retornos_diarios: pd.Series) -> MetricasRiesgo | None:
    propios = [c for c in cierres if c.regla == regla]
    if not propios or retornos_diarios is None or retornos_diarios.empty:
        return None

    r = np.array([c.retorno_neto for c in propios], dtype=float)
    maes = np.array([c.mae for c in propios if c.mae is not None], dtype=float)

    equity = curva_equity(retornos_diarios)
    drawdown = serie_drawdown(equity)
    sesiones = len(retornos_diarios)
    anios = max(sesiones / SESIONES_ANIO, 1 / SESIONES_ANIO)

    valor_final = float(equity.iloc[-1])
    cagr = (valor_final ** (1 / anios) - 1) * 100 if valor_final > 0 else float("nan")
    max_dd = float(drawdown.min() * 100)

    diarios = retornos_diarios.to_numpy(dtype=float)
    vol = float(diarios.std(ddof=1) * np.sqrt(SESIONES_ANIO) * 100) if sesiones > 1 else 0.0
    negativos = diarios[diarios < 0]
    downside = float(negativos.std(ddof=1) * np.sqrt(SESIONES_ANIO) * 100) if len(negativos) > 1 else 0.0

    media_diaria = float(diarios.mean())
    sharpe = (media_diaria / diarios.std(ddof=1) * np.sqrt(SESIONES_ANIO)) if diarios.std(ddof=1) else 0.0
    sortino = (media_diaria / negativos.std(ddof=1) * np.sqrt(SESIONES_ANIO)) if len(negativos) > 1 and negativos.std(ddof=1) else 0.0
    calmar = (cagr / abs(max_dd)) if max_dd < 0 else float("nan")
    ulcer = float(np.sqrt(np.mean((drawdown.to_numpy() * 100) ** 2)))

    return MetricasRiesgo(
        regla=regla,
        cagr_pct=float(cagr),
        max_drawdown_pct=max_dd,
        duracion_drawdown_dias=_duracion_maxima_drawdown(drawdown),
        volatilidad_pct=vol,
        downside_pct=downside,
        sharpe=float(sharpe),
        sortino=float(sortino),
        calmar=float(calmar),
        ulcer=ulcer,
        p5_pct=float(np.percentile(r, 5) * 100),
        p1_pct=float(np.percentile(r, 1) * 100),
        cvar5_pct=float(_cvar(r) * 100),
        peor_operacion_pct=float(r.min() * 100),
        mae_medio_pct=float(maes.mean() * 100) if len(maes) else float("nan"),
        media_pct=float(r.mean() * 100),
        mediana_pct=float(np.median(r) * 100),
        asimetria=float(pd.Series(r).skew()),
        curtosis=float(pd.Series(r).kurtosis()),
        operaciones=len(propios),
        ic_cvar5=tuple(x * 100 for x in _bootstrap_ic(r, _cvar)),
    )


def comparar_riesgo(cierres: Sequence[Cierre], precios: dict[str, pd.DataFrame],
                    *, peso_fijo: float | None = None) -> dict[str, MetricasRiesgo]:
    salida: dict[str, MetricasRiesgo] = {}
    for regla in REGLAS:
        propios = [c for c in cierres if c.regla == regla]
        if not propios:
            continue
        diarios = retornos_diarios_cartera(propios, precios, peso_fijo=peso_fijo)
        m = metricas_riesgo(regla, propios, diarios)
        if m is not None:
            salida[regla] = m
    return salida


# ==========================================================================
# VEREDICTO
# ==========================================================================


def canje_maxdd_por_retorno(regla: MetricasRiesgo, referencia: MetricasRiesgo) -> float | None:
    """Puntos de maxDD recortados por cada punto de CAGR cedido.

    None si la regla no cede retorno (entonces no hay canje que evaluar: si
    además recorta caída, simplemente domina).
    """
    cedido = referencia.cagr_pct - regla.cagr_pct
    recortado = abs(referencia.max_drawdown_pct) - abs(regla.max_drawdown_pct)
    if cedido <= 0:
        return None
    return recortado / cedido


def veredicto_seguro(regla: MetricasRiesgo, referencia: MetricasRiesgo) -> dict[str, Any]:
    """Aplica el criterio pre-registrado. No se negocia después de verlo."""
    mejor_calmar = regla.calmar > referencia.calmar
    mejor_sortino = regla.sortino > referencia.sortino
    mejor_cvar = regla.cvar5_pct > referencia.cvar5_pct      # menos negativo
    menor_dd = abs(regla.max_drawdown_pct) < abs(referencia.max_drawdown_pct)

    cumple_a = mejor_calmar and mejor_sortino and mejor_cvar and menor_dd

    canje = canje_maxdd_por_retorno(regla, referencia)
    cumple_b = canje is not None and canje >= CRITERIO["canje_minimo"] and mejor_cvar

    return {
        "regla": regla.regla,
        "criterio_A": cumple_a,
        "criterio_B": cumple_b,
        "merece_la_pena": bool(cumple_a or cumple_b),
        "canje_maxdd_por_punto": None if canje is None else round(canje, 2),
        "detalle": {
            "calmar_mejora": mejor_calmar,
            "sortino_mejora": mejor_sortino,
            "cvar5_mejora": mejor_cvar,
            "maxdd_menor": menor_dd,
        },
    }
