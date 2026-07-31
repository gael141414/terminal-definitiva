"""Motor de cruce score-vs-retorno (Sub-fase 4, calibración del score).

Cruza cada score congelado point-in-time (Sub-fase 3,
modulos.point_in_time_scoring) con su retorno futuro real a 6 meses y a 1
año, y agrega el resultado en deciles de score + correlación de rango
(Spearman) -- la pregunta que motiva todo este bloque: ¿el ValueQuant Score
predice algo del retorno futuro, o no?

Entrada/salida de precio
-------------------------
Reutiliza ``_entry_exit_prices`` de modulos.signal_backtesting (entrada =
primer cierre >= fecha del evento, salida = primer cierre >= fecha +
horizonte) sin reimplementarla -- ese módulo ya resuelve correctamente los
casos límite (fin de semana, festivo, serie corta). No se usa
``_download_close`` de ese mismo módulo porque asume un periodo fijo de 5
años hacia atrás desde HOY, insuficiente para los puntos de congelación más
antiguos de este bloque (hasta 2012 para los casos de supervivencia).

Precio histórico: yfinance seguía con su propio bug de cookie/crumb
contaminado por rate-limit (diagnosticado en la Sub-fase 3: su preflight de
autenticación recibía 429 en query1.finance.yahoo.com/v1/test/getcrumb
aunque el endpoint de datos, consultado directamente, respondía con
normalidad) en el momento de este trabajo. Se usa la misma vía de bypass ya
confirmada -- petición HTTP directa al endpoint de gráfico de Yahoo.

Universo FMP
-------------
Los ~78 tickers accesibles bajo el plan de FMP identificados en la
Sub-fase 2 nunca se guardaron en código -- solo se narró el conteo en el
mensaje de commit. Este módulo los redescubre en el momento: prueba un
conjunto amplio y diverso de tickers grandes/líquidos contra el propio
motor "as reported" de la Sub-fase 1/3, y los que devuelven datos SON el
universo de hoy. ``construir_dataset_fmp`` reporta cuántos candidatos se
probaron y cuántos resultaron accesibles -- no se asume que coincida con
los 78 originales de la Sub-fase 2 (el plan de FMP pudo cambiar desde
entonces).

Casos de supervivencia
------------------------
BBBY/SHLD/TOYS (modulos.survivorship_universe) se incluyen siempre en el
dataset con su score de fundamentales -- pero NINGUNO de los 3 tiene precio
histórico fiable hoy (ver ese módulo: BBBY se corrigió en esta misma
sub-fase -- su ticker fue reabsorbido por Overstock.com en 2023, que
reescribe silenciosamente el historial de precio bajo el mismo símbolo).
Se marcan explícitamente ``tiene_retorno=False`` con el motivo -- nunca se
descartan en silencio.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from scipy.stats import spearmanr

from modulos.point_in_time_scoring import (
    FrozenScore,
    _descargar_historial_yahoo_directo,
    congelar_score_fmp,
    congelar_score_sec,
    generar_puntos_de_congelacion_fmp,
    generar_puntos_de_congelacion_sec,
)
from modulos.signal_backtesting import _entry_exit_prices
from modulos.survivorship_universe import SURVIVORSHIP_CASES

DATA_FOLDER = Path("data")
RETURN_CROSSING_FILE = DATA_FOLDER / "return_crossing_results.json"
DECILES_6M_FILE = DATA_FOLDER / "return_crossing_deciles_6m.csv"
DECILES_1Y_FILE = DATA_FOLDER / "return_crossing_deciles_1y.csv"

HORIZONTE_6M_DIAS = 182
HORIZONTE_1A_DIAS = 365
_MARGEN_DESCARGA_DIAS = 15  # colchón tras el horizonte más largo, por días no bursátiles

_MIN_MUESTRA_SPEARMAN = 3
_MIN_MUESTRA_DECILES = 10

# Candidatos para redescubrir el universo FMP accesible (ver docstring del
# módulo: la lista real de 78 tickers de la Sub-fase 2 nunca se persistió).
# Gran caps líquidas de EE.UU., diversas por sector -- no es la misma lista
# de la Sub-fase 2, es una reconstrucción; el universo real de hoy es el
# subconjunto de esto que construir_dataset_fmp() confirme accesible.
#
# Lista recortada a propósito (~30, no ~120): extraer_datos_as_reported_fmp
# no cuesta 3 llamadas por ticker como parecía a primera vista -- internamente
# también llama a extraer_datos_fundamentales_fmp (el endpoint "legacy", para
# completar filing_dates, ver fmp_api.py) y ese hace hasta 4 llamadas más
# (income/balance/cash-flow/key-metrics). Bajo carga sostenida esto agota el
# límite de ráfaga de FMP en minutos con una lista de ~120 -- se prioriza un
# universo más chico pero completo (con pausa entre tickers) sobre uno más
# grande a medias por rate-limit.
CANDIDATOS_UNIVERSO_FMP: tuple[str, ...] = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "ORCL",
    "NFLX", "DIS", "T", "VZ",
    "JPM", "BAC", "GS", "MS", "AXP", "V", "MA", "PYPL",
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK",
    "WMT", "PG", "KO", "PEP", "COST", "MCD", "NKE", "HD",
    "BA", "CAT", "HON", "GE",
    "XOM", "CVX",
    "RIOT",
)


# ---------------------------------------------------------------------------
# 1. Precio histórico (bypass del bug de cookie/crumb de yfinance)
# ---------------------------------------------------------------------------


def descargar_cierre_yahoo_directo(ticker: str, start: str, end: str) -> pd.Series:
    """Serie de cierres diarios -- reutiliza el mismo bypass HTTP directo a
    Yahoo que modulos.point_in_time_scoring ya usa internamente (mismo bug
    de cookie/crumb de yfinance, mismo arreglo; una sola implementación
    para no duplicar la lógica de parseo del endpoint de gráfico). Nunca
    fabrica datos: Serie vacía ante cualquier fallo (HTTP, JSON, símbolo
    sin datos)."""
    hist = _descargar_historial_yahoo_directo(ticker, start, end)
    if hist.empty or "Close" not in hist.columns:
        return pd.Series(dtype=float)
    return hist["Close"].dropna()


def _rango_precio_necesario(puntos: list[dict[str, Any]]) -> tuple[str, str]:
    """Rango [inicio, fin] que cubre todos los puntos de congelación de un
    ticker más el horizonte de retorno más largo (1 año) del último punto."""
    fechas = [p["as_of_date"] for p in puntos]
    inicio = min(fechas)
    fin = (pd.Timestamp(max(fechas)) + pd.Timedelta(days=HORIZONTE_1A_DIAS + _MARGEN_DESCARGA_DIAS)).strftime("%Y-%m-%d")
    return inicio, fin


# ---------------------------------------------------------------------------
# 2. Cruce score <-> retorno
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetornoCruzado:
    """Un FrozenScore (Sub-fase 3) cruzado con su retorno futuro real a 6
    meses y 1 año. ``tiene_retorno`` es False cuando no hay precio fiable
    (casos de supervivencia sin cotización utilizable) o cuando no hay
    suficiente cobertura de precio tras la fecha de congelación -- en
    ningún caso se rellena con un número inventado."""

    identificador: str
    fuente: str
    as_of_date: str
    fiscal_year_mas_reciente_incluido: str | None
    final_score: float | None
    confidence: float | None
    verdict: str | None
    tiene_retorno: bool
    motivo_sin_retorno: str | None
    fecha_entrada: str | None
    precio_entrada: float | None
    retorno_6m: float | None
    fecha_salida_6m: str | None
    retorno_1y: float | None
    fecha_salida_1y: str | None
    generado_en: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _cruzar_retorno(score: FrozenScore, close: pd.Series, *, motivo_si_vacio: str) -> RetornoCruzado:
    base = {
        "identificador": score.identificador,
        "fuente": score.fuente,
        "as_of_date": score.as_of_date,
        "fiscal_year_mas_reciente_incluido": score.fiscal_year_mas_reciente_incluido,
        "final_score": score.final_score,
        "confidence": score.confidence,
        "verdict": score.verdict,
    }

    if close is None or close.empty:
        return RetornoCruzado(
            **base, tiene_retorno=False, motivo_sin_retorno=motivo_si_vacio,
            fecha_entrada=None, precio_entrada=None,
            retorno_6m=None, fecha_salida_6m=None, retorno_1y=None, fecha_salida_1y=None,
        )

    r6 = _entry_exit_prices(close, score.as_of_date, horizon_days=HORIZONTE_6M_DIAS)
    r1y = _entry_exit_prices(close, score.as_of_date, horizon_days=HORIZONTE_1A_DIAS)
    entrada = r6 or r1y

    retorno_6m = round((r6[3] / r6[1]) - 1.0, 6) if r6 else None
    retorno_1y = round((r1y[3] / r1y[1]) - 1.0, 6) if r1y else None
    tiene_retorno = retorno_6m is not None or retorno_1y is not None

    return RetornoCruzado(
        **base,
        tiene_retorno=tiene_retorno,
        motivo_sin_retorno=None if tiene_retorno else "sin cierre disponible en ventana suficiente tras la fecha de congelación",
        fecha_entrada=entrada[0].date().isoformat() if entrada else None,
        precio_entrada=round(float(entrada[1]), 4) if entrada else None,
        retorno_6m=retorno_6m,
        fecha_salida_6m=r6[2].date().isoformat() if r6 else None,
        retorno_1y=retorno_1y,
        fecha_salida_1y=r1y[2].date().isoformat() if r1y else None,
    )


# ---------------------------------------------------------------------------
# 3. Construcción del dataset
# ---------------------------------------------------------------------------


def construir_dataset_fmp(
    tickers_candidatos: list[str], *, limite_anios: int = 5, verbose: bool = False, pausa_segundos: float = 0.0
) -> tuple[list[RetornoCruzado], list[str]]:
    """Prueba cada candidato contra el motor "as reported" -- los que
    devuelven puntos de congelación SON el universo FMP accesible hoy (ver
    docstring del módulo: la lista de 78 de la Sub-fase 2 no se persistió).
    Devuelve (filas cruzadas, tickers que resultaron accesibles).

    ``verbose`` imprime una línea por candidato (accesible o no) -- este
    proceso es lento (varios FMP/Yahoo por ticker); sin esto, un batch de
    decenas de tickers no da ninguna señal de progreso hasta el final."""
    resultados: list[RetornoCruzado] = []
    accesibles: list[str] = []

    for i, ticker in enumerate(tickers_candidatos, start=1):
        if pausa_segundos and i > 1:
            time.sleep(pausa_segundos)
        puntos = generar_puntos_de_congelacion_fmp(ticker, limite_anios=limite_anios)
        if not puntos:
            if verbose:
                print(f"[{i}/{len(tickers_candidatos)}] {ticker}: no accesible", flush=True)
            continue
        accesibles.append(ticker)

        inicio, fin = _rango_precio_necesario(puntos)
        close = descargar_cierre_yahoo_directo(ticker, inicio, fin)

        n_antes = len(resultados)
        for punto in puntos:
            score = congelar_score_fmp(ticker, punto["as_of_date"], limite_anios=limite_anios)
            if score is None:
                continue
            resultados.append(
                _cruzar_retorno(score, close, motivo_si_vacio="sin precio histórico disponible en Yahoo para este ticker/rango")
            )

        if verbose:
            print(f"[{i}/{len(tickers_candidatos)}] {ticker}: accesible, {len(resultados) - n_antes} puntos de congelación", flush=True)

    return resultados, accesibles


def construir_dataset_supervivencia(*, años: int = 5) -> list[RetornoCruzado]:
    """Los 3 casos de supervivencia -- incluidos siempre con su score de
    fundamentales, marcados explícitamente sin retorno cuando (como es el
    caso de los 3 hoy, ver survivorship_universe.py) no hay precio fiable."""
    resultados: list[RetornoCruzado] = []

    for clave, caso in SURVIVORSHIP_CASES.items():
        puntos = generar_puntos_de_congelacion_sec(caso.cik, años=años)
        for punto in puntos:
            score = congelar_score_sec(caso.cik, punto["as_of_date"], caso.ticker_historico, años=años)
            if score is None:
                continue

            if not caso.precio_historico_disponible:
                resultados.append(
                    _cruzar_retorno(
                        score, pd.Series(dtype=float),
                        motivo_si_vacio=f"{clave}: sin precio histórico fiable (ver modulos.survivorship_universe -- {caso.nota[:140]}...)",
                    )
                )
                continue

            inicio, fin = _rango_precio_necesario(puntos)
            close = descargar_cierre_yahoo_directo(caso.ticker_historico, inicio, fin)
            resultados.append(
                _cruzar_retorno(score, close, motivo_si_vacio=f"{clave}: sin precio histórico disponible en Yahoo")
            )

    return resultados


# ---------------------------------------------------------------------------
# 4. Agregación: deciles y correlación de rango (Spearman)
# ---------------------------------------------------------------------------


def construir_dataframe(resultados: list[RetornoCruzado]) -> pd.DataFrame:
    return pd.DataFrame([asdict(r) for r in resultados])


def calcular_deciles(df: pd.DataFrame, columna_retorno: str) -> pd.DataFrame:
    """Deciles de score (solo filas con score Y retorno reales) -- retorno
    medio/mediano y tamaño de muestra por decil. Nunca imputa un score o
    retorno faltante; con menos de _MIN_MUESTRA_DECILES puntos utilizables
    devuelve un DataFrame vacío en vez de forzar deciles poco fiables."""
    sub = df[df["tiene_retorno"] & df["final_score"].notna() & df[columna_retorno].notna()].copy()
    if len(sub) < _MIN_MUESTRA_DECILES:
        return pd.DataFrame()

    try:
        sub["decil"] = pd.qcut(sub["final_score"], q=10, labels=False, duplicates="drop") + 1
    except ValueError:
        return pd.DataFrame()

    resumen = (
        sub.groupby("decil")
        .agg(
            n=(columna_retorno, "size"),
            score_medio=("final_score", "mean"),
            score_min=("final_score", "min"),
            score_max=("final_score", "max"),
            retorno_medio=(columna_retorno, "mean"),
            retorno_mediana=(columna_retorno, "median"),
        )
        .reset_index()
        .sort_values("decil")
    )
    return resumen


def calcular_spearman(df: pd.DataFrame, columna_retorno: str) -> dict[str, Any]:
    """Correlación de rango (Spearman) entre final_score y el retorno dado.
    Con menos de _MIN_MUESTRA_SPEARMAN puntos, devuelve rho=None explícito
    en vez de un número no significativo -- el tamaño de muestra siempre
    viaja junto al resultado para que nunca se lea sin ese contexto."""
    sub = df[df["tiene_retorno"] & df["final_score"].notna() & df[columna_retorno].notna()]
    n = len(sub)
    if n < _MIN_MUESTRA_SPEARMAN:
        return {"n": n, "rho": None, "p_value": None, "nota": f"muestra insuficiente (< {_MIN_MUESTRA_SPEARMAN} puntos) para calcular Spearman"}

    rho, p_value = spearmanr(sub["final_score"], sub[columna_retorno])
    return {"n": n, "rho": round(float(rho), 4), "p_value": round(float(p_value), 4)}


# ---------------------------------------------------------------------------
# 5. Persistencia (dominio propio -- extiende la Sub-fase 3, no
# analysis_store.py)
# ---------------------------------------------------------------------------


def _ensure_data_folder() -> None:
    DATA_FOLDER.mkdir(parents=True, exist_ok=True)


def guardar_resultado(
    resultados: list[RetornoCruzado],
    *,
    universo_probado: list[str],
    universo_accesible: list[str],
    path: Path = RETURN_CROSSING_FILE,
) -> dict[str, Any]:
    """Persiste el dataset fila a fila más el resumen agregado (deciles +
    Spearman a 6m y 1y) en un único JSON auditable, y los deciles también
    en CSV aparte para inspección tabular directa. Devuelve el resumen
    (mismo contenido que queda en el JSON) para poder reportarlo sin releer
    el archivo."""
    _ensure_data_folder()
    df = construir_dataframe(resultados)

    deciles_6m = calcular_deciles(df, "retorno_6m") if not df.empty else pd.DataFrame()
    deciles_1y = calcular_deciles(df, "retorno_1y") if not df.empty else pd.DataFrame()
    spearman_6m = calcular_spearman(df, "retorno_6m") if not df.empty else {"n": 0, "rho": None, "p_value": None}
    spearman_1y = calcular_spearman(df, "retorno_1y") if not df.empty else {"n": 0, "rho": None, "p_value": None}

    resumen = {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "universo_fmp_probado": len(universo_probado),
        "universo_fmp_accesible": len(universo_accesible),
        "tickers_fmp_accesibles": sorted(universo_accesible),
        "tamaño_muestra_total_filas": len(resultados),
        "tamaño_muestra_con_retorno_6m": int(df["retorno_6m"].notna().sum()) if not df.empty else 0,
        "tamaño_muestra_con_retorno_1y": int(df["retorno_1y"].notna().sum()) if not df.empty else 0,
        "spearman_6m": spearman_6m,
        "spearman_1y": spearman_1y,
        "deciles_6m": deciles_6m.to_dict(orient="records"),
        "deciles_1y": deciles_1y.to_dict(orient="records"),
    }

    with path.open("w", encoding="utf-8") as fh:
        json.dump({**resumen, "filas": [asdict(r) for r in resultados]}, fh, indent=2, ensure_ascii=False, default=str)

    if not deciles_6m.empty:
        deciles_6m.to_csv(DECILES_6M_FILE, index=False)
    if not deciles_1y.empty:
        deciles_1y.to_csv(DECILES_1Y_FILE, index=False)

    return resumen


def cargar_resultado(*, path: Path = RETURN_CROSSING_FILE) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None
