"""¿Queda selección después de descontar el riesgo asumido?

Una cartera puede batir a su índice de dos maneras muy distintas: eligiendo mejor
(alfa) o asumiendo más riesgo de mercado (beta). Un +30% con beta 1,8 no es
selección: es el índice apalancado, y se podría haber conseguido sin elegir nada.
Este módulo separa las dos cosas.

Ver docs/preregistro_alfa_beta.md: métricas, tipo libre de riesgo, método de
intervalos y criterio de evidencia quedaron escritos y commiteados antes de
ejecutar nada.

Dos decisiones que sostienen todo lo demás
-------------------------------------------
**Todos los retornos salen de la serie unitizada (TWR).** Sobre la serie de valor,
cada aportación parecería un retorno enorme y contaminaría a la vez la regresión,
la volatilidad y el bootstrap.

**El intervalo es por bloques, no gaussiano.** Los retornos diarios están
autocorrelacionados y tienen colas gordas. Un IC de t de Student saldría
artificialmente estrecho justo donde el objetivo es no engañarse.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from modulos.config import (
    LONGITUD_BLOQUE_BOOTSTRAP, NIVEL_CONFIANZA, REMUESTREOS_BLOQUE,
    TICKER_LIBRE_RIESGO, TIPO_LIBRE_RIESGO_FALLBACK,
)

LOGGER = logging.getLogger("valuequant.rendimiento_riesgo")

__all__ = [
    "ResultadoCAPM", "VolMatched", "Descomposicion", "Concentracion",
    "VeredictoSeleccion", "AnalisisRiesgo",
    "bootstrap_bloques", "serie_libre_de_riesgo", "benchmark_vol_matched",
    "regresion_capm", "descomponer_exceso", "medir_concentracion",
    "emitir_veredicto", "analizar", "SEMILLA",
]

SESIONES_ANIO = 252
SEMILLA = 20260906


# ==========================================================================
# BOOTSTRAP POR BLOQUES
# ==========================================================================


def bootstrap_bloques(
    datos: np.ndarray | Sequence[float],
    funcion: Callable[[np.ndarray], float],
    *,
    longitud: int = LONGITUD_BLOQUE_BOOTSTRAP,
    remuestreos: int = REMUESTREOS_BLOQUE,
    semilla: int = SEMILLA,
    confianza: float = NIVEL_CONFIANZA,
) -> tuple[float, float]:
    """IC por bootstrap de bloques móviles.

    Remuestrea BLOQUES contiguos en vez de observaciones sueltas, que es lo que
    preserva la autocorrelación de los retornos diarios. Con bootstrap IID el
    intervalo sale demasiado estrecho y una serie sin ninguna señal puede
    aparentar significación.
    """
    matriz = np.asarray(datos, dtype=float)
    if matriz.ndim == 1:
        matriz = matriz.reshape(-1, 1)
    n = len(matriz)
    if n < longitud * 2:
        return (float("nan"), float("nan"))

    rng = np.random.default_rng(semilla)
    n_bloques = int(np.ceil(n / longitud))
    maximo_inicio = n - longitud

    muestras = np.empty(remuestreos, dtype=float)
    for i in range(remuestreos):
        inicios = rng.integers(0, maximo_inicio + 1, size=n_bloques)
        indices = np.concatenate([np.arange(s, s + longitud) for s in inicios])[:n]
        try:
            muestras[i] = funcion(matriz[indices])
        except Exception:
            muestras[i] = np.nan

    validas = muestras[np.isfinite(muestras)]
    if len(validas) < remuestreos * 0.5:
        return (float("nan"), float("nan"))
    cola = (1 - confianza) / 2 * 100
    return (float(np.percentile(validas, cola)), float(np.percentile(validas, 100 - cola)))


# ==========================================================================
# TIPO LIBRE DE RIESGO
# ==========================================================================


def serie_libre_de_riesgo(indice: pd.DatetimeIndex,
                          serie_proxy: pd.Series | None = None) -> tuple[pd.Series, list[str]]:
    """Retornos diarios del activo libre de riesgo, alineados al índice dado.

    ``serie_proxy`` se inyecta en los tests. Si no hay proxy, se cae a una
    constante y SE AVISA: el tipo entra en el vol-matched y en el alfa, así que
    sustituirlo en silencio cambiaría el veredicto sin dejar rastro.
    """
    avisos: list[str] = []
    if serie_proxy is not None and not serie_proxy.empty:
        limpio = pd.Series(serie_proxy).dropna()
        if getattr(limpio.index, "tz", None) is not None:
            limpio.index = limpio.index.tz_localize(None)
        retornos = limpio.pct_change().reindex(indice).fillna(0.0)
        if retornos.abs().sum() > 0:
            return retornos, avisos
        avisos.append(f"El proxy {TICKER_LIBRE_RIESGO} no aportó variación utilizable.")
    else:
        avisos.append(f"Sin datos de {TICKER_LIBRE_RIESGO}.")

    diario = (1 + TIPO_LIBRE_RIESGO_FALLBACK) ** (1 / SESIONES_ANIO) - 1
    avisos.append(
        f"Se usa un tipo libre de riesgo constante del {TIPO_LIBRE_RIESGO_FALLBACK:.1%} "
        "anual. Afecta al vol-matched y al alfa."
    )
    return pd.Series(diario, index=indice), avisos


# ==========================================================================
# BENCHMARK IGUALADO EN VOLATILIDAD
# ==========================================================================


@dataclass(slots=True)
class VolMatched:
    """El índice escalado a la volatilidad de la cartera.

    LENTE ANALÍTICA, no una estrategia: un ETF no se apalanca al tipo libre de
    riesgo sin coste ni garantías, y el reajuste diario del apalancamiento tiene
    un arrastre por volatilidad que esto no modela.
    """

    k: float
    vol_cartera_pct: float
    vol_benchmark_pct: float
    cagr_cartera_pct: float
    cagr_benchmark_pct: float
    cagr_volmatched_pct: float
    diferencia_pct: float
    retornos: pd.Series = field(default_factory=lambda: pd.Series(dtype=float), repr=False)

    @property
    def cartera_gana(self) -> bool:
        """True si la cartera bate al índice ya igualado en riesgo."""
        return self.cagr_cartera_pct > self.cagr_volmatched_pct

    def como_fila(self) -> dict[str, Any]:
        return {
            "k": round(self.k, 3),
            "vol_cartera_%": round(self.vol_cartera_pct, 2),
            "vol_benchmark_%": round(self.vol_benchmark_pct, 2),
            "CAGR_cartera_%": round(self.cagr_cartera_pct, 2),
            "CAGR_benchmark_%": round(self.cagr_benchmark_pct, 2),
            "CAGR_volmatched_%": round(self.cagr_volmatched_pct, 2),
            "diferencia_%": round(self.diferencia_pct, 2),
        }


def _cagr(retornos: np.ndarray) -> float:
    if len(retornos) == 0:
        return float("nan")
    total = float(np.prod(1 + retornos))
    if total <= 0:
        return float("nan")
    anios = max(len(retornos) / SESIONES_ANIO, 1 / SESIONES_ANIO)
    return (total ** (1 / anios) - 1) * 100


def benchmark_vol_matched(r_cartera: pd.Series, r_benchmark: pd.Series,
                          r_libre: pd.Series) -> VolMatched | None:
    """Escala el índice a la volatilidad de la cartera, financiado al tipo libre.

    Si el vol-matched rinde igual o más que la cartera, todo el exceso lo explica
    el riesgo asumido y no queda nada que atribuir a la selección.
    """
    marco = pd.DataFrame({"p": r_cartera, "b": r_benchmark, "f": r_libre}).dropna()
    if len(marco) < 20:
        return None

    exceso_p = (marco["p"] - marco["f"]).to_numpy(dtype=float)
    exceso_b = (marco["b"] - marco["f"]).to_numpy(dtype=float)
    sigma_p, sigma_b = float(exceso_p.std(ddof=1)), float(exceso_b.std(ddof=1))
    if sigma_b <= 0:
        return None

    k = sigma_p / sigma_b
    r_vm = marco["f"].to_numpy(dtype=float) + k * exceso_b

    return VolMatched(
        k=k,
        vol_cartera_pct=sigma_p * np.sqrt(SESIONES_ANIO) * 100,
        vol_benchmark_pct=sigma_b * np.sqrt(SESIONES_ANIO) * 100,
        cagr_cartera_pct=_cagr(marco["p"].to_numpy(dtype=float)),
        cagr_benchmark_pct=_cagr(marco["b"].to_numpy(dtype=float)),
        cagr_volmatched_pct=_cagr(r_vm),
        diferencia_pct=_cagr(marco["p"].to_numpy(dtype=float)) - _cagr(r_vm),
        retornos=pd.Series(r_vm, index=marco.index),
    )


# ==========================================================================
# CAPM
# ==========================================================================


@dataclass(slots=True)
class ResultadoCAPM:
    alfa_anual_pct: float
    ic_alfa: tuple[float, float]
    beta: float
    ic_beta: tuple[float, float]
    r2: float
    information_ratio: float
    tracking_error_pct: float
    retorno_activo_pct: float
    sesiones: int

    @property
    def alfa_significativo(self) -> bool:
        """El IC completo por encima de cero. Cruzar cero es no tener evidencia."""
        bajo, alto = self.ic_alfa
        return bool(np.isfinite(bajo) and bajo > 0)

    def como_fila(self) -> dict[str, Any]:
        return {
            "alfa_anual_%": round(self.alfa_anual_pct, 2),
            "IC95_alfa": f"[{self.ic_alfa[0]:.2f}, {self.ic_alfa[1]:.2f}]",
            "beta": round(self.beta, 3),
            "IC95_beta": f"[{self.ic_beta[0]:.3f}, {self.ic_beta[1]:.3f}]",
            "R2": round(self.r2, 3),
            "IR": round(self.information_ratio, 3),
            "tracking_error_%": round(self.tracking_error_pct, 2),
            "sesiones": self.sesiones,
        }


def _ajuste(matriz: np.ndarray) -> tuple[float, float, float]:
    """Mínimos cuadrados sobre [exceso_cartera, exceso_benchmark]."""
    y, x = matriz[:, 0], matriz[:, 1]
    if len(y) < 3 or float(x.std()) == 0:
        return float("nan"), float("nan"), float("nan")
    from scipy.stats import linregress

    r = linregress(x, y)
    return float(r.intercept), float(r.slope), float(r.rvalue ** 2)


def regresion_capm(r_cartera: pd.Series, r_benchmark: pd.Series,
                   r_libre: pd.Series) -> ResultadoCAPM | None:
    """Alfa y beta sobre retornos de EXCESO, con IC por bloques."""
    marco = pd.DataFrame({"p": r_cartera, "b": r_benchmark, "f": r_libre}).dropna()
    if len(marco) < 30:
        return None

    matriz = np.column_stack([
        (marco["p"] - marco["f"]).to_numpy(dtype=float),
        (marco["b"] - marco["f"]).to_numpy(dtype=float),
    ])
    alfa_d, beta, r2 = _ajuste(matriz)
    if not np.isfinite(alfa_d):
        return None

    # El alfa diario se anualiza componiendo, no multiplicando por 252.
    alfa_anual = ((1 + alfa_d) ** SESIONES_ANIO - 1) * 100

    ic_alfa = bootstrap_bloques(
        matriz, lambda m: ((1 + _ajuste(m)[0]) ** SESIONES_ANIO - 1) * 100
    )
    ic_beta = bootstrap_bloques(matriz, lambda m: _ajuste(m)[1])

    activo = (marco["p"] - marco["b"]).to_numpy(dtype=float)
    tracking = float(activo.std(ddof=1) * np.sqrt(SESIONES_ANIO))
    retorno_activo = float(activo.mean() * SESIONES_ANIO)

    return ResultadoCAPM(
        alfa_anual_pct=float(alfa_anual),
        ic_alfa=ic_alfa,
        beta=float(beta),
        ic_beta=ic_beta,
        r2=float(r2),
        information_ratio=float(retorno_activo / tracking) if tracking else 0.0,
        tracking_error_pct=tracking * 100,
        retorno_activo_pct=retorno_activo * 100,
        sesiones=len(marco),
    )


# ==========================================================================
# DESCOMPOSICIÓN DEL EXCESO
# ==========================================================================


@dataclass(slots=True)
class Descomposicion:
    """De cuánto batí al índice, cuánto es riesgo y cuánto selección."""

    exceso_total_pct: float
    por_beta_pct: float
    por_alfa_pct: float
    residual_pct: float

    def como_texto(self) -> str:
        return (
            f"De tus {self.exceso_total_pct:+.1f} puntos anuales sobre el índice, "
            f"{self.por_beta_pct:+.1f} son exposición al mercado amplificada y "
            f"{self.por_alfa_pct:+.1f} son selección."
        )

    def como_fila(self) -> dict[str, Any]:
        return {
            "exceso_total_%": round(self.exceso_total_pct, 2),
            "por_beta_%": round(self.por_beta_pct, 2),
            "por_alfa_%": round(self.por_alfa_pct, 2),
            "residual_%": round(self.residual_pct, 2),
        }


def descomponer_exceso(capm: ResultadoCAPM, r_cartera: pd.Series,
                       r_benchmark: pd.Series, r_libre: pd.Series) -> Descomposicion | None:
    """Reparte el exceso anual entre beta, alfa y residuo.

    Con ``beta`` sobre el exceso del índice, la parte explicada por la exposición
    al mercado es ``(beta − 1)·prima_de_mercado``: lo que se gana por llevar más
    mercado del que lleva el propio índice. El resto es alfa, y lo que no cuadre
    queda como residuo explícito en vez de repartirse a ojo.
    """
    marco = pd.DataFrame({"p": r_cartera, "b": r_benchmark, "f": r_libre}).dropna()
    if marco.empty or not np.isfinite(capm.beta):
        return None

    anualizar = lambda s: float(s.mean() * SESIONES_ANIO * 100)
    exceso_total = anualizar(marco["p"] - marco["b"])
    prima_mercado = anualizar(marco["b"] - marco["f"])

    por_beta = (capm.beta - 1.0) * prima_mercado
    por_alfa = capm.alfa_anual_pct
    residual = exceso_total - por_beta - por_alfa

    return Descomposicion(
        exceso_total_pct=exceso_total,
        por_beta_pct=por_beta,
        por_alfa_pct=por_alfa,
        residual_pct=residual,
    )


# ==========================================================================
# CONCENTRACIÓN
# ==========================================================================


@dataclass(slots=True)
class Concentracion:
    """¿El resultado está repartido o cuelga de un nombre?"""

    herfindahl: float
    posiciones: int
    mayor_ticker: str | None
    mayor_alfa_eur: float
    cuota_mayor_pct: float

    @property
    def cuelga_de_un_nombre(self) -> bool:
        """Herfindahl por encima de 0,5 equivale a menos de dos posiciones
        efectivas: el resultado es esencialmente una apuesta."""
        return self.herfindahl >= 0.5

    def como_fila(self) -> dict[str, Any]:
        return {
            "herfindahl": round(self.herfindahl, 3),
            "posiciones_efectivas": round(1 / self.herfindahl, 2) if self.herfindahl else None,
            "mayor": self.mayor_ticker,
            "alfa_mayor_eur": round(self.mayor_alfa_eur, 2),
            "cuota_mayor_%": round(self.cuota_mayor_pct, 1),
        }


def medir_concentracion(atribucion: Sequence[Any]) -> Concentracion | None:
    """Herfindahl sobre el |alfa| de cada posición.

    Se usa el VALOR ABSOLUTO: una posición que resta mucho concentra el
    resultado igual que una que suma mucho. Con alfas netos podrían cancelarse
    y dar una falsa impresión de reparto.
    """
    if not atribucion:
        return None

    alfas = {a.ticker: abs(float(a.alfa_eur)) for a in atribucion}
    total = sum(alfas.values())
    if total <= 0:
        return Concentracion(herfindahl=0.0, posiciones=len(alfas), mayor_ticker=None,
                             mayor_alfa_eur=0.0, cuota_mayor_pct=0.0)

    cuotas = {t: v / total for t, v in alfas.items()}
    herfindahl = float(sum(c ** 2 for c in cuotas.values()))
    mayor = max(atribucion, key=lambda a: abs(float(a.alfa_eur)))

    return Concentracion(
        herfindahl=herfindahl,
        posiciones=len(alfas),
        mayor_ticker=mayor.ticker,
        mayor_alfa_eur=float(mayor.alfa_eur),
        cuota_mayor_pct=cuotas[mayor.ticker] * 100,
    )


# ==========================================================================
# VEREDICTO
# ==========================================================================


CRITERIO = {
    "a": "El IC del 95% del alfa anualizado queda enteramente por encima de 0.",
    "b": "El benchmark vol-matched rinde MENOS que la cartera.",
    "c": "La conclusión sobrevive a excluir la mayor posición.",
}


@dataclass(slots=True)
class VeredictoSeleccion:
    criterio_a: bool
    criterio_b: bool
    criterio_c: bool
    hay_evidencia: bool
    motivo: str

    def como_fila(self) -> dict[str, Any]:
        return {
            "criterio_A_alfa_significativo": self.criterio_a,
            "criterio_B_bate_al_volmatched": self.criterio_b,
            "criterio_C_sobrevive_sin_la_mayor": self.criterio_c,
            "hay_evidencia": self.hay_evidencia,
            "motivo": self.motivo,
        }


def emitir_veredicto(capm: ResultadoCAPM | None, vol_matched: VolMatched | None,
                     capm_sin_mayor: ResultadoCAPM | None,
                     vol_sin_mayor: VolMatched | None) -> VeredictoSeleccion:
    """Aplica el criterio pre-registrado. Las tres condiciones, o nada."""
    a = bool(capm and capm.alfa_significativo)
    b = bool(vol_matched and vol_matched.cartera_gana)
    # (c) no exige significación tras excluir —la muestra encoge— sino que el
    # signo aguante: si el alfa se vuelve negativo, el resultado colgaba de un
    # nombre.
    c = bool(
        capm_sin_mayor and np.isfinite(capm_sin_mayor.alfa_anual_pct)
        and capm_sin_mayor.alfa_anual_pct > 0
        and vol_sin_mayor and vol_sin_mayor.cartera_gana
    )

    if a and b and c:
        motivo = "Se cumplen las tres condiciones pre-registradas."
        return VeredictoSeleccion(a, b, c, True, motivo)

    fallos = []
    if not a:
        fallos.append("el IC del alfa cruza cero" if capm else "no hay regresión válida")
    if not b:
        fallos.append("el índice igualado en volatilidad rinde igual o más")
    if not c:
        fallos.append("sin la mayor posición la ventaja desaparece")

    return VeredictoSeleccion(
        a, b, c, False,
        "Insuficiente evidencia de selección: " + "; ".join(fallos) + ".",
    )


# ==========================================================================
# ORQUESTACIÓN
# ==========================================================================


@dataclass(slots=True)
class AnalisisRiesgo:
    capm: ResultadoCAPM | None = None
    vol_matched: VolMatched | None = None
    descomposicion: Descomposicion | None = None
    concentracion: Concentracion | None = None
    capm_sin_mayor: ResultadoCAPM | None = None
    vol_sin_mayor: VolMatched | None = None
    veredicto: VeredictoSeleccion | None = None
    avisos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capm": self.capm.como_fila() if self.capm else None,
            "vol_matched": self.vol_matched.como_fila() if self.vol_matched else None,
            "descomposicion": self.descomposicion.como_fila() if self.descomposicion else None,
            "concentracion": self.concentracion.como_fila() if self.concentracion else None,
            "capm_sin_mayor": self.capm_sin_mayor.como_fila() if self.capm_sin_mayor else None,
            "vol_sin_mayor": self.vol_sin_mayor.como_fila() if self.vol_sin_mayor else None,
            "veredicto": self.veredicto.como_fila() if self.veredicto else None,
            "avisos": self.avisos,
        }


def _retornos_unitizados(rendimiento: Any) -> tuple[pd.Series, pd.Series] | None:
    """Retornos diarios de cartera y benchmark, desde la serie unitizada.

    Nunca desde la serie de valor: sobre ella cada aportación parecería un
    retorno enorme y contaminaría regresión, volatilidad y bootstrap a la vez.
    """
    series = getattr(rendimiento, "series", None)
    if series is None or series.empty:
        return None
    if "unitizada_cartera" not in series.columns:
        return None
    p = series["unitizada_cartera"].pct_change().dropna()
    b = series["unitizada_benchmark"].pct_change().dropna()
    return (p, b) if not p.empty and not b.empty else None


def analizar(rendimiento: Any, *, serie_libre: pd.Series | None = None,
             rendimiento_sin_mayor: Any = None) -> AnalisisRiesgo:
    """Análisis completo. Función pura: no toca la red.

    ``rendimiento_sin_mayor`` lo construye el llamador reejecutando el cálculo
    de cartera sin el ticker de mayor |alfa|.
    """
    resultado = AnalisisRiesgo()

    retornos = _retornos_unitizados(rendimiento)
    if retornos is None:
        resultado.avisos.append("Sin serie unitizada suficiente para el análisis.")
        return resultado
    r_p, r_b = retornos

    indice = r_p.index.intersection(r_b.index)
    r_libre, avisos = serie_libre_de_riesgo(indice, serie_libre)
    resultado.avisos.extend(avisos)

    resultado.vol_matched = benchmark_vol_matched(r_p, r_b, r_libre)
    resultado.capm = regresion_capm(r_p, r_b, r_libre)
    if resultado.capm:
        resultado.descomposicion = descomponer_exceso(resultado.capm, r_p, r_b, r_libre)
    resultado.concentracion = medir_concentracion(getattr(rendimiento, "atribucion", []))

    if rendimiento_sin_mayor is not None:
        sin = _retornos_unitizados(rendimiento_sin_mayor)
        if sin is not None:
            p2, b2 = sin
            idx2 = p2.index.intersection(b2.index)
            libre2, _ = serie_libre_de_riesgo(idx2, serie_libre)
            resultado.capm_sin_mayor = regresion_capm(p2, b2, libre2)
            resultado.vol_sin_mayor = benchmark_vol_matched(p2, b2, libre2)
        else:
            resultado.avisos.append("No se pudo recalcular la cartera sin la mayor posición.")

    resultado.veredicto = emitir_veredicto(
        resultado.capm, resultado.vol_matched,
        resultado.capm_sin_mayor, resultado.vol_sin_mayor,
    )
    return resultado
