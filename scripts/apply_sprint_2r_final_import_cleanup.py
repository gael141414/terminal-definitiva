from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path("app.py")
INVENTORY_SCRIPT = Path("scripts/print_app_legacy_inventory.py")

OPTIONAL_IMPORT_BLOCKS = [
    '''try:
    import google.generativeai as genai
except Exception:
    genai = None

''',
    '''try:
    from streamlit_option_menu import option_menu
except Exception:
    option_menu = None

''',
    '''try:
    from textblob import TextBlob
except Exception:
    TextBlob = None

''',
    '''try:
    from streamlit_lottie import st_lottie
except Exception:
    def st_lottie(*args, **kwargs):
        return None

''',
]

DIRECT_IMPORTS_TO_REMOVE = [
    "import pandas as pd\n",
    "import yfinance as yf\n",
    "import requests\n",
    "import streamlit.components.v1 as components\n",
]

NAMES_EXPECTED_ABSENT = {
    "pd",
    "yf",
    "requests",
    "components",
    "genai",
    "option_menu",
    "TextBlob",
    "st_lottie",
}

NAMES_EXPECTED_PRESENT = {
    "st",
    "html",
    "CONFIG",
    "asset_to_data_uri",
    "strip_visual_prefix",
    "render_ticker_tape",
    "render_home_page",
    "render_company_tool",
}

MOVED_FUNCTIONS_EXPECTED_ABSENT = {
    "inyectar_atajo_teclado",
    "load_lottieurl",
    "obtener_modelo_gemini",
    "obtener_tickers_filtrados",
    "render_company_empty_state",
    "escanear_vulnerabilidades",
    "generar_reporte_pdf",
}


def collect_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
    return names


def collect_top_level_functions(source: str) -> set[str]:
    tree = ast.parse(source)
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")

    source = APP_PATH.read_text(encoding="utf-8")

    if "st.set_page_config(" not in source[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2R.")

    original_names = collect_names(source)
    still_used = sorted(NAMES_EXPECTED_ABSENT & original_names)
    if still_used:
        raise RuntimeError(
            "No se puede limpiar Sprint 2R porque estos nombres aún se usan en app.py: "
            f"{still_used}"
        )

    new_source = source
    for import_line in DIRECT_IMPORTS_TO_REMOVE:
        new_source = new_source.replace(import_line, "", 1)

    for block in OPTIONAL_IMPORT_BLOCKS:
        new_source = new_source.replace(block, "", 1)

    present_names = collect_names(new_source)
    missing_present = sorted(NAMES_EXPECTED_PRESENT - present_names)
    if missing_present:
        raise RuntimeError(
            "La limpieza eliminó referencias necesarias de app.py: "
            f"{missing_present}"
        )

    top_level_functions = collect_top_level_functions(new_source)
    if top_level_functions:
        raise RuntimeError(
            "app.py todavía tiene funciones top-level tras el refactor: "
            f"{sorted(top_level_functions)}"
        )

    residual_moved_functions = sorted(MOVED_FUNCTIONS_EXPECTED_ABSENT & top_level_functions)
    if residual_moved_functions:
        raise RuntimeError(
            "Quedan funciones que deberían estar extraídas: "
            f"{residual_moved_functions}"
        )

    backup = APP_PATH.with_suffix(".py.bak_sprint_2r")
    backup.write_text(source, encoding="utf-8")
    APP_PATH.write_text(new_source, encoding="utf-8")

    print("OK: Sprint 2R aplicado.")
    print("Imports residuales limpiados en app.py.")
    print(f"Backup creado: {backup}")
    if INVENTORY_SCRIPT.exists():
        print("Ejecuta ahora: python scripts/print_app_legacy_inventory.py --write")
    print("Valida con: python -m py_compile app.py scripts/apply_sprint_2r_final_import_cleanup.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
