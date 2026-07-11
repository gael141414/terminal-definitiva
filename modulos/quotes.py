from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import pandas as pd
import yfinance as yf

from modulos import fmp_api
from modulos.yahoo_resilience import safe_yfinance_fetch

# Futuros/índices sin equivalente fiable en el endpoint quote-short de FMP: si Yahoo
# falla para estos símbolos no existe un fallback real, así que se etiquetan como
# "unsupported_symbol" en vez de intentar (y fingir) un fallback inexistente.
UNSUPPORTED_FMP_SYMBOLS = {"GC=F", "CL=F", "^VIX", "^TNX", "^GSPC", "^DJI", "^IXIC"}

STATUS_OK = "ok"
STATUS_OK_FALLBACK_FMP = "ok_fallback_fmp"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_NO_DATA = "no_data"
STATUS_ERROR = "error"
STATUS_UNSUPPORTED_SYMBOL = "unsupported_symbol"

STATUS_LABELS = {
    STATUS_OK: "Yahoo Finance",
    STATUS_OK_FALLBACK_FMP: "FMP (respaldo)",
    STATUS_RATE_LIMITED: "Rate limit temporal de Yahoo",
    STATUS_NO_DATA: "Sin datos disponibles",
    STATUS_ERROR: "Error de proveedor",
    STATUS_UNSUPPORTED_SYMBOL: "Fuente no disponible para este instrumento",
}


@dataclass
class QuoteResult:
    symbol: str
    price: Optional[float] = None
    previous_close: Optional[float] = None
    change_pct: Optional[float] = None
    source: str = "none"
    status: str = STATUS_NO_DATA

    @property
    def ok(self) -> bool:
        return self.price is not None

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)


def _quote_from_history(hist: pd.DataFrame) -> Optional[tuple[float, float]]:
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    closes = hist["Close"].dropna()
    if len(closes) < 2:
        return None
    price = float(closes.iloc[-1])
    previous = float(closes.iloc[-2])
    if previous == 0:
        return None
    return price, previous


def fetch_quotes_with_fallback(symbols: Iterable[str], *, period: str = "5d") -> dict[str, QuoteResult]:
    """Obtiene cotizaciones para una lista de símbolos con fallback FMP y estados
    explícitos, en vez de omitir en silencio los símbolos que fallan.

    Orden de intento por símbolo:
    1. Yahoo Finance (`yf.Ticker(...).history`, vía `yahoo_resilience.safe_yfinance_fetch`,
       con un reintento corto si el primer intento fue rate limit).
    2. Si Yahoo falla y el símbolo es un instrumento normal (no futuro/índice),
       fallback a FMP (`obtener_cotizacion_fmp`) — solo da el precio actual, no el
       cierre previo, así que el cambio % queda sin dato pero el precio sí se muestra.
    3. Si el símbolo es un futuro/índice sin soporte FMP fiable (`GC=F`, `CL=F`,
       `^VIX`, `^TNX`, ...), se marca `unsupported_symbol` en vez de fingir un
       fallback inexistente.
    """

    symbols = list(dict.fromkeys(symbols))  # dedupe preservando orden
    results: dict[str, QuoteResult] = {}

    for symbol in symbols:
        hist, status = safe_yfinance_fetch(
            lambda s=symbol: yf.Ticker(s).history(period=period, interval="1d", auto_adjust=False),
            empty_value=pd.DataFrame(),
            context=f"quotes:{symbol}",
        )
        quote = _quote_from_history(hist) if status == "ok" else None

        if quote is not None:
            price, previous = quote
            results[symbol] = QuoteResult(
                symbol=symbol,
                price=price,
                previous_close=previous,
                change_pct=((price - previous) / previous) * 100,
                source="yfinance",
                status=STATUS_OK,
            )
            continue

        if symbol in UNSUPPORTED_FMP_SYMBOLS:
            results[symbol] = QuoteResult(symbol=symbol, source="none", status=STATUS_UNSUPPORTED_SYMBOL)
            continue

        fmp_price = fmp_api.obtener_cotizacion_fmp(symbol)
        if fmp_price:
            results[symbol] = QuoteResult(
                symbol=symbol,
                price=float(fmp_price),
                previous_close=None,
                change_pct=None,
                source="fmp",
                status=STATUS_OK_FALLBACK_FMP,
            )
            continue

        fallback_status = status if status != STATUS_OK else STATUS_NO_DATA
        results[symbol] = QuoteResult(symbol=symbol, source="none", status=fallback_status)

    return results


def any_quote_succeeded(results: dict[str, QuoteResult]) -> bool:
    return any(result.ok for result in results.values())
