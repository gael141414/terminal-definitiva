"""Congelado hacia delante de las decisiones y su lectura predictiva.

Sin red: la función de decisión se inyecta.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.congelado_forward import (
    INICIO_CONGELADO, RegistroCongelado, cargar_registros, congelar_universo,
    cruzar_con_retorno_posterior, guardar_registros, resumen_poder_predictivo,
)


class _DecisionFalsa:
    def __init__(self, ticker, accion="MANTENER", score=20.0, precio=100.0):
        self.ticker = ticker
        self.accion = accion
        self.sell_score = score
        self.sub_scores = {"valoracion": 30.0, "fundamentales": 10.0, "tecnico": score}
        self.precio_actual = precio


def _decidir(ticker, **kwargs):
    return _DecisionFalsa(ticker)


# ==========================================================================
# CONGELADO
# ==========================================================================


def test_congela_una_observacion_por_valor():
    registros = congelar_universo(["AAPL", "MSFT"], fecha="2026-09-06", decidir=_decidir)

    assert len(registros) == 2
    assert {r.ticker for r in registros} == {"AAPL", "MSFT"}
    assert all(r.fecha == "2026-09-06" for r in registros)
    assert all(r.origen == "forward" for r in registros)


def test_un_valor_que_falla_no_tumba_el_congelado():
    """El registro se compone de observaciones independientes: perder una no
    puede costar las demás."""
    def decidir(ticker, **kwargs):
        if ticker == "ROTO":
            raise RuntimeError("sin datos")
        return _DecisionFalsa(ticker)

    registros = congelar_universo(["AAPL", "ROTO", "MSFT"], fecha="2026-09-06", decidir=decidir)
    assert {r.ticker for r in registros} == {"AAPL", "MSFT"}


def test_se_guardan_los_tres_sub_scores_no_solo_el_total():
    """Sin los sub-scores no se puede medir qué pilar predice y cuál no, que es
    justo lo que este registro existe para averiguar."""
    r = congelar_universo(["AAPL"], fecha="2026-09-06", decidir=_decidir)[0]

    assert r.sub_valoracion == 30.0
    assert r.sub_fundamentales == 10.0
    assert r.sub_tecnico == 20.0


# ==========================================================================
# PERSISTENCIA
# ==========================================================================


def test_guardar_es_append_nunca_sobrescribe(tmp_path):
    fichero = tmp_path / "congelado.json"
    primero = congelar_universo(["AAPL"], fecha="2026-09-01", decidir=_decidir)
    segundo = congelar_universo(["AAPL"], fecha="2026-09-08", decidir=_decidir)

    assert guardar_registros(primero, path=fichero) == 1
    assert guardar_registros(segundo, path=fichero) == 1

    guardados = json.loads(fichero.read_text(encoding="utf-8"))
    assert len(guardados) == 2


def test_ejecutar_dos_veces_el_mismo_dia_no_duplica_la_muestra():
    """Duplicar observaciones estrecharía artificialmente cualquier intervalo
    de confianza posterior: parecería que hay el doble de evidencia."""
    import tempfile

    with tempfile.TemporaryDirectory() as carpeta:
        fichero = Path(carpeta) / "c.json"
        registros = congelar_universo(["AAPL", "MSFT"], fecha="2026-09-06", decidir=_decidir)

        assert guardar_registros(registros, path=fichero) == 2
        assert guardar_registros(registros, path=fichero) == 0

        assert len(json.loads(fichero.read_text(encoding="utf-8"))) == 2


def test_los_backfills_no_se_mezclan_con_el_registro_forward(tmp_path):
    """Mezclarlos destruiría la propiedad que hace valioso al forward: que
    nadie pueda acusarlo de conocer el futuro."""
    fichero = tmp_path / "c.json"
    fichero.write_text(json.dumps([
        {"ticker": "AAPL", "fecha": "2020-01-01", "origen": "backfill", "perfil": "largo_plazo"},
        {"ticker": "MSFT", "fecha": "2026-09-06", "origen": "forward", "perfil": "largo_plazo"},
    ]), encoding="utf-8")

    solo_forward = cargar_registros(path=fichero)
    assert [r["ticker"] for r in solo_forward] == ["MSFT"]
    assert len(cargar_registros(path=fichero, solo_forward=False)) == 2


def test_un_fichero_corrupto_no_rompe_la_lectura(tmp_path):
    fichero = tmp_path / "c.json"
    fichero.write_text("{esto no es json", encoding="utf-8")
    assert cargar_registros(path=fichero) == []


# ==========================================================================
# CRUCE CON EL RETORNO POSTERIOR
# ==========================================================================


def _precios(valor_inicial: float, valor_final: float, n: int = 200) -> pd.Series:
    return pd.Series(
        np.linspace(valor_inicial, valor_final, n),
        index=pd.date_range("2026-01-01", periods=n, freq="B"),
    )


def test_solo_se_cruzan_las_observaciones_cuyo_horizonte_ha_vencido():
    """Incluir las que aún no han madurado sesgaría la muestra hacia los
    movimientos rápidos, que son justo los más extremos."""
    registros = [
        {"ticker": "A", "fecha": "2026-01-05", "accion": "MANTENER", "sell_score": 20,
         "precio": 100.0, "sub_valoracion": 10, "sub_fundamentales": 20, "sub_tecnico": 30},
        {"ticker": "A", "fecha": "2026-09-01", "accion": "MANTENER", "sell_score": 20,
         "precio": 100.0, "sub_valoracion": 10, "sub_fundamentales": 20, "sub_tecnico": 30},
    ]
    cruce = cruzar_con_retorno_posterior(registros, {"A": _precios(100.0, 150.0)},
                                         horizonte_dias=63)

    assert len(cruce) == 1, "la observación reciente aún no ha vencido"
    assert cruce.iloc[0]["fecha"] == "2026-01-05"


def test_el_retorno_posterior_se_mide_desde_el_precio_congelado():
    registros = [{"ticker": "A", "fecha": "2026-01-05", "accion": "MANTENER",
                  "sell_score": 20, "precio": 100.0,
                  "sub_valoracion": 10, "sub_fundamentales": 20, "sub_tecnico": 30}]
    cruce = cruzar_con_retorno_posterior(registros, {"A": _precios(100.0, 200.0)},
                                         horizonte_dias=10)

    assert len(cruce) == 1
    assert cruce.iloc[0]["retorno_posterior"] > 0


def test_sin_precios_del_valor_no_se_cruza_nada():
    registros = [{"ticker": "Z", "fecha": "2026-01-05", "precio": 100.0}]
    assert cruzar_con_retorno_posterior(registros, {}).empty


# ==========================================================================
# PODER PREDICTIVO
# ==========================================================================


def test_con_muestra_insuficiente_no_se_publica_ningun_numero():
    """Es el estado esperado al principio, y decirlo es más útil que una
    correlación calculada sobre cuatro puntos."""
    cruce = pd.DataFrame({"sell_score": [10, 20], "retorno_posterior": [0.1, -0.1]})
    resumen = resumen_poder_predictivo(cruce)

    assert not resumen["suficiente"]
    assert resumen["observaciones"] == 2
    assert "insuficiente" in resumen["nota"].lower()


def test_un_score_que_predice_bien_da_correlacion_negativa():
    """Más score de venta debería ir con PEOR retorno posterior."""
    n = 80
    scores = np.linspace(0, 100, n)
    cruce = pd.DataFrame({
        "sell_score": scores,
        "sub_valoracion": scores,
        "sub_fundamentales": scores,
        "sub_tecnico": scores,
        "retorno_posterior": -scores / 500 + np.random.default_rng(3).normal(0, 0.01, n),
    })
    resumen = resumen_poder_predictivo(cruce)

    assert resumen["suficiente"]
    assert resumen["sell_score"]["spearman"] < -0.5
    assert resumen["sell_score"]["coherente"]


def test_un_score_que_predice_al_reves_se_marca_incoherente():
    n = 80
    scores = np.linspace(0, 100, n)
    cruce = pd.DataFrame({"sell_score": scores, "retorno_posterior": scores / 500})
    resumen = resumen_poder_predictivo(cruce)

    assert resumen["sell_score"]["spearman"] > 0
    assert not resumen["sell_score"]["coherente"], (
        "un score de venta que sube con el retorno posterior está invertido"
    )


def test_la_fecha_de_inicio_del_registro_esta_declarada():
    """Sin ella no se puede distinguir el registro forward de un backfill."""
    assert INICIO_CONGELADO
    pd.Timestamp(INICIO_CONGELADO)
