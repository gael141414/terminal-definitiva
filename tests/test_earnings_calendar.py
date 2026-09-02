"""Calendario de resultados: orden, ventana de alerta y estilo de la tabla.

Todo hermético: ``obtener_earnings_ticker`` se sustituye por datos fijos para no
depender de Yahoo ni de la fecha real de ejecución.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import earnings_calendar as ec

HOY = dt.date(2026, 3, 10)


@pytest.fixture
def sin_red(monkeypatch):
    """Datos deterministas por ticker, sin llamadas de red."""
    catalogo = {
        "AAA": dt.date(2026, 3, 12),   # dentro de la ventana de 7 dias
        "BBB": dt.date(2026, 4, 20),   # lejos
        "CCC": None,                   # sin fecha publicada (p. ej. un ETF)
        "DDD": dt.date(2026, 3, 1),    # ya reportado
    }

    def falso(ticker):
        return {
            "ticker": ticker,
            "nombre": f"{ticker} Inc.",
            "fecha": catalogo.get(ticker),
            "eps_estimado": 1.5,
            "eps_anterior": 1.4,
            "sorpresa_media_pct": 7.1,
            "estado": "ok",
        }

    monkeypatch.setattr(ec, "obtener_earnings_ticker", falso)


def test_tabla_ordena_por_proximidad_y_deja_los_sin_fecha_al_final(sin_red):
    df = ec.construir_tabla_earnings(["CCC", "BBB", "DDD", "AAA"], hoy=HOY)

    assert list(df["Ticker"]) == ["AAA", "BBB", "DDD", "CCC"]


def test_marca_inminente_solo_dentro_de_la_ventana(sin_red):
    df = ec.construir_tabla_earnings(["AAA", "BBB", "CCC", "DDD"], hoy=HOY)
    inminentes = set(df.loc[df["Inminente"], "Ticker"])

    # DDD ya reportó (días negativos) y no debe considerarse inminente.
    assert inminentes == {"AAA"}


def test_ticker_sin_fecha_no_rompe_y_queda_con_dias_nulos(sin_red):
    df = ec.construir_tabla_earnings(["CCC"], hoy=HOY)

    assert len(df) == 1
    assert df.loc[0, "Días"] is None
    assert pd.isna(df.loc[0, "Fecha earnings"]) or df.loc[0, "Fecha earnings"] is None


def test_estilo_devuelve_una_entrada_por_columna_visible():
    """Regresión: el styler recibía la fila con la columna auxiliar "Inminente"
    y devolvía un elemento de más, lo que hacía que pandas rechazara la tabla
    entera con "created invalid columns labels"."""
    fila_visible = pd.Series({"Ticker": "AAA", "Nombre": "AAA Inc.", "Fecha earnings": "12/03/2026"})

    assert len(ec._estilo_fila(fila_visible, True)) == len(fila_visible)
    assert len(ec._estilo_fila(fila_visible, False)) == len(fila_visible)
    assert all(estilo for estilo in ec._estilo_fila(fila_visible, True))
    assert not any(ec._estilo_fila(fila_visible, False))


def test_primera_fecha_normaliza_lista_datetime_y_texto():
    assert ec._primera_fecha([dt.date(2026, 5, 2), dt.date(2026, 4, 1)]) == dt.date(2026, 4, 1)
    assert ec._primera_fecha(dt.datetime(2026, 4, 1, 16, 0)) == dt.date(2026, 4, 1)
    assert ec._primera_fecha("2026-04-01") == dt.date(2026, 4, 1)
    assert ec._primera_fecha(None) is None
    assert ec._primera_fecha("no es una fecha") is None
