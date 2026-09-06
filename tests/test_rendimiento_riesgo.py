"""¿Queda selección tras descontar el riesgo? Alfa, beta y concentración.

Sin red. Las series se construyen con alfa y beta INYECTADOS para comprobar que
la regresión los recupera: si no los recupera sobre datos donde se conoce la
respuesta, tampoco sirve sobre datos reales.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.config import LONGITUD_BLOQUE_BOOTSTRAP, TIPO_LIBRE_RIESGO_FALLBACK
from modulos.rendimiento_riesgo import (
    CRITERIO, SESIONES_ANIO, analizar, benchmark_vol_matched, bootstrap_bloques,
    descomponer_exceso, emitir_veredicto, medir_concentracion, regresion_capm,
    serie_libre_de_riesgo,
)

N = 800
FECHAS = pd.bdate_range("2023-01-02", periods=N)
TIPO_DIARIO = 0.02 / SESIONES_ANIO       # 2% anual, constante


def _series_sinteticas(alfa_anual: float, beta: float, semilla: int = 7,
                       ruido: float = 0.004) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Construye cartera = rf + beta·(bench − rf) + alfa + ruido."""
    rng = np.random.default_rng(semilla)
    r_f = pd.Series(TIPO_DIARIO, index=FECHAS)
    r_b = pd.Series(rng.normal(0.0004, 0.010, N), index=FECHAS)

    alfa_diario = (1 + alfa_anual) ** (1 / SESIONES_ANIO) - 1
    r_p = r_f + beta * (r_b - r_f) + alfa_diario + rng.normal(0, ruido, N)
    return r_p, r_b, r_f


@dataclass
class _Atribucion:
    ticker: str
    alfa_eur: float


class _RendimientoFalso:
    """Imita lo justo de RendimientoCartera que consume este módulo."""

    def __init__(self, r_p: pd.Series, r_b: pd.Series, atribucion=None):
        self.series = pd.DataFrame({
            "unitizada_cartera": 100 * (1 + r_p).cumprod(),
            "unitizada_benchmark": 100 * (1 + r_b).cumprod(),
        })
        self.atribucion = atribucion or []


# ==========================================================================
# BOOTSTRAP POR BLOQUES
# ==========================================================================


def test_el_bootstrap_por_bloques_devuelve_un_intervalo_que_contiene_la_media():
    rng = np.random.default_rng(3)
    datos = rng.normal(0.05, 0.02, 500)
    bajo, alto = bootstrap_bloques(datos, lambda m: float(m[:, 0].mean()), remuestreos=1500)

    assert bajo < 0.05 < alto


def test_el_bootstrap_por_bloques_es_mas_ancho_que_el_iid_con_autocorrelacion():
    """La razón de ser del método: con retornos autocorrelacionados, el IID da
    un intervalo artificialmente estrecho y una serie sin señal puede aparentar
    significación."""
    rng = np.random.default_rng(11)
    ruido = rng.normal(0, 0.01, 600)
    # AR(1) fuerte: cada valor arrastra al siguiente.
    serie = np.zeros(600)
    for i in range(1, 600):
        serie[i] = 0.85 * serie[i - 1] + ruido[i]

    por_bloques = bootstrap_bloques(serie, lambda m: float(m[:, 0].mean()),
                                    longitud=20, remuestreos=1500)
    iid = bootstrap_bloques(serie, lambda m: float(m[:, 0].mean()),
                            longitud=1, remuestreos=1500)

    ancho_bloques = por_bloques[1] - por_bloques[0]
    ancho_iid = iid[1] - iid[0]
    assert ancho_bloques > ancho_iid * 1.5, (
        f"el bootstrap por bloques debe ser más ancho ({ancho_bloques:.5f} vs {ancho_iid:.5f})"
    )


def test_una_serie_demasiado_corta_no_produce_intervalo():
    """Mejor no dar intervalo que darlo sobre ocho observaciones."""
    bajo, alto = bootstrap_bloques(np.arange(8.0), lambda m: float(m[:, 0].mean()))
    assert np.isnan(bajo) and np.isnan(alto)


# ==========================================================================
# TIPO LIBRE DE RIESGO
# ==========================================================================


def test_sin_proxy_se_usa_la_constante_y_se_avisa():
    """El tipo entra en el vol-matched y en el alfa: sustituirlo en silencio
    cambiaría el veredicto sin dejar rastro."""
    serie, avisos = serie_libre_de_riesgo(FECHAS, None)

    assert len(serie) == len(FECHAS)
    assert float(serie.iloc[0]) == pytest.approx((1 + TIPO_LIBRE_RIESGO_FALLBACK) ** (1 / SESIONES_ANIO) - 1)
    assert any("constante" in a for a in avisos)


def test_con_proxy_se_derivan_los_retornos_de_su_precio():
    precios = pd.Series(np.linspace(100.0, 102.0, len(FECHAS)), index=FECHAS)
    serie, avisos = serie_libre_de_riesgo(FECHAS, precios)

    assert not any("constante" in a for a in avisos)
    assert float(serie.sum()) > 0


# ==========================================================================
# VOL-MATCHING
# ==========================================================================


def test_el_vol_matched_iguala_la_volatilidad_con_una_k_conocida():
    """Con la cartera al doble de volatilidad que el índice, k debe salir 2."""
    r_p, r_b, r_f = _series_sinteticas(alfa_anual=0.0, beta=2.0, ruido=0.0)
    vm = benchmark_vol_matched(r_p, r_b, r_f)

    assert vm is not None
    assert vm.k == pytest.approx(2.0, abs=0.02)
    assert vm.vol_cartera_pct == pytest.approx(vm.vol_benchmark_pct * 2.0, rel=0.02)


def test_sin_alfa_el_vol_matched_iguala_a_la_cartera():
    """Si el exceso es solo beta, igualar el riesgo debe igualar el retorno: no
    queda nada que atribuir a la selección."""
    r_p, r_b, r_f = _series_sinteticas(alfa_anual=0.0, beta=1.8, ruido=0.0)
    vm = benchmark_vol_matched(r_p, r_b, r_f)

    assert vm.cagr_cartera_pct == pytest.approx(vm.cagr_volmatched_pct, abs=0.6)
    assert abs(vm.diferencia_pct) < 1.0


def test_con_alfa_positivo_la_cartera_bate_al_vol_matched():
    r_p, r_b, r_f = _series_sinteticas(alfa_anual=0.10, beta=1.2, ruido=0.0)
    vm = benchmark_vol_matched(r_p, r_b, r_f)

    assert vm.cartera_gana
    assert vm.diferencia_pct > 5.0


def test_el_vol_matched_necesita_muestra_suficiente():
    corta = pd.Series([0.01, -0.01], index=FECHAS[:2])
    assert benchmark_vol_matched(corta, corta, corta) is None


# ==========================================================================
# REGRESIÓN CAPM
# ==========================================================================


def test_la_regresion_recupera_el_alfa_y_la_beta_inyectados():
    """Prueba central: si no los recupera donde se conoce la respuesta, no
    sirve donde no se conoce."""
    r_p, r_b, r_f = _series_sinteticas(alfa_anual=0.08, beta=1.5, ruido=0.002)
    capm = regresion_capm(r_p, r_b, r_f)

    assert capm is not None
    assert capm.beta == pytest.approx(1.5, abs=0.05)
    assert capm.alfa_anual_pct == pytest.approx(8.0, abs=2.5)
    assert capm.r2 > 0.5


def test_una_cartera_que_es_el_indice_da_beta_uno_y_alfa_cero():
    r_p, r_b, r_f = _series_sinteticas(alfa_anual=0.0, beta=1.0, ruido=0.0)
    capm = regresion_capm(r_p, r_b, r_f)

    assert capm.beta == pytest.approx(1.0, abs=0.02)
    assert capm.alfa_anual_pct == pytest.approx(0.0, abs=1.0)
    assert capm.r2 > 0.99


def test_con_mucho_ruido_el_intervalo_del_alfa_cruza_cero():
    """El caso que se espera con una cartera real de tres posiciones: alfa
    puntual grande pero intervalo que no permite afirmar nada."""
    r_p, r_b, r_f = _series_sinteticas(alfa_anual=0.05, beta=1.5, ruido=0.030)
    capm = regresion_capm(r_p, r_b, r_f)

    bajo, alto = capm.ic_alfa
    assert bajo < 0 < alto
    assert not capm.alfa_significativo


def test_el_alfa_se_anualiza_componiendo_no_multiplicando():
    """Multiplicar por 252 sobreestima: 0,04% diario son 10,6% anual, no 10,1%."""
    r_p, r_b, r_f = _series_sinteticas(alfa_anual=0.12, beta=1.0, ruido=0.0)
    capm = regresion_capm(r_p, r_b, r_f)

    assert capm.alfa_anual_pct == pytest.approx(12.0, abs=0.5)


def test_el_information_ratio_relaciona_retorno_activo_con_tracking_error():
    r_p, r_b, r_f = _series_sinteticas(alfa_anual=0.10, beta=1.0, ruido=0.004)
    capm = regresion_capm(r_p, r_b, r_f)

    assert capm.tracking_error_pct > 0
    esperado = capm.retorno_activo_pct / capm.tracking_error_pct
    assert capm.information_ratio == pytest.approx(esperado, rel=1e-6)


# ==========================================================================
# DESCOMPOSICIÓN
# ==========================================================================


def test_la_descomposicion_suma_el_exceso_total():
    """Si beta + alfa + residuo no suman el exceso, se está perdiendo o
    duplicando una parte por el camino."""
    r_p, r_b, r_f = _series_sinteticas(alfa_anual=0.06, beta=1.6, ruido=0.003)
    capm = regresion_capm(r_p, r_b, r_f)
    d = descomponer_exceso(capm, r_p, r_b, r_f)

    assert d is not None
    assert d.por_beta_pct + d.por_alfa_pct + d.residual_pct == pytest.approx(
        d.exceso_total_pct, abs=1e-6
    )


def test_con_beta_alta_y_sin_alfa_el_exceso_es_casi_todo_beta():
    r_p, r_b, r_f = _series_sinteticas(alfa_anual=0.0, beta=2.0, ruido=0.0)
    capm = regresion_capm(r_p, r_b, r_f)
    d = descomponer_exceso(capm, r_p, r_b, r_f)

    assert abs(d.por_alfa_pct) < abs(d.por_beta_pct), (
        "un exceso conseguido con beta no puede atribuirse a la selección"
    )


def test_el_texto_de_la_descomposicion_es_legible():
    r_p, r_b, r_f = _series_sinteticas(alfa_anual=0.06, beta=1.4)
    d = descomponer_exceso(regresion_capm(r_p, r_b, r_f), r_p, r_b, r_f)
    assert "selección" in d.como_texto()


# ==========================================================================
# CONCENTRACIÓN
# ==========================================================================


def test_el_herfindahl_detecta_que_todo_cuelga_de_un_nombre():
    concentrada = medir_concentracion([
        _Atribucion("GOOG", 566.0), _Atribucion("AAPL", 39.0), _Atribucion("NVDA", 32.0),
    ])
    assert concentrada.mayor_ticker == "GOOG"
    assert concentrada.cuota_mayor_pct > 85
    assert concentrada.cuelga_de_un_nombre


def test_un_resultado_repartido_no_se_marca_concentrado():
    repartida = medir_concentracion([
        _Atribucion("A", 100.0), _Atribucion("B", 100.0),
        _Atribucion("C", 100.0), _Atribucion("D", 100.0),
    ])
    assert repartida.herfindahl == pytest.approx(0.25)
    assert not repartida.cuelga_de_un_nombre


def test_la_concentracion_usa_el_valor_absoluto_del_alfa():
    """Una posición que resta mucho concentra el resultado igual que una que
    suma mucho; con alfas netos podrían cancelarse y aparentar reparto."""
    c = medir_concentracion([_Atribucion("MALA", -900.0), _Atribucion("BUENA", 100.0)])

    assert c.mayor_ticker == "MALA"
    assert c.cuelga_de_un_nombre


def test_sin_atribucion_no_hay_concentracion():
    assert medir_concentracion([]) is None


# ==========================================================================
# VEREDICTO
# ==========================================================================


def _capm_falso(alfa, ic):
    from modulos.rendimiento_riesgo import ResultadoCAPM

    return ResultadoCAPM(alfa_anual_pct=alfa, ic_alfa=ic, beta=1.4, ic_beta=(1.0, 1.8),
                         r2=0.7, information_ratio=0.5, tracking_error_pct=10.0,
                         retorno_activo_pct=5.0, sesiones=600)


def _vol_falso(cartera, vm):
    from modulos.rendimiento_riesgo import VolMatched

    return VolMatched(k=1.5, vol_cartera_pct=25.0, vol_benchmark_pct=16.0,
                      cagr_cartera_pct=cartera, cagr_benchmark_pct=12.0,
                      cagr_volmatched_pct=vm, diferencia_pct=cartera - vm)


def test_hay_evidencia_solo_si_se_cumplen_las_tres_condiciones():
    v = emitir_veredicto(
        _capm_falso(8.0, (2.0, 14.0)), _vol_falso(30.0, 22.0),
        _capm_falso(5.0, (-1.0, 11.0)), _vol_falso(25.0, 20.0),
    )
    assert v.criterio_a and v.criterio_b and v.criterio_c
    assert v.hay_evidencia


def test_un_intervalo_que_cruza_cero_no_es_evidencia():
    v = emitir_veredicto(
        _capm_falso(8.0, (-3.0, 19.0)), _vol_falso(30.0, 22.0),
        _capm_falso(5.0, (-1.0, 11.0)), _vol_falso(25.0, 20.0),
    )
    assert not v.criterio_a
    assert not v.hay_evidencia
    assert "cruza cero" in v.motivo


def test_perder_contra_el_vol_matched_no_es_evidencia():
    v = emitir_veredicto(
        _capm_falso(8.0, (2.0, 14.0)), _vol_falso(30.0, 34.0),
        _capm_falso(5.0, (1.0, 9.0)), _vol_falso(25.0, 20.0),
    )
    assert not v.criterio_b
    assert not v.hay_evidencia


def test_si_la_ventaja_desaparece_sin_la_mayor_posicion_no_es_evidencia():
    v = emitir_veredicto(
        _capm_falso(8.0, (2.0, 14.0)), _vol_falso(30.0, 22.0),
        _capm_falso(-4.0, (-9.0, 1.0)), _vol_falso(15.0, 18.0),
    )
    assert not v.criterio_c
    assert not v.hay_evidencia
    assert "mayor posición" in v.motivo


def test_el_motivo_del_veredicto_negativo_enumera_lo_que_falla():
    v = emitir_veredicto(None, None, None, None)
    assert not v.hay_evidencia
    assert "Insuficiente evidencia" in v.motivo


def test_el_criterio_esta_declarado_y_tiene_tres_condiciones():
    """Si alguien lo relaja después de ver resultados, este test lo delata."""
    assert set(CRITERIO) == {"a", "b", "c"}


# ==========================================================================
# ORQUESTACIÓN
# ==========================================================================


def test_el_analisis_completo_usa_la_serie_unitizada():
    r_p, r_b, _ = _series_sinteticas(alfa_anual=0.06, beta=1.3)
    rendimiento = _RendimientoFalso(r_p, r_b, [_Atribucion("A", 100.0), _Atribucion("B", 50.0)])

    resultado = analizar(rendimiento)

    assert resultado.capm is not None
    assert resultado.vol_matched is not None
    assert resultado.concentracion is not None
    assert resultado.veredicto is not None


def test_sin_serie_unitizada_se_avisa_en_vez_de_calcular_sobre_el_valor():
    class SinUnitizar:
        series = pd.DataFrame({"valor_cartera": [100.0, 110.0]})
        atribucion: list = []

    resultado = analizar(SinUnitizar())
    assert resultado.capm is None
    assert any("unitizada" in a for a in resultado.avisos)


def test_el_analisis_es_serializable_a_json():
    import json

    r_p, r_b, _ = _series_sinteticas(alfa_anual=0.04, beta=1.2)
    resultado = analizar(_RendimientoFalso(r_p, r_b, [_Atribucion("A", 10.0)]))
    assert '"veredicto"' in json.dumps(resultado.to_dict(), default=str)
