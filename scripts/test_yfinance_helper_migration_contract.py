#!/usr/bin/env python3
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

    data_provider = _read("data_provider.py")
    assert_true("safe_yfinance_download" in data_provider, "data_provider debe usar safe_yfinance_download")
    assert_true("yf.download(" not in data_provider, "data_provider no debe llamar directamente a yf.download")
    checks.append("data_provider uses resilient download helper")

    backtester = _read("backtester.py")
    assert_true("safe_yfinance_download" in backtester, "backtester debe usar safe_yfinance_download")
    assert_true("yf.download(" not in backtester, "backtester no debe llamar directamente a yf.download")
    assert_true("Backtest cancelado sin romper ejecución" in backtester, "backtester debe degradar sin romper si no hay precios")
    checks.append("backtester uses resilient download helper")

    screener = _read("screener.py")
    assert_true("safe_yfinance_info" in screener, "screener debe usar safe_yfinance_info")
    assert_true("yf.Ticker(" not in screener, "screener no debe llamar directamente a yf.Ticker")
    assert_true(".info" not in screener, "screener no debe acceder directamente a .info")
    checks.append("screener uses resilient info helper")

    yahoo_resilience = _read("modulos/yahoo_resilience.py")
    assert_true("contextlib.redirect_stdout" in yahoo_resilience, "el helper debe capturar stdout")
    assert_true("contextlib.redirect_stderr" in yahoo_resilience, "el helper debe capturar stderr")
    checks.append("Yahoo helper captures noisy provider output")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== YFinance Helper Migration Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== YFinance Helper Migration Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
