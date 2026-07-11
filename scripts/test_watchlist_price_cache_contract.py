#!/usr/bin/env python3
"""Guards the watchlist perf fix: before this pass, opening/rerunning the
Watchlist tab looped over every ticker calling ``yf.Ticker(...).history()``
one-by-one with no cache — N uncached Yahoo requests just from redrawing the
tab. It must now batch through the centralized quotes provider and cache the
result for a short TTL.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_contract_checks() -> list[str]:
    checks: list[str] = []

    from modulos import watchlist

    assert_true(
        hasattr(watchlist._obtener_precios_watchlist, "clear"),
        "_obtener_precios_watchlist debe estar decorada con st.cache_data",
    )
    checks.append("watchlist price refresh is cached")

    watchlist_source = (PROJECT_ROOT / "modulos" / "watchlist.py").read_text(encoding="utf-8")
    assert_true(
        "fetch_quotes_with_fallback" in watchlist_source,
        "watchlist debe usar modulos.quotes.fetch_quotes_with_fallback en lugar de un bucle serie sin caché",
    )
    assert_true(
        "yf.Ticker(" not in watchlist_source,
        "watchlist no debe volver a llamar directamente a yf.Ticker por ticker",
    )
    checks.append("watchlist batches quotes through the centralized provider, no per-ticker raw calls")

    import inspect

    signature = inspect.signature(watchlist._obtener_precios_watchlist)
    assert_true(
        "tickers" in signature.parameters,
        "_obtener_precios_watchlist debe aceptar la lista completa de tickers para pedirlos en lote",
    )
    checks.append("watchlist prices are fetched in a single batched call")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Watchlist Price Cache Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Watchlist Price Cache Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
