"""Indicadores técnicos: validación contra casos analíticos conocidos.

Se comprueban contra series construidas a mano cuyo resultado se puede razonar
sin ejecutar el código. Un indicador mal calculado no falla: devuelve números
plausibles y contamina en silencio todas las señales que dependen de él.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.indicadores import (
    adx, atr, donchian, enriquecer_ohlcv, limpiar_velas_incompletas,
    rsi, sma, volumen_relativo,
)


def _ohlcv(n=300, precio=100.0, rango=2.0, volumen=1_000_000.0):
    return pd.DataFrame(
        {
            "Open": [precio] * n,
            "High": [precio + rango / 2] * n,
            "Low": [precio - rango / 2] * n,
            "Close": [precio] * n,
            "Volume": [volumen] * n,
        },
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )


# --- RSI ------------------------------------------------------------------


def test_rsi_satura_en_los_extremos():
    subida = pd.Series(np.arange(1, 80, dtype=float))
    bajada = pd.Series(np.arange(80, 1, -1, dtype=float))

    assert rsi(subida).iloc[-1] == 100.0
    assert rsi(bajada).iloc[-1] == 0.0


def test_rsi_siempre_dentro_de_rango():
    np.random.seed(7)
    serie = pd.Series(100 + np.random.randn(500).cumsum())
    valores = rsi(serie).dropna()

    assert valores.between(0, 100).all()


# --- ATR ------------------------------------------------------------------


def test_atr_converge_al_rango_real():
    """Con un rango diario constante de 2, el ATR debe converger a 2."""
    assert round(atr(_ohlcv(rango=2.0)).iloc[-1], 6) == 2.0


def test_atr_incluye_los_huecos_de_apertura():
    """El True Range debe capturar el salto contra el cierre previo.

    Es justo el riesgo que un stop por ATR tiene que cubrir: si sólo midiera
    máximo menos mínimo, un hueco de apertura quedaría fuera del cálculo.
    """
    df = _ohlcv(n=60)
    df.loc[df.index[-1], ["Open", "High", "Low", "Close"]] = [120.0, 121.0, 119.0, 120.0]

    from modulos.indicadores import _rango_verdadero

    tr = _rango_verdadero(df).iloc[-1]
    assert tr > 2.0  # 121 - 99 (cierre previo) = 22, no el rango intradía de 2


# --- ADX ------------------------------------------------------------------


def test_adx_es_bajo_sin_tendencia():
    assert adx(_ohlcv()).iloc[-1] < 5.0


def test_adx_es_alto_en_tendencia_limpia():
    n = 300
    precios = np.arange(100.0, 100.0 + n, dtype=float)
    df = pd.DataFrame(
        {"Open": precios, "High": precios + 1, "Low": precios - 1, "Close": precios,
         "Volume": [1e6] * n},
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )
    assert adx(df).iloc[-1] > 40.0


# --- Donchian -------------------------------------------------------------


def test_donchian_excluye_la_vela_actual():
    """Regresión: incluir la vela actual hace que el precio nunca pueda superar
    su propio máximo de N sesiones, y el escáner de rupturas no da señales."""
    df = pd.DataFrame(
        {"High": [10, 11, 12, 13, 50.0], "Low": [9] * 5, "Close": [10] * 5,
         "Open": [10] * 5, "Volume": [1] * 5}
    )
    canal = donchian(df, 4)

    assert canal["dc_superior"].iloc[-1] == 13.0  # no 50


# --- Volumen --------------------------------------------------------------


def test_volumen_relativo_es_uno_cuando_es_la_media():
    constante = pd.Series([100.0] * 40)
    assert round(volumen_relativo(constante, 20).iloc[-1], 6) == 1.0


# --- Velas incompletas ----------------------------------------------------


def test_descarta_la_vela_en_curso_sin_cierre():
    """Con el mercado abierto, yfinance añade la sesión actual con OHLC a NaN
    pero con volumen ya informado. Si llega a las estrategias, todas evalúan NaN
    y el escáner deja de encontrar señales sin dar ningún error."""
    df = _ohlcv(n=250)
    df.loc[df.index[-1], ["Open", "High", "Low", "Close"]] = [np.nan] * 4

    limpio = limpiar_velas_incompletas(df)
    assert len(limpio) == 249

    enriquecido = enriquecer_ohlcv(df)
    assert not pd.isna(enriquecido["rsi14"].iloc[-1])
    assert not pd.isna(enriquecido["atr_pct"].iloc[-1])


def test_enriquecer_devuelve_vacio_sin_columnas_requeridas():
    assert enriquecer_ohlcv(pd.DataFrame({"Close": [1, 2, 3]})).empty
    assert enriquecer_ohlcv(None).empty
    assert enriquecer_ohlcv(pd.DataFrame()).empty


def test_todos_los_indicadores_son_causales():
    """Ningún indicador puede cambiar su valor pasado al añadir datos nuevos.

    Es la propiedad de la que depende que el backtest no tenga look-ahead: si un
    indicador mirara al futuro, los resultados históricos serían ficción.
    """
    df = _ohlcv(n=400)
    np.random.seed(3)
    ruido = np.random.randn(400).cumsum()
    df["Close"] = 100 + ruido
    df["High"] = df["Close"] + 1
    df["Low"] = df["Close"] - 1

    completo = enriquecer_ohlcv(df)
    recortado = enriquecer_ohlcv(df.iloc[:-30])

    columnas = ["rsi14", "atr14", "adx14", "sma200", "dc_superior20", "vol_rel"]
    ultima = recortado.index[-1]
    for columna in columnas:
        a = completo.loc[ultima, columna]
        b = recortado.loc[ultima, columna]
        if pd.isna(a) and pd.isna(b):
            continue
        assert abs(float(a) - float(b)) < 1e-9, f"{columna} cambia al añadir datos futuros"
