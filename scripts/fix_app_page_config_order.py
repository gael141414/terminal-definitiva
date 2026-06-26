from __future__ import annotations

from pathlib import Path

APP_PATH = Path("app.py")

PAGE_CONFIG_BLOCK = '''st.set_page_config(
    page_title="ValueQuant Terminal",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="collapsed",
)
'''

OLD_PAGE_CONFIG_BLOCK = '''# 1. CONFIGURACIÓN DE PÁGINA (Debe ser el primer comando de Streamlit)
st.set_page_config(
    page_title="ValueQuant Terminal",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="collapsed",
)
'''

OLD_SECTION_HEADER = '''# ---------------- CONFIGURACIÓN ---------------- #
# 1. CONFIGURACIÓN DE PÁGINA movida al inicio del archivo para cumplir Streamlit.
'''


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")

    text = APP_PATH.read_text(encoding="utf-8")
    original = text

    if OLD_PAGE_CONFIG_BLOCK in text:
        text = text.replace(
            OLD_PAGE_CONFIG_BLOCK,
            "# 1. CONFIGURACIÓN DE PÁGINA movida al inicio del archivo para cumplir Streamlit.\n",
            1,
        )

    if PAGE_CONFIG_BLOCK not in text.split("from pathlib import Path", 1)[0]:
        marker = "import streamlit as st\n"
        if marker not in text:
            raise RuntimeError("No se ha encontrado `import streamlit as st` en app.py.")
        text = text.replace(marker, marker + "\n" + PAGE_CONFIG_BLOCK + "\n", 1)

    if text == original:
        print("Sin cambios: app.py ya tiene st.set_page_config al inicio.")
        return 0

    backup = APP_PATH.with_suffix(".py.bak_page_config")
    backup.write_text(original, encoding="utf-8")
    APP_PATH.write_text(text, encoding="utf-8")
    print("OK: st.set_page_config movido al inicio de app.py.")
    print(f"Backup creado: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
