"""El sistema visual: contraste legible y coherencia entre tema y gráficos.

Los colores "más vivos" no pueden costar legibilidad. Estas pruebas miden el
contraste real según WCAG 2.1 sobre la paleta de modulos/config.py, que es la
misma que consumen el CSS del tema y los gráficos de Plotly.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import config

# WCAG 2.1: 4.5:1 para texto normal, 3:1 para texto grande (>=24px o >=18.66px
# en negrita). Las cifras del terminal son grandes y en negrita, pero el texto
# corrido no, así que se exige el umbral estricto a todo lo que es texto.
AA_TEXTO = 4.5
AA_GRANDE = 3.0


def _luminancia(color_hex: str) -> float:
    canales = [int(color_hex[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lineal = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lineal[0] + 0.7152 * lineal[1] + 0.0722 * lineal[2]


def contraste(a: str, b: str) -> float:
    mayor, menor = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (mayor + 0.05) / (menor + 0.05)


# ==========================================================================
# CONTRASTE
# ==========================================================================


@pytest.mark.parametrize(
    "nombre,primer_plano",
    [
        ("texto primario", config.COLOR_TEXT),
        ("texto apagado", config.COLOR_TEXT_MUTED),
        ("azul de acento", config.COLOR_PRIMARY),
        ("cian de acento", config.COLOR_ACCENT),
        ("verde favorable", config.COLOR_POSITIVE),
        ("rojo de riesgo", config.COLOR_NEGATIVE),
        ("ámbar de aviso", config.COLOR_WARNING),
    ],
)
def test_todo_color_de_texto_es_legible_sobre_una_tarjeta(nombre, primer_plano):
    ratio = contraste(primer_plano, config.COLOR_SURFACE)
    assert ratio >= AA_TEXTO, f"{nombre}: {ratio:.2f}:1 sobre la tarjeta, por debajo de AA"


@pytest.mark.parametrize(
    "nombre,primer_plano",
    [("texto primario", config.COLOR_TEXT), ("texto apagado", config.COLOR_TEXT_MUTED)],
)
def test_el_texto_es_legible_tambien_sobre_el_fondo_de_la_pagina(nombre, primer_plano):
    ratio = contraste(primer_plano, config.COLOR_BG)
    assert ratio >= AA_TEXTO, f"{nombre}: {ratio:.2f}:1 sobre el fondo, por debajo de AA"


def test_la_tarjeta_se_asienta_sobre_el_fondo_y_lleva_borde():
    """En una interfaz oscura dos superficies vecinas nunca van a tener un
    contraste alto: 1.13:1 es lo normal y lo deseable. Lo que separa de verdad
    la tarjeta del fondo es el borde y la sombra, no la luminancia. Así que se
    exige lo que sí importa: que la tarjeta sea MÁS CLARA que el fondo (si no,
    se hunde) y que el sistema defina borde y sombra."""
    assert _luminancia(config.COLOR_SURFACE) > _luminancia(config.COLOR_BG)

    css = _css()
    assert "--vq-border:" in css
    assert "--vq-shadow-card:" in css
    assert "--vq-shadow-card: none" not in css, "sin sombra la interfaz se ve plana"


def test_favorable_y_riesgo_se_distinguen_sin_depender_del_color():
    """Verde y rojo son la señal más importante del terminal. Alrededor del 8%
    de los hombres no distingue bien esas dos tintas, así que no pueden
    diferenciarse solo por el tono: tienen que separarse también en
    luminancia, que es lo que sobrevive en escala de grises."""
    separacion = abs(_luminancia(config.COLOR_POSITIVE) - _luminancia(config.COLOR_NEGATIVE))
    assert separacion >= 0.15, (
        f"verde y rojo difieren solo {separacion:.3f} en luminancia: en escala "
        "de grises se verían casi iguales"
    )


# ==========================================================================
# COHERENCIA ENTRE EL TEMA Y LOS GRÁFICOS
# ==========================================================================


def _css() -> str:
    return (PROJECT_ROOT / "modulos" / "app_theme.py").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "token,valor",
    [
        ("--vq-bg", config.COLOR_BG),
        ("--vq-panel", config.COLOR_SURFACE),
        ("--vq-primary", config.COLOR_PRIMARY),
        ("--vq-cyan", config.COLOR_ACCENT),
        ("--vq-green", config.COLOR_POSITIVE),
        ("--vq-red", config.COLOR_NEGATIVE),
        ("--vq-amber", config.COLOR_WARNING),
    ],
)
def test_el_css_y_los_graficos_usan_el_mismo_color(token, valor):
    """Si el CSS y config.py divergen, una tarjeta y su gráfico se pintan de
    colores distintos para el mismo concepto. Ha pasado antes."""
    encontrado = re.search(rf"{re.escape(token)}:\s*([^;]+);", _css())
    assert encontrado, f"{token} no está definido en el tema"
    assert encontrado.group(1).strip().lower() == valor.lower()


def test_las_tres_familias_tipograficas_se_importan_de_verdad():
    """JetBrains Mono se usaba en todas las cifras sin importarse nunca: cada
    número caía al monoespaciado por defecto del navegador."""
    css = _css()
    importacion = re.search(r"@import url\('https://fonts\.googleapis[^']+'\);", css)
    assert importacion, "no hay importación de fuentes"

    for familia in ("Inter", "Space+Grotesk", "JetBrains+Mono"):
        assert familia in importacion.group(0), f"{familia} se usa pero no se importa"


def test_ninguna_familia_usada_en_el_css_queda_sin_importar():
    """Guard general: cualquier font-family declarada tiene que existir."""
    css = _css()
    importadas = set(re.findall(r"family=([A-Za-z+]+)", css))
    importadas = {f.replace("+", " ") for f in importadas}
    # Familias del sistema y genéricas que no requieren descarga.
    del_sistema = {
        "ui-sans-serif", "system-ui", "-apple-system", "BlinkMacSystemFont",
        "Segoe UI", "sans-serif", "ui-monospace", "SFMono-Regular", "Menlo",
        "monospace", "serif", "inherit", "var(--vq-font-titulo)",
        "var(--vq-font-texto)", "var(--vq-font-dato)",
    }
    usadas = set()
    for decl in re.findall(r"font-family:\s*([^;!]+)", css):
        for parte in decl.split(","):
            usadas.add(parte.strip().strip('"\''))

    faltan = {f for f in usadas if f and f not in del_sistema and f not in importadas}
    assert not faltan, f"familias usadas pero no importadas: {sorted(faltan)}"


# ==========================================================================
# MOVIMIENTO Y ACCESIBILIDAD
# ==========================================================================


def test_el_movimiento_respeta_la_preferencia_de_movimiento_reducido():
    """Cualquier animación tiene que poder desactivarse.

    Reducir movimiento no es quitar la respuesta: es sustituirla por una que no
    active el sistema vestibular. Hay personas a quienes el desplazamiento y el
    zoom les provocan mareo, y el sistema operativo ya expone esa preferencia.
    """
    css = _css()
    assert "@keyframes" in css, "no hay animaciones que comprobar"
    assert "prefers-reduced-motion: reduce" in css, (
        "hay animaciones sin bloque @media (prefers-reduced-motion: reduce)"
    )

    bloque = css.split("prefers-reduced-motion: reduce", 1)[1]
    for propiedad in ("animation-duration", "transition-duration"):
        assert propiedad in bloque, f"el bloque de movimiento reducido no neutraliza {propiedad}"


def test_la_pulsacion_responde_al_bajar_el_dedo_no_al_soltar():
    """:active se dispara al pulsar; :focus y el click, al soltar. En cuanto la
    reacción espera al release, la interfaz deja de sentirse directa."""
    css = _css()
    assert ".stButton > button:active" in css
    assert "transform: scale(" in css


def test_ninguna_animacion_se_repite_indefinidamente_salvo_las_de_espera():
    """Un bucle permanente en pantalla distrae y consume batería. Solo se
    admite en indicadores de carga, donde el bucle ES la información."""
    css = _css()
    infinitas = re.findall(r"animation:\s*([^;]*infinite[^;]*);", css)
    for decl in infinitas:
        assert any(p in decl for p in ("vq-barrido", "vq-ticker-scroll")), (
            f"animación infinita que no es un indicador de espera: {decl}"
        )


# ==========================================================================
# ERRORES QUE YA SE COMETIERON UNA VEZ
# ==========================================================================


def test_toda_clase_con_hover_existe_en_alguna_parte_de_la_aplicacion():
    """El CSS animaba .vq-group-card, que no la generaba nadie.

    El efecto simplemente no ocurría, y sin abrir el navegador no había forma de
    notarlo: el CSS era válido, la regla existía, y no fallaba ningún test.
    """
    css = _css()
    clases = set()
    for selector in re.findall(r"\.((?:vq-)[a-z0-9-]+):hover", css):
        clases.add(selector)
    assert clases, "no hay reglas :hover que comprobar"

    fuentes = "\n".join(
        ruta.read_text(encoding="utf-8")
        for ruta in PROJECT_ROOT.rglob("*.py")
        if ".venv" not in str(ruta) and "app_theme" not in ruta.name
    )
    huerfanas = [c for c in sorted(clases) if c not in fuentes]
    assert not huerfanas, (
        f"clases con :hover que ningún módulo genera: {huerfanas}. "
        "El efecto no ocurre y no lo detecta ningún test que no abra el navegador."
    )


def test_ninguna_animacion_congela_el_transform_de_un_elemento_con_hover():
    """fill-mode "both" deja fijado el fotograma final para siempre, y una
    animación CSS gana al :hover en la cascada. Eso dejó las tarjetas quietas
    aunque la regla de hover existiera y fuera correcta."""
    css = _css()
    bloques = re.findall(r"animation:\s*vq-entrada[^;]*;", css)
    assert bloques, "no se encontró la animación de entrada"
    for b in bloques:
        assert " both" not in b, (
            f"«{b.strip()}» usa fill-mode both: congelará el transform y "
            "anulará el hover. Usa backwards."
        )


def test_la_tarjeta_no_se_aplica_a_todo_contenedor_de_streamlit():
    """Streamlit envuelve TODA columna y contenedor en stVerticalBlockBorderWrapper.

    Estilarlos todos ponía un recuadro alrededor de cada columna y sumaba el
    padding en cada nivel, hasta partir el texto en una palabra por línea.
    """
    css = _css()
    for regla in re.findall(
        r'div\[data-testid="stVerticalBlockBorderWrapper"\][^{]*\{[^}]*\}', css
    ):
        cabecera = regla.split("{")[0]
        if "padding" in regla and "0" not in regla.split("padding")[1][:12]:
            assert ":has(" in cabecera, (
                "regla con padding que afecta a TODOS los contenedores: "
                f"{cabecera.strip()[:90]}"
            )


def test_el_terminal_ocupa_todo_el_ancho():
    """Un max-width fijo deja dos franjas muertas en cualquier monitor ancho."""
    css = _css()
    encontrado = re.search(r"\.block-container\s*\{[^}]*max-width:\s*([^;!]+)", css)
    assert encontrado, "no se define el ancho del contenedor principal"
    assert "100%" in encontrado.group(1), (
        f"el contenedor está limitado a {encontrado.group(1).strip()}"
    )
