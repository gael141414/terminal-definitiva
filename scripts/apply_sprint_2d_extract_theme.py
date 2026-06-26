from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path("app.py")
THEME_PATH = Path("modulos/app_theme.py")
TARGET_FUNCTION = "inject_terminal_theme"
IMPORT_LINE = "from modulos.app_theme import inject_terminal_theme\n"
IMPORT_ANCHOR = "from modulos.app_assets import asset_to_data_uri, strip_visual_prefix\n"

MODULE_HEADER = '''from __future__ import annotations

import streamlit as st


'''


def find_function_span(source: str, function_name: str) -> tuple[int, int]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            if node.lineno is None or node.end_lineno is None:
                raise RuntimeError("La versión de Python no expone lineno/end_lineno correctamente.")
            start_index = node.lineno - 1
            end_index = node.end_lineno

            # Retira líneas en blanco inmediatamente anteriores para evitar huecos dobles.
            while start_index > 0 and lines[start_index - 1].strip() == "":
                start_index -= 1

            return start_index, end_index

    raise RuntimeError(f"No se encontró la función {function_name} en app.py.")


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")

    source = APP_PATH.read_text(encoding="utf-8")

    if "st.set_page_config(" not in source[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2D.")

    if TARGET_FUNCTION not in source and THEME_PATH.exists():
        print("Sin cambios: inject_terminal_theme ya parece extraída de app.py.")
        return 0

    start, end = find_function_span(source, TARGET_FUNCTION)
    lines = source.splitlines(keepends=True)
    function_source = "".join(lines[start:end]).strip() + "\n"

    if "st.markdown(" not in function_source:
        raise RuntimeError("La función extraída no parece contener el tema Streamlit esperado.")

    module_source = MODULE_HEADER + function_source

    new_lines = lines[:start] + lines[end:]
    new_source = "".join(new_lines)

    if IMPORT_LINE not in new_source:
        if IMPORT_ANCHOR not in new_source:
            raise RuntimeError("No se encontró el import anchor de app_assets para insertar app_theme.")
        new_source = new_source.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    backup = APP_PATH.with_suffix(".py.bak_sprint_2d")
    backup.write_text(source, encoding="utf-8")

    THEME_PATH.parent.mkdir(parents=True, exist_ok=True)
    THEME_PATH.write_text(module_source, encoding="utf-8")
    APP_PATH.write_text(new_source, encoding="utf-8")

    print("OK: Sprint 2D aplicado.")
    print(f"Función extraída: {TARGET_FUNCTION} -> {THEME_PATH}")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile app.py modulos/app_theme.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
