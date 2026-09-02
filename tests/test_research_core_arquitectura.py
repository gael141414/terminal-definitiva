"""Arquitectura de navegación del Research Core.

Tenía nueve pestañas arriba y otras cinco anidadas dentro de "Tesis": catorce
destinos repartidos en dos niveles. Encontrar algo exigía recordar en cuál de
los dos vivía. Estas pruebas fijan la reorganización a cinco destinos en un
solo nivel y evitan que el amontonamiento vuelva por acumulación.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EMOJI = re.compile("[\U0001F000-\U0001FAFF←-⯿️]")


def _arbol(ruta: str) -> ast.Module:
    return ast.parse((PROJECT_ROOT / ruta).read_text(encoding="utf-8"))


def _llamadas_a_tabs(arbol: ast.Module) -> list[ast.Call]:
    return [
        n for n in ast.walk(arbol)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "tabs"
    ]


def _etiquetas(llamada: ast.Call) -> list[str]:
    if not llamada.args or not isinstance(llamada.args[0], (ast.List, ast.Tuple)):
        return []
    return [e.value for e in llamada.args[0].elts if isinstance(e, ast.Constant)]


def test_el_research_core_tiene_cinco_destinos():
    llamadas = _llamadas_a_tabs(_arbol("modulos/research_core.py"))
    assert len(llamadas) == 1, "debe haber un único juego de pestañas"

    etiquetas = _etiquetas(llamadas[0])
    assert etiquetas == ["Veredicto", "Valoración", "Finanzas", "Riesgo", "Proyección e informe"]


def test_las_pestañas_del_research_core_no_llevan_emoji():
    etiquetas = _etiquetas(_llamadas_a_tabs(_arbol("modulos/research_core.py"))[0])
    for e in etiquetas:
        assert not EMOJI.search(e), f"emoji en la pestaña «{e}»: la iconografía va aparte"


def test_la_tesis_ya_no_abre_pestañas_dentro_de_una_pestaña():
    """El anidamiento era la causa real de que la navegación no se entendiera."""
    assert not _llamadas_a_tabs(_arbol("modulos/investment_thesis.py")), (
        "investment_thesis vuelve a crear pestañas; sus secciones deben repartirse "
        "entre los destinos del Research Core"
    )


def test_cada_seccion_de_la_tesis_se_puede_colocar_por_separado():
    """Es lo que permite deshacer el anidamiento sin duplicar lógica."""
    from modulos import investment_thesis as it

    for nombre in (
        "render_tesis_veredicto",
        "render_tesis_valoracion",
        "render_tesis_entrada_salida",
        "render_tesis_riesgos",
        "render_tesis_exportar",
    ):
        assert callable(getattr(it, nombre, None)), f"falta {nombre}"


def test_la_tesis_se_construye_una_sola_vez_por_analisis():
    """Construirla por sección repetiría el cálculo cinco veces."""
    fuente = (PROJECT_ROOT / "modulos" / "research_core.py").read_text(encoding="utf-8")
    assert fuente.count("build_investment_thesis(") == 1


def test_ninguna_pestaña_del_terminal_lleva_emoji_en_su_etiqueta():
    """Guard general: el emoji dentro de la etiqueta es a la vez dato y adorno,
    y en este proyecto las etiquetas se usan además como claves."""
    ofensores = []
    for ruta in sorted((PROJECT_ROOT / "modulos").glob("*.py")):
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for llamada in _llamadas_a_tabs(arbol):
            for etiqueta in _etiquetas(llamada):
                if EMOJI.search(etiqueta):
                    ofensores.append(f"{ruta.name}:{llamada.lineno} «{etiqueta}»")

    assert not ofensores, f"pestañas con emoji: {ofensores}"
