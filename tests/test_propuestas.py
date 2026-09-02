"""PEAD, validación out-of-sample, salidas, concentración y diario."""

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
from modulos.pead import DIAS_FRESCURA, SORPRESA_MINIMA_PCT, enriquecer_con_earnings, evaluar_pead
from modulos.swing_backtest import (
    MUESTRA_INSUFICIENTE, NO_SOBREVIVE, SE_DEGRADA, SOBREVIVE, _dictaminar, _fecha_de_corte,
)
from modulos.swing_concentracion import MAX_CALOR_CARTERA_PCT, analizar_concentracion, calor_cartera
from modulos.swing_salidas import MANTENER, SALIR, VIGILAR, evaluar_salida, stop_chandelier


def _precios(n=320, base=100.0, tendencia=0.15, semilla=3):
    np.random.seed(semilla)
    p = np.maximum(base + np.arange(n) * tendencia + np.random.randn(n).cumsum() * 0.3, 1.0)
    return pd.DataFrame(
        {"Open": p, "High": p * 1.01, "Low": p * 0.99, "Close": p, "Volume": [2_000_000.0] * n},
        index=pd.date_range("2023-01-02", periods=n, freq="B"),
    )


# ==========================================================================
# PEAD
# ==========================================================================


def _earnings(fechas_sorpresas):
    return pd.DataFrame(
        [{"fecha": pd.Timestamp(f), "sorpresa_pct": s, "eps_reportado": 1.0}
         for f, s in fechas_sorpresas]
    )


def test_la_informacion_de_resultados_no_aparece_antes_del_anuncio():
    """Las empresas publican tras el cierre, así que la primera sesión operable
    es la SIGUIENTE. Tratar el día del anuncio como operable sería look-ahead."""
    precios = _precios(n=250)
    fecha = precios.index[100]
    enriquecido = enriquecer_con_earnings(precios, _earnings([(fecha, 12.0)]))

    # El día del anuncio y los anteriores no saben nada.
    assert pd.isna(enriquecido["sorpresa_pct"].iloc[100])
    assert pd.isna(enriquecido["sorpresa_pct"].iloc[99])
    # La sesión siguiente sí.
    assert enriquecido["sorpresa_pct"].iloc[101] == 12.0
    assert enriquecido["dias_desde_earnings"].iloc[101] == 0


def test_la_reaccion_se_mide_sobre_la_primera_sesion_operable():
    precios = _precios(n=250)
    fecha = precios.index[100]
    enriquecido = enriquecer_con_earnings(precios, _earnings([(fecha, 10.0)]))

    esperada = (precios["Close"].iloc[101] / precios["Close"].iloc[100] - 1) * 100
    assert abs(enriquecido["reaccion_earnings_pct"].iloc[101] - esperada) < 1e-9


def test_un_anuncio_posterior_sustituye_al_anterior():
    precios = _precios(n=250)
    enriquecido = enriquecer_con_earnings(
        precios, _earnings([(precios.index[100], 8.0), (precios.index[180], 20.0)])
    )

    assert enriquecido["sorpresa_pct"].iloc[150] == 8.0
    assert enriquecido["sorpresa_pct"].iloc[200] == 20.0


def test_sin_calendario_las_columnas_quedan_vacias_sin_romper():
    precios = _precios(n=250)
    for vacio in (pd.DataFrame(), None):
        enriquecido = enriquecer_con_earnings(precios, vacio)
        assert "sorpresa_pct" in enriquecido.columns
        assert enriquecido["sorpresa_pct"].isna().all()


def test_pead_exige_sorpresa_relevante_y_reaccion_positiva():
    """Una sorpresa positiva con el precio cayendo suele significar que la guía
    decepcionó: ahí la deriva va a la baja, no al alza."""
    precios = _precios(n=320)
    base = enriquecer_ohlcv(precios)

    # Sorpresa por debajo del umbral -> no dispara.
    pequena = enriquecer_con_earnings(base, _earnings([(base.index[-3], SORPRESA_MINIMA_PCT - 1)]))
    assert evaluar_pead(pequena) is None

    # Sorpresa suficiente pero reacción negativa -> no dispara.
    con_caida = base.copy()
    con_caida.iloc[-2, con_caida.columns.get_loc("Close")] = float(con_caida["Close"].iloc[-3]) * 0.9
    negativa = enriquecer_con_earnings(con_caida, _earnings([(con_caida.index[-3], 15.0)]))
    assert evaluar_pead(negativa) is None


def test_pead_caduca_pasada_la_ventana_de_deriva():
    precios = _precios(n=320)
    base = enriquecer_ohlcv(precios)
    antiguo = enriquecer_con_earnings(
        base, _earnings([(base.index[-(DIAS_FRESCURA + 30)], 20.0)])
    )
    assert evaluar_pead(antiguo) is None


# ==========================================================================
# OUT-OF-SAMPLE
# ==========================================================================


def test_el_veredicto_distingue_degradarse_de_derrumbarse():
    assert _dictaminar({"operaciones": 100, "expectativa_r": 0.20},
                       {"operaciones": 100, "expectativa_r": 0.18}) == SOBREVIVE
    assert _dictaminar({"operaciones": 100, "expectativa_r": 0.20},
                       {"operaciones": 100, "expectativa_r": 0.05}) == SE_DEGRADA
    assert _dictaminar({"operaciones": 100, "expectativa_r": 0.20},
                       {"operaciones": 100, "expectativa_r": -0.01}) == NO_SOBREVIVE


def test_una_regla_ya_mala_en_diseno_no_puede_sobrevivir():
    """No se premia a una estrategia por ser consistentemente mala."""
    assert _dictaminar({"operaciones": 200, "expectativa_r": -0.10},
                       {"operaciones": 200, "expectativa_r": -0.02}) == NO_SOBREVIVE


def test_muestra_pequena_no_emite_veredicto():
    assert _dictaminar({"operaciones": 5, "expectativa_r": 0.5},
                       {"operaciones": 200, "expectativa_r": 0.4}) == MUESTRA_INSUFICIENTE


def test_la_fecha_de_corte_es_comun_a_todo_el_universo():
    """Un corte por valor mezclaría 2022 de unos con 2025 de otros y la
    comparación entre periodos no significaría nada."""
    precios = {
        "A": _precios(n=300),
        "B": _precios(n=300).iloc[50:],
    }
    corte = _fecha_de_corte(precios, 0.6)

    assert corte is not None
    assert precios["A"].index[0] < corte < precios["A"].index[-1]


def test_el_backtest_acotado_solo_abre_operaciones_en_la_ventana():
    from modulos.swing_backtest import backtest_estrategia

    precios = {"T": _precios(n=400)}
    completo = backtest_estrategia("pullback_tendencia", precios)
    corte = _fecha_de_corte(precios, 0.6)
    primera = backtest_estrategia("pullback_tendencia", precios, hasta=corte)
    segunda = backtest_estrategia("pullback_tendencia", precios, desde=corte)

    assert primera.total + segunda.total <= completo.total + 1  # margen por el propio día de corte
    assert all(pd.Timestamp(op.fecha_señal) <= corte for op in primera.operaciones)
    assert all(pd.Timestamp(op.fecha_señal) >= corte for op in segunda.operaciones)


# ==========================================================================
# SALIDAS
# ==========================================================================


def test_el_stop_dinamico_sube_con_el_precio_y_nunca_baja():
    df = _precios(n=300, tendencia=0.5)
    pronto = stop_chandelier(df, indice_entrada=210, indice_actual=240)
    tarde = stop_chandelier(df, indice_entrada=210, indice_actual=290)

    assert pronto is not None and tarde is not None
    assert tarde > pronto


def test_perder_el_stop_es_la_senal_mas_grave():
    df = enriquecer_ohlcv(_precios(n=300))
    precio = float(df["Close"].iloc[-1])

    decision = evaluar_salida(df, entrada=precio * 1.2, stop=precio * 1.1)
    assert decision.accion == SALIR
    assert any("stop" in m.lower() for m in decision.motivos)


def test_una_posicion_sana_no_genera_alarma():
    df = enriquecer_ohlcv(_precios(n=320, tendencia=0.3))
    precio = float(df["Close"].iloc[-1])

    decision = evaluar_salida(df, entrada=precio * 0.8, stop=precio * 0.7)
    assert decision.accion == MANTENER


def test_datos_insuficientes_no_rompen_la_evaluacion():
    assert evaluar_salida(pd.DataFrame(), entrada=100).accion == MANTENER
    assert evaluar_salida(None, entrada=100).accion == MANTENER


# ==========================================================================
# CONCENTRACIÓN
# ==========================================================================


def test_el_calor_suma_el_riesgo_de_todas_las_posiciones():
    posiciones = [
        {"acciones": 100, "entrada": 100.0, "stop": 90.0},  # 1.000 de riesgo
        {"acciones": 50, "entrada": 200.0, "stop": 190.0},  # 500 de riesgo
    ]
    assert calor_cartera(posiciones, 30_000.0) == 5.0


def test_las_posiciones_sin_stop_no_suman_riesgo_pero_se_avisan():
    """Contarlas con riesgo cero daría una falsa sensación de seguridad."""
    assert calor_cartera([{"acciones": 10, "entrada": 100.0}], 10_000.0) == 0.0

    informe = analizar_concentracion("NUEVO", {"X": {"acciones": 10, "entrada": 100.0}},
                                     capital=10_000.0, incluir_correlacion=False)
    assert any(a.tipo == "sin_stop" for a in informe.avisos)


def test_bloquea_cuando_el_riesgo_agregado_se_dispara():
    posiciones = {
        f"T{i}": {"acciones": 100, "entrada": 100.0, "stop": 90.0} for i in range(5)
    }
    informe = analizar_concentracion("NUEVO", posiciones, capital=20_000.0,
                                     riesgo_nuevo_euros=200.0, incluir_correlacion=False)

    assert informe.calor_actual_pct > MAX_CALOR_CARTERA_PCT
    assert informe.hay_bloqueo


def test_sin_posiciones_abiertas_no_hay_problema_de_concentracion():
    informe = analizar_concentracion("AAPL", {}, capital=10_000.0, incluir_correlacion=False)
    assert informe.despejado


# ==========================================================================
# DIARIO
# ==========================================================================


@pytest.fixture
def diario_aislado(tmp_path, monkeypatch):
    import modulos.diario as diario

    monkeypatch.setattr(diario, "DB_FOLDER", str(tmp_path))
    monkeypatch.setattr(diario, "DB_FILE", str(tmp_path / "diario.json"))
    return diario


def test_el_resultado_se_mide_con_el_stop_declarado_al_abrir(diario_aislado):
    """Recalcular el riesgo a posteriori permitiría maquillar el resultado."""
    idd = diario_aislado.registrar_decision("AAPL", diario_aislado.EJECUTADA, precio=100.0, stop=90.0)
    assert diario_aislado.cerrar_operacion(idd, precio_salida=120.0, motivo="Alcanzó el objetivo")

    df = diario_aislado.diario_a_dataframe()
    assert float(df.iloc[0]["resultado_r"]) == 2.0  # 20 de ganancia sobre 10 de riesgo


def test_el_corto_gana_cuando_el_precio_baja(diario_aislado):
    idd = diario_aislado.registrar_decision("XYZ", diario_aislado.EJECUTADA,
                                            direccion="corto", precio=100.0, stop=110.0)
    diario_aislado.cerrar_operacion(idd, precio_salida=80.0)

    df = diario_aislado.diario_a_dataframe()
    assert float(df.iloc[0]["resultado_r"]) == 2.0


def test_se_registran_tambien_las_descartadas(diario_aislado):
    """Sin ellas el diario tiene sesgo de supervivencia y no puede decir si tu
    filtro aporta o sólo te quita oportunidades."""
    diario_aislado.registrar_decision("AAA", diario_aislado.EJECUTADA, precio=10, stop=9)
    diario_aislado.registrar_decision("BBB", diario_aislado.DESCARTADA, motivo="No me convence")

    resumen = diario_aislado.resumen_global()
    assert resumen["descartadas"] == 1
    assert resumen["ratio_descarte"] == 50.0


def test_no_se_puede_cerrar_dos_veces(diario_aislado):
    idd = diario_aislado.registrar_decision("AAA", diario_aislado.EJECUTADA, precio=100, stop=90)
    assert diario_aislado.cerrar_operacion(idd, precio_salida=110)
    assert not diario_aislado.cerrar_operacion(idd, precio_salida=200)


def test_el_analisis_por_motivo_de_cierre_revela_el_coste_de_cada_salida(diario_aislado):
    a = diario_aislado.registrar_decision("AAA", diario_aislado.EJECUTADA,
                                          estrategia="pullback", precio=100, stop=90)
    b = diario_aislado.registrar_decision("BBB", diario_aislado.EJECUTADA,
                                          estrategia="pullback", precio=100, stop=90)
    diario_aislado.cerrar_operacion(a, precio_salida=120, motivo="Alcanzó el objetivo")
    diario_aislado.cerrar_operacion(b, precio_salida=97, motivo="Cerré por nervios / dudas")

    tabla = diario_aislado.rendimiento_por_motivo_cierre()
    nervios = tabla[tabla["Motivo de cierre"] == "Cerré por nervios / dudas"]
    assert float(nervios["Resultado medio (R)"].iloc[0]) < 0


def test_entradas_no_validas_se_ignoran(diario_aislado):
    assert diario_aislado.registrar_decision("", diario_aislado.EJECUTADA) == ""
    assert diario_aislado.registrar_decision("AAA", "estado_inventado") == ""
    assert diario_aislado.cargar_diario() == []
