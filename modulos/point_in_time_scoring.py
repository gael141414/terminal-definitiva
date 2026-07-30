"""Motor de scoring point-in-time (Sub-fase 3, calibración del score).

Ejecuta la lógica ACTUAL de scoring_engine.py/financials/* (sin modificarlas)
sobre fundamentales reconstruidos tal como estaban disponibles públicamente
en una fecha histórica concreta -- nunca usa un dato cuya fecha de filing
sea posterior a esa fecha. Esa es la regla que evita el look-ahead bias que
motivó todo este bloque de calibración.

Dos fuentes, ambas ya construidas en sub-fases anteriores:

- FMP "as reported" (Sub-fase 1, modulos.fmp_api.extraer_datos_as_reported_fmp)
  para los ~78 tickers ya confirmados accesibles bajo el plan actual.
- SEC EDGAR (downloader.py, con filing_dates desde la Sub-fase 0) para los
  3 casos de supervivencia curados por CIK (Sub-fase 2,
  modulos.survivorship_universe).

Ambas fuentes ya traen ``filing_dates`` (dict año -> fecha ISO) vía
``df.attrs`` -- este módulo solo añade el paso que faltaba: filtrar por esa
fecha antes de pasarle nada a los analizadores.

Reshape "as reported" -> forma "_legacy"
------------------------------------------
FMP "as reported" viene con fecha como índice y el concepto XBRL en bruto
(minúsculas) como columna -- una forma distinta tanto de la FMP normalizada
como de la "_legacy" (concepto como fila vía columna "concept", año como
columna) que ya usan income_analyzer.py/balance_analyzer.py/
cashflow_analyzer.py. Se transpone a la forma "_legacy" -- que ya sabe
interpretar cualquier nombre de concepto XBRL, con o sin prefijo de
espacio de nombres, vía regex case-insensitive en extraer_dato_robusto --
en vez de tocar esos 3 analizadores. La ruta SEC ya viene nativamente en
esa forma (no hace falta reshape, solo el filtro de fecha).

Precio y snapshot de mercado: qué es reconstruible y qué no
--------------------------------------------------------------
``valorar_empresa`` (financials/valuator.py) llama internamente a
``obtener_cotizacion_fmp(ticker)`` -- la cotización ACTUAL, no la histórica.
``calcular_valuequant_score`` (scoring_engine.py) llama internamente a
``_market_data_snapshot(ticker)`` -- también el snapshot ACTUAL (beta,
market cap, sector, insiders, institucionales, short ratio vía
``yf.Ticker().info``, que no acepta fecha; más RSI/retornos/volatilidad/
drawdown/medias móviles vía ``.history()``, que sí acepta rango de fechas).
Ninguna de las dos funciones tiene un parámetro para pedir una fecha
pasada, y no se van a modificar. Este módulo sustituye temporalmente esos
dos nombres a nivel de módulo (mismo mecanismo que ya usa esta suite de
tests para inyectar dobles, aplicado aquí en código de producción en vez de
en un test) por versiones que sí aceptan fecha, y los restaura al terminar.

De lo que usa ``_market_data_snapshot``, esto es lo reconstruible con
``yfinance`` y una fecha de corte, y esto no:

- Reconstruible (derivado de precio, ``.history(start=..., end=as_of)``):
  RSI, retorno 6m/1y, volatilidad 1y, drawdown máximo 1y, cruces de medias
  móviles 50/200, y ``sector_rel_3m`` (usa el mismo sector ETF que hoy).
- NO reconstruible con ``yfinance`` (``.info`` solo da el instante actual,
  sin fecha): beta, market cap, % insiders, % institucional, short ratio.
  Se dejan explícitamente en ``None`` -- nunca se rellenan con el valor de
  hoy a modo de proxy silencioso. Como consecuencia, los componentes que
  dependen de ellos (Riesgo y forense usa beta; Asignación de capital,
  Momentum, Macro y Alt-data usan el snapshot completo) quedan con menor
  confianza en el score congelado -- exactamente el mecanismo de cobertura/
  confianza que scoring_engine.py ya tiene, sin necesidad de tocarlo.
  Única excepción: ``sector`` se toma del snapshot actual como proxy
  documentado (cambia con muy poca frecuencia; sin él, ``sector_rel_3m``
  tampoco sería calculable en absoluto).

No es thread-safe (sustituye nombres a nivel de módulo temporalmente) --
pensado para un proceso batch secuencial, no para el request path de la
app Streamlit en vivo.
"""

from __future__ import annotations

import json
import math
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

import financials.valuator as valuator
import modulos.scoring_engine as scoring_engine
from financials.balance_analyzer import analizar_balance
from financials.cashflow_analyzer import analizar_flujo_efectivo
from financials.income_analyzer import analizar_cuenta_resultados
from financials.valuator import valorar_empresa
from modulos.fmp_api import extraer_datos_as_reported_fmp
from modulos.scoring_engine import calcular_valuequant_score
from modulos.yahoo_resilience import safe_yfinance_fetch, safe_yfinance_info

DATA_FOLDER = Path("data")
FROZEN_SCORES_FILE = DATA_FOLDER / "point_in_time_scores.json"

_METADATA_COLUMNS_AS_REPORTED = {"fiscalYear", "period"}

# Misma tabla que _market_data_snapshot (scoring_engine.py) -- duplicada a
# propósito: no hay forma de reutilizarla sin modificar ese módulo, y es
# solo una tabla de constantes, no lógica de negocio.
_SECTOR_TO_ETF = {
    "Technology": "XLK", "Communication Services": "XLC", "Financial Services": "XLF",
    "Healthcare": "XLV", "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
    "Industrials": "XLI", "Energy": "XLE", "Utilities": "XLU",
    "Real Estate": "XLRE", "Basic Materials": "XLB",
}


# ---------------------------------------------------------------------------
# 1. Reconstrucción de fundamentales point-in-time
# ---------------------------------------------------------------------------


def _as_reported_a_forma_legacy(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Transpone el DataFrame 'as reported' (fecha=índice, concepto=columna)
    a la forma que ya entienden analizar_cuenta_resultados/analizar_balance/
    analizar_flujo_efectivo cuando el estado no es FMP normalizado: columna
    'concept' + una columna por año (mismo formato que ya produce
    downloader.py para SEC/XBRL). Conserva filing_dates/accepted_dates en
    .attrs (no sobreviven la reconstrucción de un DataFrame nuevo por
    defecto -- hay que copiarlos a mano)."""
    if df is None or df.empty:
        return None

    conceptos = [c for c in df.columns if c not in _METADATA_COLUMNS_AS_REPORTED]
    if not conceptos:
        return None

    filas: list[dict[str, Any]] = []
    for concepto in conceptos:
        fila: dict[str, Any] = {"concept": concepto}
        for idx in df.index:
            fila[str(idx.year)] = df.at[idx, concepto]
        filas.append(fila)

    resultado = pd.DataFrame(filas)
    resultado.attrs["filing_dates"] = dict(df.attrs.get("filing_dates", {}))
    resultado.attrs["accepted_dates"] = dict(df.attrs.get("accepted_dates", {}))
    return resultado


def _filtrar_columnas_por_filing_date(df: pd.DataFrame | None, as_of_date: str) -> pd.DataFrame | None:
    """Descarta las columnas-año cuya fecha de filing sea posterior a
    as_of_date, o cuya fecha de filing se desconozca -- un año sin fecha
    conocida nunca se asume disponible (mismo principio de "nunca dato
    artificial" que el resto del proyecto). Requiere que df traiga
    filing_dates en .attrs (ver _as_reported_a_forma_legacy / downloader.py)."""
    if df is None or df.empty:
        return None

    filing_dates = df.attrs.get("filing_dates", {})
    as_of_ts = pd.Timestamp(as_of_date)

    años_permitidos = set()
    for year, filing_date in filing_dates.items():
        if not filing_date:
            continue
        try:
            if pd.Timestamp(filing_date) <= as_of_ts:
                años_permitidos.add(str(year))
        except (ValueError, TypeError):
            continue

    metadata_cols = [c for c in df.columns if not str(c).isdigit()]
    year_cols = [c for c in df.columns if str(c) in años_permitidos]
    if not year_cols:
        return None

    filtrado = df[metadata_cols + year_cols].copy()
    filtrado.attrs["filing_dates"] = {y: filing_dates[y] for y in años_permitidos if y in filing_dates}
    return filtrado


def construir_fundamentales_point_in_time_fmp(
    ticker: str,
    as_of_date: str,
    *,
    limite_anios: int = 5,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None]:
    """Reconstruye income/balance/cashflow "as reported" de FMP tal como
    estaban disponibles públicamente en as_of_date. Nunca incluye un año
    cuya fecha de filing sea posterior a as_of_date."""
    df_is, df_bs, df_cf = extraer_datos_as_reported_fmp(ticker, limite_anios)
    resultado = []
    for df in (df_is, df_bs, df_cf):
        legacy = _as_reported_a_forma_legacy(df)
        resultado.append(_filtrar_columnas_por_filing_date(legacy, as_of_date))
    return tuple(resultado)  # type: ignore[return-value]


def construir_fundamentales_point_in_time_sec(
    cik: int | str,
    as_of_date: str,
    *,
    años: int = 5,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None]:
    """Igual que la versión FMP, pero vía SEC EDGAR (downloader.py) -- para
    los casos de supervivencia (Sub-fase 2), identificados por CIK, no por
    ticker. downloader.py ya expone filing_dates (Sub-fase 0); aquí solo se
    aplica el mismo filtro por fecha."""
    import downloader

    df_is, df_bs, df_cf, status = downloader.obtener_estados_financieros_con_diagnostico(
        str(cik), años=años, usar_cache=False,
    )
    if status is not None:
        return None, None, None

    return tuple(_filtrar_columnas_por_filing_date(df, as_of_date) for df in (df_is, df_bs, df_cf))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 2. Puntos de congelación por empresa
# ---------------------------------------------------------------------------


def generar_puntos_de_congelacion_fmp(ticker: str, *, limite_anios: int = 5) -> list[dict[str, Any]]:
    """Un punto de congelación por cada año fiscal con fecha de filing
    conocida, situado el día siguiente al filing real -- nunca en la fecha
    de cierre del periodo (que es anterior a que el dato existiera
    públicamente)."""
    df_is, df_bs, df_cf = extraer_datos_as_reported_fmp(ticker, limite_anios)
    filing_dates: dict[str, str] = {}
    for df in (df_is, df_bs, df_cf):
        if df is not None:
            filing_dates.update(df.attrs.get("filing_dates", {}))

    puntos = []
    for year in sorted(filing_dates):
        filing_date = filing_dates[year]
        as_of = (pd.Timestamp(filing_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        puntos.append({"ticker": ticker, "fuente": "fmp", "fiscal_year": year, "filing_date": filing_date, "as_of_date": as_of})
    return puntos


def generar_puntos_de_congelacion_sec(cik: int | str, *, años: int = 5) -> list[dict[str, Any]]:
    import downloader

    df_is, df_bs, df_cf, status = downloader.obtener_estados_financieros_con_diagnostico(
        str(cik), años=años, usar_cache=False,
    )
    if status is not None:
        return []

    filing_dates: dict[str, str] = {}
    for df in (df_is, df_bs, df_cf):
        if df is not None:
            filing_dates.update(df.attrs.get("filing_dates", {}))

    puntos = []
    for year in sorted(filing_dates):
        filing_date = filing_dates[year]
        as_of = (pd.Timestamp(filing_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        puntos.append({"ticker": str(cik), "fuente": "sec", "fiscal_year": year, "filing_date": filing_date, "as_of_date": as_of})
    return puntos


# ---------------------------------------------------------------------------
# 3. Precio y snapshot de mercado histórico (ver docstring del módulo)
# ---------------------------------------------------------------------------


def _historical_price(ticker: str, as_of_date: str) -> float | None:
    """Último cierre disponible en/antes de as_of_date. None si Yahoo no
    da datos -- nunca 0.0 fabricado aquí (el 0.0 lo decide el llamador, ver
    _inyectar_datos_historicos, para igualar el contrato ya existente de
    obtener_cotizacion_fmp)."""
    as_of_ts = pd.Timestamp(as_of_date)
    start = (as_of_ts - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    end = (as_of_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    hist, _status = safe_yfinance_fetch(
        lambda: yf.Ticker(ticker).history(start=start, end=end, interval="1d", auto_adjust=True),
        empty_value=pd.DataFrame(),
        context=f"point_in_time:price:{ticker}",
    )
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    close = hist["Close"].dropna()
    return float(close.iloc[-1]) if not close.empty else None


def _historical_market_snapshot(ticker: str, as_of_date: str) -> dict[str, Any]:
    """Ver docstring del módulo: reconstruye lo reconstruible (derivado de
    precio) y deja explícitamente en None lo que no lo es (beta, market
    cap, insiders, institucional, short ratio)."""
    output: dict[str, Any] = {
        "beta": None, "market_cap": None, "sector": None, "rsi": None,
        "ret_6m": None, "ret_1y": None, "vol_1y": None, "max_drawdown_1y": None,
        "sma50_above_sma200": None, "price_above_sma200": None, "sector_rel_3m": None,
        "insider_pct": None, "inst_pct": None, "short_ratio": None,
    }

    try:
        info = safe_yfinance_info(yf, ticker, context=f"point_in_time:info:{ticker}")
        output["sector"] = info.get("sector") if info else None
    except Exception:
        pass

    as_of_ts = pd.Timestamp(as_of_date)
    start = (as_of_ts - pd.Timedelta(days=550)).strftime("%Y-%m-%d")
    end = (as_of_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    hist, _status = safe_yfinance_fetch(
        lambda: yf.Ticker(ticker).history(start=start, end=end, interval="1d", auto_adjust=True),
        empty_value=pd.DataFrame(),
        context=f"point_in_time:history:{ticker}",
    )
    if hist is None or hist.empty or "Close" not in hist.columns:
        return output

    close = hist["Close"].dropna()
    if len(close) < 220:
        return output

    returns = close.pct_change().dropna()
    output["ret_6m"] = float(close.iloc[-1] / close.iloc[-126] - 1) if len(close) > 126 else None
    output["ret_1y"] = float(close.iloc[-1] / close.iloc[-252] - 1) if len(close) > 252 else None
    output["vol_1y"] = float(returns.tail(252).std() * math.sqrt(252)) if not returns.empty else None
    running_max = close.tail(252).cummax()
    drawdown = (close.tail(252) / running_max) - 1
    output["max_drawdown_1y"] = float(drawdown.min())

    sma50 = close.rolling(50).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1]
    output["sma50_above_sma200"] = bool(sma50 > sma200) if pd.notna(sma50) and pd.notna(sma200) else None
    output["price_above_sma200"] = bool(close.iloc[-1] > sma200) if pd.notna(sma200) else None

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    output["rsi"] = float(rsi.dropna().iloc[-1]) if not rsi.dropna().empty else None

    sector_etf = _SECTOR_TO_ETF.get(str(output.get("sector") or ""))
    if sector_etf:
        sector_hist, _ = safe_yfinance_fetch(
            lambda: yf.Ticker(sector_etf).history(start=start, end=end, interval="1d", auto_adjust=True),
            empty_value=pd.DataFrame(), context=f"point_in_time:sector_etf:{sector_etf}",
        )
        spy_hist, _ = safe_yfinance_fetch(
            lambda: yf.Ticker("SPY").history(start=start, end=end, interval="1d", auto_adjust=True),
            empty_value=pd.DataFrame(), context="point_in_time:sector_etf:SPY",
        )
        sector_close = sector_hist["Close"].dropna() if not sector_hist.empty else sector_hist
        spy_close = spy_hist["Close"].dropna() if not spy_hist.empty else spy_hist
        if len(sector_close) > 63 and len(spy_close) > 63:
            sector_return = float(sector_close.iloc[-1] / sector_close.iloc[-63] - 1)
            spy_return = float(spy_close.iloc[-1] / spy_close.iloc[-63] - 1)
            output["sector_rel_3m"] = sector_return - spy_return

    return output


@contextmanager
def _inyectar_datos_historicos(ticker: str, as_of_date: str):
    """Sustituye temporalmente valuator.obtener_cotizacion_fmp y
    scoring_engine._market_data_snapshot por versiones ancladas a
    as_of_date -- ver docstring del módulo para el porqué (ninguna de las
    dos funciones acepta una fecha, y no se van a modificar). Restaura
    ambas al salir, incluso si el bloque lanza."""
    precio_historico = _historical_price(ticker, as_of_date)
    snapshot_historico = _historical_market_snapshot(ticker, as_of_date)

    precio_original = valuator.obtener_cotizacion_fmp
    snapshot_original = scoring_engine._market_data_snapshot

    # Mismo contrato que obtener_cotizacion_fmp real: 0.0 si no hay precio,
    # nunca None ni una excepción (así lo esperan sus llamadores actuales).
    valuator.obtener_cotizacion_fmp = lambda _t: precio_historico if precio_historico is not None else 0.0
    scoring_engine._market_data_snapshot = lambda _t: snapshot_historico
    try:
        yield precio_historico
    finally:
        valuator.obtener_cotizacion_fmp = precio_original
        scoring_engine._market_data_snapshot = snapshot_original


# ---------------------------------------------------------------------------
# 4. Ejecutar el score actual sobre un punto de congelación
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FrozenScore:
    """Un ValueQuantScore (código actual, sin modificar) calculado sobre
    fundamentales point-in-time de una fecha pasada."""

    identificador: str
    fuente: str  # "fmp" o "sec"
    as_of_date: str
    fiscal_year_mas_reciente_incluido: str | None
    final_score: float | None
    confidence: float | None
    verdict: str | None
    data_coverage: float | None
    componentes: list[dict[str, Any]]
    precio_historico: float | None
    red_flags: list[str]
    generado_en: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _empaquetar_componentes(valuequant_score: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": componente.name,
            "score": round(float(componente.score), 2),
            "weight": componente.weight,
            "confidence": round(float(componente.confidence), 3),
        }
        for componente in valuequant_score.components
    ]


def _año_mas_reciente(df: pd.DataFrame | None) -> str | None:
    if df is None:
        return None
    años = sorted(c for c in df.columns if str(c).isdigit())
    return años[-1] if años else None


def _congelar_score_desde_fundamentales(
    identificador: str,
    fuente: str,
    as_of_date: str,
    is_df: pd.DataFrame | None,
    bs_df: pd.DataFrame | None,
    cf_df: pd.DataFrame | None,
    ticker_precio: str,
) -> FrozenScore | None:
    if is_df is None or bs_df is None or cf_df is None:
        return None

    res_is = analizar_cuenta_resultados(is_df, cf_df)
    res_bs = analizar_balance(bs_df, is_df)
    res_cf = analizar_flujo_efectivo(cf_df, is_df)
    if res_is is None or res_bs is None or res_cf is None:
        return None

    with _inyectar_datos_historicos(ticker_precio, as_of_date) as precio_historico:
        res_val = valorar_empresa(is_df, bs_df, cf_df, None, ticker_precio)
        valuequant_score = calcular_valuequant_score(
            ticker=ticker_precio, is_df=is_df, bs_df=bs_df, cf_df=cf_df,
            res_is=res_is, res_bs=res_bs, res_cf=res_cf, res_val=res_val,
        )

    return FrozenScore(
        identificador=identificador,
        fuente=fuente,
        as_of_date=as_of_date,
        fiscal_year_mas_reciente_incluido=_año_mas_reciente(is_df),
        final_score=float(valuequant_score.final_score),
        confidence=float(valuequant_score.confidence),
        verdict=valuequant_score.verdict,
        data_coverage=float(valuequant_score.data_coverage),
        componentes=_empaquetar_componentes(valuequant_score),
        precio_historico=precio_historico,
        red_flags=list(valuequant_score.red_flags),
    )


def congelar_score_fmp(ticker: str, as_of_date: str, *, limite_anios: int = 5) -> FrozenScore | None:
    """Punto de entrada principal para los ~78 tickers FMP accesibles."""
    is_df, bs_df, cf_df = construir_fundamentales_point_in_time_fmp(ticker, as_of_date, limite_anios=limite_anios)
    return _congelar_score_desde_fundamentales(ticker, "fmp", as_of_date, is_df, bs_df, cf_df, ticker)


def congelar_score_sec(cik: int | str, as_of_date: str, ticker_historico: str, *, años: int = 5) -> FrozenScore | None:
    """Punto de entrada para los 3 casos de supervivencia (Sub-fase 2). El
    precio histórico se busca por ticker_historico (yfinance no indexa por
    CIK) -- ver el diagnóstico de la Sub-fase 3 sobre disponibilidad real
    de ese precio para empresas ya deslistadas."""
    is_df, bs_df, cf_df = construir_fundamentales_point_in_time_sec(cik, as_of_date, años=años)
    return _congelar_score_desde_fundamentales(str(cik), "sec", as_of_date, is_df, bs_df, cf_df, ticker_historico)


# ---------------------------------------------------------------------------
# 5. Persistencia (dominio propio -- no se mezcla con analysis_store.py,
# que es para snapshots manuales del usuario desde Research Core)
# ---------------------------------------------------------------------------


def _ensure_data_folder() -> None:
    DATA_FOLDER.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    _ensure_data_folder()
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    _ensure_data_folder()
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def guardar_score_congelado(score: FrozenScore, *, path: Path = FROZEN_SCORES_FILE) -> None:
    """Añade un FrozenScore al histórico persistido (append, nunca sobrescribe
    los ya guardados) -- la Sub-fase 4 necesita todos los puntos, no solo el último."""
    datos = _read_json(path, [])
    if not isinstance(datos, list):
        datos = []
    datos.append(asdict(score))
    _write_json(path, datos)


def cargar_scores_congelados(*, path: Path = FROZEN_SCORES_FILE) -> list[dict[str, Any]]:
    datos = _read_json(path, [])
    return datos if isinstance(datos, list) else []
