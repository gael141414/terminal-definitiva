"""Treemap del screener, score express y respaldo de fundamentales por yfinance."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import screener, yfinance_fundamentals
from modulos.config import (
    BUFFETT_SCORE_BAJO,
    BUFFETT_SCORE_MEDIO,
    COLOR_NEGATIVE,
    COLOR_POSITIVE,
    COLOR_WARNING,
    color_por_buffett_score,
)


# --------------------------------------------------------------------------
# Escala de color del score
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score, esperado",
    [
        (0, COLOR_NEGATIVE),
        (39.9, COLOR_NEGATIVE),
        (BUFFETT_SCORE_BAJO, COLOR_WARNING),
        (59.9, COLOR_WARNING),
        (BUFFETT_SCORE_MEDIO, COLOR_POSITIVE),
        (100, COLOR_POSITIVE),
    ],
)
def test_escala_de_color_por_tramos(score, esperado):
    assert color_por_buffett_score(score) == esperado


def test_color_tolera_valores_no_numericos():
    assert color_por_buffett_score(None) not in {COLOR_NEGATIVE, COLOR_WARNING, COLOR_POSITIVE}


# --------------------------------------------------------------------------
# Score express del screener
# --------------------------------------------------------------------------


def test_score_express_premia_calidad_y_castiga_apalancamiento():
    excelente = screener.buffett_score_express(
        {
            "grossMargins": 0.46, "profitMargins": 0.25, "returnOnEquity": 0.30,
            "returnOnAssets": 0.12, "debtToEquity": 50.0, "freeCashflow": 1e10,
        }
    )
    mala = screener.buffett_score_express(
        {
            "grossMargins": 0.10, "profitMargins": 0.02, "returnOnEquity": 0.03,
            "returnOnAssets": 0.01, "debtToEquity": 320.0, "freeCashflow": -5e8,
        }
    )

    assert excelente >= BUFFETT_SCORE_MEDIO
    assert mala < BUFFETT_SCORE_BAJO
    assert 0 <= mala < excelente <= 100


def test_score_express_no_rompe_con_info_incompleta():
    """Yahoo omite campos con frecuencia; eso no debe lanzar ni dar None."""
    assert screener.buffett_score_express({}) == 0.0
    assert screener.buffett_score_express({"grossMargins": None, "debtToEquity": float("nan")}) == 0.0


# --------------------------------------------------------------------------
# Treemap
# --------------------------------------------------------------------------


def _df_treemap():
    return pd.DataFrame(
        [
            {"Ticker": "AAA", "Sector": "Tech", "Market Cap": 3.0e12, "Buffett Score": 82.0, "PER": 30.0},
            {"Ticker": "BBB", "Sector": "Consumo", "Market Cap": 3.0e10, "Buffett Score": 35.0, "PER": 11.0},
        ]
    )


def test_treemap_usa_capitalizacion_como_tamano_y_score_como_color():
    fig = screener.construir_treemap(_df_treemap())

    assert fig is not None
    traza = fig.data[0]
    # El treemap es jerárquico (Mercado > Sector > empresa), así que values y
    # colors incluyen también los nodos agregados: se buscan las hojas por su
    # etiqueta en vez de asumir una posición.
    por_etiqueta = dict(zip(traza.labels, traza.values))
    hoja_aaa = next(k for k in por_etiqueta if str(k).startswith("AAA"))
    hoja_bbb = next(k for k in por_etiqueta if str(k).startswith("BBB"))

    assert por_etiqueta[hoja_aaa] == 3.0e12
    assert por_etiqueta[hoja_bbb] == 3.0e10

    colores = dict(zip(traza.labels, traza.marker.colors))
    assert colores[hoja_aaa] == 82.0
    assert colores[hoja_bbb] == 35.0


def test_treemap_etiqueta_el_ticker_para_no_depender_solo_del_color():
    """La identidad no puede ir sólo en el color: quien no distinga rojo de
    verde tiene que poder leer el ticker y el score dentro del bloque."""
    fig = screener.construir_treemap(_df_treemap())
    etiquetas = " ".join(str(v) for v in fig.data[0].labels)

    assert "AAA" in etiquetas and "BBB" in etiquetas
    assert "82" in etiquetas and "35" in etiquetas


def test_treemap_sin_capitalizacion_devuelve_none_en_vez_de_romper():
    df = _df_treemap()
    df["Market Cap"] = 0.0

    assert screener.construir_treemap(df) is None


# --------------------------------------------------------------------------
# Respaldo de fundamentales por yfinance
# --------------------------------------------------------------------------


def test_traduccion_a_esquema_fmp_reconocible_por_los_analyzers():
    """El respaldo tiene que hablar el mismo idioma de columnas que FMP: si no,
    financials/*.py cae a su rama "legacy" y calcula ratios distintos."""
    crudo = pd.DataFrame(
        {
            pd.Timestamp("2024-09-28"): [391035000000, 180683000000, 93736000000],
            pd.Timestamp("2023-09-30"): [383285000000, 169148000000, 96995000000],
        },
        index=["Total Revenue", "Gross Profit", "Net Income"],
    )

    df = yfinance_fundamentals._traducir(crudo, yfinance_fundamentals._INCOME_MAP)

    assert df is not None
    assert {"revenue", "grossProfit", "netIncome", "calendarYear"} <= set(df.columns)
    # Orden ascendente por fecha, como entrega FMP.
    assert list(df["calendarYear"]) == ["2023", "2024"]
    assert df["revenue"].iloc[-1] == 391035000000

    from financials.income_analyzer import _is_fmp_statement

    assert _is_fmp_statement(df)


def test_traduccion_sin_conceptos_conocidos_devuelve_none():
    crudo = pd.DataFrame(
        {pd.Timestamp("2024-09-28"): [1, 2]},
        index=["Concepto Inventado", "Otro Concepto"],
    )

    assert yfinance_fundamentals._traducir(crudo, yfinance_fundamentals._INCOME_MAP) is None
    assert yfinance_fundamentals._traducir(None, yfinance_fundamentals._INCOME_MAP) is None
    assert yfinance_fundamentals._traducir(pd.DataFrame(), yfinance_fundamentals._INCOME_MAP) is None


def test_mapa_income_cubre_lo_que_necesita_el_valuator():
    """Sin acciones ni EPS la serie de BPA queda vacía y valorar_empresa()
    devuelve None entero, dejando la ficha sin valoración."""
    campos = set(yfinance_fundamentals._INCOME_MAP)

    assert {"weightedAverageShsOutDil", "epsdiluted"} <= campos
