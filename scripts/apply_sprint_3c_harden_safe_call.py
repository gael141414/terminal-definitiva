from __future__ import annotations

from pathlib import Path

MODULE_LOADER_PATH = Path("modulos/module_loader.py")

NEW_MODULE_LOADER = '''"""Carga segura y perezosa de módulos opcionales de ValueQuant.

Este módulo permite que app.py no importe todas las herramientas al arrancar.
Si un módulo secundario falla, se muestra un error controlado en Streamlit en vez de
romper toda la aplicación.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module
from types import ModuleType
from typing import Any, Callable
import traceback

import streamlit as st

try:
    from modulos.config import CONFIG
except Exception:  # pragma: no cover - evita ciclos/arranque parcial fuera de Streamlit
    CONFIG = None


@lru_cache(maxsize=128)
def lazy_import(module_path: str) -> ModuleType:
    """Importa un módulo una sola vez y lo cachea.

    Lanza la excepción original para que el wrapper superior pueda mostrarla.
    """
    return import_module(module_path)


def _debug_enabled() -> bool:
    """Indica si los diagnósticos deben mostrar traceback completo."""

    return bool(getattr(CONFIG, "debug", False))


def _format_exception(exc: Exception) -> str:
    """Formatea una excepción sin exponer traceback completo salvo en debug."""

    if _debug_enabled():
        return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return f"{type(exc).__name__}: {exc}"


def _render_diagnostic(message: str, exc: Exception) -> None:
    """Muestra un error de herramienta con diagnóstico técnico controlado."""

    st.error(message)
    with st.expander("Diagnóstico técnico"):
        st.code(_format_exception(exc), language="text")


def lazy_callable(module_path: str, callable_name: str) -> Callable[..., Any] | None:
    """Devuelve una función de un módulo cargado bajo demanda.

    Si el import o la resolución del callable falla, devuelve None y muestra un
    diagnóstico controlado dentro de la app.
    """
    try:
        module = lazy_import(module_path)
    except Exception as exc:
        _render_diagnostic(f"No se pudo cargar el módulo `{module_path}`.", exc)
        return None

    try:
        target = getattr(module, callable_name)
    except AttributeError as exc:
        _render_diagnostic(f"El módulo `{module_path}` no contiene `{callable_name}`.", exc)
        return None

    if not callable(target):
        st.error(f"`{module_path}.{callable_name}` existe pero no es ejecutable.")
        return None

    return target


def safe_call(module_path: str, callable_name: str, *args: Any, **kwargs: Any) -> Any:
    """Ejecuta una función opcional con import perezoso y error controlado."""

    target = lazy_callable(module_path, callable_name)
    if target is None:
        return None

    try:
        return target(*args, **kwargs)
    except Exception as exc:
        _render_diagnostic(f"Error ejecutando `{module_path}.{callable_name}`.", exc)
        return None
'''

REQUIRED_TOKENS = [
    "import traceback",
    "from modulos.config import CONFIG",
    "def _debug_enabled()",
    "def _format_exception(exc: Exception)",
    "def _render_diagnostic(message: str, exc: Exception)",
    "traceback.format_exception",
    "st.code(_format_exception(exc), language=\"text\")",
]


def main() -> int:
    if not MODULE_LOADER_PATH.exists():
        raise FileNotFoundError("No se encuentra modulos/module_loader.py. Ejecuta desde la raíz del proyecto.")

    source = MODULE_LOADER_PATH.read_text(encoding="utf-8")

    if all(token in source for token in REQUIRED_TOKENS):
        print("Sin cambios: Sprint 3C ya parece aplicado.")
        return 0

    for token in ["def lazy_import(", "def lazy_callable(", "def safe_call("]:
        if token not in source:
            raise RuntimeError(f"module_loader.py no contiene la estructura esperada. Falta: {token}")

    missing = [token for token in REQUIRED_TOKENS if token not in NEW_MODULE_LOADER]
    if missing:
        raise RuntimeError(f"La plantilla de Sprint 3C está incompleta. Faltan: {missing}")

    backup = MODULE_LOADER_PATH.with_suffix(".py.bak_sprint_3c")
    backup.write_text(source, encoding="utf-8")
    MODULE_LOADER_PATH.write_text(NEW_MODULE_LOADER, encoding="utf-8")

    print("OK: Sprint 3C aplicado.")
    print("safe_call ahora usa diagnóstico centralizado y traceback completo solo en VALUEQUANT_DEBUG/DEBUG.")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile modulos/module_loader.py scripts/apply_sprint_3c_harden_safe_call.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
