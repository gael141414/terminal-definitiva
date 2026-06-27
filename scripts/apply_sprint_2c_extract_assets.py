from __future__ import annotations

from pathlib import Path

APP_PATH = Path("app.py")

IMPORT_ANCHOR = "from modulos.config import CONFIG\n"
IMPORT_ADDITION = "from modulos.app_assets import asset_to_data_uri, strip_visual_prefix\nfrom modulos.app_runtime import build_runtime_paths\n"

OLD_ASSET_BLOCK = '''# ---------------- TERMINAL UI 2026: ASSETS, CSS, HOME Y NAVEGACIÓN ---------------- #
APP_DIR = Path(__file__).resolve().parent
LOGO_PATH = APP_DIR / "logo.png"
HOME_BG_PATH = APP_DIR / "fondo.png"
FMP_API_KEY = CONFIG.fmp_api_key


def asset_to_data_uri(path: Path) -> str:
    """Convierte un asset local en data URI para usarlo de forma estable en CSS/HTML."""
    try:
        if not path.exists():
            return ""
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return ""


def strip_visual_prefix(texto: str) -> str:
    """Elimina pictogramas/símbolos iniciales de las etiquetas antiguas sin tocar el router interno."""
    limpio = re.sub(r"^[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+", "", texto or "").strip()
    return limpio or texto


'''

NEW_ASSET_BLOCK = '''# ---------------- TERMINAL UI 2026: ASSETS, CSS, HOME Y NAVEGACIÓN ---------------- #
RUNTIME_PATHS = build_runtime_paths(__file__)
APP_DIR = RUNTIME_PATHS.app_dir
LOGO_PATH = RUNTIME_PATHS.logo_path
HOME_BG_PATH = RUNTIME_PATHS.home_bg_path
FMP_API_KEY = CONFIG.fmp_api_key


'''


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")

    text = APP_PATH.read_text(encoding="utf-8")
    original = text

    if "st.set_page_config(" not in text[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2C.")

    if IMPORT_ADDITION not in text:
        if IMPORT_ANCHOR not in text:
            raise RuntimeError("No se ha encontrado el import de CONFIG para insertar imports de assets/runtime.")
        text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_ADDITION, 1)

    if OLD_ASSET_BLOCK in text:
        text = text.replace(OLD_ASSET_BLOCK, NEW_ASSET_BLOCK, 1)
    elif "RUNTIME_PATHS = build_runtime_paths(__file__)" in text:
        print("Aviso: el bloque de assets ya parece extraído.")
    else:
        raise RuntimeError("No se encontró el bloque exacto de assets en app.py. No se aplican cambios parciales.")

    if text == original:
        print("Sin cambios: Sprint 2C ya parece aplicado.")
        return 0

    backup = APP_PATH.with_suffix(".py.bak_sprint_2c")
    backup.write_text(original, encoding="utf-8")
    APP_PATH.write_text(text, encoding="utf-8")

    print("OK: Sprint 2C aplicado sobre app.py.")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile app.py modulos/app_assets.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
