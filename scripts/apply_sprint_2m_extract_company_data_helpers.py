from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path("app.py")
HELPERS_PATH = Path("modulos/company_data_helpers.py")

TARGET_FUNCTIONS = [
    "obtener_transacciones_insiders",
    "obtener_tickers_filtrados",
    "obtener_valoracion_sectorial",
    "obtener_datos_directiva",
]

IMPORT_ANCHOR = "from modulos.tradingview_widgets import render_tradingview_widget, renderizar_grafico_tradingview\n"
IMPORT_LINE = "from modulos.company_data_helpers import obtener_datos_directiva, obtener_tickers_filtrados, obtener_transacciones_insiders, obtener_valoracion_sectorial\n"

MODULE_HEADER = '''from __future__ import annotations

import pandas as pd
import requests
import streamlit as st
import yfinance as yf


'''


def collect_function_spans(source: str) -> dict[str, tuple[int, int, str]]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    spans: dict[str, tuple[int, int, str]] = {}

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in TARGET_FUNCTIONS:
            continue

        if node.lineno is None or node.end_lineno is None:
            raise RuntimeError(f"No se pudo localizar el rango de {node.name}.")

        start_index = node.lineno - 1
        end_index = node.end_lineno

        # Incluye decoradores de cache si existen.
        if node.decorator_list:
            start_index = min(decorator.lineno for decorator in node.decorator_list) - 1

        while start_index > 0 and lines[start_index - 1].strip() == "":
            start_index -= 1

        block = "".join(lines[start_index:end_index]).strip() + "\n"
        spans[node.name] = (start_index, end_index, block)

    return spans


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")

    source = APP_PATH.read_text(encoding="utf-8")

    if "st.set_page_config(" not in source[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2M.")

    if IMPORT_LINE in source and HELPERS_PATH.exists():
        print("Sin cambios: Sprint 2M ya parece aplicado.")
        return 0

    spans = collect_function_spans(source)
    missing = [name for name in TARGET_FUNCTIONS if name not in spans]
    if missing:
        raise RuntimeError(f"No se encontraron estas funciones en app.py: {missing}")

    module_blocks = [spans[name][2] for name in TARGET_FUNCTIONS]
    module_source = MODULE_HEADER + "\n\n".join(module_blocks) + "\n"

    required_tokens = [
        "@st.cache_data",
        "yf.Ticker",
        "company_tickers.json",
        "heldPercentInsiders",
        "enterpriseToEbitda",
    ]
    missing_tokens = [token for token in required_tokens if token not in module_source]
    if missing_tokens:
        raise RuntimeError(f"La extracción no contiene los helpers esperados. Faltan: {missing_tokens}")

    lines = source.splitlines(keepends=True)
    for _name, (start, end, _block) in sorted(spans.items(), key=lambda item: item[1][0], reverse=True):
        del lines[start:end]

    new_source = "".join(lines)

    if IMPORT_LINE not in new_source:
        if IMPORT_ANCHOR not in new_source:
            raise RuntimeError("No se encontró el import de tradingview_widgets para insertar company_data_helpers.")
        new_source = new_source.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    backup = APP_PATH.with_suffix(".py.bak_sprint_2m")
    backup.write_text(source, encoding="utf-8")

    HELPERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    HELPERS_PATH.write_text(module_source, encoding="utf-8")
    APP_PATH.write_text(new_source, encoding="utf-8")

    print("OK: Sprint 2M aplicado.")
    print(f"Helpers de datos extraídos a: {HELPERS_PATH}")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile app.py modulos/company_data_helpers.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
