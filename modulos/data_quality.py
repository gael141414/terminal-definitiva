from __future__ import annotations

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
