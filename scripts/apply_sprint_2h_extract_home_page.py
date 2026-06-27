from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path("app.py")
HOME_PATH = Path("modulos/app_home.py")
TARGET_FUNCTION = "render_home_page"
OLD_IMPORT = "from modulos.app_home import render_module_showcase\n"
NEW_IMPORT = "from modulos.app_home import render_home_page, render_module_showcase\n"
OLD_CALL = "render_home_page()"
NEW_CALL = "render_home_page(LOGO_PATH, HOME_BG_PATH)"

REQUIRED_HOME_IMPORTS = {
    "from datetime import datetime, time, timedelta, timezone\n": "import html\n",
    "import plotly.graph_objects as go\n": "import streamlit as st\n",
}

MARKET_IMPORT = '''from modulos.market_widgets import (
    analizar_rotacion_sectores,
    obtener_market_snapshot,
    obtener_market_treemap_data,
    obtener_ultimas_noticias,
)
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


def adapt_home_function(function_source: str) -> str:
    adapted = function_source
    adapted = adapted.replace(
        "def render_home_page() -> None:",
        "def render_home_page(logo_path, home_bg_path) -> None:",
        1,
    )
    adapted = adapted.replace("asset_to_data_uri(LOGO_PATH)", "asset_to_data_uri(logo_path)")
    adapted = adapted.replace("asset_to_data_uri(HOME_BG_PATH)", "asset_to_data_uri(home_bg_path)")

    required_tokens = [
        "def render_home_page(logo_path, home_bg_path) -> None:",
        "obtener_market_snapshot()",
        "obtener_market_treemap_data()",
        "obtener_ultimas_noticias(6)",
        "analizar_rotacion_sectores()",
    ]
    missing = [token for token in required_tokens if token not in adapted]
    if missing:
        raise RuntimeError(f"La función Home adaptada no contiene los tokens esperados: {missing}")

    return adapted


def update_home_module(home_source: str, function_source: str) -> str:
    if "def render_home_page(" in home_source:
        print("modulos/app_home.py ya contiene render_home_page; no se añade otra vez.")
        return home_source

    updated = home_source

    for import_line, anchor in REQUIRED_HOME_IMPORTS.items():
        if import_line not in updated:
            if anchor not in updated:
                raise RuntimeError(f"No se encontró el anchor de import en app_home.py: {anchor.strip()}")
            updated = updated.replace(anchor, anchor + import_line, 1)

    old_assets_import = "from modulos.app_assets import strip_visual_prefix\n"
    new_assets_import = "from modulos.app_assets import asset_to_data_uri, strip_visual_prefix\n"
    if new_assets_import not in updated:
        if old_assets_import not in updated:
            raise RuntimeError("No se encontró el import de app_assets en app_home.py.")
        updated = updated.replace(old_assets_import, new_assets_import, 1)

    if MARKET_IMPORT not in updated:
        tool_catalog_import = "from modulos.tool_catalog import TOOL_CATALOG\n"
        if tool_catalog_import not in updated:
            raise RuntimeError("No se encontró el import de TOOL_CATALOG en app_home.py.")
        updated = updated.replace(tool_catalog_import, tool_catalog_import + MARKET_IMPORT, 1)

    updated = updated.rstrip() + "\n\n\n" + function_source.strip() + "\n"
    return updated


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")
    if not HOME_PATH.exists():
        raise FileNotFoundError("No se encuentra modulos/app_home.py. Aplica antes Sprint 2F.")

    app_source = APP_PATH.read_text(encoding="utf-8")
    home_source = HOME_PATH.read_text(encoding="utf-8")

    if "st.set_page_config(" not in app_source[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2H.")

    if NEW_CALL in app_source and "def render_home_page(" not in app_source and "def render_home_page(" in home_source:
        print("Sin cambios: Sprint 2H ya parece aplicado.")
        return 0

    start, end, function_source = find_function_span(app_source, TARGET_FUNCTION)
    adapted_function = adapt_home_function(function_source)

    lines = app_source.splitlines(keepends=True)
    del lines[start:end]
    new_app_source = "".join(lines)

    if OLD_IMPORT in new_app_source:
        new_app_source = new_app_source.replace(OLD_IMPORT, NEW_IMPORT, 1)
    elif NEW_IMPORT not in new_app_source:
        raise RuntimeError("No se encontró el import de app_home para actualizarlo.")

    if OLD_CALL not in new_app_source:
        raise RuntimeError("No se encontró la llamada render_home_page() en app.py.")
    new_app_source = new_app_source.replace(OLD_CALL, NEW_CALL, 1)

    new_home_source = update_home_module(home_source, adapted_function)

    backup_app = APP_PATH.with_suffix(".py.bak_sprint_2h")
    backup_home = HOME_PATH.with_suffix(".py.bak_sprint_2h")
    backup_app.write_text(app_source, encoding="utf-8")
    backup_home.write_text(home_source, encoding="utf-8")

    APP_PATH.write_text(new_app_source, encoding="utf-8")
    HOME_PATH.write_text(new_home_source, encoding="utf-8")

    print("OK: Sprint 2H aplicado.")
    print("render_home_page extraída a modulos/app_home.py")
    print(f"Backups creados: {backup_app}, {backup_home}")
    print("Valida con: python -m py_compile app.py modulos/app_home.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
