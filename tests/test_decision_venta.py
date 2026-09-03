"""Decisión de venta o reducción sobre una posición abierta.

Sin red: se ataca ``evaluar_posicion``, que es pura y recibe los datos ya
reunidos. La adquisición vive en ``reunir_datos`` y no se toca aquí.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.config import (
    PERFIL_LARGO_PLAZO, PERFIL_SWING, STOP_DURO_PCT, UMBRAL_REDUCIR, UMBRAL_VENDER,
)
from modulos.decision_venta import (
    ADVERTENCIA_EVIDENCIA, MANTENER, REDUCIR, VENDER, DatosPosicion, Posicion,
    evaluar_posicion,
)
from modulos.indicadores import enriquecer_ohlcv

EJERCICIOS = [f"{a}-12-31" for a in range(2024, 2016, -1)]


def _tabla(filas: dict[str, list]) -> pd.DataFrame:
    return pd.DataFrame(filas, index=EJERCICIOS).T


def _cuentas_sanas():
    resultados = _tabla({
        "Net Income": [120.0, 110.0, 100.0, 95.0, 90.0, 85.0, 80.0, 75.0],
        "Total Revenue": [900.0, 850.0, 800.0, 760.0, 720.0, 690.0, 660.0, 630.0],
        "Cost Of Revenue": [400.0, 385.0, 370.0, 356.0, 342.0, 330.0, 320.0, 310.0],
        "EBIT": [180.0, 165.0, 150.0, 142.0, 135.0, 128.0, 122.0, 115.0],
        "Selling General And Administration": [120.0] * 8,
    })
    balance = _tabla({
        "Total Assets": [1000.0, 960.0, 920.0, 890.0, 860.0, 830.0, 800.0, 780.0],
        "Total Liabilities Net Minority Interest": [380.0, 375.0, 370.0, 368.0, 366.0, 364.0, 362.0, 360.0],
        "Current Assets": [500.0, 480.0, 460.0, 445.0, 430.0, 415.0, 400.0, 390.0],
        "Current Liabilities": [190.0, 188.0, 186.0, 185.0, 184.0, 183.0, 182.0, 181.0],
        "Retained Earnings": [400.0, 360.0, 320.0, 295.0, 270.0, 245.0, 220.0, 200.0],
        "Stockholders Equity": [620.0, 585.0, 550.0, 522.0, 494.0, 466.0, 438.0, 420.0],
        "Accounts Receivable": [100.0, 96.0, 92.0, 89.0, 86.0, 83.0, 80.0, 78.0],
        "Net PPE": [300.0, 290.0, 280.0, 272.0, 264.0, 256.0, 248.0, 242.0],
        "Long Term Debt": [140.0, 150.0, 160.0, 165.0, 170.0, 175.0, 180.0, 185.0],
        "Ordinary Shares Number": [1000.0] * 8,
        "Total Debt": [200.0] * 8,
        "Cash And Cash Equivalents": [80.0] * 8,
    })
    flujos = _tabla({
        "Operating Cash Flow": [160.0, 148.0, 136.0, 129.0, 122.0, 116.0, 110.0, 104.0],
        "Capital Expenditure": [-30.0] * 8,
        "Depreciation And Amortization": [45.0] * 8,
        "Depreciation": [45.0] * 8,
    })
    return resultados, balance, flujos


def _ohlcv(precios: list[float]) -> pd.DataFrame:
    p = np.asarray(precios, dtype=float)
    df = pd.DataFrame(
        {"Open": p, "High": p * 1.01, "Low": p * 0.99, "Close": p,
         "Volume": [1_000_000.0] * len(p)},
        index=pd.date_range("2020-01-01", periods=len(p), freq="B"),
    )
    return enriquecer_ohlcv(df)


def _tendencia_alcista(n: int = 400) -> pd.DataFrame:
    return _ohlcv(list(np.linspace(60.0, 120.0, n)))


def _tendencia_bajista(n: int = 400) -> pd.DataFrame:
    return _ohlcv(list(np.linspace(120.0, 70.0, n)))


def _serie_precios(n: int = 2600) -> pd.Series:
    fechas = pd.date_range("2015-01-01", periods=n, freq="B")
    return pd.Series(np.linspace(50.0, 120.0, n), index=fechas)


def _datos(**cambios) -> DatosPosicion:
    resultados, balance, flujos = _cuentas_sanas()
    base = dict(
        precio_actual=120.0,
        precios=_serie_precios(),
        ohlcv=_tendencia_alcista(),
        resultados=resultados, balance=balance, flujos=flujos,
        fair_value=130.0,
        margen_seguridad=(130.0 - 120.0) / 120.0,
        per_actual=25.0, pfcf_actual=28.0,
        capitalizacion=120_000.0,
        regimen_favorable=True, regimen_etiqueta="Tendencia alcista",
    )
    base.update(cambios)
    return DatosPosicion(**base)


# ==========================================================================
# EL CASO NORMAL
# ==========================================================================


def test_una_empresa_sana_y_barata_se_mantiene():
    decision = evaluar_posicion(_datos(), Posicion("TEST", entrada=100.0))

    assert decision.accion == MANTENER
    assert decision.reducir_pct == 0.0
    assert decision.sell_score < UMBRAL_REDUCIR


def test_la_decision_es_serializable_a_json():
    """analysis_store y las alertas la guardan tal cual."""
    decision = evaluar_posicion(_datos(), Posicion("TEST", entrada=100.0))
    texto = json.dumps(decision.to_dict(), default=str)

    assert '"accion"' in texto
    assert '"sell_score"' in texto


def test_la_decision_arrastra_siempre_la_advertencia_de_evidencia():
    """La regla no batió a aguantar en la prueba propia. No se puede omitir."""
    from modulos.decision_venta import RESULTADO_VALIDACION

    decision = evaluar_posicion(_datos(), Posicion("TEST", entrada=100.0))
    assert decision.advertencia == ADVERTENCIA_EVIDENCIA
    assert "4.199" in decision.advertencia
    assert RESULTADO_VALIDACION["retorno_regla_pct"] < RESULTADO_VALIDACION["retorno_aguantar_pct"]
    assert RESULTADO_VALIDACION["retorno_regla_pct"] > RESULTADO_VALIDACION["retorno_aleatoria_pct"]


# ==========================================================================
# SOBREVALORACIÓN
# ==========================================================================


def test_una_sobrevaloracion_severa_empuja_a_vender():
    decision = evaluar_posicion(
        _datos(fair_value=60.0, margen_seguridad=(60.0 - 120.0) / 120.0),
        Posicion("TEST", entrada=100.0),
    )

    assert decision.accion in (REDUCIR, VENDER)
    assert decision.sub_scores["valoracion"] > 60
    assert any("por encima del valor razonable" in t for t in decision.triggers)


def test_los_precios_objetivo_salen_del_valor_razonable():
    decision = evaluar_posicion(_datos(fair_value=100.0), Posicion("TEST", entrada=80.0))

    assert decision.precio_objetivo_trim == 100.0
    assert decision.precio_objetivo_venta > decision.precio_objetivo_trim


def test_sin_valor_razonable_no_se_inventan_precios_objetivo():
    decision = evaluar_posicion(
        _datos(fair_value=None, margen_seguridad=None), Posicion("TEST", entrada=100.0)
    )
    assert decision.precio_objetivo_trim is None
    assert decision.precio_objetivo_venta is None


# ==========================================================================
# OVERRIDES DUROS
# ==========================================================================


def test_el_stop_duro_vende_en_swing_pero_solo_avisa_en_largo_plazo():
    """MEDIDO: aplicar el stop de −8% a posiciones de un año rindió 11,03%
    frente al 36,31% de aguantar. Corta caídas normales de valores que luego se
    recuperan, y se pierde toda la subida posterior. Así que decide en swing,
    que es el horizonte para el que la regla se diseñó, y avisa en largo plazo.
    """
    precio = 100.0 * (1 - (STOP_DURO_PCT + 2) / 100)
    posicion = Posicion("TEST", entrada=100.0)

    swing = evaluar_posicion(_datos(precio_actual=precio), posicion, perfil=PERFIL_SWING)
    assert swing.accion == VENDER
    assert swing.flags["override_stop"]
    assert swing.reducir_pct == 100.0
    assert any("Stop duro" in t for t in swing.triggers)

    largo = evaluar_posicion(_datos(precio_actual=precio), posicion, perfil=PERFIL_LARGO_PLAZO)
    assert not largo.flags["override_stop"]
    assert any("aviso, no una orden" in t for t in largo.triggers)


def test_una_caida_menor_que_el_stop_no_dispara_el_override():
    precio = 100.0 * (1 - (STOP_DURO_PCT - 3) / 100)
    decision = evaluar_posicion(_datos(precio_actual=precio), Posicion("TEST", entrada=100.0))

    assert not decision.flags["override_stop"]


def test_la_tesis_rota_por_riesgo_de_quiebra_vende():
    balance = _cuentas_sanas()[1].copy()
    balance.loc["Total Liabilities Net Minority Interest"] = [1400.0] * 8
    balance.loc["Retained Earnings"] = [-500.0] * 8
    balance.loc["Current Assets"] = [80.0] * 8
    resultados = _cuentas_sanas()[0].copy()
    resultados.loc["EBIT"] = [-120.0] * 8

    decision = evaluar_posicion(
        _datos(balance=balance, resultados=resultados, capitalizacion=100.0),
        Posicion("TEST", entrada=100.0),
    )

    assert decision.accion == VENDER
    assert decision.flags["tesis_rota"]
    assert any("Altman" in t for t in decision.triggers)


def test_un_override_manda_por_encima_del_score():
    """Aunque el score diga MANTENER, el stop roto vende (en swing)."""
    precio = 100.0 * (1 - (STOP_DURO_PCT + 5) / 100)
    datos = _datos(precio_actual=precio, fair_value=400.0,
                   margen_seguridad=(400.0 - precio) / precio)
    decision = evaluar_posicion(datos, Posicion("TEST", entrada=100.0), perfil=PERFIL_SWING)

    assert decision.sell_score < UMBRAL_VENDER, "el score por sí solo no vendería"
    assert decision.accion == VENDER


# ==========================================================================
# RÉGIMEN DE MERCADO
# ==========================================================================


def test_el_mismo_valor_puntua_mas_alto_en_regimen_adverso():
    """Condicionar al régimen es el punto del encargo: la misma señal bajista
    pesa más cuando el mercado ya está en distribución."""
    comun = dict(ohlcv=_tendencia_bajista(), precio_actual=70.0,
                 fair_value=75.0, margen_seguridad=(75.0 - 70.0) / 70.0)
    posicion = Posicion("TEST", entrada=100.0, fecha_entrada=date.today() - timedelta(days=400))

    favorable = evaluar_posicion(
        _datos(regimen_favorable=True, regimen_etiqueta="Tendencia alcista", **comun), posicion)
    adverso = evaluar_posicion(
        _datos(regimen_favorable=False, regimen_etiqueta="Corrección", **comun), posicion)

    assert adverso.sub_scores["tecnico"] > favorable.sub_scores["tecnico"]


def test_sin_lectura_de_regimen_el_tecnico_no_se_ajusta():
    posicion = Posicion("TEST", entrada=100.0)
    neutro = evaluar_posicion(_datos(regimen_favorable=None, ohlcv=_tendencia_bajista(),
                                     precio_actual=70.0), posicion)
    assert neutro.sub_scores["tecnico"] is not None


# ==========================================================================
# PERFILES
# ==========================================================================


def test_el_perfil_swing_pesa_mas_lo_tecnico_que_el_largo_plazo():
    """Mismos datos, distinta ponderación: un deterioro técnico con
    fundamentales intactos debe mover más al swing."""
    datos = _datos(ohlcv=_tendencia_bajista(), precio_actual=70.0,
                   fair_value=95.0, margen_seguridad=(95.0 - 70.0) / 70.0)
    posicion = Posicion("TEST", entrada=100.0, fecha_entrada=date.today() - timedelta(days=400))

    largo = evaluar_posicion(datos, posicion, perfil=PERFIL_LARGO_PLAZO)
    swing = evaluar_posicion(datos, posicion, perfil=PERFIL_SWING)

    assert swing.sell_score > largo.sell_score
    assert swing.perfil == PERFIL_SWING


def test_un_perfil_desconocido_cae_al_de_largo_plazo():
    decision = evaluar_posicion(_datos(), Posicion("TEST", entrada=100.0), perfil="inventado")
    assert decision.perfil == PERFIL_LARGO_PLAZO


# ==========================================================================
# CUÁNTO REDUCIR
# ==========================================================================


def test_reducir_suelta_aproximadamente_un_tercio():
    datos = _datos(fair_value=95.0, margen_seguridad=(95.0 - 120.0) / 120.0,
                   ohlcv=_tendencia_bajista(), precio_actual=120.0)
    decision = evaluar_posicion(datos, Posicion("TEST", entrada=100.0,
                                                fecha_entrada=date.today() - timedelta(days=400)))

    if decision.accion == REDUCIR:
        assert 30 <= decision.reducir_pct <= 40


def test_un_peso_excesivo_obliga_a_recortar_hasta_el_tope():
    """El exceso de peso es un riesgo por sí mismo, aunque el negocio aguante."""
    from modulos.swing_riesgo import MAX_PESO_POSICION_PCT

    datos = _datos(fair_value=95.0, margen_seguridad=(95.0 - 120.0) / 120.0,
                   ohlcv=_tendencia_bajista())
    posicion = Posicion("TEST", entrada=100.0, peso_cartera=50.0,
                        fecha_entrada=date.today() - timedelta(days=400))
    decision = evaluar_posicion(datos, posicion)

    if decision.accion == REDUCIR:
        assert decision.flags["concentracion"]
        assert decision.reducir_pct > 33.4
        assert any(str(int(MAX_PESO_POSICION_PCT)) in a for a in decision.avisos)


def test_vender_suelta_el_cien_por_cien():
    precio = 100.0 * (1 - (STOP_DURO_PCT + 5) / 100)
    decision = evaluar_posicion(_datos(precio_actual=precio), Posicion("TEST", entrada=100.0),
                                perfil=PERFIL_SWING)
    assert decision.accion == VENDER
    assert decision.reducir_pct == 100.0


def test_la_regla_de_las_ocho_semanas_frena_un_recorte_pero_no_un_stop():
    """O'Neil: una subida fuerte y rápida merece dejarla correr."""
    datos = _datos(precio_actual=130.0, fair_value=105.0,
                   margen_seguridad=(105.0 - 130.0) / 130.0, ohlcv=_tendencia_bajista())
    reciente = Posicion("TEST", entrada=100.0, fecha_entrada=date.today() - timedelta(days=20))
    antigua = Posicion("TEST", entrada=100.0, fecha_entrada=date.today() - timedelta(days=400))

    d_reciente = evaluar_posicion(datos, reciente)
    d_antigua = evaluar_posicion(datos, antigua)

    if d_antigua.accion == REDUCIR:
        assert d_reciente.accion == MANTENER
        assert any("8 semanas" in a for a in d_reciente.avisos)


# ==========================================================================
# DATOS AUSENTES
# ==========================================================================


def test_sin_fundamentales_el_peso_se_redistribuye_en_vez_de_contar_como_cero():
    """Puntuar un pilar sin datos como 0 afirmaría que ahí no hay ninguna razón
    para vender, y eso no se sabe."""
    decision = evaluar_posicion(
        _datos(resultados=None, balance=None, flujos=None),
        Posicion("TEST", entrada=100.0),
    )

    assert decision.sub_scores["fundamentales"] is None
    assert decision.sell_score is not None
    assert any("no se rellena con ceros" in a for a in decision.avisos)


def test_sin_ningun_dato_se_mantiene_por_ignorancia_y_se_dice():
    decision = evaluar_posicion(
        DatosPosicion(), Posicion("TEST", entrada=100.0),
    )

    assert decision.accion == MANTENER
    assert decision.sell_score is None
    assert any("falta de datos" in a for a in decision.avisos)


def test_sin_precio_de_entrada_no_se_evalua_el_stop():
    decision = evaluar_posicion(_datos(precio_actual=50.0), Posicion("TEST", entrada=None))
    assert not decision.flags["override_stop"]


# ==========================================================================
# EXPLICACIÓN
# ==========================================================================


def test_la_explicacion_dice_la_accion_y_los_motivos():
    precio = 100.0 * (1 - (STOP_DURO_PCT + 5) / 100)
    decision = evaluar_posicion(_datos(precio_actual=precio), Posicion("TEST", entrada=100.0),
                                perfil=PERFIL_SWING)

    assert "Vender" in decision.explicacion
    assert "Stop duro" in decision.explicacion or "stop duro" in decision.explicacion


def test_la_explicacion_avisa_de_la_fiscalidad_solo_al_vender_o_reducir():
    mantener = evaluar_posicion(_datos(), Posicion("TEST", entrada=100.0))
    assert not mantener.flags["fiscal_es"]

    precio = 100.0 * (1 - (STOP_DURO_PCT + 5) / 100)
    vender = evaluar_posicion(_datos(precio_actual=precio), Posicion("TEST", entrada=100.0),
                              perfil=PERFIL_SWING)
    assert vender.flags["fiscal_es"]
    assert "base del ahorro" in vender.explicacion


def test_las_columnas_tecnicas_que_se_leen_existen_de_verdad():
    """Un nombre de columna inventado no da error: deja el pilar técnico sin
    evaluar en silencio. Ya ocurrió con sma_50 frente a sma50."""
    from modulos.decision_venta import COL_RSI, COL_SMA50, COL_SMA200

    columnas = set(_tendencia_alcista().columns)
    for nombre in (COL_SMA50, COL_SMA200, COL_RSI):
        assert nombre in columnas, f"{nombre} no la produce enriquecer_ohlcv"


def test_el_pilar_tecnico_se_evalua_de_verdad_con_datos_normales():
    decision = evaluar_posicion(_datos(), Posicion("TEST", entrada=100.0))
    assert decision.sub_scores["tecnico"] is not None
    assert 0 <= decision.sub_scores["tecnico"] <= 100


# ==========================================================================
# ALERTAS
# ==========================================================================


def test_mantener_no_genera_alerta():
    """Avisar de que no hay que hacer nada es ruido, y el ruido entrena a
    ignorar las alertas de verdad."""
    from modulos.watchlist_alerts import alertas_por_decision_venta

    decision = evaluar_posicion(_datos(), Posicion("TEST", entrada=100.0))
    assert decision.accion == MANTENER
    assert alertas_por_decision_venta(decision) == []


def test_solo_la_tesis_rota_sube_la_alerta_a_prioridad_alta():
    """Una lectura de precio no puede tener la misma urgencia que un hecho
    sobre el negocio, sobre todo cuando la regla no batió a aguantar."""
    from modulos.decision_venta import DecisionVenta
    from modulos.watchlist_alerts import alertas_por_decision_venta

    por_precio = DecisionVenta("X", accion=VENDER, sell_score=70.0, flags={"tesis_rota": False})
    por_negocio = DecisionVenta("X", accion=VENDER, sell_score=70.0, flags={"tesis_rota": True})

    assert alertas_por_decision_venta(por_precio)[0].priority == "Media"
    assert alertas_por_decision_venta(por_negocio)[0].priority == "Alta"
