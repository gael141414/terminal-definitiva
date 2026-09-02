"""Fallback de estados financieros vía yfinance cuando FMP no está disponible.

Motivación
----------
El plan contratado de FMP devuelve HTTP 402/403 ("restricted_plan") para un
subconjunto de símbolos que no se puede predecir por tamaño de empresa: AAPL o
MSFT responden, pero AXON, PETS, KHC, IBM, MCD... no. Hasta ahora eso dejaba la
pantalla de empresa con un error rojo y sin salida posible, porque reintentar no
arregla una restricción de plan.

Este módulo traduce ``yf.Ticker(...).income_stmt / .balance_sheet / .cashflow``
al **mismo esquema de columnas de FMP** que ya consumen ``financials/*.py``
(``revenue``, ``totalStockholdersEquity``, ``operatingCashFlow``, ...), de modo
que los analyzers y el scoring funcionan sin tocarse. Es un respaldo degradado,
no un sustituto: yfinance no expone key metrics (``metrics_df`` va a ``None``,
caso ya contemplado por ``financials/valuator.py``) y su histórico es de 4-5
ejercicios, no 10.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import yfinance as yf

from modulos.yahoo_resilience import safe_yfinance_fetch

logger = logging.getLogger(__name__)


# Mapa etiqueta-yfinance -> columna-FMP. Se listan varias etiquetas candidatas
# por concepto porque yfinance cambia nombres entre versiones y entre sectores
# (una financiera no publica "Cost Of Revenue"). Se toma la primera que exista.
_INCOME_MAP: dict[str, tuple[str, ...]] = {
    "revenue": ("Total Revenue", "Operating Revenue"),
    "costOfRevenue": ("Cost Of Revenue", "Reconciled Cost Of Revenue"),
    "grossProfit": ("Gross Profit",),
    "sellingGeneralAndAdministrativeExpenses": (
        "Selling General And Administration",
        "Selling General And Administrative",
    ),
    "researchAndDevelopmentExpenses": ("Research And Development",),
    "depreciationAndAmortization": (
        "Reconciled Depreciation",
        "Depreciation And Amortization In Income Statement",
    ),
    "interestExpense": ("Interest Expense", "Interest Expense Non Operating"),
    "operatingIncome": ("Operating Income", "Total Operating Income As Reported", "EBIT"),
    "incomeBeforeTax": ("Pretax Income",),
    "incomeTaxExpense": ("Tax Provision",),
    "netIncome": (
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income Continuous Operations",
    ),
    # Necesarios para financials/valuator.py: sin acciones ni EPS la serie de
    # beneficio por acción queda vacía y la valoración entera devuelve None.
    "weightedAverageShsOutDil": ("Diluted Average Shares",),
    "weightedAverageShsOut": ("Basic Average Shares",),
    "epsdiluted": ("Diluted EPS",),
    "eps": ("Basic EPS",),
}

_BALANCE_MAP: dict[str, tuple[str, ...]] = {
    "totalAssets": ("Total Assets",),
    "totalStockholdersEquity": ("Stockholders Equity", "Common Stock Equity"),
    "totalEquity": ("Total Equity Gross Minority Interest", "Stockholders Equity"),
    "totalDebt": ("Total Debt",),
    "shortTermDebt": ("Current Debt", "Current Debt And Capital Lease Obligation"),
    "longTermDebt": ("Long Term Debt", "Long Term Debt And Capital Lease Obligation"),
    "cashAndCashEquivalents": ("Cash And Cash Equivalents", "Cash Financial"),
    "shortTermInvestments": ("Other Short Term Investments",),
    "cashAndShortTermInvestments": ("Cash Cash Equivalents And Short Term Investments",),
    "retainedEarnings": ("Retained Earnings",),
    "propertyPlantEquipmentNet": ("Net PPE",),
}

_CASHFLOW_MAP: dict[str, tuple[str, ...]] = {
    "operatingCashFlow": ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
    "capitalExpenditure": ("Capital Expenditure", "Purchase Of PPE"),
    "freeCashFlow": ("Free Cash Flow",),
    "commonStockRepurchased": ("Repurchase Of Capital Stock", "Common Stock Payments"),
    "dividendsPaid": ("Cash Dividends Paid", "Common Stock Dividend Paid"),
    "depreciationAndAmortization": ("Depreciation And Amortization", "Depreciation Amortization Depletion"),
    "netIncome": ("Net Income From Continuing Operations", "Net Income"),
}


def _fila(df: pd.DataFrame, etiquetas: tuple[str, ...]) -> pd.Series | None:
    """Primera fila existente entre ``etiquetas``, ya numérica."""
    for etiqueta in etiquetas:
        if etiqueta in df.index:
            serie = pd.to_numeric(df.loc[etiqueta], errors="coerce")
            if serie.notna().any():
                return serie
    return None


def _traducir(df: pd.DataFrame | None, mapa: dict[str, tuple[str, ...]]) -> pd.DataFrame | None:
    """Convierte un estado de yfinance (conceptos en filas, fechas en columnas)
    al layout de FMP (periodos en filas, conceptos en columnas)."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None

    columnas: dict[str, pd.Series] = {}
    for campo_fmp, etiquetas in mapa.items():
        serie = _fila(df, etiquetas)
        if serie is not None:
            columnas[campo_fmp] = serie

    if not columnas:
        return None

    resultado = pd.DataFrame(columnas)
    # yfinance indexa por Timestamp de cierre de ejercicio; FMP por fecha + calendarYear.
    fechas = pd.to_datetime(resultado.index, errors="coerce")
    resultado = resultado.loc[fechas.notna()]
    if resultado.empty:
        return None

    resultado.index = pd.Index(pd.to_datetime(resultado.index), name="date")
    resultado = resultado.sort_index()
    # calendarYear se deriva del índice YA ORDENADO. Calcularlo antes del
    # sort_index() y asignarlo después lo desincroniza: la asignación de un
    # array a una columna es posicional, y yfinance entrega los ejercicios de
    # más reciente a más antiguo, así que cada fila acababa etiquetada con el
    # año de otra.
    resultado["calendarYear"] = resultado.index.year.astype(str)
    return resultado


def _capex_negativo(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """FMP publica ``capitalExpenditure`` en negativo; yfinance también, pero no
    siempre. Los analyzers hacen ``.abs()``, así que basta con dejarlo coherente."""
    return df


def obtener_fundamentales_yfinance(
    ticker: str,
    limite_anios: int = 5,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None, None]:
    """Respaldo de ``extraer_datos_fundamentales_fmp`` con la misma firma de salida.

    Devuelve ``(is_df, bs_df, cf_df, None)``. El cuarto elemento (key metrics) es
    siempre ``None`` porque yfinance no publica un equivalente; ``valorar_empresa``
    ya acepta ``metrics_df=None`` y degrada a cálculo propio.
    """
    simbolo = str(ticker or "").strip().upper()
    if not simbolo:
        return None, None, None, None

    try:
        yf_ticker = yf.Ticker(simbolo)
    except Exception as exc:  # pragma: no cover - construcción no debería fallar
        logger.warning("yfinance fallback: no se pudo crear Ticker(%s): %s", simbolo, exc)
        return None, None, None, None

    crudos: dict[str, pd.DataFrame | None] = {}
    for clave, atributo in (
        ("income", "income_stmt"),
        ("balance", "balance_sheet"),
        ("cashflow", "cashflow"),
    ):
        valor, status = safe_yfinance_fetch(
            lambda attr=atributo: getattr(yf_ticker, attr),
            empty_value=pd.DataFrame(),
            context=f"yfinance_fundamentals:{clave}:{simbolo}",
        )
        crudos[clave] = valor if status == "ok" else None

    is_df = _traducir(crudos["income"], _INCOME_MAP)
    bs_df = _traducir(crudos["balance"], _BALANCE_MAP)
    cf_df = _capex_negativo(_traducir(crudos["cashflow"], _CASHFLOW_MAP))

    if is_df is None and bs_df is None and cf_df is None:
        logger.warning("yfinance fallback: sin estados financieros para %s.", simbolo)
        return None, None, None, None

    # Recorte al histórico pedido (yfinance suele dar 4-5 ejercicios).
    limite = max(int(limite_anios), 1)
    is_df = is_df.tail(limite) if is_df is not None else None
    bs_df = bs_df.tail(limite) if bs_df is not None else None
    cf_df = cf_df.tail(limite) if cf_df is not None else None

    return is_df, bs_df, cf_df, None


def resumen_cobertura(is_df: Any, bs_df: Any, cf_df: Any) -> str:
    """Texto corto para explicar al usuario qué se pudo recuperar."""
    partes = []
    for nombre, df in (("resultados", is_df), ("balance", bs_df), ("flujo de caja", cf_df)):
        if df is not None and not df.empty:
            partes.append(f"{nombre} ({len(df)} ejercicios)")
    return ", ".join(partes) if partes else "sin datos"
