#!/usr/bin/env python3
from __future__ import annotations

import re
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

    screener = _read("screener.py")
    assert_true(screener.count('if __name__ == "__main__":') == 1, "screener.py debe tener un único bloque main")
    assert_true("import os" not in screener, "screener.py no debe conservar import os no usado")
    assert_true("from valuator import valorar_empresa" not in screener, "screener.py no debe conservar valorar_empresa no usado")
    checks.append("screener cleanup")

    for required in [
        "modulos/yahoo_resilience.py",
        "modulos/yfinance_global_guard.py",
        "sitecustomize.py",
        "scripts/test_yahoo_resilience_contract.py",
        "scripts/test_yfinance_helper_migration_contract.py",
        "scripts/test_charts_yfinance_resilience_contract.py",
    ]:
        assert_true((PROJECT_ROOT / required).exists(), f"Falta {required}")
    checks.append("yfinance resilience files exist")

    assert_true("safe_yfinance_info" in screener, "screener debe usar safe_yfinance_info")
    checks.append("core yfinance calls use helpers")

    charts = _read("charts.py")
    sitecustomize = _read("sitecustomize.py")
    assert_true("yf.download" in charts, "charts.py conserva llamadas legacy documentadas")
    assert_true("install_yfinance_guard" in sitecustomize, "sitecustomize debe instalar el guard de yfinance")
    checks.append("legacy chart downloads are guard-covered")

    direct_info_pattern = re.compile(r"yf\.Ticker\([^\n]+\)\.info|\.info\s*$")
    assert_true("yf.Ticker(" not in screener, "screener no debe llamar directamente a yf.Ticker")
    assert_true(not direct_info_pattern.search(screener), "screener no debe acceder directamente a .info")
    checks.append("screener avoids direct quoteSummary")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Final Cleanup Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Final Cleanup Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
