"""Sprint 1G: activa navegación por modo de producto en app.py.

Este script modifica app.py de forma conservadora para que la interfaz permita elegir
entre modo MVP, Consolidado y Completo usando el catálogo centralizado.

Uso:
    python scripts/apply_sprint_1g_navigation_modes.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
BACKUP_PATH = ROOT / "app.py.bak_sprint_1g"


OLD_IMPORT = '''from modulos.tool_catalog import (
    TOOL_CATALOG,
    BLOQUES_HERRAMIENTAS,
    HERRAMIENTAS_POR_LABEL,
    obtener_herramientas_por_bloque,
)
'''

NEW_IMPORT = '''from modulos.tool_catalog import (
    TOOL_CATALOG,
    BLOQUES_HERRAMIENTAS,
    HERRAMIENTAS_POR_LABEL,
    obtener_bloques_por_modo,
    obtener_herramientas_por_bloque,
    obtener_herramientas_por_bloque_y_modo,
    obtener_modos_navegacion,
)
'''

OLD_NAVIGATION = '''bloques_internos = list(BLOQUES_HERRAMIENTAS)
menu_interno = ["__home__"] + bloques_internos
menu_labels = ["Home"] + [BLOQUE_UI.get(b, (strip_visual_prefix(b), "grid"))[0] for b in bloques_internos]
menu_icons = ["house"] + [BLOQUE_UI.get(b, (strip_visual_prefix(b), "grid"))[1] for b in bloques_internos]
seleccion_menu = render_option_menu_safe(menu_labels, menu_icons, key="vq_main_nav")
st.markdown("</div>", unsafe_allow_html=True)

seleccion_idx = menu_labels.index(seleccion_menu) if seleccion_menu in menu_labels else 0
if menu_interno[seleccion_idx] == "__home__":
    render_home_page()
    st.stop()

bloque_actual = menu_interno[seleccion_idx]
herramientas_bloque = obtener_herramientas_por_bloque(bloque_actual)
'''

NEW_NAVIGATION = '''modos_navegacion = obtener_modos_navegacion()
modo_labels = [modo["label"] for modo in modos_navegacion]
modo_keys = [modo["key"] for modo in modos_navegacion]
modo_default_idx = modo_keys.index("mvp") if "mvp" in modo_keys else 0

with st.sidebar:
    st.markdown("### Modo de producto")
    modo_label = st.radio(
        "Modo de navegación",
        modo_labels,
        index=modo_default_idx,
        key="vq_navigation_mode",
        label_visibility="collapsed",
        help="MVP muestra solo el producto principal. Consolidado agrupa herramientas por arquitectura objetivo. Completo muestra todo.",
    )

modo_navegacion = modo_keys[modo_labels.index(modo_label)] if modo_label in modo_labels else "mvp"
modo_meta = next((modo for modo in modos_navegacion if modo["key"] == modo_navegacion), modos_navegacion[0])

bloques_internos = list(obtener_bloques_por_modo(modo_navegacion))
if not bloques_internos:
    bloques_internos = list(BLOQUES_HERRAMIENTAS)

menu_interno = ["__home__"] + bloques_internos
menu_labels = ["Home"] + [BLOQUE_UI.get(b, (strip_visual_prefix(b), "grid"))[0] for b in bloques_internos]
menu_icons = ["house"] + [BLOQUE_UI.get(b, (strip_visual_prefix(b), "grid"))[1] for b in bloques_internos]
seleccion_menu = render_option_menu_safe(menu_labels, menu_icons, key=f"vq_main_nav_{modo_navegacion}")
st.markdown("</div>", unsafe_allow_html=True)

st.markdown(
    f"""
    <div class="vq-control-panel" style="padding:.75rem 1rem; margin-bottom:.85rem;">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
            <div>
                <div class="vq-context-eyebrow">Modo de navegación</div>
                <div style="color:#FFFFFF; font-weight:800;">{html.escape(str(modo_meta.get('label', 'MVP')))}</div>
                <div style="color:var(--vq-muted); font-size:.86rem; margin-top:.15rem;">{html.escape(str(modo_meta.get('caption', '')))}</div>
            </div>
            <span class="vq-badge vq-badge-success"><i class="bi bi-layers"></i> {html.escape(str(modo_meta.get('badge', 'Producto')))}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

seleccion_idx = menu_labels.index(seleccion_menu) if seleccion_menu in menu_labels else 0
if menu_interno[seleccion_idx] == "__home__":
    render_home_page()
    st.stop()

bloque_actual = menu_interno[seleccion_idx]
herramientas_bloque = obtener_herramientas_por_bloque_y_modo(bloque_actual, modo_navegacion)
'''


def main() -> None:
    if not APP_PATH.exists():
        raise FileNotFoundError(f"No se encuentra {APP_PATH}")

    text = APP_PATH.read_text(encoding="utf-8")
    original = text

    if "vq_navigation_mode" in text and "obtener_herramientas_por_bloque_y_modo" in text:
        print("Sprint 1G ya parece aplicado en app.py. No se realizan cambios.")
        return

    if OLD_IMPORT not in text:
        raise RuntimeError("No se encontró el bloque de import esperado de modulos.tool_catalog.")
    text = text.replace(OLD_IMPORT, NEW_IMPORT, 1)

    if OLD_NAVIGATION not in text:
        raise RuntimeError("No se encontró el bloque de navegación esperado. Revisa cambios manuales previos en app.py.")
    text = text.replace(OLD_NAVIGATION, NEW_NAVIGATION, 1)

    if text == original:
        raise RuntimeError("No hubo cambios. app.py no fue modificado.")

    BACKUP_PATH.write_text(original, encoding="utf-8")
    APP_PATH.write_text(text, encoding="utf-8")

    print("Sprint 1G aplicado correctamente.")
    print(f"Backup creado en: {BACKUP_PATH}")
    print("Siguiente paso: python -m py_compile app.py modulos/tool_catalog.py")


if __name__ == "__main__":
    main()
