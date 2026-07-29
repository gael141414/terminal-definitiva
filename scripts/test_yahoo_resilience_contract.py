#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _clear_cache(fn) -> None:
    clear = getattr(fn, "clear", None)
    if callable(clear):
        clear()


def run_contract_checks() -> list[str]:
    from modulos import market_widgets as mw

    checks: list[str] = []

    assert_true(mw._is_yahoo_rate_limit_error(RuntimeError("429 Client Error: Too Many Requests")), "Debe detectar 429")
    assert_true(mw._is_yahoo_rate_limit_error(RuntimeError("rate limit exceeded")), "Debe detectar rate limit")
    assert_true(not mw._is_yahoo_rate_limit_error(RuntimeError("schema error")), "No debe marcar cualquier error como rate limit")
    checks.append("rate limit classifier")

    original_ticker = mw.yf.Ticker

    class RateLimitedTicker:
        def __init__(self, ticker: str):
            self.ticker = ticker

        def history(self, *args, **kwargs):
            raise RuntimeError("429 Client Error: Too Many Requests")

    try:
        mw.yf.Ticker = RateLimitedTicker
        hist = mw._safe_yahoo_history("AAPL", period="5d")
        assert_true(isinstance(hist, pd.DataFrame), "El helper debe devolver DataFrame")
        assert_true(hist.empty, "Ante rate limit debe devolver DataFrame vacío")
    finally:
        mw.yf.Ticker = original_ticker
    checks.append("safe history handles rate limits")

    class FastInfoOnlyTicker:
        def __init__(self, ticker: str):
            self.ticker = ticker
            self.fast_info = {"market_cap": 123_000_000_000}

        @property
        def info(self):
            raise AssertionError("No debe usar .info porque dispara quoteSummary")

        def history(self, *args, **kwargs):
            return pd.DataFrame({"Close": [100.0, 102.0, 104.0]})

    try:
        mw.yf.Ticker = FastInfoOnlyTicker
        _clear_cache(mw.obtener_market_treemap_data)
        treemap = mw.obtener_market_treemap_data()
        assert_true(isinstance(treemap, pd.DataFrame), "Treemap debe devolver DataFrame")
        assert_true(not treemap.empty, "Treemap debe construir datos con fast_info")
        assert_true("MarketCap" in treemap.columns, "Treemap debe incluir MarketCap")
    finally:
        mw.yf.Ticker = original_ticker
        _clear_cache(mw.obtener_market_treemap_data)
    checks.append("treemap avoids quoteSummary info fallback")

    from modulos import fmp_api, yahoo_resilience

    original_fmp_quote = fmp_api.obtener_cotizacion_fmp
    original_sleep = yahoo_resilience.time.sleep

    def fmp_also_unavailable(_ticker: str) -> float:
        return 0.0

    try:
        mw.yf.Ticker = RateLimitedTicker
        fmp_api.obtener_cotizacion_fmp = fmp_also_unavailable
        yahoo_resilience.time.sleep = lambda _seconds: None  # no esperar el backoff real en el test
        _clear_cache(mw.obtener_datos_ticker_tape)
        tape = mw.obtener_datos_ticker_tape()
        assert_true(
            "Rate limit temporal de Yahoo" in tape or "Fuente no disponible" in tape,
            "Ticker tape debe mostrar un estado explícito por símbolo cuando Yahoo y FMP fallan, no desaparecer en silencio",
        )
        assert_true("vq-tape-item" in tape, "Ticker tape debe seguir renderizando items aunque falten datos")
    finally:
        mw.yf.Ticker = original_ticker
        fmp_api.obtener_cotizacion_fmp = original_fmp_quote
        yahoo_resilience.time.sleep = original_sleep
        _clear_cache(mw.obtener_datos_ticker_tape)
    checks.append("ticker tape shows explicit per-symbol status when Yahoo and FMP both fail")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Yahoo Resilience Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Yahoo Resilience Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
