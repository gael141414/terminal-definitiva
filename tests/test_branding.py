"""Logotipo de la empresa analizada, con respaldo propio."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.branding import (
    PALETA_MONOGRAMA, color_de_ticker, html_logo, monograma_data_uri, url_logo,
)


def test_el_color_de_una_empresa_no_cambia_entre_ejecuciones():
    """Con hash() integrado el color cambiaría en cada reinicio del servidor,
    porque Python aleatoriza el hash por proceso. Por eso se usa sha256."""
    assert color_de_ticker("AAPL") == color_de_ticker("AAPL")
    assert color_de_ticker("aapl") == color_de_ticker("  AAPL ")
    assert color_de_ticker("AAPL") in PALETA_MONOGRAMA


def test_el_monograma_solo_usa_colores_del_sistema():
    """Una lista de empresas no puede parecer un semáforo averiado."""
    for t in ("AAPL", "MSFT", "NVDA", "KHC", "TSLA", "BRK-B", "XOM"):
        assert color_de_ticker(t) in PALETA_MONOGRAMA


def test_el_monograma_lleva_la_inicial_y_es_un_svg_valido():
    uri = monograma_data_uri("NVDA")
    assert uri.startswith("data:image/svg+xml;utf8,")

    svg = unquote(uri.split(",", 1)[1])
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert ">N<" in svg


def test_un_ticker_vacio_no_rompe_el_monograma():
    svg = unquote(monograma_data_uri("").split(",", 1)[1])
    assert ">?<" in svg


def test_la_url_del_logotipo_escapa_el_ticker():
    """Un ticker con caracteres raros no debe poder salirse de la ruta."""
    assert url_logo("BRK-B").endswith("/BRK-B.png")
    assert "/" not in url_logo("A/B").rsplit("/", 1)[1].replace(".png", "")


def test_el_img_lleva_respaldo_para_cuando_la_fuente_devuelva_404():
    """La fuente responde 404 en empresas que no tiene. Sin onerror quedaría el
    icono roto del navegador."""
    marca = html_logo("AAPL")
    assert 'src="https://financialmodelingprep.com/image-stock/AAPL.png"' in marca
    assert "onerror=" in marca
    assert "data:image/svg+xml" in marca
    assert "this.onerror=null" in marca, "sin esto, un fallo del respaldo entra en bucle"


def test_el_img_es_accesible_y_no_bloquea_el_pintado():
    marca = html_logo("MSFT")
    assert 'alt="Logotipo de MSFT"' in marca
    assert 'loading="lazy"' in marca
    assert 'width="44"' in marca and 'height="44"' in marca, "sin medidas, la página salta al cargar"


def test_sin_ticker_se_pinta_el_monograma_directamente_sin_pedir_red():
    marca = html_logo("")
    assert "financialmodelingprep" not in marca
    assert "data:image/svg+xml" in marca


def test_el_ticker_se_escapa_en_el_atributo_alt():
    marca = html_logo('X" onload="alert(1)')
    assert 'onload=' not in marca.split("onerror=")[0]
    assert "&quot;" in marca or "&#x27;" in marca
