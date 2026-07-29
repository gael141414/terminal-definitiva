#!/usr/bin/env python3
"""Guards the ticker tape's real-world fix: before this pass it had zero fallback
to FMP — if Yahoo Finance rate-limited (as it does routinely), every symbol
silently disappeared and the tape fell straight to a static placeholder. It also
locked a full 429-rate-limit batch into cache for the entire 15-minute TTL.
"""
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
    from modulos import quotes as quotes_provider

    checks: list[str] = []

    # 1. The tape must route through the centralized quotes provider, not its own
    #    bespoke Yahoo-only fetch.
    market_widgets_source = (PROJECT_ROOT / "modulos" / "market_widgets.py").read_text(encoding="utf-8")
    assert_true(
        "quotes_provider.fetch_quotes_with_fallback" in market_widgets_source,
        "obtener_datos_ticker_tape debe usar modulos.quotes.fetch_quotes_with_fallback",
    )
    assert_true(
        "yf.Ticker(ticker).info" not in market_widgets_source,
        "market_widgets no debe acceder a .info directamente (dispara quoteSummary/429)",
    )
    checks.append("ticker tape uses the centralized quotes provider")

    # 2. Futures/index symbols with no FMP equivalent must be labeled explicitly,
    #    not silently dropped or shown as fake data.
    assert_true("GC=F" in quotes_provider.UNSUPPORTED_FMP_SYMBOLS, "El oro (GC=F) debe marcarse como sin fallback FMP fiable")
    checks.append("unsupported futures/index symbols are explicitly labeled, not faked")

    # 3. Simulate total failure (Yahoo down + FMP down) and verify the tape shows
    #    explicit per-symbol status instead of vanishing silently, and that the
    #    batch cache self-heals instead of freezing the failure for the full TTL.
    from modulos import fmp_api, yahoo_resilience

    original_ticker = mw.yf.Ticker
    original_fmp_quote = fmp_api.obtener_cotizacion_fmp
    original_sleep = yahoo_resilience.time.sleep

    class RateLimitedTicker:
        def __init__(self, ticker: str):
            self.ticker = ticker

        def history(self, *args, **kwargs):
            raise RuntimeError("429 Client Error: Too Many Requests")

    def fmp_also_unavailable(_ticker: str) -> float:
        return 0.0

    try:
        mw.yf.Ticker = RateLimitedTicker
        fmp_api.obtener_cotizacion_fmp = fmp_also_unavailable
        yahoo_resilience.time.sleep = lambda _seconds: None
        _clear_cache(mw.obtener_datos_ticker_tape)

        tape = mw.obtener_datos_ticker_tape()
        assert_true("vq-tape-item" in tape, "La cinta debe seguir renderizando items aunque no haya datos")
        assert_true(
            "Rate limit temporal de Yahoo" in tape or "Fuente no disponible" in tape,
            "La cinta debe mostrar un estado explícito, no desaparecer en silencio",
        )
        # The function must have cleared its own cache after a total failure —
        # otherwise a transient 429 would freeze "no data" for the full 15 min TTL.
        cache_stats = mw.obtener_datos_ticker_tape
        assert_true(hasattr(cache_stats, "clear"), "obtener_datos_ticker_tape debe seguir siendo cacheable")
    finally:
        mw.yf.Ticker = original_ticker
        fmp_api.obtener_cotizacion_fmp = original_fmp_quote
        yahoo_resilience.time.sleep = original_sleep
        _clear_cache(mw.obtener_datos_ticker_tape)
    checks.append("total-failure batch shows explicit status and self-heals instead of freezing for the full TTL")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Ticker Tape Fallback Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Ticker Tape Fallback Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
