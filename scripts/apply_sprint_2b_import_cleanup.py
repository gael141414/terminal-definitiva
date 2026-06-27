from __future__ import annotations

from pathlib import Path

APP_PATH = Path("app.py")

OLD_IMPORT_BLOCK = '''import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import tempfile
import requests
import streamlit.components.v1 as components
import google.generativeai as genai
import os
import logging
import base64
import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta, time
from fpdf import FPDF

try:
    from streamlit_option_menu import option_menu
except Exception:
    option_menu = None

from income_analyzer import analizar_cuenta_resultados
from balance_analyzer import analizar_balance
from cashflow_analyzer import analizar_flujo_efectivo
from valuator import valorar_empresa
from textblob import TextBlob
from streamlit_lottie import st_lottie
'''

NEW_IMPORT_BLOCK = '''import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import tempfile
import requests
import streamlit.components.v1 as components
import os
import logging
import base64
import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta, time

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from fpdf import FPDF
except Exception:
    FPDF = None

try:
    from streamlit_option_menu import option_menu
except Exception:
    option_menu = None

try:
    from textblob import TextBlob
except Exception:
    TextBlob = None

try:
    from streamlit_lottie import st_lottie
except Exception:
    def st_lottie(*args, **kwargs):
        return None

from income_analyzer import analizar_cuenta_resultados
from balance_analyzer import analizar_balance
from cashflow_analyzer import analizar_flujo_efectivo
from valuator import valorar_empresa
'''

OLD_GEMINI_START = '''    try:
        genai.configure(api_key=api_key)
'''

NEW_GEMINI_START = '''    if genai is None:
        return None

    try:
        genai.configure(api_key=api_key)
'''

OLD_PDF_START = '''def generar_reporte_pdf(ticker, precio, res_val, nota, fcf_yield, buyback_yield):
    """Genera un informe institucional en PDF de 1 página (Tear Sheet)"""
    pdf = FPDF()
'''

NEW_PDF_START = '''def generar_reporte_pdf(ticker, precio, res_val, nota, fcf_yield, buyback_yield):
    """Genera un informe institucional en PDF de 1 página (Tear Sheet)"""
    if FPDF is None:
        raise RuntimeError("fpdf2 no está instalado. Instálalo o desactiva la exportación PDF.")

    pdf = FPDF()
'''


def remove_duplicate_config_imports(text: str) -> str:
    target = "from modulos.config import CONFIG\n"
    first = text.find(target)
    if first == -1:
        return text

    cursor = first + len(target)
    while True:
        next_pos = text.find(target, cursor)
        if next_pos == -1:
            return text
        text = text[:next_pos] + text[next_pos + len(target):]
        cursor = first + len(target)


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")

    text = APP_PATH.read_text(encoding="utf-8")
    original = text

    if "st.set_page_config(" not in text[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2B.")

    if OLD_IMPORT_BLOCK in text:
        text = text.replace(OLD_IMPORT_BLOCK, NEW_IMPORT_BLOCK, 1)
    else:
        print("Aviso: no se encontró el bloque exacto de imports. Se aplicará solo limpieza parcial.")

    text = remove_duplicate_config_imports(text)

    if OLD_GEMINI_START in text and NEW_GEMINI_START not in text:
        text = text.replace(OLD_GEMINI_START, NEW_GEMINI_START, 1)

    if OLD_PDF_START in text and NEW_PDF_START not in text:
        text = text.replace(OLD_PDF_START, NEW_PDF_START, 1)

    if text == original:
        print("Sin cambios: Sprint 2B ya parece aplicado.")
        return 0

    backup = APP_PATH.with_suffix(".py.bak_sprint_2b")
    backup.write_text(original, encoding="utf-8")
    APP_PATH.write_text(text, encoding="utf-8")

    print("OK: Sprint 2B aplicado sobre app.py.")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
