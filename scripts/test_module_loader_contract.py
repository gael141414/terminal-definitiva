#!/usr/bin/env python3
"""Contract checks for modulos.module_loader.

These checks are intentionally lightweight and do not require pytest. They monkeypatch
Streamlit with a tiny fake object, exercise the public lazy-loading helpers, and fail
with a non-zero exit code if safe_call stops swallowing optional tool failures.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace
from typing import Any

TARGET_MODULE = "valuequant_test_module_loader_target"


@dataclass
class FakeStreamlit:
    errors: list[str] = field(default_factory=list)
    code_blocks: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors.append(str(message))

    def code(self, body: str, language: str | None = None) -> None:
        self.code_blocks.append(str(body))

    def expander(self, label: str):
        return FakeExpander(self, label)


@dataclass
class FakeExpander:
    fake_st: FakeStreamlit
    label: str

    def __enter__(self) -> FakeStreamlit:
        return self.fake_st

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


def make_target_module() -> ModuleType:
    module = ModuleType(TARGET_MODULE)

    def add(left: int, right: int) -> int:
        return left + right

    def explode() -> None:
        raise RuntimeError("boom")

    module.add = add  # type: ignore[attr-defined]
    module.explode = explode  # type: ignore[attr-defined]
    module.not_callable = "not callable"  # type: ignore[attr-defined]
    return module


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_contract_checks() -> list[str]:
    import modulos.module_loader as loader

    checks: list[str] = []
    original_st = loader.st
    original_config = loader.CONFIG
    original_module = sys.modules.get(TARGET_MODULE)
    fake_st = FakeStreamlit()

    try:
        loader.lazy_import.cache_clear()
        loader.st = fake_st  # type: ignore[assignment]
        loader.CONFIG = SimpleNamespace(debug=False)  # type: ignore[assignment]
        sys.modules[TARGET_MODULE] = make_target_module()

        target = loader.lazy_callable(TARGET_MODULE, "add")
        assert_true(callable(target), "lazy_callable debe devolver un callable existente")
        checks.append("lazy_callable existing callable")

        result = loader.safe_call(TARGET_MODULE, "add", 2, 3)
        assert_true(result == 5, "safe_call debe devolver el resultado del callable")
        checks.append("safe_call success result")

        missing = loader.lazy_callable(TARGET_MODULE, "missing")
        assert_true(missing is None, "lazy_callable debe devolver None si falta el callable")
        assert_true(any("no contiene" in message for message in fake_st.errors), "Debe registrar error para callable ausente")
        checks.append("missing callable handled")

        not_callable = loader.lazy_callable(TARGET_MODULE, "not_callable")
        assert_true(not_callable is None, "lazy_callable debe devolver None si el atributo no es ejecutable")
        assert_true(any("no es ejecutable" in message for message in fake_st.errors), "Debe registrar error para atributo no ejecutable")
        checks.append("non-callable handled")

        exploded = loader.safe_call(TARGET_MODULE, "explode")
        assert_true(exploded is None, "safe_call debe devolver None si la herramienta falla")
        assert_true(any("Error ejecutando" in message for message in fake_st.errors), "Debe registrar error de ejecución")
        assert_true(any("RuntimeError: boom" in block for block in fake_st.code_blocks), "Debe registrar diagnóstico corto del fallo")
        checks.append("runtime failure swallowed")

        formatted = loader._format_exception(RuntimeError("short"))
        assert_true(formatted == "RuntimeError: short", "Sin debug debe mostrar diagnóstico corto")
        checks.append("short diagnostic without debug")

        try:
            raise ValueError("debug trace")
        except ValueError as exc:
            loader.CONFIG = SimpleNamespace(debug=True)  # type: ignore[assignment]
            debug_formatted = loader._format_exception(exc)
        assert_true("Traceback" in debug_formatted and "ValueError: debug trace" in debug_formatted, "Con debug debe incluir traceback")
        checks.append("full traceback with debug")

    finally:
        loader.lazy_import.cache_clear()
        loader.st = original_st  # type: ignore[assignment]
        loader.CONFIG = original_config  # type: ignore[assignment]
        if original_module is None:
            sys.modules.pop(TARGET_MODULE, None)
        else:
            sys.modules[TARGET_MODULE] = original_module

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Module Loader Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Module Loader Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print(f"\nResultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
