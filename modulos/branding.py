"""Identidad visual de las empresas analizadas: logotipo con respaldo propio.

El logotipo se pide directamente al navegador en vez de descargarlo en el
servidor. Así la página no espera a ninguna petición de red para pintarse y el
terminal no gasta cuota en imágenes decorativas.

Cuando la fuente no tiene esa empresa devuelve 404, y entonces entra el
monograma: la inicial del ticker sobre un color derivado de forma determinista
del propio ticker. Nunca queda el icono roto del navegador, y la misma empresa
tiene siempre el mismo color, que es lo que permite reconocerla de un vistazo en
una lista.
"""

from __future__ import annotations

import hashlib
import html
from urllib.parse import quote

__all__ = ["url_logo", "monograma_data_uri", "color_de_ticker", "html_logo"]

FUENTE_LOGOS = "https://financialmodelingprep.com/image-stock/{ticker}.png"

# Paleta del sistema. El monograma no inventa colores: reutiliza los del tema
# para que una lista de empresas no parezca un semáforo averiado.
PALETA_MONOGRAMA = (
    "#3b82f6",  # azul
    "#22d3ee",  # cian
    "#10e39a",  # verde
    "#fbbf24",  # ámbar
    "#a78bfa",  # violeta
    "#fb5e6d",  # rojo
)


def _normalizar(ticker: str) -> str:
    return (ticker or "").strip().upper()


def color_de_ticker(ticker: str) -> str:
    """Color estable para un ticker.

    Determinista a propósito: se usa hashlib y no hash(), porque el hash
    integrado de Python está aleatorizado por proceso y el color de una misma
    empresa cambiaría en cada reinicio del servidor.
    """
    limpio = _normalizar(ticker)
    if not limpio:
        return PALETA_MONOGRAMA[0]
    digest = hashlib.sha256(limpio.encode("utf-8")).digest()
    return PALETA_MONOGRAMA[digest[0] % len(PALETA_MONOGRAMA)]


def url_logo(ticker: str) -> str:
    """URL del logotipo. Puede devolver 404: el respaldo lo cubre en el cliente."""
    return FUENTE_LOGOS.format(ticker=quote(_normalizar(ticker), safe=""))


def monograma_data_uri(ticker: str, tamano: int = 44) -> str:
    """SVG embebido con la inicial del ticker. Sin red y sin dependencias."""
    limpio = _normalizar(ticker)
    inicial = limpio[0] if limpio else "?"
    color = color_de_ticker(limpio)
    radio = round(tamano * 0.24, 2)
    fuente = round(tamano * 0.44, 2)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tamano}" height="{tamano}" '
        f'viewBox="0 0 {tamano} {tamano}" role="img" aria-label="{html.escape(limpio or "sin ticker")}">'
        f'<rect width="{tamano}" height="{tamano}" rx="{radio}" fill="{color}" fill-opacity="0.16"/>'
        f'<rect width="{tamano}" height="{tamano}" rx="{radio}" fill="none" '
        f'stroke="{color}" stroke-opacity="0.42"/>'
        f'<text x="50%" y="50%" dy="0.35em" text-anchor="middle" fill="{color}" '
        f'font-family="JetBrains Mono, ui-monospace, monospace" font-size="{fuente}" '
        f'font-weight="700">{html.escape(inicial)}</text>'
        f"</svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg, safe="")


def html_logo(ticker: str, tamano: int = 44, clase: str = "vq-logo-empresa") -> str:
    """<img> del logotipo con el monograma como respaldo en el propio cliente.

    El respaldo va en onerror y no en una comprobación previa en el servidor:
    así la página se pinta sin esperar a ninguna red, y si la imagen falla el
    cambio ocurre sin que el usuario vea un hueco roto.
    """
    limpio = _normalizar(ticker)
    respaldo = monograma_data_uri(limpio, tamano)
    if not limpio:
        return (
            f'<img class="{html.escape(clase)}" src="{respaldo}" alt="" '
            f'width="{tamano}" height="{tamano}" loading="lazy">'
        )

    return (
        f'<img class="{html.escape(clase)}" src="{html.escape(url_logo(limpio))}" '
        f'alt="Logotipo de {html.escape(limpio)}" width="{tamano}" height="{tamano}" '
        f'loading="lazy" onerror="this.onerror=null;this.src=\'{respaldo}\';">'
    )
