from __future__ import annotations

from pathlib import Path

DATA_QUALITY_PATH = Path("modulos/data_quality.py")
CONTRACT_TEST_PATH = Path("scripts/test_data_quality_contract.py")
SMOKE_PATH = Path("modulos/smoke_tests.py")

DATA_QUALITY_SOURCE = '''from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

OK = "ok"
PARTIAL = "partial"
EMPTY = "empty"
INVALID_TYPE = "invalid_type"
MISSING_COLUMNS = "missing_columns"
MISSING_KEYS = "missing_keys"
INSUFFICIENT_ROWS = "insufficient_rows"
ERROR = "error"

USABLE_STATUSES = {OK, PARTIAL}
BLOCKING_STATUSES = {EMPTY, INVALID_TYPE, MISSING_COLUMNS, MISSING_KEYS, INSUFFICIENT_ROWS, ERROR}


@dataclass(frozen=True)
class DataQualityResult:
    """Resultado normalizado de validación de una fuente de datos."""

    source: str
    status: str
    rows: int = 0
    columns: list[str] = field(default_factory=list)
    required_columns: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    required_keys: list[str] = field(default_factory=list)
    missing_keys: list[str] = field(default_factory=list)
    coverage: float = 0.0
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == OK

    @property
    def usable(self) -> bool:
        return self.status in USABLE_STATUSES

    @property
    def blocking(self) -> bool:
        return self.status in BLOCKING_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "rows": self.rows,
            "columns": self.columns,
            "required_columns": self.required_columns,
            "missing_columns": self.missing_columns,
            "required_keys": self.required_keys,
            "missing_keys": self.missing_keys,
            "coverage": self.coverage,
            "message": self.message,
            "usable": self.usable,
            "blocking": self.blocking,
            "details": self.details,
        }


def _as_list(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    return [str(value) for value in values]


def _clamp_ratio(value: Any) -> float:
    try:
        numeric = float(value)
    except Exception:
        return 0.0
    if not np.isfinite(numeric):
        return 0.0
    return float(max(0.0, min(1.0, numeric)))


def is_valid_value(value: Any) -> bool:
    """True si el valor aporta información utilizable para un cálculo."""

    try:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, bool):
            return True
        if pd.isna(value):
            return False
        if isinstance(value, (int, float, np.number)):
            return bool(np.isfinite(float(value)))
        return True
    except Exception:
        return False


def coverage_ratio(values: Iterable[Any]) -> float:
    """Ratio 0-1 de valores utilizables en una colección."""

    values_list = list(values)
    if not values_list:
        return 0.0
    return _clamp_ratio(sum(is_valid_value(value) for value in values_list) / len(values_list))


def safe_numeric_series(df: pd.DataFrame | None, column: str) -> pd.Series:
    """Devuelve una serie numérica limpia o una serie vacía si no existe."""

    if df is None or not isinstance(df, pd.DataFrame) or df.empty or column not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def dataframe_has_columns(df: pd.DataFrame | None, required_columns: Iterable[str]) -> bool:
    required = _as_list(required_columns)
    if df is None or not isinstance(df, pd.DataFrame):
        return False
    return all(column in df.columns for column in required)


def validate_dataframe(
    df: pd.DataFrame | None,
    required_columns: Iterable[str] | None = None,
    *,
    source: str = "dataframe",
    min_rows: int = 1,
    min_coverage: float = 0.60,
    allow_empty: bool = False,
) -> DataQualityResult:
    """Valida estructura mínima y cobertura de un DataFrame de entrada."""

    required = _as_list(required_columns)
    min_rows = max(int(min_rows), 0)
    min_coverage = _clamp_ratio(min_coverage)

    if df is None or not isinstance(df, pd.DataFrame):
        return DataQualityResult(
            source=source,
            status=INVALID_TYPE,
            required_columns=required,
            message="La fuente no es un DataFrame válido.",
        )

    columns = [str(column) for column in df.columns]
    rows = int(len(df))
    missing = [column for column in required if column not in df.columns]

    if missing:
        return DataQualityResult(
            source=source,
            status=MISSING_COLUMNS,
            rows=rows,
            columns=columns,
            required_columns=required,
            missing_columns=missing,
            coverage=0.0,
            message="Faltan columnas obligatorias.",
        )

    if rows == 0 and not allow_empty:
        return DataQualityResult(
            source=source,
            status=EMPTY,
            rows=0,
            columns=columns,
            required_columns=required,
            message="DataFrame vacío.",
        )

    if rows < min_rows:
        return DataQualityResult(
            source=source,
            status=INSUFFICIENT_ROWS,
            rows=rows,
            columns=columns,
            required_columns=required,
            coverage=0.0,
            message=f"Filas insuficientes: {rows}/{min_rows}.",
        )

    if required and rows > 0:
        valid_cells = df[required].applymap(is_valid_value)
        coverage = _clamp_ratio(float(valid_cells.to_numpy().mean()))
    else:
        coverage = 1.0 if rows >= min_rows else 0.0

    status = OK if coverage >= min_coverage else PARTIAL
    message = "Cobertura suficiente." if status == OK else "Cobertura parcial de datos."

    return DataQualityResult(
        source=source,
        status=status,
        rows=rows,
        columns=columns,
        required_columns=required,
        coverage=coverage,
        message=message,
    )


def validate_mapping(
    data: dict[str, Any] | None,
    required_keys: Iterable[str] | None = None,
    *,
    source: str = "mapping",
    min_coverage: float = 0.60,
) -> DataQualityResult:
    """Valida estructura y cobertura de un diccionario de datos."""

    required = _as_list(required_keys)
    min_coverage = _clamp_ratio(min_coverage)

    if data is None or not isinstance(data, dict):
        return DataQualityResult(
            source=source,
            status=INVALID_TYPE,
            required_keys=required,
            message="La fuente no es un diccionario válido.",
        )

    missing = [key for key in required if key not in data]
    if missing:
        return DataQualityResult(
            source=source,
            status=MISSING_KEYS,
            required_keys=required,
            missing_keys=missing,
            coverage=0.0,
            message="Faltan claves obligatorias.",
            details={"keys": sorted(map(str, data.keys()))},
        )

    if required:
        coverage = coverage_ratio(data.get(key) for key in required)
    else:
        coverage = coverage_ratio(data.values()) if data else 0.0

    status = OK if coverage >= min_coverage else PARTIAL
    message = "Cobertura suficiente." if status == OK else "Cobertura parcial de datos."

    return DataQualityResult(
        source=source,
        status=status,
        required_keys=required,
        coverage=coverage,
        message=message,
        details={"keys": sorted(map(str, data.keys()))},
    )


def merge_quality_results(results: Iterable[DataQualityResult], *, source: str = "aggregate") -> DataQualityResult:
    """Resume múltiples validaciones en un único estado agregado."""

    result_list = list(results)
    if not result_list:
        return DataQualityResult(source=source, status=EMPTY, message="Sin resultados de calidad.")

    blocking = [result for result in result_list if result.blocking]
    partial = [result for result in result_list if result.status == PARTIAL]
    coverage = coverage_ratio(result.coverage for result in result_list)

    if blocking:
        status = ERROR
        message = f"{len(blocking)} fuentes bloqueantes."
    elif partial:
        status = PARTIAL
        message = f"{len(partial)} fuentes parciales."
    else:
        status = OK
        message = "Todas las fuentes son utilizables."

    return DataQualityResult(
        source=source,
        status=status,
        rows=sum(result.rows for result in result_list),
        coverage=coverage,
        message=message,
        details={"sources": [result.to_dict() for result in result_list]},
    )
'''

CONTRACT_TEST_SOURCE = '''#!/usr/bin/env python3
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
'''

SMOKE_CRITICAL_FILE_ANCHOR = '    "modulos/config.py",\n'
SMOKE_DATA_QUALITY_FILE_LINE = '    "modulos/data_quality.py",\n'
SMOKE_CONTRACT_FILE_ANCHOR = '    "scripts/test_module_loader_contract.py",\n'
SMOKE_DATA_QUALITY_TEST_LINE = '    "scripts/test_data_quality_contract.py",\n'
SMOKE_IMPORT_ANCHOR = '    "modulos.config",\n'
SMOKE_DATA_QUALITY_IMPORT_LINE = '    "modulos.data_quality",\n'
SMOKE_FUNCTION_ANCHOR = "\ndef _check_catalog() -> list[SmokeCheck]:\n"
SMOKE_DATA_QUALITY_FUNCTION = '''

def _check_data_quality_contract() -> list[SmokeCheck]:
    """Ejecuta los checks contractuales de data_quality."""

    checks: list[SmokeCheck] = []
    try:
        contract = importlib.import_module("scripts.test_data_quality_contract")
        contract_checks = contract.run_contract_checks()
        checks.append(_ok("data_quality_contract:loaded", f"{len(contract_checks)} checks"))
        checks.append(_ok("data_quality_contract:behavior", "data quality contract OK"))
    except Exception as exc:
        checks.append(_fail("data_quality_contract:behavior", f"{type(exc).__name__}: {exc}"))
    return checks
'''
SMOKE_CALL_ANCHOR = "    checks.extend(_check_import(name) for name in CRITICAL_IMPORTS)\n"
SMOKE_DATA_QUALITY_CALL_LINE = "    checks.extend(_check_data_quality_contract())\n"


def write_if_absent(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def patch_smoke_tests() -> bool:
    source = SMOKE_PATH.read_text(encoding="utf-8")
    new_source = source

    replacements = [
        (SMOKE_CRITICAL_FILE_ANCHOR, SMOKE_CRITICAL_FILE_ANCHOR + SMOKE_DATA_QUALITY_FILE_LINE, SMOKE_DATA_QUALITY_FILE_LINE),
        (SMOKE_CONTRACT_FILE_ANCHOR, SMOKE_CONTRACT_FILE_ANCHOR + SMOKE_DATA_QUALITY_TEST_LINE, SMOKE_DATA_QUALITY_TEST_LINE),
        (SMOKE_IMPORT_ANCHOR, SMOKE_IMPORT_ANCHOR + SMOKE_DATA_QUALITY_IMPORT_LINE, SMOKE_DATA_QUALITY_IMPORT_LINE),
    ]

    for anchor, replacement, token in replacements:
        if token not in new_source:
            if anchor not in new_source:
                raise RuntimeError(f"No se encontró anchor en smoke_tests.py: {anchor!r}")
            new_source = new_source.replace(anchor, replacement, 1)

    if "def _check_data_quality_contract()" not in new_source:
        if SMOKE_FUNCTION_ANCHOR not in new_source:
            raise RuntimeError("No se encontró punto de inserción antes de _check_catalog.")
        new_source = new_source.replace(SMOKE_FUNCTION_ANCHOR, SMOKE_DATA_QUALITY_FUNCTION + SMOKE_FUNCTION_ANCHOR, 1)

    if SMOKE_DATA_QUALITY_CALL_LINE not in new_source:
        if SMOKE_CALL_ANCHOR not in new_source:
            raise RuntimeError("No se encontró punto de llamada tras CRITICAL_IMPORTS.")
        new_source = new_source.replace(SMOKE_CALL_ANCHOR, SMOKE_CALL_ANCHOR + SMOKE_DATA_QUALITY_CALL_LINE, 1)

    required_tokens = [
        '"modulos/data_quality.py"',
        '"scripts/test_data_quality_contract.py"',
        '"modulos.data_quality"',
        "def _check_data_quality_contract()",
        'importlib.import_module("scripts.test_data_quality_contract")',
        "checks.extend(_check_data_quality_contract())",
    ]
    missing = [token for token in required_tokens if token not in new_source]
    if missing:
        raise RuntimeError(f"Integración incompleta en smoke_tests.py. Faltan: {missing}")

    if new_source == source:
        return False

    backup = SMOKE_PATH.with_suffix(".py.bak_sprint_4b")
    backup.write_text(source, encoding="utf-8")
    SMOKE_PATH.write_text(new_source, encoding="utf-8")
    return True


def main() -> int:
    if not SMOKE_PATH.exists():
        raise FileNotFoundError("No se encuentra modulos/smoke_tests.py. Ejecuta desde la raíz del proyecto.")

    created_data_quality = write_if_absent(DATA_QUALITY_PATH, DATA_QUALITY_SOURCE)
    created_contract = write_if_absent(CONTRACT_TEST_PATH, CONTRACT_TEST_SOURCE)
    patched_smoke = patch_smoke_tests()

    print("OK: Sprint 4B aplicado.")
    print(f"data_quality.py creado: {created_data_quality}")
    print(f"test_data_quality_contract.py creado: {created_contract}")
    print(f"smoke_tests.py actualizado: {patched_smoke}")
    print("Valida con:")
    print("python -m py_compile modulos/data_quality.py scripts/test_data_quality_contract.py modulos/smoke_tests.py")
    print("python scripts/test_data_quality_contract.py")
    print("python scripts/run_smoke_tests.py --strict")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
