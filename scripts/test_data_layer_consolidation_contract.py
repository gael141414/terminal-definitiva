#!/usr/bin/env python3
"""Guards against the core regression found in this stabilization pass: the
Yahoo/yfinance resilience layer (``modulos/yahoo_resilience.py``) existed but was
only wired into orphaned root-level files (``screener.py``, ``backtester.py``,
``data_provider.py``) that the Streamlit app never imports. The modules the
router actually calls (``modulos/screener.py``, ``modulos/backtester.py``,
``modulos/watchlist.py``, ``charts.py``, ``modulos/market_widgets.py``) kept
making raw, unprotected ``yf.Ticker(...).info``/``.history`` calls.
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


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def run_contract_checks() -> list[str]:
    checks: list[str] = []

    # These modules are fully migrated: they must not call yf.Ticker directly at all.
    fully_migrated = ["modulos/screener.py", "modulos/watchlist.py", "modulos/backtester.py"]
    for relative_path in fully_migrated:
        source = _read(relative_path)
        assert_true(
            "yf.Ticker(" not in source,
            f"{relative_path} no debe llamar directamente a yf.Ticker — debe pasar por modulos.yahoo_resilience o modulos.quotes",
        )
    checks.append("screener/watchlist/backtester (modulos/) have zero raw yf.Ticker calls")

    # These modules legitimately keep yf.Ticker(...) inside dedicated cached/safe
    # wrapper functions, so we assert the resilience helper is actually imported
    # and used, rather than banning yf.Ticker(" outright.
    must_import_resilience = {
        "charts.py": ("modulos.yahoo_resilience", "safe_yfinance_fetch"),
        "modulos/market_widgets.py": ("modulos.yahoo_resilience", "is_yahoo_rate_limit_error"),
        "modulos/company_data_helpers.py": ("modulos.yahoo_resilience", "safe_yfinance_info"),
        "modulos/scoring_engine.py": ("modulos.yahoo_resilience", "safe_yfinance_info"),
        "modulos/proyeccion.py": ("modulos.yahoo_resilience", "safe_yfinance_info"),
        "modulos/utils.py": ("modulos.yahoo_resilience", "safe_yfinance_info"),
    }
    for relative_path, (module_name, symbol) in must_import_resilience.items():
        source = _read(relative_path)
        assert_true(module_name in source, f"{relative_path} debe importar {module_name}")
        assert_true(symbol in source, f"{relative_path} debe usar {symbol}")
    checks.append("charts/market_widgets/company_data helpers import the resilience layer")

    # modulos/quotes.py is the centralized batch-quote provider (ticker tape,
    # watchlist, market snapshot/treemap, opportunity briefing all depend on it).
    quotes_source = _read("modulos/quotes.py")
    assert_true("def fetch_quotes_with_fallback" in quotes_source, "modulos/quotes.py debe exponer fetch_quotes_with_fallback")
    assert_true("obtener_cotizacion_fmp" in quotes_source, "modulos/quotes.py debe hacer fallback a FMP")
    checks.append("modulos/quotes.py centralizes batch quotes with FMP fallback")

    for consumer in ["modulos/market_widgets.py", "modulos/watchlist.py", "modulos/opportunity_briefing.py"]:
        source = _read(consumer)
        assert_true(
            "fetch_quotes_with_fallback" in source or "quotes_provider" in source,
            f"{consumer} debe usar el proveedor centralizado de cotizaciones (modulos.quotes)",
        )
    checks.append("ticker tape, watchlist and opportunity briefing consume the centralized quotes provider")

    yahoo_resilience_source = _read("modulos/yahoo_resilience.py")
    assert_true("def safe_yfinance_fetch" in yahoo_resilience_source, "yahoo_resilience debe exponer safe_yfinance_fetch genérico")
    assert_true("time.sleep" in yahoo_resilience_source, "safe_yfinance_fetch debe reintentar con backoff ante rate limit")
    checks.append("yahoo_resilience exposes a generic retrying fetch helper")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Data Layer Consolidation Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Data Layer Consolidation Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
