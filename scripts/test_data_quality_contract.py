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
    from modulos import data_quality as dq

    checks: list[str] = []

    df = pd.DataFrame({"revenue": [100, 110, 120], "netIncome": [10, 12, 13]})
    result = dq.validate_dataframe(df, ["revenue", "netIncome"], source="income", min_rows=3)
    assert_true(result.ok, "Un DataFrame completo debe ser OK")
    assert_true(result.usable and not result.blocking, "Un resultado OK debe ser usable")
    assert_true(result.coverage == 1.0, "La cobertura completa debe ser 1.0")
    checks.append("valid dataframe")

    missing = dq.validate_dataframe(df, ["revenue", "freeCashFlow"], source="cashflow")
    assert_true(missing.status == dq.MISSING_COLUMNS, "Debe detectar columnas ausentes")
    assert_true(missing.blocking, "Columnas ausentes debe ser bloqueante")
    assert_true(missing.missing_columns == ["freeCashFlow"], "Debe informar columnas ausentes")
    checks.append("missing columns")

    empty = dq.validate_dataframe(pd.DataFrame(columns=["revenue"]), ["revenue"], source="empty")
    assert_true(empty.status == dq.EMPTY, "Debe detectar DataFrame vacío")
    checks.append("empty dataframe")

    invalid = dq.validate_dataframe(None, ["revenue"], source="none")
    assert_true(invalid.status == dq.INVALID_TYPE, "Debe detectar tipo inválido")
    checks.append("invalid dataframe type")

    partial_df = pd.DataFrame({"a": [1, None, None], "b": [2, None, None]})
    partial = dq.validate_dataframe(partial_df, ["a", "b"], source="partial", min_coverage=0.90)
    assert_true(partial.status == dq.PARTIAL, "Debe marcar cobertura parcial")
    assert_true(partial.usable and not partial.blocking, "Parcial debe ser usable pero no bloqueante")
    checks.append("partial dataframe coverage")

    series = dq.safe_numeric_series(pd.DataFrame({"x": ["1", "bad", 3, None]}), "x")
    assert_true(series.tolist() == [1, 3], "safe_numeric_series debe limpiar valores no numéricos")
    checks.append("safe numeric series")

    mapping = dq.validate_mapping({"price": 100, "beta": 1.2}, ["price", "beta"], source="market")
    assert_true(mapping.ok and mapping.coverage == 1.0, "Mapping completo debe ser OK")
    checks.append("valid mapping")

    missing_mapping = dq.validate_mapping({"price": 100}, ["price", "beta"], source="market")
    assert_true(missing_mapping.status == dq.MISSING_KEYS, "Debe detectar claves ausentes")
    checks.append("missing mapping keys")

    aggregate = dq.merge_quality_results([result, partial], source="aggregate")
    assert_true(aggregate.status == dq.PARTIAL, "OK + parcial debe agregar como parcial")
    checks.append("aggregate partial")

    aggregate_blocking = dq.merge_quality_results([result, missing], source="aggregate")
    assert_true(aggregate_blocking.status == dq.ERROR, "Un bloqueante debe agregar como error")
    checks.append("aggregate blocking")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Data Quality Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Data Quality Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print(f"\nResultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
