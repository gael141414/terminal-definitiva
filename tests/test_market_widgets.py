"""Widgets de mercado de la Home: el mapa de calor y la rotación sectorial.

El mapa de calor estuvo permanentemente vacío ("No hay datos suficientes para
construir el mapa de calor") porque se pedía la capitalización con una clave que
yfinance no expone en ``.get()``. No lanzaba ningún error: devolvía None para
todos los tickers y el DataFrame salía vacío. El contrato que debía cubrirlo
simulaba ``fast_info`` con la clave equivocada, así que daba el fallo por bueno.

Estas pruebas usan la forma REAL de yfinance 1.7: ``.get()`` responde en
camelCase (``marketCap``) y el acceso por atributo en snake_case.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import market_widgets as mw


class FastInfoRealista:
    """Imita a yfinance.FastInfo: get() en camelCase, atributo en snake_case."""

    def __init__(self, market_cap: float):
        self._datos = {"marketCap": market_cap, "lastPrice": 100.0}

    def get(self, clave, defecto=None):
        return self._datos.get(clave, defecto)

    def keys(self):
        return self._datos.keys()

    def __getattr__(self, nombre):
        if nombre == "market_cap":
            return self._datos["marketCap"]
        raise AttributeError(nombre)


class TickerFalso:
    def __init__(self, _simbolo, fast_info):
        self.fast_info = fast_info

    @property
    def info(self):
        raise AssertionError("No debe tocar .info: dispara quoteSummary y se rate-limita")


def _historico():
    return pd.DataFrame({"Close": [100.0, 102.0, 104.0, 103.0, 105.0]})


def _preparar(monkeypatch, fast_info):
    monkeypatch.setattr(mw, "_safe_yahoo_history", lambda *a, **k: _historico())
    monkeypatch.setattr(mw.yf, "Ticker", lambda s: TickerFalso(s, fast_info))
    mw.obtener_market_treemap_data.clear()


# ==========================================================================
# LA CAPITALIZACIÓN
# ==========================================================================


def test_lee_la_capitalizacion_de_un_fast_info_como_el_real(monkeypatch):
    """El caso que fallaba: .get('market_cap') devuelve None en yfinance real."""
    monkeypatch.setattr(mw.yf, "Ticker", lambda s: TickerFalso(s, FastInfoRealista(3e12)))

    assert mw._safe_fast_market_cap(mw.yf.Ticker("AAPL")) == 3e12


def test_sigue_leyendo_un_fast_info_antiguo_en_snake_case(monkeypatch):
    """Compatibilidad hacia atrás: versiones viejas exponían snake_case."""
    assert mw._safe_fast_market_cap(TickerFalso("X", {"market_cap": 2e12})) == 2e12


def test_una_capitalizacion_ausente_o_absurda_no_pasa_el_filtro():
    assert mw._safe_fast_market_cap(TickerFalso("X", {})) is None
    assert mw._safe_fast_market_cap(TickerFalso("X", {"marketCap": 0})) is None
    assert mw._safe_fast_market_cap(TickerFalso("X", {"marketCap": float("nan")})) is None
    assert mw._safe_fast_market_cap(TickerFalso("X", {"marketCap": -5})) is None


# ==========================================================================
# EL MAPA DE CALOR
# ==========================================================================


def test_el_mapa_de_calor_construye_filas_con_un_fast_info_real(monkeypatch):
    """La prueba que faltaba: con la forma real de yfinance, hay datos.

    Antes salía vacío para todos los tickers y la Home mostraba siempre
    "No hay datos suficientes para construir el mapa de calor".
    """
    _preparar(monkeypatch, FastInfoRealista(3e12))
    df = mw.obtener_market_treemap_data()

    assert not df.empty, "el mapa de calor volvió a quedarse sin datos"
    assert list(df.columns) == ["Ticker", "Sector", "MarketCap", "Rendimiento_Diario"]
    assert (df["MarketCap"] > 0).all()
    assert len(df) >= 10, "debería cubrir la mayor parte del universo definido"


def test_el_rendimiento_diario_compara_el_ultimo_cierre_con_el_anterior(monkeypatch):
    _preparar(monkeypatch, FastInfoRealista(1e12))
    df = mw.obtener_market_treemap_data()

    # _historico(): 103.0 -> 105.0 = +1.94%
    esperado = ((105.0 - 103.0) / 103.0) * 100
    assert df["Rendimiento_Diario"].round(4).eq(round(esperado, 4)).all()


def test_sin_capitalizacion_el_mapa_queda_vacio_pero_no_revienta(monkeypatch):
    """Degradar limpiamente sigue siendo el comportamiento correcto."""
    _preparar(monkeypatch, {})
    df = mw.obtener_market_treemap_data()

    assert df.empty
    assert list(df.columns) == ["Ticker", "Sector", "MarketCap", "Rendimiento_Diario"]


def test_un_historico_de_una_sola_sesion_no_produce_rendimiento(monkeypatch):
    monkeypatch.setattr(mw, "_safe_yahoo_history", lambda *a, **k: pd.DataFrame({"Close": [100.0]}))
    monkeypatch.setattr(mw.yf, "Ticker", lambda s: TickerFalso(s, FastInfoRealista(1e12)))
    mw.obtener_market_treemap_data.clear()

    assert mw.obtener_market_treemap_data().empty


# ==========================================================================
# ROTACIÓN SECTORIAL
# ==========================================================================


def test_los_nombres_de_sector_no_llevan_emoji_incrustado():
    """El emoji es presentación; si viaja dentro del dato acaba en el eje del
    gráfico, en el CSV exportado y en cualquier comparación de cadenas."""
    import inspect

    fuente = inspect.getsource(mw.analizar_rotacion_sectores)
    emojis = [c for c in fuente if ord(c) > 0x2100]
    assert not emojis, f"emoji dentro de los nombres de sector: {emojis}"
