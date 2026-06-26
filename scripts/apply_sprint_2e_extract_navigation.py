from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path("app.py")
NAVIGATION_PATH = Path("modulos/app_navigation.py")

IMPORT_ANCHOR = "from modulos.app_theme import inject_terminal_theme\n"
IMPORT_LINE = (
    "from modulos.app_navigation import (\n"
    "    BLOQUE_UI,\n"
    "    TOOL_UI_ICONS,\n"
    "    render_context_header,\n"
    "    render_option_menu_safe,\n"
    ")\n"
)

TARGETS = {
    "functions": {"render_context_header", "render_option_menu_safe"},
    "assignments": {"BLOQUE_UI", "TOOL_UI_ICONS"},
}

MODULE_HEADER = '''from __future__ import annotations

import html

import streamlit as st

try:
    from streamlit_option_menu import option_menu
except Exception:
    option_menu = None

from modulos.app_assets import strip_visual_prefix


'''


def _node_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.FunctionDef):
        return node.name
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                return target.id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def collect_spans(source: str) -> dict[str, tuple[int, int, str]]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    spans: dict[str, tuple[int, int, str]] = {}

    for node in tree.body:
        name = _node_name(node)
        if not name:
            continue

        is_target = (
            isinstance(node, ast.FunctionDef) and name in TARGETS["functions"]
        ) or (
            isinstance(node, (ast.Assign, ast.AnnAssign)) and name in TARGETS["assignments"]
        )

        if not is_target:
            continue

        if node.lineno is None or node.end_lineno is None:
            raise RuntimeError(f"No se pudo localizar el rango de {name}.")

        start_index = node.lineno - 1
        end_index = node.end_lineno

        while start_index > 0 and lines[start_index - 1].strip() == "":
            start_index -= 1

        block = "".join(lines[start_index:end_index]).strip() + "\n"
        spans[name] = (start_index, end_index, block)

    return spans


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")

    source = APP_PATH.read_text(encoding="utf-8")

    if "st.set_page_config(" not in source[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2E.")

    if IMPORT_LINE in source and NAVIGATION_PATH.exists():
        print("Sin cambios: Sprint 2E ya parece aplicado.")
        return 0

    spans = collect_spans(source)
    required = TARGETS["functions"] | TARGETS["assignments"]
    missing = sorted(required - set(spans))
    if missing:
        raise RuntimeError(f"No se encontraron estos elementos en app.py: {missing}")

    module_blocks = [
        spans["BLOQUE_UI"][2],
        spans["TOOL_UI_ICONS"][2],
        spans["render_context_header"][2],
        spans["render_option_menu_safe"][2],
    ]
    module_source = MODULE_HEADER + "\n\n".join(module_blocks) + "\n"

    lines = source.splitlines(keepends=True)
    for name, (start, end, _block) in sorted(spans.items(), key=lambda item: item[1][0], reverse=True):
        del lines[start:end]

    new_source = "".join(lines)

    if IMPORT_LINE not in new_source:
        if IMPORT_ANCHOR not in new_source:
            raise RuntimeError("No se encontró el import anchor de app_theme para insertar app_navigation.")
        new_source = new_source.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    backup = APP_PATH.with_suffix(".py.bak_sprint_2e")
    backup.write_text(source, encoding="utf-8")

    NAVIGATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    NAVIGATION_PATH.write_text(module_source, encoding="utf-8")
    APP_PATH.write_text(new_source, encoding="utf-8")

    print("OK: Sprint 2E aplicado.")
    print(f"Navegación extraída a: {NAVIGATION_PATH}")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile app.py modulos/app_navigation.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
