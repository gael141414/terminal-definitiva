"""Embudo de la watchlist: estados, posiciones abiertas y alertas técnicas."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.watchlist_estados import (
    ARCHIVADA, EN_CARTERA, ESPERANDO_PRECIO, INVESTIGANDO, LISTA_PARA_COMPRAR,
    evaluar_alertas_tecnicas, evaluar_posicion, inferir_estado, normalizar_estado,
    ordenar_por_embudo, resumen_embudo,
)


# --- Estados --------------------------------------------------------------


def test_las_fichas_antiguas_conservan_su_sentido():
    """Retrocompatibilidad: las fichas guardadas antes de existir los estados no
    deben caer todas en el mismo cajón, sino inferirse por lo que ya contienen."""
    assert inferir_estado({"posicion": {"acciones": 10}}) == EN_CARTERA
    assert inferir_estado({"target": 150.0}) == ESPERANDO_PRECIO
    assert inferir_estado({}) == INVESTIGANDO


def test_estado_desconocido_degrada_a_investigando():
    assert normalizar_estado("fase_inventada") == INVESTIGANDO
    assert normalizar_estado(None) == INVESTIGANDO
    assert normalizar_estado(EN_CARTERA) == EN_CARTERA


def test_el_orden_prioriza_lo_que_exige_decision():
    """Lo que ya está en cartera exige atención antes que una idea sin analizar."""
    items = [
        ("IDEA", {"estado": INVESTIGANDO}),
        ("VIEJA", {"estado": ARCHIVADA}),
        ("ABIERTA", {"estado": EN_CARTERA}),
        ("LISTA", {"estado": LISTA_PARA_COMPRAR}),
    ]
    assert [t for t, _ in ordenar_por_embudo(items)] == ["ABIERTA", "LISTA", "IDEA", "VIEJA"]


def test_resumen_cuenta_todas_las_fases():
    db = {"A": {"estado": EN_CARTERA}, "B": {"estado": EN_CARTERA}, "C": {"target": 10}}
    conteo = resumen_embudo(db)

    assert conteo[EN_CARTERA] == 2
    assert conteo[ESPERANDO_PRECIO] == 1


# --- Posiciones -----------------------------------------------------------


def test_calcula_resultado_en_euros_y_en_r():
    resultado = evaluar_posicion({"acciones": 100, "entrada": 100.0, "stop": 90.0}, 120.0)

    assert resultado.pnl_euros == 2000.0
    assert resultado.pnl_pct == 20.0
    assert resultado.resultado_r == 2.0  # 20 de ganancia sobre 10 de riesgo
    assert not resultado.stop_roto


def test_detecta_el_stop_roto():
    resultado = evaluar_posicion({"acciones": 100, "entrada": 100.0, "stop": 90.0}, 88.0)

    assert resultado.stop_roto
    assert resultado.resultado_r < -1.0


def test_sin_stop_no_se_inventa_una_referencia_de_riesgo():
    """El resultado en R no existe si no se declaró cuánto se arriesgaba."""
    resultado = evaluar_posicion({"acciones": 10, "entrada": 100.0}, 110.0)

    assert resultado.pnl_euros == 100.0
    assert resultado.resultado_r is None


def test_posiciones_no_validas_devuelven_none():
    assert evaluar_posicion({}, 100.0) is None
    assert evaluar_posicion({"acciones": 0, "entrada": 100.0}, 100.0) is None
    assert evaluar_posicion({"acciones": 10, "entrada": 100.0}, 0.0) is None
    assert evaluar_posicion({"acciones": "diez", "entrada": "cien"}, 100.0) is None


# --- Alertas técnicas -----------------------------------------------------


def _serie(n=300, tendencia=0.0, base=100.0, semilla=1):
    np.random.seed(semilla)
    precios = np.maximum(base + np.arange(n) * tendencia + np.random.randn(n).cumsum() * 0.4, 1.0)
    return pd.DataFrame(
        {"Open": precios, "High": precios * 1.01, "Low": precios * 0.99,
         "Close": precios, "Volume": [1e6] * n},
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )


def test_sin_alertas_configuradas_no_se_evalua_nada():
    assert evaluar_alertas_tecnicas(_serie(), []) == []
    assert evaluar_alertas_tecnicas(_serie(), None) == []


def test_alerta_de_volumen_inusual_se_dispara():
    df = _serie()
    df.loc[df.index[-1], "Volume"] = 5e6  # 5x la media

    disparadas = evaluar_alertas_tecnicas(df, ["volumen_inusual"])
    assert [a["id"] for a in disparadas] == ["volumen_inusual"]


def test_alerta_de_sobreventa_solo_en_caida():
    tranquilo = evaluar_alertas_tecnicas(_serie(tendencia=0.1), ["sobreventa"])
    assert tranquilo == []


def test_datos_insuficientes_no_rompen_la_evaluacion():
    assert evaluar_alertas_tecnicas(pd.DataFrame(), ["sobreventa"]) == []
    assert evaluar_alertas_tecnicas(None, ["sobreventa"]) == []
    assert evaluar_alertas_tecnicas(_serie(n=5), ["sobreventa"]) == []


def test_id_de_alerta_inexistente_se_ignora():
    assert evaluar_alertas_tecnicas(_serie(), ["alerta_que_no_existe"]) == []
