from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path("app.py")
UI_PATH = Path("modulos/app_company_ui.py")

TARGET_FUNCTION = "render_company_empty_state"
IMPORT_ANCHOR = "from modulos.company_data_helpers import obtener_datos_directiva, obtener_tickers_filtrados, obtener_transacciones_insiders, obtener_valoracion_sectorial\n"
IMPORT_LINE = "from modulos.app_company_ui import render_company_empty_state\n"

MODULE_HEADER = '''from __future__ import annotations

import html

import streamlit as st

from modulos.app_assets import strip_visual_prefix


'''


def collect_function_span(source: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != TARGET_FUNCTION:
            continue

        if node.lineno is None or node.end_lineno is None:
            raise RuntimeError(f"No se pudo localizar el rango de {TARGET_FUNCTION}.")

        start_index = node.lineno - 1
        end_index = node.end_lineno

        while start_index > 0 and lines[start_index - 1].strip() == "":
            start_index -= 1

        block = "".join(lines[start_index:end_index]).strip() + "\n"
        return start_index, end_index, block

    raise RuntimeError(f"No se encontró {TARGET_FUNCTION} en app.py.")


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")

    source = APP_PATH.read_text(encoding="utf-8")

    if "st.set_page_config(" not in source[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2N.")

    if IMPORT_LINE in source and UI_PATH.exists():
        print("Sin cambios: Sprint 2N ya parece aplicado.")
        return 0

    start, end, function_block = collect_function_span(source)
    module_source = MODULE_HEADER + function_block + "\n"

    required_tokens = [
        "def render_company_empty_state(",
        "strip_visual_prefix",
        "html.escape",
        "st.markdown",
        "vq-empty-state",
    ]
    missing_tokens = [token for token in required_tokens if token not in module_source]
    if missing_tokens:
        raise RuntimeError(f"La extracción no contiene el estado vacío esperado. Faltan: {missing_tokens}")

    lines = source.splitlines(keepends=True)
    del lines[start:end]
    new_source = "".join(lines)

    if IMPORT_LINE not in new_source:
        if IMPORT_ANCHOR not in new_source:
            raise RuntimeError("No se encontró el import de company_data_helpers para insertar app_company_ui.")
        new_source = new_source.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    backup = APP_PATH.with_suffix(".py.bak_sprint_2n")
    backup.write_text(source, encoding="utf-8")

    UI_PATH.parent.mkdir(parents=True, exist_ok=True)
    UI_PATH.write_text(module_source, encoding="utf-8")
    APP_PATH.write_text(new_source, encoding="utf-8")

    print("OK: Sprint 2N aplicado.")
    print(f"Estado vacío de empresa extraído a: {UI_PATH}")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile app.py modulos/app_company_ui.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
