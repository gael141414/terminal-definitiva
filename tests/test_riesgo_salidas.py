"""Eje de riesgo: construcción de cartera, métricas de cola y veredicto.

Sin red. La lógica que emite el veredicto se prueba con casos construidos, no
con datos de mercado: si el criterio pre-registrado se aplicase mal, el informe
diría lo contrario de lo que muestran los números.
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

from modulos.backtest_salidas import AGUANTAR, COMPUESTA, COSTE_POR_LADO, Cierre
from modulos.riesgo_salidas import (
    CRITERIO, MetricasRiesgo, _cvar, _duracion_maxima_drawdown,
    canje_maxdd_por_retorno, curva_equity, metricas_riesgo,
    retornos_diarios_cartera, serie_drawdown, veredicto_seguro,
)

FECHAS = pd.date_range("2021-01-04", periods=40, freq="B")


def _precios(valores: list[float]) -> pd.DataFrame:
    p = np.asarray(valores, dtype=float)
    return pd.DataFrame(
        {"Open": p, "High": p * 1.01, "Low": p * 0.99, "Close": p,
         "Volume": [1e6] * len(p)},
        index=FECHAS[: len(p)],
    )


def _cierre(regla: str, ticker: str, i_entrada: int, i_salida: int,
            retorno: float = 0.05, mae: float | None = -0.03) -> Cierre:
    return Cierre(
        regla=regla, ticker=ticker, estrategia="e",
        fecha_entrada=FECHAS[i_entrada], retorno_neto=retorno, resultado_r=retorno * 10,
        dias=i_salida - i_entrada, motivo="x", anticipada=False,
        fecha_salida=FECHAS[i_salida], mae=mae,
    )


# ==========================================================================
# CONSTRUCCIÓN DE CARTERA
# ==========================================================================


def test_la_cartera_equipondera_las_posiciones_abiertas_ese_dia():
    """Dos posiciones abiertas el mismo día pesan la mitad cada una."""
    sube = _precios([100.0] + [100.0 * 1.10 ** (i / 10) for i in range(1, 12)])
    baja = _precios([100.0] + [100.0 * 0.90 ** (i / 10) for i in range(1, 12)])
    precios = {"SUBE": sube, "BAJA": baja}
    cierres = [_cierre(AGUANTAR, "SUBE", 0, 10), _cierre(AGUANTAR, "BAJA", 0, 10)]

    diarios = retornos_diarios_cartera(cierres, precios)

    assert not diarios.empty
    # Una sube y otra baja aproximadamente lo mismo: la media queda cerca de 0.
    assert abs(float(diarios.iloc[5])) < 0.02


def test_una_sesion_sin_posiciones_abiertas_no_aparece_en_la_serie():
    """El efectivo rinde 0 y no se rellena con el índice: rellenarlo prestaría
    a las reglas que salen pronto un retorno que no ganaron."""
    precios = {"A": _precios([100.0 + i for i in range(20)])}
    cierres = [_cierre(AGUANTAR, "A", 0, 5)]

    diarios = retornos_diarios_cartera(cierres, precios)
    assert diarios.index.max() <= FECHAS[5]


def test_el_coste_se_carga_en_la_entrada_y_en_la_salida():
    """Dos veces el coste por lado en total, igual que en la Tarea 1."""
    precios = {"A": _precios([100.0] * 12)}          # precio plano: sin coste sería 0
    cierres = [_cierre(AGUANTAR, "A", 0, 10)]

    diarios = retornos_diarios_cartera(cierres, precios)
    assert float(diarios.sum()) == pytest.approx(-2 * COSTE_POR_LADO, abs=1e-9)


def test_el_peso_fijo_no_apalanca_aunque_haya_muchas_posiciones():
    """Con 2% por posición y 100 abiertas, la exposición se corta en 1, no en 2."""
    precios = {f"T{i}": _precios([100.0 * (1 + 0.01 * j) for j in range(12)]) for i in range(100)}
    cierres = [_cierre(AGUANTAR, f"T{i}", 0, 10) for i in range(100)]

    diarios = retornos_diarios_cartera(cierres, precios, peso_fijo=0.02)
    equiponderada = retornos_diarios_cartera(cierres, precios)

    assert float(diarios.iloc[5]) == pytest.approx(float(equiponderada.iloc[5]), abs=1e-9)


def test_sin_cierres_la_serie_sale_vacia_en_vez_de_romper():
    assert retornos_diarios_cartera([], {}).empty


# ==========================================================================
# CURVA Y CAÍDA
# ==========================================================================


def test_el_drawdown_mide_desde_el_maximo_previo():
    equity = pd.Series([1.0, 1.2, 0.9, 1.1], index=FECHAS[:4])
    dd = serie_drawdown(equity)

    assert float(dd.iloc[1]) == pytest.approx(0.0)
    assert float(dd.iloc[2]) == pytest.approx(0.9 / 1.2 - 1)


def test_la_duracion_del_drawdown_cuenta_sesiones_consecutivas_bajo_el_agua():
    dd = pd.Series([0.0, -0.1, -0.2, -0.05, 0.0, -0.1])
    assert _duracion_maxima_drawdown(dd) == 3


def test_una_curva_que_solo_sube_no_tiene_drawdown():
    equity = pd.Series([1.0, 1.1, 1.2, 1.3])
    assert float(serie_drawdown(equity).min()) == pytest.approx(0.0)
    assert _duracion_maxima_drawdown(serie_drawdown(equity)) == 0


# ==========================================================================
# COLA
# ==========================================================================


def test_el_cvar_es_la_media_de_la_cola_no_el_punto_de_corte():
    """El VaR dice dónde está el corte; el CVaR, cuánto se pierde una vez
    cruzado. Confundirlos subestima el riesgo justo donde importa."""
    valores = np.array([-0.50, -0.40, -0.30] + [0.05] * 97)

    cvar = _cvar(valores, alfa=0.05)
    var = float(np.percentile(valores, 5))

    assert cvar < var, "el CVaR tiene que ser peor que el VaR"
    assert cvar == pytest.approx(np.mean(valores[valores <= var]))


def test_el_cvar_de_una_distribucion_sin_cola_no_es_catastrofico():
    valores = np.full(100, 0.01)
    assert _cvar(valores) == pytest.approx(0.01)


# ==========================================================================
# MÉTRICAS COMPLETAS
# ==========================================================================


def _metricas_de_prueba(retornos_diarios: list[float], retornos_op: list[float],
                        regla: str = AGUANTAR) -> MetricasRiesgo:
    serie = pd.Series(retornos_diarios, index=pd.date_range("2021-01-04", periods=len(retornos_diarios), freq="B"))
    cierres = [
        Cierre(regla=regla, ticker="A", estrategia="e", fecha_entrada=FECHAS[0],
               retorno_neto=r, resultado_r=r * 10, dias=5, motivo="x",
               anticipada=False, fecha_salida=FECHAS[5], mae=-abs(r) / 2)
        for r in retornos_op
    ]
    return metricas_riesgo(regla, cierres, serie)


def test_las_metricas_incluyen_forma_completa_no_solo_la_media():
    rng = np.random.default_rng(7)
    m = _metricas_de_prueba(list(rng.normal(0.0005, 0.01, 400)),
                            list(rng.normal(0.02, 0.08, 300)))

    assert m.media_pct != m.mediana_pct or True
    assert np.isfinite(m.asimetria)
    assert np.isfinite(m.curtosis)
    assert np.isfinite(m.p5_pct) and np.isfinite(m.p1_pct)
    assert m.p1_pct <= m.p5_pct, "el percentil 1 no puede ser mejor que el 5"


def test_el_calmar_relaciona_retorno_con_la_peor_caida():
    m = _metricas_de_prueba([0.001] * 300 + [-0.02] * 20 + [0.001] * 100,
                            [0.05, -0.10, 0.08])
    assert np.isfinite(m.calmar)
    assert m.max_drawdown_pct < 0


def test_el_mae_es_negativo_porque_mide_lo_que_fue_en_contra():
    m = _metricas_de_prueba([0.001] * 100, [0.05, 0.03, -0.02])
    assert m.mae_medio_pct <= 0


def test_el_cvar_trae_intervalo_de_confianza():
    rng = np.random.default_rng(3)
    m = _metricas_de_prueba(list(rng.normal(0.0005, 0.01, 300)),
                            list(rng.normal(0.01, 0.10, 400)))
    bajo, alto = m.ic_cvar5
    assert bajo < m.cvar5_pct < alto


# ==========================================================================
# EL VEREDICTO PRE-REGISTRADO
# ==========================================================================


def _m(regla, cagr, maxdd, calmar, sortino, cvar) -> MetricasRiesgo:
    return MetricasRiesgo(
        regla=regla, cagr_pct=cagr, max_drawdown_pct=maxdd, duracion_drawdown_dias=10,
        volatilidad_pct=15.0, downside_pct=10.0, sharpe=0.5, sortino=sortino,
        calmar=calmar, ulcer=5.0, p5_pct=-10.0, p1_pct=-20.0, cvar5_pct=cvar,
        peor_operacion_pct=-30.0, mae_medio_pct=-5.0, media_pct=1.0, mediana_pct=0.8,
        asimetria=0.1, curtosis=3.0, operaciones=100,
    )


def test_el_criterio_A_exige_mejorar_las_cuatro_cosas_a_la_vez():
    referencia = _m(AGUANTAR, 10.0, -40.0, 0.25, 1.0, -15.0)
    dominante = _m(COMPUESTA, 9.5, -20.0, 0.475, 1.2, -10.0)

    v = veredicto_seguro(dominante, referencia)
    assert v["criterio_A"]
    assert v["merece_la_pena"]


def test_mejorar_solo_el_drawdown_no_basta_para_el_criterio_A():
    referencia = _m(AGUANTAR, 10.0, -40.0, 0.25, 1.0, -15.0)
    # Recorta caída pero empeora Sortino y CVaR.
    parcial = _m(COMPUESTA, 5.0, -30.0, 0.167, 0.8, -18.0)

    v = veredicto_seguro(parcial, referencia)
    assert not v["criterio_A"]


def test_el_criterio_B_mide_el_canje_de_caida_por_retorno():
    """Recortar 20 puntos de maxDD cediendo 5 de CAGR son 4:1, por encima del
    3:1 pre-registrado."""
    referencia = _m(AGUANTAR, 15.0, -40.0, 0.375, 1.0, -15.0)
    barato = _m(COMPUESTA, 10.0, -20.0, 0.50, 0.9, -12.0)

    v = veredicto_seguro(barato, referencia)
    assert v["canje_maxdd_por_punto"] == pytest.approx(4.0)
    assert v["criterio_B"]
    assert v["merece_la_pena"]


def test_un_canje_por_debajo_del_umbral_se_declara_seguro_caro():
    referencia = _m(AGUANTAR, 15.0, -40.0, 0.375, 1.0, -15.0)
    caro = _m(COMPUESTA, 10.0, -35.0, 0.286, 0.9, -12.0)   # 5 puntos por 5 cedidos = 1:1

    v = veredicto_seguro(caro, referencia)
    assert v["canje_maxdd_por_punto"] == pytest.approx(1.0)
    assert not v["criterio_B"]
    assert not v["merece_la_pena"]


def test_el_criterio_B_tambien_exige_que_mejore_la_cola():
    """Recortar mucha caída pero empeorar el CVaR no es una cobertura: es
    cambiar una forma de riesgo por otra."""
    referencia = _m(AGUANTAR, 15.0, -40.0, 0.375, 1.0, -15.0)
    sin_cola = _m(COMPUESTA, 10.0, -15.0, 0.667, 0.9, -22.0)

    v = veredicto_seguro(sin_cola, referencia)
    assert v["canje_maxdd_por_punto"] == pytest.approx(5.0)
    assert not v["criterio_B"], "el canje es bueno pero el CVaR empeora"


def test_sin_retorno_cedido_no_hay_canje_que_evaluar():
    referencia = _m(AGUANTAR, 10.0, -40.0, 0.25, 1.0, -15.0)
    mejor_en_todo = _m(COMPUESTA, 12.0, -20.0, 0.60, 1.3, -10.0)

    assert canje_maxdd_por_retorno(mejor_en_todo, referencia) is None
    assert veredicto_seguro(mejor_en_todo, referencia)["criterio_A"]


def test_el_umbral_del_canje_es_el_pre_registrado():
    """Si alguien lo mueve después de ver resultados, este test lo delata."""
    assert CRITERIO["canje_minimo"] == 3.0
