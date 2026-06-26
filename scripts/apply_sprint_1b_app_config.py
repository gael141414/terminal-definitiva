"""Patch local de Sprint 1B para centralizar secretos en app.py.

Uso desde la raíz del proyecto:
    python scripts/apply_sprint_1b_app_config.py
    python -m py_compile app.py modulos/config.py modulos/fmp_api.py modulos/scoring_engine.py

El script es idempotente: puede ejecutarse más de una vez sin duplicar imports.
"""
from __future__ import annotations

from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
HARDCODED_FMP_FRAGMENT = "vo1atWFBZ"


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if old not in text:
        return text, False
    return text.replace(old, new, 1), True


def main() -> None:
    if not APP_PATH.exists():
        raise FileNotFoundError(f"No existe app.py en {APP_PATH}")

    text = APP_PATH.read_text(encoding="utf-8")
    changes: list[str] = []

    if "from modulos.config import CONFIG" not in text:
        text, changed = replace_once(
            text,
            "from streamlit_lottie import st_lottie\n",
            "from streamlit_lottie import st_lottie\nfrom modulos.config import CONFIG\n",
            "config import",
        )
        if changed:
            changes.append("Añadido import de CONFIG")

    old_gemini = '''    api_key = (\n        obtener_secreto_streamlit("GEMINI_API_KEY")\n        or obtener_secreto_streamlit("GOOGLE_API_KEY")\n        or os.getenv("GEMINI_API_KEY")\n        or os.getenv("GOOGLE_API_KEY")\n    )'''
    new_gemini = '''    api_key = CONFIG.gemini_api_key or CONFIG.google_api_key'''
    text, changed = replace_once(text, old_gemini, new_gemini, "gemini config")
    if changed:
        changes.append("Gemini/Google API centralizadas en CONFIG")

    old_fmp_line = 'FMP_API_KEY = os.getenv("FMP_API_KEY", "vo1atWFBZwr64ScXucowhC0Wmy3Wweaf")  # Producción: mover a .env o st.secrets.'
    new_fmp_line = 'FMP_API_KEY = CONFIG.fmp_api_key'
    text, changed = replace_once(text, old_fmp_line, new_fmp_line, "fmp config")
    if changed:
        changes.append("Eliminado fallback hardcodeado de FMP_API_KEY")

    old_news_block = '''    try:\n        try:\n            from modulos.fmp_api import API_KEY as clave_api\n        except ImportError:\n            from modulos.fmp_api import FMP_API_KEY as clave_api\n\n        url = "https://financialmodelingprep.com/api/v3/stock_news"'''
    new_news_block = '''    try:\n        clave_api = CONFIG.fmp_api_key\n        if not clave_api:\n            raise RuntimeError("FMP_API_KEY no configurada")\n\n        url = "https://financialmodelingprep.com/api/v3/stock_news"'''
    text, changed = replace_once(text, old_news_block, new_news_block, "news fmp config")
    if changed:
        changes.append("Noticias FMP pasan a leer CONFIG")

    if HARDCODED_FMP_FRAGMENT in text:
        raise RuntimeError(
            "Sigue existiendo el fragmento de la clave FMP hardcodeada en app.py. "
            "Revisa manualmente antes de guardar."
        )

    APP_PATH.write_text(text, encoding="utf-8")

    if changes:
        print("Sprint 1B aplicado en app.py:")
        for item in changes:
            print(f"- {item}")
    else:
        print("No había cambios pendientes: app.py ya estaba parcheado.")


if __name__ == "__main__":
    main()
