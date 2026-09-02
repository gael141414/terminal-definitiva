"""Bloque de swing: riesgo, estrategias, régimen y backtest."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.indicadores import enriquecer_ohlcv
from modulos.swing_backtest import _simular_operacion
from modulos.swing_estrategias import (
    ESTRATEGIAS, ESTRATEGIAS_POR_ID, _bonus_fundamental, evaluar_todas,
)
from modulos.swing_regimen import CORRECCION, PANICO, Regimen, TENDENCIA_ALCISTA, calcular_amplitud
from modulos.swing_riesgo import (
    calcular_objetivos, calcular_stop, construir_plan, dimensionar_posicion, expectativa_sistema,
)


# ==========================================================================
# RIESGO
# ==========================================================================


def test_el_riesgo_real_coincide_con_el_riesgo_pedido():
    """La promesa del módulo: si salta el stop se pierde el % configurado."""
    plan = construir_plan(entrada=100.0, atr=3.0, capital=20_000.0, riesgo_por_operacion_pct=1.0)

    perdida = plan.acciones * (plan.entrada - plan.stop)
    assert abs(perdida - 200.0) <= 100.0 * (plan.entrada - plan.stop) / 100  # margen de 1 acción
    assert plan.riesgo_pct_real <= 1.0


def test_mas_volatilidad_implica_menos_acciones():
    """A igual riesgo, un valor más volátil obliga a una posición más pequeña."""
    tranquilo = construir_plan(entrada=100.0, atr=1.0, capital=50_000.0)
    volatil = construir_plan(entrada=100.0, atr=8.0, capital=50_000.0)

    assert tranquilo.acciones > volatil.acciones


def test_el_stop_va_debajo_en_largos_y_encima_en_cortos():
    assert calcular_stop(100.0, 3.0, "largo") == 94.0
    assert calcular_stop(100.0, 3.0, "corto") == 106.0


def test_los_objetivos_del_corto_van_a_la_baja():
    objetivos = calcular_objetivos(100.0, 106.0, "corto")
    assert objetivos["1R"] == 94.0
    assert objetivos["2R"] == 88.0


def test_tope_de_concentracion_por_posicion():
    """Un stop muy estrecho dispararía el número de acciones y concentraría la
    cartera en un solo valor sin que el usuario se diera cuenta."""
    acciones, avisos = dimensionar_posicion(10_000.0, 1.0, 100.0, 99.9)

    assert acciones * 100.0 <= 10_000.0 * 0.20 + 100.0
    assert any("recortado" in a for a in avisos)


def test_bloquea_cuando_no_sale_ni_una_accion():
    acciones, avisos = dimensionar_posicion(500.0, 0.5, 1000.0, 900.0)

    assert acciones == 0
    assert any(a.startswith("BLOQUEO") for a in avisos)


def test_stop_igual_a_entrada_no_es_operable():
    plan = construir_plan(entrada=100.0, atr=0.0, capital=10_000.0)
    assert not plan.operable


def test_el_factor_de_regimen_reduce_el_tamano():
    normal = construir_plan(entrada=100.0, atr=3.0, capital=50_000.0, factor_regimen=1.0)
    hostil = construir_plan(entrada=100.0, atr=3.0, capital=50_000.0, factor_regimen=0.5)

    assert hostil.acciones < normal.acciones


def test_expectativa_desmonta_la_trampa_del_alto_acierto():
    """Acertar mucho con ganancias pequeñas puede ser un sistema perdedor."""
    assert expectativa_sistema(60, 0.5, 1.0) < 0
    assert expectativa_sistema(40, 3.0, 1.0) > 0
    assert expectativa_sistema(50, 1.0, 1.0) == 0.0


# ==========================================================================
# ESTRATEGIAS
# ==========================================================================


def _serie(n=320, tendencia=0.0, base=100.0, volumen=1_000_000.0, semilla=1):
    np.random.seed(semilla)
    precios = base + np.arange(n) * tendencia + np.random.randn(n).cumsum() * 0.3
    precios = np.maximum(precios, 1.0)
    return pd.DataFrame(
        {
            "Open": precios, "High": precios * 1.01, "Low": precios * 0.99,
            "Close": precios, "Volume": [volumen] * n,
        },
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )


def test_ninguna_estrategia_dispara_sin_historico_suficiente():
    corto = enriquecer_ohlcv(_serie(n=100))
    assert evaluar_todas(corto, "TEST") == []


def test_se_descartan_valores_ilíquidos():
    """Sin volumen no hay salida al precio que marca el gráfico."""
    df = enriquecer_ohlcv(_serie(tendencia=0.3, volumen=1_000))
    assert evaluar_todas(df, "CHICHARRO") == []


def test_se_descartan_precios_de_centimos():
    df = enriquecer_ohlcv(_serie(tendencia=0.01, base=0.5))
    assert evaluar_todas(df, "PENNY") == []


def test_las_estrategias_largas_exigen_estar_sobre_la_media_de_200():
    """Comprar por debajo de la media de 200 es comprar una caída estructural."""
    bajista = enriquecer_ohlcv(_serie(tendencia=-0.25, semilla=5))
    señales = evaluar_todas(bajista, "CAIDA")

    assert all(not s.es_largo for s in señales)


def test_una_estrategia_que_falla_no_tumba_el_escaneo():
    """Un dato raro en un valor no puede dejar sin señales a los otros 499."""
    df = enriquecer_ohlcv(_serie(tendencia=0.2))
    original = ESTRATEGIAS_POR_ID["ruptura_maximos"].evaluar

    def explota(*_args, **_kwargs):
        raise ValueError("dato corrupto")

    object.__setattr__(ESTRATEGIAS_POR_ID["ruptura_maximos"], "evaluar", explota)
    try:
        evaluar_todas(df, "TEST")  # no debe propagar
    finally:
        object.__setattr__(ESTRATEGIAS_POR_ID["ruptura_maximos"], "evaluar", original)


def test_todas_las_estrategias_declaran_su_expectativa_medida():
    """La interfaz no debe poder mostrar una regla sin su resultado real al lado."""
    for estrategia in ESTRATEGIAS:
        assert estrategia.expectativa_medida is not None
        assert estrategia.operaciones_medidas and estrategia.operaciones_medidas > 0


def test_ninguna_estrategia_corta_esta_validada():
    """Hallazgo del backtest: los cortos pierden en ambos periodos."""
    cortas = [e for e in ESTRATEGIAS if e.direccion == "corto"]

    assert cortas
    assert not any(e.validada for e in cortas)


def test_la_validacion_usa_la_cifra_fuera_de_muestra():
    """«Ruptura de máximos» era positiva en el periodo de diseño (+0,05R) y se
    queda en cero en el reservado. Marcarla como validada por su cifra
    in-sample sería justo el error que la validación out-of-sample evita."""
    ruptura = ESTRATEGIAS_POR_ID["ruptura_maximos"]

    assert ruptura.expectativa_medida is not None and ruptura.expectativa_medida > 0
    assert ruptura.expectativa_fuera_muestra is not None and ruptura.expectativa_fuera_muestra <= 0
    assert not ruptura.validada


def test_las_estrategias_validadas_conservan_ventaja_fuera_de_muestra():
    validadas = [e for e in ESTRATEGIAS if e.validada]

    assert validadas, "debería haber al menos una estrategia con ventaja demostrada"
    for estrategia in validadas:
        assert estrategia.expectativa_fuera_muestra is not None
        assert estrategia.expectativa_fuera_muestra > 0


def test_todas_las_estrategias_declaran_su_expectativa_fuera_de_muestra():
    """La interfaz no debe poder mostrar una regla sin su cifra reservada."""
    for estrategia in ESTRATEGIAS:
        assert estrategia.expectativa_fuera_muestra is not None


# --- fusión con fundamentales ---------------------------------------------


def test_el_contexto_fundamental_premia_calidad_en_largos():
    bueno, motivos = _bonus_fundamental({"buffett_score": 80}, "largo")
    malo, _ = _bonus_fundamental({"buffett_score": 25}, "largo")

    assert bueno > 0 > malo
    assert any("Calidad" in m for m in motivos)


def test_el_contexto_fundamental_premia_deterioro_en_cortos():
    """Es la fusión que diferencia a este escáner de uno puramente técnico."""
    deteriorada, motivos = _bonus_fundamental(
        {"red_flags": 3, "fcf_negativo": True, "deuda_alta": True}, "corto"
    )
    assert deteriorada > 0
    assert any("bandera" in m.lower() for m in motivos)


def test_avisa_al_ponerse_corto_contra_una_buena_empresa():
    puntos, motivos = _bonus_fundamental({"buffett_score": 85}, "corto")

    assert puntos < 0
    assert any("Cuidado" in m for m in motivos)


# ==========================================================================
# RÉGIMEN
# ==========================================================================


def test_el_regimen_hostil_reduce_el_tamano_sugerido():
    assert Regimen(codigo=TENDENCIA_ALCISTA).factor_tamano > Regimen(codigo=CORRECCION).factor_tamano
    assert Regimen(codigo=PANICO).factor_tamano < 0.5


def test_favorabilidad_por_regimen():
    assert Regimen(codigo=TENDENCIA_ALCISTA).favorable_a_largos
    assert not Regimen(codigo=TENDENCIA_ALCISTA).favorable_a_cortos
    assert Regimen(codigo=CORRECCION).favorable_a_cortos


def test_amplitud_necesita_muestra_representativa():
    """Con pocos valores el porcentaje no significa nada y es mejor no darlo."""
    pocos = {f"T{i}": _serie(n=250) for i in range(5)}
    assert calcular_amplitud(pocos) is None
    assert calcular_amplitud({}) is None


def test_amplitud_detecta_mercado_deteriorado():
    bajistas = {f"B{i}": _serie(n=260, tendencia=-0.2, semilla=i) for i in range(25)}
    amplitud = calcular_amplitud(bajistas)

    assert amplitud is not None and amplitud < 50.0


# ==========================================================================
# BACKTEST
# ==========================================================================


def _df_con_salida(direccion="largo"):
    n = 260
    precios = [100.0] * n
    df = pd.DataFrame(
        {"Open": precios, "High": [101.0] * n, "Low": [99.0] * n, "Close": precios,
         "Volume": [1e6] * n},
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )
    return df


def test_la_entrada_es_en_la_apertura_siguiente_no_en_el_cierre_de_la_senal():
    """Operar el cierre que genera la señal es imposible en la práctica: no se
    conoce hasta que el mercado ha cerrado. Entrar ahí infla los resultados."""
    df = _df_con_salida()
    df.loc[df.index[251], "Open"] = 105.0
    estrategia = ESTRATEGIAS_POR_ID["pullback_tendencia"]

    op = _simular_operacion(df, 250, estrategia, atr_señal=2.0, direccion="largo")

    assert op is not None
    assert op.entrada == 105.0
    assert op.fecha_entrada == df.index[251]


def test_si_stop_y_objetivo_caen_el_mismo_dia_gana_el_stop():
    """Sin datos intradía no se sabe cuál se tocó primero; asumir el objetivo
    sería inflar artificialmente el resultado del backtest."""
    df = _df_con_salida()
    df.loc[df.index[251], ["Open", "High", "Low"]] = [100.0, 130.0, 70.0]
    estrategia = ESTRATEGIAS_POR_ID["pullback_tendencia"]

    op = _simular_operacion(df, 250, estrategia, atr_señal=2.0, direccion="largo")

    assert op.motivo_salida == "stop"
    assert op.resultado_r == -1.0


def test_el_corto_gana_cuando_el_precio_baja():
    df = _df_con_salida()
    # Cae por debajo del objetivo 2R: entrada 100, stop 104, objetivo 92.
    df.loc[df.index[252], ["Open", "High", "Low", "Close"]] = [99.0, 99.5, 90.0, 91.0]
    estrategia = ESTRATEGIAS_POR_ID["ruptura_bajista"]

    op = _simular_operacion(df, 250, estrategia, atr_señal=2.0, direccion="corto")

    assert op.motivo_salida == "objetivo"
    assert op.resultado_r == 2.0


def test_sin_atr_no_hay_operacion_simulable():
    df = _df_con_salida()
    estrategia = ESTRATEGIAS_POR_ID["pullback_tendencia"]

    assert _simular_operacion(df, 250, estrategia, atr_señal=0.0, direccion="largo") is None
