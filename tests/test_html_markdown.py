"""HTML emitido por st.markdown: que Markdown no lo rompa y lo vuelque en crudo.

Streamlit no inyecta el HTML tal cual. Lo pasa por ``textwrap.dedent(...).strip()``
(streamlit/string_util.py) y después por su intérprete de Markdown. En CommonMark
una línea en blanco cierra el bloque HTML, y las líneas siguientes que queden
sangradas cuatro espacios o más se convierten en bloque de código: aparecen en
pantalla como texto literal.

Las plantillas del proyecto son f-strings sangradas que interpolan fragmentos
opcionales en su propia línea. Con el fragmento vacío quedaba una línea de solo
espacios que ``dedent`` normaliza a línea en blanco, y el ``</div>`` siguiente
—a cuatro espacios tras deshacer la sangría común— se pintaba en crudo. Es lo que
se veía en el Scorecard Ejecutivo.
"""

from __future__ import annotations

import ast
import sys
import textwrap
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.html_markdown import compactar_html

MD = MarkdownIt("commonmark")


def _fuga(bloque: str) -> bool:
    """True si Streamlit acabaría mostrando etiquetas como texto visible.

    Replica la tubería real: dedent + strip (string_util.clean_text) y CommonMark.
    """
    salida = MD.render(textwrap.dedent(str(bloque)).strip())
    return "&lt;" in salida


# Plantilla equivalente a la de render_kpi_card: sangrada, con dos huecos
# opcionales, cada uno en su propia línea.
PLANTILLA = """
        <div style="background:#121926; border:1px solid rgba(147,164,187,0.35);
                    border-radius:12px; padding:18px 20px;">
            <div style="display:flex;">
                <span style="font-size:11px;">ROE (Rentabilidad)</span>
                {tag}
            </div>
            <div style="display:flex; align-items:baseline;">
                <span style="font-size:30px;">171.4%</span>
                {delta}
            </div>
            <div style="font-size:11.5px; color:#5b6a80;">Retorno sobre patrimonio.</div>
        </div>
        """


# ==========================================================================
# LA CAUSA
# ==========================================================================


def test_un_hueco_vacio_vuelca_el_html_restante_como_texto():
    """El fallo del Scorecard: sin delta, la línea queda vacía y Markdown corta."""
    assert _fuga(PLANTILLA.format(tag="<span>TTM</span>", delta=""))


def test_con_los_dos_huecos_llenos_la_misma_plantilla_va_bien():
    """Aísla la variable: lo que rompe es el hueco vacío, no la plantilla."""
    assert not _fuga(PLANTILLA.format(tag="<span>TTM</span>", delta="<span>+2.1%</span>"))


def test_lo_que_se_filtra_es_exactamente_el_cierre_y_el_detalle():
    """Fija el síntoma concreto que reportó el usuario, no un genérico."""
    salida = MD.render(textwrap.dedent(PLANTILLA.format(tag="", delta="")).strip())
    assert "&lt;/div&gt;" in salida
    assert "font-size:11.5px" in salida.replace("&quot;", '"')


# ==========================================================================
# LA CORRECCIÓN
# ==========================================================================


@pytest.mark.parametrize("tag", ["", "<span>TTM</span>"])
@pytest.mark.parametrize("delta", ["", "<span>+2.1%</span>"])
def test_compactar_html_aguanta_cualquier_combinacion_de_huecos(tag, delta):
    assert not _fuga(compactar_html(PLANTILLA.format(tag=tag, delta=delta)))


def test_compactar_html_no_deja_saltos_de_linea():
    """Sin saltos de línea no puede haber línea en blanco ni sangría: la clase
    de fallo desaparece entera en vez de parchearse caso a caso."""
    assert "\n" not in compactar_html(PLANTILLA.format(tag="", delta=""))


def test_compactar_html_conserva_el_espacio_entre_atributos_partidos():
    """Las plantillas parten declaraciones CSS largas entre líneas; unirlas sin
    separador pegaría ``0.35);border-radius`` y perdería la regla."""
    assert "rgba(147,164,187,0.35); border-radius:12px" in compactar_html(
        PLANTILLA.format(tag="", delta="")
    )


def test_compactar_html_no_altera_el_texto_visible():
    salido = compactar_html(PLANTILLA.format(tag="", delta=""))
    for esperado in ("ROE (Rentabilidad)", "171.4%", "Retorno sobre patrimonio."):
        assert esperado in salido


# ==========================================================================
# LAS TARJETAS REALES DEL SCORECARD
# ==========================================================================


def _capturar(monkeypatch, modulo):
    capturado = []
    monkeypatch.setattr(modulo.st, "markdown", lambda t, **k: capturado.append(t))
    return capturado


def test_la_tarjeta_kpi_sin_delta_no_filtra_html(monkeypatch):
    """El caso exacto de la captura: cuatro tarjetas, ninguna con delta."""
    from modulos import ui_components

    capturado = _capturar(monkeypatch, ui_components)
    ui_components.render_kpi_card(
        "ROE (Rentabilidad)", "171.4%",
        detail="Retorno sobre patrimonio, último año.", tag="TTM",
    )

    assert len(capturado) == 1
    assert not _fuga(capturado[0])
    assert "171.4%" in capturado[0]


def test_la_tarjeta_kpi_sin_delta_ni_etiqueta_no_filtra_html(monkeypatch):
    """Los dos huecos vacíos a la vez: tag_html y delta_html."""
    from modulos import ui_components

    capturado = _capturar(monkeypatch, ui_components)
    ui_components.render_kpi_card("FCF Último Año", "$98.8B", status="favorable")

    assert not _fuga(capturado[0])


def test_la_tarjeta_kpi_sin_dato_no_filtra_html(monkeypatch):
    from modulos import ui_components

    capturado = _capturar(monkeypatch, ui_components)
    ui_components.render_kpi_card("ROIC (Calidad)", None)

    assert not _fuga(capturado[0])
    assert "n/d" in capturado[0]


@pytest.mark.parametrize("herramientas", [0, 2, 5])
def test_la_tarjeta_de_grupo_no_filtra_html(monkeypatch, herramientas):
    """items_html vacío (grupo sin herramientas) es el mismo fallo en la rejilla."""
    from modulos import ui_components

    monkeypatch.setattr(
        ui_components, "obtener_herramientas_por_grupo_consolidado",
        lambda _clave: [{"label": f"Herramienta {i}"} for i in range(herramientas)],
    )
    capturado = _capturar(monkeypatch, ui_components)
    ui_components.render_navigation_group_card("research_core", index=1)

    assert capturado, "la tarjeta no llegó a pintarse"
    assert not _fuga(capturado[0])


def test_la_tarjeta_de_grupo_oculto_no_filtra_html(monkeypatch):
    """La variante punteada (utilities_postmvp) usa otra plantilla."""
    from modulos import ui_components

    monkeypatch.setattr(
        ui_components, "obtener_herramientas_por_grupo_consolidado", lambda _c: [],
    )
    capturado = _capturar(monkeypatch, ui_components)
    ui_components.render_navigation_group_card("utilities_postmvp")

    assert capturado and not _fuga(capturado[0])


# ==========================================================================
# LA RED PARA QUE NO VUELVA
# ==========================================================================


def test_ningun_bloque_html_de_la_app_puede_romperse():
    """Barrido estático de todo el proyecto: ninguna llamada a st.markdown con
    HTML multilínea puede tener una línea en blanco o un hueco a solas."""

    def literales(nodo):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            yield nodo.value
        elif isinstance(nodo, ast.JoinedStr):
            yield "".join(str(v.value) if isinstance(v, ast.Constant) else "\x00"
                          for v in nodo.values)
        elif isinstance(nodo, ast.BinOp):
            for lado in (nodo.left, nodo.right):
                yield from literales(lado)

    ofensores = []
    for ruta in sorted(PROJECT_ROOT.rglob("*.py")):
        if ".venv" in str(ruta) or "/tests/" in str(ruta):
            continue
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(arbol):
            if not isinstance(n, ast.Call) or getattr(n.func, "attr", None) != "markdown":
                continue
            if not any(k.arg == "unsafe_allow_html" for k in n.keywords) or not n.args:
                continue
            for txt in literales(n.args[0]):
                lineas = txt.splitlines()
                # <style> es bloque HTML de tipo 1: sólo lo cierra </style>, así
                # que las líneas en blanco del CSS son inofensivas.
                if len(lineas) < 3 or "<style" in txt:
                    continue
                if any(l.strip() in ("", "\x00") for l in lineas[1:-1]):
                    ofensores.append(f"{ruta.relative_to(PROJECT_ROOT)}:{n.lineno}")

    assert not ofensores, (
        "Bloques HTML que Markdown puede romper; pásalos por "
        f"modulos.html_markdown.escribir_html: {ofensores}"
    )

def test_ninguna_llamada_abre_un_div_que_cierra_otra_llamada():
    """Un <div> abierto en una llamada y cerrado en otra no envuelve nada.

    Streamlit pinta cada elemento en su propio contenedor hermano, así que el
    navegador autocierra el <div> al final del primero: la tarjeta sale VACÍA y
    los widgets que debía envolver quedan fuera, pegados al margen y sin su
    padding. Era la causa del recuadro vacío del hero de Research Core y del
    texto que se salía de su caja.

    Para envolver widgets hay que usar un contenedor real (``st.container``) y
    estilarlo por CSS, no HTML suelto.
    """

    def literales(nodo):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            yield nodo.value
        elif isinstance(nodo, ast.JoinedStr):
            yield "".join(str(v.value) if isinstance(v, ast.Constant) else ""
                          for v in nodo.values)
        elif isinstance(nodo, ast.BinOp):
            for lado in (nodo.left, nodo.right):
                yield from literales(lado)

    import re

    ofensores = []
    for ruta in sorted(PROJECT_ROOT.rglob("*.py")):
        if ".venv" in str(ruta) or "/tests/" in str(ruta) or "/scripts/" in str(ruta):
            continue
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(arbol):
            if not isinstance(n, ast.Call) or not n.args:
                continue
            nombre = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
            if nombre not in ("markdown", "escribir_html"):
                continue
            if nombre == "markdown" and not any(
                k.arg == "unsafe_allow_html" for k in n.keywords
            ):
                continue
            for txt in literales(n.args[0]):
                # Los bloques <style> son CSS: cualquier "<div>" ahí es prosa de
                # un comentario o un selector, no una etiqueta abierta.
                if "<style" in txt:
                    continue
                abre = len(re.findall(r"<div\b", txt))
                cierra = len(re.findall(r"</div>", txt))
                if abre != cierra:
                    ofensores.append(
                        f"{ruta.relative_to(PROJECT_ROOT)}:{n.lineno} "
                        f"(<div>={abre}, </div>={cierra})"
                    )

    assert not ofensores, (
        "HTML con <div> descompensados: no envolverá a los widgets siguientes. "
        f"Usa st.container() y estílalo por CSS: {ofensores}"
    )
