from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path("app.py")

SIMPLE_IMPORT_CANDIDATES = {
    "import tempfile\n": {"tempfile"},
    "import os\n": {"os"},
    "import logging\n": {"logging"},
    "import base64\n": {"base64"},
    "import re\n": {"re"},
    "import xml.etree.ElementTree as ET\n": {"ET"},
    "from pathlib import Path\n": {"Path"},
    "from datetime import datetime, timezone, timedelta, time\n": {"datetime", "timezone", "timedelta", "time"},
    "import plotly.graph_objects as go\n": {"go"},
}

APP_HOME_IMPORT_FULL = "from modulos.app_home import render_home_page, render_module_showcase\n"
APP_HOME_IMPORT_MINIMAL = "from modulos.app_home import render_home_page\n"

TOOL_CATALOG_UNUSED_LINE = "    obtener_herramientas_por_bloque,\n"


def used_names(source: str) -> set[str]:
    tree = ast.parse(source)
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}


def remove_simple_unused_imports(source: str, names: set[str]) -> tuple[str, list[str]]:
    updated = source
    removed: list[str] = []

    for import_line, imported_names in SIMPLE_IMPORT_CANDIDATES.items():
        if import_line not in updated:
            continue
        if imported_names.isdisjoint(names):
            updated = updated.replace(import_line, "", 1)
            removed.append(import_line.strip())

    return updated, removed


def cleanup_app_home_import(source: str, names: set[str]) -> tuple[str, list[str]]:
    if APP_HOME_IMPORT_FULL not in source:
        return source, []

    if "render_module_showcase" in names:
        return source, []

    return source.replace(APP_HOME_IMPORT_FULL, APP_HOME_IMPORT_MINIMAL, 1), ["render_module_showcase from modulos.app_home"]


def cleanup_tool_catalog_import(source: str, names: set[str]) -> tuple[str, list[str]]:
    if TOOL_CATALOG_UNUSED_LINE not in source:
        return source, []

    if "obtener_herramientas_por_bloque" in names:
        return source, []

    return source.replace(TOOL_CATALOG_UNUSED_LINE, "", 1), ["obtener_herramientas_por_bloque from modulos.tool_catalog"]


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")

    source = APP_PATH.read_text(encoding="utf-8")

    if "st.set_page_config(" not in source[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2J.")

    names = used_names(source)
    updated, removed_simple = remove_simple_unused_imports(source, names)
    updated, removed_home = cleanup_app_home_import(updated, names)
    updated, removed_tool_catalog = cleanup_tool_catalog_import(updated, names)

    removed = removed_simple + removed_home + removed_tool_catalog

    if updated == source:
        print("Sin cambios: no se detectaron imports legacy residuales seguros de eliminar.")
        return 0

    # Validación posterior: la fuente resultante debe seguir siendo parseable.
    ast.parse(updated)

    backup = APP_PATH.with_suffix(".py.bak_sprint_2j")
    backup.write_text(source, encoding="utf-8")
    APP_PATH.write_text(updated, encoding="utf-8")

    print("OK: Sprint 2J aplicado.")
    print("Imports eliminados:")
    for item in removed:
        print(f"- {item}")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile app.py scripts/apply_sprint_2j_legacy_import_cleanup.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
