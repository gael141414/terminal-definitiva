from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path("app.py")
HOME_PATH = Path("modulos/app_home.py")
TARGET_FUNCTION = "render_module_showcase"
IMPORT_LINE = "from modulos.app_home import render_module_showcase\n"
IMPORT_ANCHOR = "from modulos.app_runtime import build_runtime_paths\n"

MODULE_HEADER = '''from __future__ import annotations

import html

import streamlit as st

from modulos.app_assets import strip_visual_prefix
from modulos.app_navigation import TOOL_UI_ICONS
from modulos.tool_catalog import TOOL_CATALOG


'''


def find_function_span(source: str, function_name: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            if node.lineno is None or node.end_lineno is None:
                raise RuntimeError(f"No se pudo localizar el rango de {function_name}.")

            start_index = node.lineno - 1
            end_index = node.end_lineno

            while start_index > 0 and lines[start_index - 1].strip() == "":
                start_index -= 1

            block = "".join(lines[start_index:end_index]).strip() + "\n"
            return start_index, end_index, block

    raise RuntimeError(f"No se encontró la función {function_name} en app.py.")


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")

    source = APP_PATH.read_text(encoding="utf-8")

    if "st.set_page_config(" not in source[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2F.")

    if IMPORT_LINE in source and HOME_PATH.exists() and TARGET_FUNCTION not in source:
        print("Sin cambios: Sprint 2F ya parece aplicado.")
        return 0

    start, end, function_source = find_function_span(source, TARGET_FUNCTION)

    required_tokens = ["TOOL_CATALOG", "TOOL_UI_ICONS", "strip_visual_prefix", "vq-module-card"]
    missing_tokens = [token for token in required_tokens if token not in function_source]
    if missing_tokens:
        raise RuntimeError(f"La función extraída no parece ser el showcase esperado. Faltan: {missing_tokens}")

    module_source = MODULE_HEADER + function_source

    lines = source.splitlines(keepends=True)
    del lines[start:end]
    new_source = "".join(lines)

    if IMPORT_LINE not in new_source:
        if IMPORT_ANCHOR not in new_source:
            raise RuntimeError("No se encontró el import anchor de app_runtime para insertar app_home.")
        new_source = new_source.replace(IMPORT_ANCHOR, IMPORT_LINE + IMPORT_ANCHOR, 1)

    backup = APP_PATH.with_suffix(".py.bak_sprint_2f")
    backup.write_text(source, encoding="utf-8")

    HOME_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOME_PATH.write_text(module_source, encoding="utf-8")
    APP_PATH.write_text(new_source, encoding="utf-8")

    print("OK: Sprint 2F aplicado.")
    print(f"Función extraída: {TARGET_FUNCTION} -> {HOME_PATH}")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile app.py modulos/app_home.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
