"""Múltiplos situados en el percentil de su propia historia.

Un PER 28 no dice nada por sí solo: es caro para una eléctrica y barato para un
software. Lo que informa es dónde cae dentro del rango en el que esa MISMA
empresa ha cotizado.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.multiplos_historicos import (
    MINIMO_EJERCICIOS, RETARDO_PUBLICACION_DIAS, evaluar_multiplos,
    percentil_en_su_historia, serie_multiplos,
)

EJERCICIOS = [f"{a}-12-31" for a in range(2024, 2016, -1)]   # 8 años, reciente primero


def _precios(valor_por_anio: dict[int, float]) -> pd.Series:
    fechas = pd.date_range("2016-01-01", "2025-12-31", freq="B")
    valores = [valor_por_anio.get(f.year, 100.0) for f in fechas]
    return pd.Series(valores, index=fechas)


def _tabla(filas: dict[str, list]) -> pd.DataFrame:
    return pd.DataFrame(filas, index=EJERCICIOS).T


def _cuentas(beneficio=100.0, acciones=1000.0):
    resultados = _tabla({
        "Net Income": [beneficio] * 8,
        "EBIT": [140.0] * 8,
    })
    balance = _tabla({
        "Ordinary Shares Number": [acciones] * 8,
        "Total Debt": [200.0] * 8,
        "Cash And Cash Equivalents": [50.0] * 8,
    })
    flujos = _tabla({
        "Operating Cash Flow": [130.0] * 8,
        "Capital Expenditure": [-30.0] * 8,
        "Depreciation And Amortization": [40.0] * 8,
    })
    return resultados, balance, flujos


# ==========================================================================
# LA SERIE
# ==========================================================================


def test_construye_la_serie_de_los_tres_multiplos():
    resultados, balance, flujos = _cuentas()
    tabla = serie_multiplos(_precios({}), resultados, balance, flujos)

    assert not tabla.empty
    for columna in ("PER", "P/FCF", "EV/EBITDA"):
        assert columna in tabla.columns


def test_el_per_se_calcula_sobre_el_beneficio_por_accion():
    resultados, balance, flujos = _cuentas(beneficio=100.0, acciones=1000.0)
    tabla = serie_multiplos(_precios({}), resultados, balance, flujos)

    # BPA = 100/1000 = 0,1 · precio 100 -> PER 1000
    assert tabla["PER"].dropna().iloc[0] == pytest.approx(1000.0, rel=1e-6)


def test_un_beneficio_negativo_no_produce_un_per_negativo():
    """Un PER negativo no es «muy barato»: es que no hay beneficio. Se omite."""
    resultados, balance, flujos = _cuentas(beneficio=-100.0)
    tabla = serie_multiplos(_precios({}), resultados, balance, flujos)

    assert tabla["PER"].isna().all()


def test_el_precio_se_toma_tras_el_retardo_de_publicacion():
    """Las cuentas del 31 de diciembre no son públicas ese día.

    Emparejarlas con el precio de esa misma fecha construiría una serie que
    nadie pudo observar, y contaminaría el percentil con información futura.
    """
    resultados, balance, flujos = _cuentas()
    # El precio cambia el 1 de enero: si se usara el cierre contable se leería
    # el precio del año viejo; con retardo, el del año siguiente.
    precios = _precios({2019: 50.0, 2020: 500.0})

    tabla = serie_multiplos(precios, resultados, balance, flujos, retardo_dias=RETARDO_PUBLICACION_DIAS)
    precio_2019 = tabla.loc["2019-12-31", "precio"]

    assert precio_2019 == pytest.approx(500.0), (
        "el ejercicio 2019 debe emparejarse con el precio vigente cuando se publicó, ya en 2020"
    )


def test_sin_precios_no_hay_serie():
    resultados, balance, flujos = _cuentas()
    assert serie_multiplos(pd.Series(dtype=float), resultados, balance, flujos).empty


def test_sin_beneficio_en_las_cuentas_no_hay_serie():
    vacio = pd.DataFrame()
    assert serie_multiplos(_precios({}), vacio, vacio, vacio).empty


# ==========================================================================
# EL PERCENTIL
# ==========================================================================


def test_el_percentil_mide_cuanta_historia_queda_por_debajo():
    serie = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0, 20.0])

    assert percentil_en_su_historia(serie, 21.0) == 100.0   # nunca tan caro
    assert percentil_en_su_historia(serie, 9.0) == 0.0      # nunca tan barato
    assert percentil_en_su_historia(serie, 15.0) == 50.0


def test_un_percentil_sobre_pocas_observaciones_no_se_publica():
    """Sobre tres puntos el percentil solo puede valer 0, 50 o 100: esa
    precisión aparente engaña más de lo que informa."""
    corta = pd.Series([10.0, 12.0, 14.0])
    assert len(corta) < MINIMO_EJERCICIOS
    assert percentil_en_su_historia(corta, 13.0) is None


def test_los_valores_infinitos_y_nulos_no_cuentan_como_observaciones():
    serie = pd.Series([10.0, np.nan, np.inf, 12.0, 14.0])
    assert percentil_en_su_historia(serie, 13.0) is None, "solo hay 3 observaciones reales"


def test_sin_valor_actual_no_hay_percentil():
    serie = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0, 20.0])
    assert percentil_en_su_historia(serie, None) is None


# ==========================================================================
# LA LECTURA COMPLETA
# ==========================================================================


def test_una_empresa_en_su_maximo_historico_se_marca_cara():
    resultados, balance, flujos = _cuentas()
    resultado = evaluar_multiplos(
        _precios({}), resultados, balance, flujos, per_actual=99_999.0,
    )

    per = resultado.multiplos["PER"]
    assert per.percentil == 100.0
    assert per.caro and not per.barato
    assert "más caro" in per.lectura


def test_una_empresa_en_su_minimo_historico_se_marca_barata():
    resultados, balance, flujos = _cuentas()
    resultado = evaluar_multiplos(_precios({}), resultados, balance, flujos, per_actual=0.01)

    per = resultado.multiplos["PER"]
    assert per.percentil == 0.0
    assert per.barato and not per.caro


def test_el_percentil_medio_ignora_los_multiplos_sin_historico():
    """Promediar sobre los que no se pudieron medir inventaría una lectura."""
    resultados, balance, flujos = _cuentas()
    resultado = evaluar_multiplos(_precios({}), resultados, balance, flujos, per_actual=99_999.0)

    vivos = resultado.evaluables
    assert vivos
    esperado = round(sum(m.percentil for m in vivos) / len(vivos), 1)
    assert resultado.percentil_medio == esperado


def test_sin_historico_suficiente_se_avisa_en_vez_de_puntuar():
    resultados = pd.DataFrame({"2024-12-31": [100.0]}, index=["Net Income"])
    balance = pd.DataFrame({"2024-12-31": [1000.0]}, index=["Ordinary Shares Number"])
    flujos = pd.DataFrame()

    resultado = evaluar_multiplos(_precios({}), resultados, balance, flujos, per_actual=30.0)

    assert resultado.percentil_medio is None
    assert not resultado.caro
    assert resultado.avisos


def test_la_lectura_es_texto_legible_no_un_numero_suelto():
    resultados, balance, flujos = _cuentas()
    resultado = evaluar_multiplos(_precios({}), resultados, balance, flujos, per_actual=1000.0)
    for m in resultado.evaluables:
        assert isinstance(m.lectura, str) and m.lectura
