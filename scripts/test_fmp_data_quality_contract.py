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


def run_contract_checks() -> list[str]:
    import modulos.fmp_api as fmp

    checks: list[str] = []
    original_descargar_json = fmp._descargar_json

    try:
        def fake_success(url, params):
            return [
                {"date": "2023-12-31", "revenue": "100", "symbol": "AAA"},
                {"date": "2024-12-31", "revenue": "125", "symbol": "AAA"},
            ]

        fmp._descargar_json = fake_success
        df = fmp._endpoint_a_dataframe([("primary", None)])
        assert_true(isinstance(df, pd.DataFrame), "Payload válido debe devolver DataFrame")
        assert_true(not df.empty, "Payload válido no debe devolver DataFrame vacío")
        assert_true(str(df.index.name) == "date", "El índice debe ser date")
        assert_true(pd.api.types.is_numeric_dtype(df["revenue"]), "Columnas numéricas deben convertirse")
        assert_true(df["revenue"].iloc[-1] == 125, "Debe preservar y ordenar los datos")
        checks.append("valid fmp payload")

        def fake_missing_date(url, params):
            return [{"revenue": "100", "symbol": "AAA"}]

        fmp._descargar_json = fake_missing_date
        missing_date_df = fmp._endpoint_a_dataframe([("missing-date", None)])
        assert_true(missing_date_df is None, "Payload sin date debe bloquearse")
        checks.append("missing date blocked")

        calls: list[str] = []

        def fake_fallback(url, params):
            calls.append(str(url))
            if len(calls) == 1:
                return None
            return [{"date": "2024-12-31", "revenue": "200", "symbol": "AAA"}]

        fmp._descargar_json = fake_fallback
        fallback_df = fmp._endpoint_a_dataframe([("primary", None), ("fallback", None)])
        assert_true(fallback_df is not None and not fallback_df.empty, "Debe probar endpoints fallback")
        assert_true(calls == ["primary", "fallback"], "Debe intentar endpoints en orden")
        checks.append("endpoint fallback")

        def fake_bad_dates(url, params):
            return [{"date": "not-a-date", "revenue": "100", "symbol": "AAA"}]

        fmp._descargar_json = fake_bad_dates
        bad_dates_df = fmp._endpoint_a_dataframe([("bad-dates", None)])
        assert_true(bad_dates_df is None, "Payload con fechas inválidas debe terminar como None")
        checks.append("bad dates blocked")

    finally:
        fmp._descargar_json = original_descargar_json

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== FMP Data Quality Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== FMP Data Quality Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
