"""Múltiplos de valoración situados en el percentil de su propia historia.

Decir que una empresa cotiza a PER 28 no informa: 28 es caro para una eléctrica
y barato para un software. Lo que sí informa es dónde cae ese 28 dentro del
rango en el que esa MISMA empresa ha cotizado los últimos años. Un PER 28 en el
percentil 20 de su propia historia es una empresa más barata de lo que suele
estar, aunque el número suene alto en abstracto.

El retardo de publicación
-------------------------
Las cuentas de un ejercicio no son públicas el 31 de diciembre: se publican uno
o tres meses después. Emparejar el cierre del ejercicio con el precio de ese
mismo día construiría una serie que nadie pudo observar, y el percentil
resultante estaría contaminado por información futura. Por eso el precio se toma
``RETARDO_PUBLICACION_DIAS`` después del cierre contable.

Mínimo de observaciones
-----------------------
Un percentil sobre tres puntos no significa nada: cualquier valor cae en el 0,
el 50 o el 100. Con menos de ``MINIMO_EJERCICIOS`` se devuelve ``None`` en vez
de un número que aparenta precisión.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("valuequant.multiplos")

__all__ = [
    "MultiploHistorico", "ResultadoMultiplos",
    "serie_multiplos", "percentil_en_su_historia", "evaluar_multiplos",
    "RETARDO_PUBLICACION_DIAS", "MINIMO_EJERCICIOS",
]

RETARDO_PUBLICACION_DIAS = 75
MINIMO_EJERCICIOS = 5
PERCENTIL_CARO = 80.0
PERCENTIL_BARATO = 20.0


# ==========================================================================
# EXTRACCIÓN
# ==========================================================================


def _fila(df: Any, claves: Sequence[str]) -> pd.Series | None:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    for clave in claves:
        if clave in df.index:
            fila = df.loc[clave]
            if isinstance(fila, pd.DataFrame):
                fila = fila.iloc[0]
            if fila.notna().any():
                return fila.astype(float)
    return None


def _a_fechas(indice) -> pd.DatetimeIndex | None:
    try:
        return pd.to_datetime(pd.Index(indice), errors="coerce")
    except Exception:
        return None


def _precio_tras_cierre(precios: pd.Series, cierre: pd.Timestamp, retardo: int) -> float | None:
    """Primer precio disponible una vez publicadas las cuentas."""
    if precios is None or precios.empty or pd.isna(cierre):
        return None
    objetivo = cierre + pd.Timedelta(days=retardo)
    posteriores = precios[precios.index >= objetivo]
    if posteriores.empty:
        return None
    return float(posteriores.iloc[0])


# ==========================================================================
# SERIE DE MÚLTIPLOS
# ==========================================================================


def serie_multiplos(
    precios: pd.Series,
    resultados: Any,
    balance: Any,
    flujos: Any,
    *,
    retardo_dias: int = RETARDO_PUBLICACION_DIAS,
) -> pd.DataFrame:
    """Serie anual de PER, EV/EBITDA y P/FCF con el precio ya publicable.

    ``precios`` es una serie de cierres indexada por fecha. Las tres tablas
    contables llevan los ejercicios en columnas, el más reciente primero.
    """
    if precios is None or not isinstance(precios, pd.Series) or precios.empty:
        return pd.DataFrame()

    precios = precios.dropna().sort_index()
    if not isinstance(precios.index, pd.DatetimeIndex):
        precios.index = pd.to_datetime(precios.index, errors="coerce")
        precios = precios[precios.index.notna()]

    beneficio = _fila(resultados, ["Net Income", "netIncome", "Net Income Continuous Operations"])
    if beneficio is None:
        return pd.DataFrame()

    fechas = _a_fechas(beneficio.index)
    if fechas is None:
        return pd.DataFrame()

    acciones = _fila(balance, ["Ordinary Shares Number", "Common Stock Shares Outstanding",
                               "weightedAverageShsOutDil", "weightedAverageShsOut"])
    if acciones is None:
        acciones = _fila(resultados, ["weightedAverageShsOutDil", "weightedAverageShsOut"])

    ebitda = _fila(resultados, ["EBITDA", "ebitda"])
    if ebitda is None:
        operativo = _fila(resultados, ["EBIT", "Operating Income", "operatingIncome"])
        amort = _fila(flujos, ["Depreciation And Amortization", "Depreciation",
                               "depreciationAndAmortization"])
        if operativo is not None and amort is not None:
            ebitda = operativo.add(amort, fill_value=np.nan)

    caja_op = _fila(flujos, ["Operating Cash Flow", "netCashProvidedByOperatingActivities",
                             "Total Cash From Operating Activities"])
    capex = _fila(flujos, ["Capital Expenditure", "capitalExpenditure"])
    deuda = _fila(balance, ["Total Debt", "totalDebt", "Long Term Debt", "longTermDebt"])
    efectivo = _fila(balance, ["Cash And Cash Equivalents", "cashAndCashEquivalents",
                               "Cash Cash Equivalents And Short Term Investments"])

    filas: list[dict[str, Any]] = []
    for posicion, cierre in enumerate(fechas):
        precio = _precio_tras_cierre(precios, cierre, retardo_dias)
        if precio is None:
            continue

        n_acciones = float(acciones.iloc[posicion]) if acciones is not None and posicion < len(acciones) else None
        if n_acciones is not None and (pd.isna(n_acciones) or n_acciones <= 0):
            n_acciones = None

        fila: dict[str, Any] = {"ejercicio": cierre.date().isoformat(), "precio": precio}

        # PER: precio entre beneficio por acción. Sin beneficio positivo el PER
        # no significa nada, así que se omite en vez de salir negativo.
        bpa = None
        if n_acciones:
            neto = float(beneficio.iloc[posicion])
            if not pd.isna(neto) and neto > 0:
                bpa = neto / n_acciones
        fila["PER"] = precio / bpa if bpa else np.nan

        # P/FCF: caja libre por acción.
        if n_acciones and caja_op is not None and capex is not None and posicion < len(caja_op):
            flujo = float(caja_op.iloc[posicion]) - abs(float(capex.iloc[posicion]))
            fila["P/FCF"] = precio / (flujo / n_acciones) if flujo > 0 else np.nan
        else:
            fila["P/FCF"] = np.nan

        # EV/EBITDA: capitalización más deuda neta, entre EBITDA.
        if n_acciones and ebitda is not None and posicion < len(ebitda):
            valor_ebitda = float(ebitda.iloc[posicion])
            capitalizacion = precio * n_acciones
            deuda_neta = 0.0
            if deuda is not None and posicion < len(deuda) and not pd.isna(deuda.iloc[posicion]):
                deuda_neta += float(deuda.iloc[posicion])
            if efectivo is not None and posicion < len(efectivo) and not pd.isna(efectivo.iloc[posicion]):
                deuda_neta -= float(efectivo.iloc[posicion])
            fila["EV/EBITDA"] = (capitalizacion + deuda_neta) / valor_ebitda if valor_ebitda > 0 else np.nan
        else:
            fila["EV/EBITDA"] = np.nan

        filas.append(fila)

    if not filas:
        return pd.DataFrame()

    tabla = pd.DataFrame(filas).set_index("ejercicio").sort_index()
    return tabla.replace([np.inf, -np.inf], np.nan)


# ==========================================================================
# PERCENTIL
# ==========================================================================


def percentil_en_su_historia(serie: pd.Series, valor_actual: float | None) -> float | None:
    """Porcentaje de la historia que queda POR DEBAJO del valor actual.

    100 = nunca ha estado tan caro. 0 = nunca tan barato. Devuelve None si no
    hay observaciones suficientes: sobre tres puntos, el percentil solo puede
    valer 0, 50 o 100, y esa precisión aparente es engañosa.
    """
    if valor_actual is None or pd.isna(valor_actual):
        return None
    limpia = pd.Series(serie).replace([np.inf, -np.inf], np.nan).dropna()
    if len(limpia) < MINIMO_EJERCICIOS:
        return None
    return round(float((limpia < valor_actual).mean() * 100), 1)


@dataclass(slots=True)
class MultiploHistorico:
    """Un múltiplo situado frente a su propio recorrido."""

    nombre: str
    actual: float | None
    percentil: float | None
    mediana: float | None
    minimo: float | None
    maximo: float | None
    observaciones: int

    @property
    def evaluable(self) -> bool:
        return self.percentil is not None

    @property
    def caro(self) -> bool:
        return self.percentil is not None and self.percentil >= PERCENTIL_CARO

    @property
    def barato(self) -> bool:
        return self.percentil is not None and self.percentil <= PERCENTIL_BARATO

    @property
    def lectura(self) -> str:
        if self.percentil is None:
            return "sin histórico suficiente"
        if self.caro:
            return f"en el {self.percentil:.0f}% más caro de su historia"
        if self.barato:
            return f"en el {self.percentil:.0f}% más barato de su historia"
        return f"en su rango habitual (percentil {self.percentil:.0f})"


@dataclass(slots=True)
class ResultadoMultiplos:
    """Los tres múltiplos frente a su historia."""

    multiplos: dict[str, MultiploHistorico] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    @property
    def evaluables(self) -> list[MultiploHistorico]:
        return [m for m in self.multiplos.values() if m.evaluable]

    @property
    def percentil_medio(self) -> float | None:
        """Media de los múltiplos que sí tienen histórico. None si ninguno."""
        vivos = self.evaluables
        if not vivos:
            return None
        return round(sum(m.percentil for m in vivos) / len(vivos), 1)

    @property
    def caro(self) -> bool:
        medio = self.percentil_medio
        return medio is not None and medio >= PERCENTIL_CARO


def evaluar_multiplos(
    precios: pd.Series,
    resultados: Any,
    balance: Any,
    flujos: Any,
    *,
    per_actual: float | None = None,
    pfcf_actual: float | None = None,
    ev_ebitda_actual: float | None = None,
    retardo_dias: int = RETARDO_PUBLICACION_DIAS,
) -> ResultadoMultiplos:
    """Sitúa los múltiplos actuales en el percentil de su propia historia.

    Los valores actuales se pueden pasar ya calculados (``investment_thesis``
    los expone como ``pe_actual`` y ``pfcf_actual``) para no recalcularlos.
    """
    tabla = serie_multiplos(precios, resultados, balance, flujos, retardo_dias=retardo_dias)
    resultado = ResultadoMultiplos()

    if tabla.empty:
        resultado.avisos.append("No se pudo construir la serie histórica de múltiplos.")
        return resultado

    actuales = {"PER": per_actual, "P/FCF": pfcf_actual, "EV/EBITDA": ev_ebitda_actual}
    for nombre, actual in actuales.items():
        if nombre not in tabla.columns:
            continue
        serie = tabla[nombre].replace([np.inf, -np.inf], np.nan).dropna()
        # Si no se pasa el valor actual, se usa el último de la serie.
        valor = actual if actual is not None else (float(serie.iloc[-1]) if not serie.empty else None)
        resultado.multiplos[nombre] = MultiploHistorico(
            nombre=nombre,
            actual=round(valor, 2) if valor is not None and not pd.isna(valor) else None,
            percentil=percentil_en_su_historia(serie, valor),
            mediana=round(float(serie.median()), 2) if not serie.empty else None,
            minimo=round(float(serie.min()), 2) if not serie.empty else None,
            maximo=round(float(serie.max()), 2) if not serie.empty else None,
            observaciones=int(len(serie)),
        )

    if not resultado.evaluables:
        resultado.avisos.append(
            f"Ningún múltiplo alcanza los {MINIMO_EJERCICIOS} ejercicios mínimos "
            "para situarlo en su historia."
        )
    return resultado
