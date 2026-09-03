"""Puntuaciones forenses como funciones puras: Altman, Beneish y Piotroski.

Estas tres métricas se calculaban dentro de ``charts.py``, mezcladas con la
construcción de la figura de Plotly y pidiendo los datos a Yahoo por su cuenta.
Eso las hacía inservibles fuera de un gráfico: para conocer el Z-Score había que
dibujar un medidor y tirarlo. Aquí reciben DataFrames y devuelven números.

Un cambio de criterio respecto a la versión anterior
----------------------------------------------------
La implementación original sustituía cualquier dato ausente por ``0.001`` "para
evitar divisiones por cero". El efecto real era peor que un error: dividir entre
0,001 produce ratios de miles que se presentaban como puntuaciones legítimas —
una empresa sin el dato de activos totales salía con un Z-Score altísimo, es
decir, en zona segura. Aquí un campo obligatorio ausente devuelve ``None`` y se
enumera en ``campos_ausentes``. Preferimos no saber a saber mal, sobre todo en
una métrica cuyo objetivo es detectar riesgo de quiebra.

Orientación de los DataFrames: la de yfinance y FMP en este repositorio —
índice = concepto contable, columnas = ejercicios, el más reciente primero.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

import pandas as pd

LOGGER = logging.getLogger("valuequant.forense")

__all__ = [
    "AltmanZ", "BeneishM", "PiotroskiF",
    "altman_z_score", "beneish_m_score", "piotroski_f_score",
    "ZONA_PELIGRO", "ZONA_GRIS", "ZONA_SEGURA", "ZONA_DESCONOCIDA",
]

ZONA_PELIGRO = "peligro"
ZONA_GRIS = "gris"
ZONA_SEGURA = "segura"
ZONA_DESCONOCIDA = "desconocida"

# Altman clásico (empresas cotizadas industriales).
UMBRAL_ALTMAN_PELIGRO = 1.81
UMBRAL_ALTMAN_SEGURO = 2.99

# Altman Z'' (servicios y mercados emergentes): no usa rotación de activos, así
# que la escala es distinta y no son intercambiables.
UMBRAL_ALTMAN_DP_PELIGRO = 1.10
UMBRAL_ALTMAN_DP_SEGURO = 2.60


# ==========================================================================
# EXTRACCIÓN
# ==========================================================================


def _serie(df: Any, claves: Sequence[str]) -> pd.Series | None:
    """Primera fila que exista entre ``claves``. None si no está ninguna."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    for clave in claves:
        if clave in df.index:
            fila = df.loc[clave]
            if isinstance(fila, pd.DataFrame):      # índice duplicado
                fila = fila.iloc[0]
            if fila.notna().any():
                return fila
    return None


def _valor(df: Any, claves: Sequence[str], ejercicio: int = 0) -> float | None:
    """Valor de un concepto en un ejercicio. None si falta: nunca un sustituto."""
    fila = _serie(df, claves)
    if fila is None or len(fila) <= ejercicio:
        return None
    valor = fila.iloc[ejercicio]
    if pd.isna(valor):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _dividir(numerador: float | None, denominador: float | None) -> float | None:
    """División que devuelve None en vez de inventar un denominador."""
    if numerador is None or denominador is None or denominador == 0:
        return None
    return numerador / denominador


# ==========================================================================
# ALTMAN Z-SCORE
# ==========================================================================


@dataclass(slots=True)
class AltmanZ:
    """Riesgo de quiebra a dos años."""

    valor: float | None
    modelo: str                       # "clasico" | "doble_prima"
    zona: str
    componentes: dict[str, float] = field(default_factory=dict)
    campos_ausentes: list[str] = field(default_factory=list)

    @property
    def evaluable(self) -> bool:
        return self.valor is not None

    @property
    def en_peligro(self) -> bool:
        if self.valor is None:
            return False
        umbral = (UMBRAL_ALTMAN_DP_PELIGRO if self.modelo == "doble_prima"
                  else UMBRAL_ALTMAN_PELIGRO)
        return self.valor < umbral


def _zona_altman(valor: float, modelo: str) -> str:
    peligro = UMBRAL_ALTMAN_DP_PELIGRO if modelo == "doble_prima" else UMBRAL_ALTMAN_PELIGRO
    seguro = UMBRAL_ALTMAN_DP_SEGURO if modelo == "doble_prima" else UMBRAL_ALTMAN_SEGURO
    if valor < peligro:
        return ZONA_PELIGRO
    if valor < seguro:
        return ZONA_GRIS
    return ZONA_SEGURA


def altman_z_score(
    balance: Any,
    resultados: Any,
    capitalizacion: float | None = None,
    *,
    modelo: str = "clasico",
) -> AltmanZ:
    """Altman Z-Score.

    ``clasico`` (Z, cotizadas industriales)::

        Z = 1,2·X1 + 1,4·X2 + 3,3·X3 + 0,6·X4 + 1,0·X5

    ``doble_prima`` (Z'', servicios y emergentes) prescinde de X5 —la rotación de
    activos— porque penaliza a las empresas de servicios, y usa valor CONTABLE
    del patrimonio en X4, así que no necesita capitalización::

        Z'' = 6,56·X1 + 3,26·X2 + 6,72·X3 + 1,05·X4

    Las dos escalas son distintas: 1,8 en la clásica y 1,1 en la doble prima
    marcan la zona de peligro. Comparar un Z con un Z'' no significa nada.
    """
    ausentes: list[str] = []

    def obligatorio(nombre: str, claves: Sequence[str], df: Any, ejercicio: int = 0):
        valor = _valor(df, claves, ejercicio)
        if valor is None:
            ausentes.append(nombre)
        return valor

    activos = obligatorio("activo total", ["Total Assets", "totalAssets"], balance)
    pasivos = obligatorio(
        "pasivo total",
        ["Total Liabilities Net Minority Interest", "Total Liabilities", "totalLiabilities"],
        balance,
    )
    act_corr = obligatorio("activo corriente", ["Current Assets", "Total Current Assets", "totalCurrentAssets"], balance)
    pas_corr = obligatorio("pasivo corriente", ["Current Liabilities", "Total Current Liabilities", "totalCurrentLiabilities"], balance)
    reservas = obligatorio("reservas", ["Retained Earnings", "retainedEarnings"], balance)
    ebit = obligatorio("EBIT", ["EBIT", "Operating Income", "operatingIncome"], resultados)

    componentes: dict[str, float] = {}
    x1 = _dividir(
        (act_corr - pas_corr) if act_corr is not None and pas_corr is not None else None,
        activos,
    )
    x2 = _dividir(reservas, activos)
    x3 = _dividir(ebit, activos)

    if modelo == "doble_prima":
        patrimonio = obligatorio(
            "patrimonio neto",
            ["Stockholders Equity", "Total Stockholder Equity", "totalStockholdersEquity"],
            balance,
        )
        x4 = _dividir(patrimonio, pasivos)
        partes = {"X1": (x1, 6.56), "X2": (x2, 3.26), "X3": (x3, 6.72), "X4": (x4, 1.05)}
    else:
        if capitalizacion is None:
            ausentes.append("capitalización bursátil")
        x4 = _dividir(capitalizacion, pasivos)
        ventas = obligatorio("ventas", ["Total Revenue", "Operating Revenue", "revenue"], resultados)
        x5 = _dividir(ventas, activos)
        partes = {"X1": (x1, 1.2), "X2": (x2, 1.4), "X3": (x3, 3.3), "X4": (x4, 0.6), "X5": (x5, 1.0)}

    total = 0.0
    for nombre, (valor, peso) in partes.items():
        if valor is None:
            if nombre not in ("X4",) or "capitalización bursátil" not in ausentes:
                ausentes.append(f"componente {nombre}")
            return AltmanZ(None, modelo, ZONA_DESCONOCIDA, componentes, sorted(set(ausentes)))
        componentes[nombre] = valor
        total += peso * valor

    return AltmanZ(round(total, 4), modelo, _zona_altman(total, modelo), componentes, sorted(set(ausentes)))


# ==========================================================================
# BENEISH M-SCORE
# ==========================================================================


@dataclass(slots=True)
class BeneishM:
    """Probabilidad de manipulación contable a partir de ocho índices."""

    valor: float | None
    indices: dict[str, float] = field(default_factory=dict)
    campos_ausentes: list[str] = field(default_factory=list)

    @property
    def evaluable(self) -> bool:
        return self.valor is not None

    def sospechoso(self, umbral: float = -1.78) -> bool:
        """Por encima del umbral, el modelo marca riesgo de manipulación.

        La literatura maneja dos cortes: −2,22 (el original de Beneish, más
        conservador, menos falsos positivos) y −1,78 (más sensible). El valor
        por defecto es el sensible porque aquí se usa como señal de alerta, no
        como acusación.
        """
        return self.valor is not None and self.valor > umbral


def beneish_m_score(balance: Any, resultados: Any, flujos: Any) -> BeneishM:
    """Beneish M-Score. Necesita DOS ejercicios: mide variación, no nivel."""
    ausentes: list[str] = []

    def par(nombre: str, claves: Sequence[str], df: Any) -> tuple[float | None, float | None]:
        actual = _valor(df, claves, 0)
        previo = _valor(df, claves, 1)
        if actual is None or previo is None:
            ausentes.append(nombre)
        return actual, previo

    ventas0, ventas1 = par("ventas", ["Total Revenue", "Operating Revenue", "revenue"], resultados)
    coste0, coste1 = par("coste de ventas", ["Cost Of Revenue", "Cost of Goods Sold", "costOfRevenue"], resultados)
    clientes0, clientes1 = par("clientes", ["Accounts Receivable", "Net Receivables", "netReceivables"], balance)
    activos0, activos1 = par("activo total", ["Total Assets", "totalAssets"], balance)
    corr0, corr1 = par("activo corriente", ["Current Assets", "Total Current Assets", "totalCurrentAssets"], balance)
    ppe0, ppe1 = par("inmovilizado", ["Net PPE", "Property Plant And Equipment", "propertyPlantEquipmentNet"], balance)
    amort0, amort1 = par("amortización", ["Depreciation", "Depreciation And Amortization", "depreciationAndAmortization"], flujos)
    gastos0, gastos1 = par("gastos generales", ["Selling General And Administration", "SG&A", "sellingGeneralAndAdministrativeExpenses"], resultados)
    pcorr0, pcorr1 = par("pasivo corriente", ["Current Liabilities", "Total Current Liabilities", "totalCurrentLiabilities"], balance)
    deuda0, deuda1 = par("deuda a largo", ["Long Term Debt", "Total Long Term Debt", "longTermDebt"], balance)

    beneficio = _valor(resultados, ["Net Income", "Net Income Continuous Operations", "netIncome"], 0)
    caja_op = _valor(flujos, ["Operating Cash Flow", "Total Cash From Operating Activities", "netCashProvidedByOperatingActivities"], 0)
    if beneficio is None:
        ausentes.append("beneficio neto")
    if caja_op is None:
        ausentes.append("flujo de caja operativo")

    if ausentes:
        return BeneishM(None, {}, sorted(set(ausentes)))

    def ratio(a, b, c, d):
        primero, segundo = _dividir(a, b), _dividir(c, d)
        return _dividir(primero, segundo)

    indices: dict[str, float | None] = {
        # Ventas pendientes de cobro: si sube, se está reconociendo ingreso que
        # todavía no se ha cobrado.
        "DSRI": ratio(clientes0, ventas0, clientes1, ventas1),
        # Margen bruto: si sube el índice, el margen se está deteriorando.
        "GMI": _dividir(
            _dividir(ventas1 - coste1, ventas1),
            _dividir(ventas0 - coste0, ventas0),
        ),
        # Calidad del activo: proporción de activo que no es corriente ni fijo.
        "AQI": _dividir(
            1 - (_dividir((corr0 or 0) + (ppe0 or 0), activos0) or 0),
            1 - (_dividir((corr1 or 0) + (ppe1 or 0), activos1) or 0),
        ),
        "SGI": _dividir(ventas0, ventas1),
        # Amortización: si se ralentiza, el beneficio sube sin que pase nada real.
        "DEPI": _dividir(
            _dividir(amort1, (ppe1 or 0) + (amort1 or 0)),
            _dividir(amort0, (ppe0 or 0) + (amort0 or 0)),
        ),
        "SGAI": ratio(gastos0, ventas0, gastos1, ventas1),
        "LVGI": _dividir(
            _dividir((pcorr0 or 0) + (deuda0 or 0), activos0),
            _dividir((pcorr1 or 0) + (deuda1 or 0), activos1),
        ),
        # Devengos: distancia entre el beneficio contable y la caja real.
        "TATA": _dividir(beneficio - caja_op, activos0),
    }

    faltan = [k for k, v in indices.items() if v is None]
    if faltan:
        return BeneishM(None, {}, sorted(set(ausentes + [f"índice {k}" for k in faltan])))

    limpios = {k: float(v) for k, v in indices.items()}
    m = (
        -4.84
        + 0.920 * limpios["DSRI"]
        + 0.528 * limpios["GMI"]
        + 0.404 * limpios["AQI"]
        + 0.892 * limpios["SGI"]
        + 0.115 * limpios["DEPI"]
        - 0.172 * limpios["SGAI"]
        + 4.679 * limpios["TATA"]
        - 0.327 * limpios["LVGI"]
    )
    return BeneishM(round(m, 4), {k: round(v, 4) for k, v in limpios.items()}, [])


# ==========================================================================
# PIOTROSKI F-SCORE
# ==========================================================================


@dataclass(slots=True)
class PiotroskiF:
    """Solidez fundamental en nueve criterios binarios (0-9)."""

    valor: int | None
    criterios: dict[str, bool] = field(default_factory=dict)
    evaluados: int = 0
    campos_ausentes: list[str] = field(default_factory=list)

    @property
    def evaluable(self) -> bool:
        return self.valor is not None

    @property
    def debil(self) -> bool:
        """3 o menos es la mitad baja de la escala original de Piotroski."""
        return self.valor is not None and self.valor <= 3


def piotroski_f_score(balance: Any, resultados: Any, flujos: Any) -> PiotroskiF:
    """F-Score de Piotroski: rentabilidad, apalancamiento y eficiencia.

    Se puntúan solo los criterios con datos. ``valor`` es la suma de los
    cumplidos y ``evaluados`` cuántos se pudieron mirar, para que un 4 sobre 4
    no se confunda con un 4 sobre 9.
    """
    ausentes: list[str] = []
    criterios: dict[str, bool] = {}

    def dato(nombre, claves, df, ejercicio=0):
        v = _valor(df, claves, ejercicio)
        if v is None:
            ausentes.append(f"{nombre} (año {ejercicio})")
        return v

    activos0 = dato("activo total", ["Total Assets", "totalAssets"], balance, 0)
    activos1 = dato("activo total", ["Total Assets", "totalAssets"], balance, 1)
    beneficio0 = dato("beneficio neto", ["Net Income", "netIncome"], resultados, 0)
    beneficio1 = dato("beneficio neto", ["Net Income", "netIncome"], resultados, 1)
    caja0 = dato("flujo operativo", ["Operating Cash Flow", "netCashProvidedByOperatingActivities"], flujos, 0)
    deuda0 = dato("deuda a largo", ["Long Term Debt", "longTermDebt"], balance, 0)
    deuda1 = dato("deuda a largo", ["Long Term Debt", "longTermDebt"], balance, 1)
    corr0 = dato("activo corriente", ["Current Assets", "totalCurrentAssets"], balance, 0)
    corr1 = dato("activo corriente", ["Current Assets", "totalCurrentAssets"], balance, 1)
    pcorr0 = dato("pasivo corriente", ["Current Liabilities", "totalCurrentLiabilities"], balance, 0)
    pcorr1 = dato("pasivo corriente", ["Current Liabilities", "totalCurrentLiabilities"], balance, 1)
    ventas0 = dato("ventas", ["Total Revenue", "revenue"], resultados, 0)
    ventas1 = dato("ventas", ["Total Revenue", "revenue"], resultados, 1)
    coste0 = dato("coste de ventas", ["Cost Of Revenue", "costOfRevenue"], resultados, 0)
    coste1 = dato("coste de ventas", ["Cost Of Revenue", "costOfRevenue"], resultados, 1)
    acciones0 = _valor(balance, ["Ordinary Shares Number", "Common Stock Shares Outstanding", "weightedAverageShsOutDil"], 0)
    acciones1 = _valor(balance, ["Ordinary Shares Number", "Common Stock Shares Outstanding", "weightedAverageShsOutDil"], 1)

    roa0 = _dividir(beneficio0, activos0)
    roa1 = _dividir(beneficio1, activos1)

    # Rentabilidad
    if roa0 is not None:
        criterios["ROA positivo"] = roa0 > 0
    if caja0 is not None:
        criterios["Flujo operativo positivo"] = caja0 > 0
    if roa0 is not None and roa1 is not None:
        criterios["ROA mejora"] = roa0 > roa1
    if caja0 is not None and beneficio0 is not None and activos0:
        criterios["Caja por encima del beneficio"] = _dividir(caja0, activos0) > (roa0 or 0)

    # Apalancamiento y liquidez
    apal0, apal1 = _dividir(deuda0, activos0), _dividir(deuda1, activos1)
    if apal0 is not None and apal1 is not None:
        criterios["Apalancamiento baja"] = apal0 < apal1
    liq0, liq1 = _dividir(corr0, pcorr0), _dividir(corr1, pcorr1)
    if liq0 is not None and liq1 is not None:
        criterios["Liquidez mejora"] = liq0 > liq1
    if acciones0 is not None and acciones1 is not None:
        criterios["Sin dilución"] = acciones0 <= acciones1

    # Eficiencia
    mb0 = _dividir((ventas0 - coste0) if ventas0 is not None and coste0 is not None else None, ventas0)
    mb1 = _dividir((ventas1 - coste1) if ventas1 is not None and coste1 is not None else None, ventas1)
    if mb0 is not None and mb1 is not None:
        criterios["Margen bruto mejora"] = mb0 > mb1
    rot0, rot1 = _dividir(ventas0, activos0), _dividir(ventas1, activos1)
    if rot0 is not None and rot1 is not None:
        criterios["Rotación de activos mejora"] = rot0 > rot1

    if not criterios:
        return PiotroskiF(None, {}, 0, sorted(set(ausentes)))

    return PiotroskiF(
        valor=sum(1 for v in criterios.values() if v),
        criterios=criterios,
        evaluados=len(criterios),
        campos_ausentes=sorted(set(ausentes)),
    )
