"""Carga segura y perezosa de módulos opcionales de ValueQuant.

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
