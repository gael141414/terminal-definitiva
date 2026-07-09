#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_contract_checks() -> list[str]:
    from modulos.yfinance_global_guard import install_yfinance_guard

    checks: list[str] = []

    original_download = yf.download

    def noisy_rate_limited_download(*args, **kwargs):
        print("429 Client Error: Too Many Requests for url: https://query2.finance.yahoo.com/v8/finance/chart/AAPL")
        raise RuntimeError("429 Client Error: Too Many Requests")

    try:
        yf.download = noisy_rate_limited_download
        installed = install_yfinance_guard(yf)
        assert_true(installed, "Debe instalar el guard sobre yf.download")
        assert_true(getattr(yf.download, "_valuequant_guarded", False), "yf.download debe quedar marcado como guarded")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = yf.download("AAPL", period="1y", progress=False)

        assert_true(isinstance(result, pd.DataFrame), "El fallback debe devolver DataFrame")
        assert_true(result.empty, "Ante 429 el resultado debe ser DataFrame vacío")
        assert_true("Too Many Requests" not in stdout.getvalue(), "El guard debe capturar stdout ruidoso")
        assert_true("Too Many Requests" not in stderr.getvalue(), "El guard debe capturar stderr ruidoso")
    finally:
        yf.download = original_download
    checks.append("global yfinance guard handles noisy 429")

    installed_again = install_yfinance_guard(yf)
    assert_true(installed_again or getattr(yf.download, "_valuequant_guarded", False), "El guard debe ser instalable o estar ya instalado")
    assert_true(getattr(yf.download, "_valuequant_guarded", False), "yf.download debe quedar protegido para charts.py")
    checks.append("global yfinance guard is active")

    charts_source = (PROJECT_ROOT / "charts.py").read_text(encoding="utf-8")
    assert_true("yf.download" in charts_source, "charts.py conserva llamadas legacy que deben estar protegidas por el guard")
    assert_true((PROJECT_ROOT / "sitecustomize.py").exists(), "sitecustomize.py debe instalar el guard al arrancar")
    checks.append("charts legacy calls are covered by startup guard")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Charts YFinance Resilience Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Charts YFinance Resilience Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
