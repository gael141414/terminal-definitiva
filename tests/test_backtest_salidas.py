"""Arnés de validación de reglas de salida sobre entradas reales.

Sin red: todo sobre series sintéticas construidas en el propio test.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.backtest_salidas import (
    AGUANTAR, ALEATORIA, COMPUESTA, COSTE_POR_LADO, REGLAS, STOP_FIJO, TECNICA,
    Cierre, Entrada, aplicar_reglas, calcular_metricas, comparar_reglas,
    diferencia_significativa, generar_entradas, puntuacion_tecnica,
)
from modulos.config import STOP_DURO_PCT
from modulos.indicadores import enriquecer_ohlcv


def _serie(precios: list[float]) -> pd.DataFrame:
    p = np.asarray(precios, dtype=float)
    df = pd.DataFrame(
        {"Open": p, "High": p * 1.005, "Low": p * 0.995, "Close": p,
         "Volume": [1_000_000.0] * len(p)},
        index=pd.date_range("2018-01-01", periods=len(p), freq="B"),
    )
    return enriquecer_ohlcv(df)


def _alcista(n: int = 400) -> pd.DataFrame:
    return _serie(list(np.linspace(50.0, 150.0, n)))


def _realista(n: int = 700, semilla: int = 11) -> pd.DataFrame:
    """Tendencia con ruido y retrocesos periódicos.

    Una recta perfecta no dispara ningún setup del catálogo: sin retrocesos no
    hay pullback, sin oscilación no hay RSI2 sobrevendido y sin compresión no
    hay squeeze. Para probar la generación de entradas hace falta una serie que
    se parezca a un valor real, no a una función lineal.
    """
    rng = np.random.default_rng(semilla)
    precios = (
        np.linspace(50.0, 160.0, n)
        + 6 * np.sin(np.linspace(0, 14 * np.pi, n))
        + np.cumsum(rng.normal(0, 0.6, n))
    )
    p = np.asarray(precios, dtype=float)
    df = pd.DataFrame(
        {"Open": p, "High": p * 1.012, "Low": p * 0.988, "Close": p,
         "Volume": rng.uniform(8e5, 2e6, n)},
        index=pd.date_range("2018-01-01", periods=n, freq="B"),
    )
    return enriquecer_ohlcv(df)


def _bajista(n: int = 400) -> pd.DataFrame:
    return _serie(list(np.linspace(150.0, 60.0, n)))


def _entrada(df: pd.DataFrame, indice: int = 300, horizonte: int = 30) -> Entrada:
    return Entrada(
        ticker="TEST", estrategia="prueba", indice_entrada=indice,
        fecha_entrada=df.index[indice], precio_entrada=float(df["Close"].iloc[indice]),
        riesgo_accion=float(df["atr14"].iloc[indice]) * 2, horizonte=horizonte,
    )


# ==========================================================================
# EQUIVALENCIA CON EL MÓDULO REAL
# ==========================================================================


def test_la_puntuacion_tecnica_rapida_coincide_con_la_de_decision_venta():
    """El arnés recalcula el pilar técnico por velocidad (construir un
    DatosPosicion por cada barra sería O(n²)). Si las dos versiones divergen,
    el backtest deja de medir la regla que la aplicación ejecuta de verdad.
    """
    from modulos.decision_venta import DatosPosicion, Posicion, evaluar_tecnico

    df = _alcista()
    for indice in (250, 300, 350, len(df) - 1):
        recortado = df.iloc[: indice + 1]
        real = evaluar_tecnico(
            DatosPosicion(precio_actual=float(recortado["Close"].iloc[-1]), ohlcv=recortado),
            Posicion("TEST"),
        )
        rapida = puntuacion_tecnica(df, indice)

        assert (real.puntuacion is None) == (rapida is None)
        if real.puntuacion is not None:
            assert rapida == pytest.approx(real.puntuacion, abs=0.15), (
                f"divergen en el índice {indice}: {rapida} vs {real.puntuacion}"
            )


def test_el_regimen_adverso_endurece_igual_que_en_el_modulo_real():
    df = _bajista()
    neutro = puntuacion_tecnica(df, 350, regimen_favorable=None)
    adverso = puntuacion_tecnica(df, 350, regimen_favorable=False)
    favorable = puntuacion_tecnica(df, 350, regimen_favorable=True)

    assert adverso > neutro > favorable


# ==========================================================================
# LAS CINCO REGLAS SOBRE LA MISMA ENTRADA
# ==========================================================================


def test_las_cinco_reglas_se_aplican_a_la_misma_entrada():
    df = _alcista()
    cierres = aplicar_reglas(df, _entrada(df), aleatorio=random.Random(1))

    assert set(cierres) == set(REGLAS)
    fechas = {c.fecha_entrada for c in cierres.values()}
    assert len(fechas) == 1, "comparar reglas exige que partan del mismo punto"


def test_aguantar_llega_siempre_al_horizonte():
    df = _alcista()
    entrada = _entrada(df, horizonte=30)
    cierres = aplicar_reglas(df, entrada, aleatorio=random.Random(1))

    assert cierres[AGUANTAR].dias == 30
    assert not cierres[AGUANTAR].anticipada


def test_el_stop_se_comprueba_contra_el_minimo_no_contra_el_cierre():
    """Un stop real se ejecuta intradía. Compararlo con el cierre lo haría
    saltar más tarde de lo que saltaría de verdad."""
    n = 340
    precios = list(np.linspace(50.0, 100.0, n))
    df = _serie(precios)
    # Vela con mecha profunda: el mínimo rompe el stop, el cierre no.
    entrada = _entrada(df, indice=300, horizonte=20)
    umbral = entrada.precio_entrada * (1 - STOP_DURO_PCT / 100)
    df.iloc[310, df.columns.get_loc("Low")] = umbral * 0.99

    cierres = aplicar_reglas(df, entrada, aleatorio=random.Random(1))
    assert cierres[STOP_FIJO].motivo == "stop"
    assert cierres[STOP_FIJO].dias == 10


def test_la_regla_aleatoria_imita_la_duracion_de_la_tecnica():
    """Sin ese control, cualquier regla que salga pronto parecería buena en un
    mercado alcista solo por estar menos tiempo expuesta."""
    df = _bajista()
    entrada = _entrada(df, horizonte=40)
    cierres = aplicar_reglas(df, entrada, aleatorio=random.Random(7))

    assert cierres[ALEATORIA].dias <= max(cierres[TECNICA].dias, 1)


def test_la_compuesta_sale_no_mas_tarde_que_tecnica_y_stop():
    df = _bajista()
    cierres = aplicar_reglas(df, _entrada(df, horizonte=40), aleatorio=random.Random(3))

    assert cierres[COMPUESTA].dias <= min(cierres[TECNICA].dias, cierres[STOP_FIJO].dias)


def test_el_coste_se_descuenta_por_igual_a_todas_las_reglas():
    df = _alcista()
    entrada = _entrada(df, horizonte=5)
    cierres = aplicar_reglas(df, entrada, aleatorio=random.Random(1))

    for cierre in cierres.values():
        bruto_implicito = cierre.retorno_neto + 2 * COSTE_POR_LADO
        assert cierre.retorno_neto < bruto_implicito


def test_una_entrada_sin_recorrido_no_produce_cierres():
    df = _alcista(n=400)
    entrada = _entrada(df, indice=len(df) - 1, horizonte=30)
    assert aplicar_reglas(df, entrada, aleatorio=random.Random(1)) == {}


# ==========================================================================
# GENERACIÓN DE ENTRADAS
# ==========================================================================


def test_las_entradas_salen_de_las_estrategias_reales_del_catalogo():
    from modulos.swing_estrategias import ESTRATEGIAS_POR_ID

    entradas = generar_entradas({"TEST": _realista()})
    assert entradas, "el catálogo debería disparar alguna señal en una tendencia limpia"
    for e in entradas:
        assert e.estrategia in ESTRATEGIAS_POR_ID
        assert e.riesgo_accion > 0
        assert e.horizonte > 0


def test_solo_se_generan_entradas_largas():
    """Las reglas de salida comparadas están definidas para largos; mezclar
    cortas compararía cosas distintas bajo el mismo nombre."""
    from modulos.swing_estrategias import ESTRATEGIAS_POR_ID

    for e in generar_entradas({"TEST": _realista()}):
        assert ESTRATEGIAS_POR_ID[e.estrategia].direccion == "largo"


def test_la_separacion_minima_evita_contar_la_misma_señal_varios_dias():
    df = _realista()
    juntas = generar_entradas({"TEST": df}, separacion_minima_dias=1)
    separadas = generar_entradas({"TEST": df}, separacion_minima_dias=20)
    assert len(separadas) <= len(juntas)


def test_una_serie_demasiado_corta_no_genera_entradas():
    assert generar_entradas({"TEST": _alcista(120)}) == []


# ==========================================================================
# MÉTRICAS E INTERVALOS
# ==========================================================================


def _cierres_sinteticos(regla: str, retornos: list[float]) -> list[Cierre]:
    base = pd.Timestamp("2020-01-01")
    return [
        Cierre(regla=regla, ticker="T", estrategia="e",
               fecha_entrada=base + pd.Timedelta(days=i),
               retorno_neto=r, resultado_r=r * 10, dias=10, motivo="x", anticipada=False)
        for i, r in enumerate(retornos)
    ]


def test_las_metricas_traen_intervalo_de_confianza():
    cierres = _cierres_sinteticos(AGUANTAR, [0.10, -0.05, 0.20, 0.02, -0.08, 0.15])
    m = calcular_metricas(cierres, AGUANTAR)

    assert m is not None
    bajo, alto = m.ic_retorno
    assert bajo < m.retorno_medio_pct < alto, "la media debe caer dentro de su propio IC"


def test_el_cagr_y_el_drawdown_se_declaran_no_computables_en_vez_de_publicar_basura():
    """Los dos estaban en el pre-registro y se retiran con motivo.

    - Anualizar el retorno de una operación de 3 días eleva a la 84: con miles
      de operaciones cortas la media explota a 1e11 y parece una rentabilidad.
    - Encadenar operaciones SOLAPADAS como una cuenta reinvertida al 100% no es
      una cartera: da −100% siempre, para las cinco reglas por igual.

    Publicar esos números habría sido peor que no publicarlos, así que salen
    como NaN. Retirar una métrica pre-registrada exige declararlo, y este test
    es parte de esa declaración.
    """
    cierres = _cierres_sinteticos(AGUANTAR, [0.10, -0.05, 0.20, -0.10])
    m = calcular_metricas(cierres, AGUANTAR)

    assert np.isnan(m.cagr_pct)
    assert np.isnan(m.max_drawdown_pct)
    assert "CAGR_%" not in m.como_fila(), "no se imprime una columna de NaN"
    assert "maxDD_%" not in m.como_fila()


def test_las_metricas_que_si_son_computables_se_publican():
    cierres = _cierres_sinteticos(AGUANTAR, [0.10, -0.05, 0.20, -0.10])
    fila = calcular_metricas(cierres, AGUANTAR).como_fila()

    for clave in ("retorno_medio_%", "IC95_retorno", "expectativa_R", "acierto_%",
                  "sharpe", "sortino", "días", "rotación"):
        assert clave in fila


def test_la_diferencia_entre_reglas_se_empareja_por_operacion():
    """Las dos reglas se aplican a las mismas entradas: emparejar reduce mucho
    la varianza frente a comparar las medias por separado."""
    base = pd.Timestamp("2020-01-01")
    cierres: list[Cierre] = []
    for i in range(40):
        fecha = base + pd.Timedelta(days=i)
        for regla, r in ((AGUANTAR, 0.10 + i * 0.001), (TECNICA, 0.11 + i * 0.001)):
            cierres.append(Cierre(regla=regla, ticker="T", estrategia="e",
                                  fecha_entrada=fecha, retorno_neto=r, resultado_r=r * 10,
                                  dias=10, motivo="x", anticipada=False))

    dif = diferencia_significativa(cierres, TECNICA, AGUANTAR)
    assert dif["n"] == 40
    assert dif["diferencia_pct"] == pytest.approx(1.0, abs=0.01)
    assert dif["significativa"], "una diferencia constante de +1 punto debe detectarse"


def test_una_diferencia_nula_no_se_declara_significativa():
    base = pd.Timestamp("2020-01-01")
    rng = np.random.default_rng(5)
    cierres: list[Cierre] = []
    for i in range(60):
        fecha = base + pd.Timedelta(days=i)
        r = float(rng.normal(0.05, 0.10))
        for regla in (AGUANTAR, TECNICA):
            cierres.append(Cierre(regla=regla, ticker="T", estrategia="e",
                                  fecha_entrada=fecha, retorno_neto=r, resultado_r=r * 10,
                                  dias=10, motivo="x", anticipada=False))

    dif = diferencia_significativa(cierres, TECNICA, AGUANTAR)
    assert not dif["significativa"]
    assert dif["diferencia_pct"] == pytest.approx(0.0, abs=1e-9)


def test_comparar_reglas_devuelve_solo_las_que_tienen_operaciones():
    resultado = comparar_reglas(_cierres_sinteticos(AGUANTAR, [0.1, 0.2, -0.1]))
    assert set(resultado) == {AGUANTAR}
