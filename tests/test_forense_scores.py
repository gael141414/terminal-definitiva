"""Altman, Beneish y Piotroski como funciones puras.

Estas métricas vivían dentro de charts.py, entrelazadas con la construcción de
la figura. Aquí se comprueba el cálculo y, sobre todo, el comportamiento ante
datos ausentes: la versión anterior los sustituía por 0,001 y eso producía
puntuaciones altísimas —zona segura— para empresas de las que no se sabía nada.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.forense_scores import (
    ZONA_PELIGRO, ZONA_SEGURA, altman_z_score, beneish_m_score, piotroski_f_score,
)

EJERCICIOS = ["2024-12-31", "2023-12-31"]


def _df(filas: dict[str, list]) -> pd.DataFrame:
    return pd.DataFrame(filas, index=EJERCICIOS).T


def _balance_sano():
    return _df({
        "Total Assets": [1000.0, 900.0],
        "Total Liabilities Net Minority Interest": [400.0, 380.0],
        "Current Assets": [500.0, 450.0],
        "Current Liabilities": [200.0, 190.0],
        "Retained Earnings": [300.0, 250.0],
        "Stockholders Equity": [600.0, 520.0],
        "Accounts Receivable": [100.0, 95.0],
        "Net PPE": [300.0, 290.0],
        "Long Term Debt": [150.0, 170.0],
        "Ordinary Shares Number": [1000.0, 1000.0],
    })


def _resultados_sanos():
    return _df({
        "Total Revenue": [800.0, 700.0],
        "Cost Of Revenue": [400.0, 360.0],
        "EBIT": [150.0, 120.0],
        "Net Income": [100.0, 80.0],
        "Selling General And Administration": [120.0, 110.0],
    })


def _flujos_sanos():
    return _df({
        "Operating Cash Flow": [140.0, 110.0],
        "Depreciation": [50.0, 45.0],
    })


# ==========================================================================
# ALTMAN
# ==========================================================================


def test_altman_clasico_calcula_la_formula_de_los_cinco_componentes():
    z = altman_z_score(_balance_sano(), _resultados_sanos(), capitalizacion=2000.0)

    assert z.evaluable
    esperado = (1.2 * 0.30) + (1.4 * 0.30) + (3.3 * 0.15) + (0.6 * 5.0) + (1.0 * 0.80)
    assert z.valor == pytest.approx(esperado, abs=1e-6)
    assert set(z.componentes) == {"X1", "X2", "X3", "X4", "X5"}


def test_una_empresa_solida_cae_en_zona_segura():
    z = altman_z_score(_balance_sano(), _resultados_sanos(), capitalizacion=2000.0)
    assert z.zona == ZONA_SEGURA
    assert not z.en_peligro


def test_una_empresa_al_borde_de_la_quiebra_cae_en_zona_de_peligro():
    balance = _df({
        "Total Assets": [1000.0, 1000.0],
        "Total Liabilities Net Minority Interest": [1200.0, 1100.0],
        "Current Assets": [100.0, 120.0],
        "Current Liabilities": [500.0, 450.0],
        "Retained Earnings": [-400.0, -300.0],
        "Stockholders Equity": [-200.0, -100.0],
    })
    resultados = _df({"Total Revenue": [300.0, 320.0], "EBIT": [-80.0, -50.0]})

    z = altman_z_score(balance, resultados, capitalizacion=150.0)
    assert z.zona == ZONA_PELIGRO
    assert z.en_peligro


def test_sin_activo_total_no_se_inventa_una_puntuacion():
    """El fallo de la versión anterior: faltaba un dato, se sustituía por 0,001,
    y la división producía un Z-Score enorme que se leía como «zona segura»."""
    balance = _balance_sano().drop(index=["Total Assets"])

    z = altman_z_score(balance, _resultados_sanos(), capitalizacion=2000.0)

    assert z.valor is None
    assert not z.evaluable
    assert not z.en_peligro, "sin datos no se afirma ni peligro ni seguridad"
    assert "activo total" in z.campos_ausentes


def test_sin_capitalizacion_el_modelo_clasico_no_es_evaluable():
    z = altman_z_score(_balance_sano(), _resultados_sanos(), capitalizacion=None)
    assert z.valor is None
    assert "capitalización bursátil" in z.campos_ausentes


def test_la_doble_prima_no_necesita_capitalizacion():
    """Z'' usa patrimonio contable, así que sirve para no cotizadas."""
    z = altman_z_score(_balance_sano(), _resultados_sanos(), modelo="doble_prima")

    assert z.evaluable
    assert set(z.componentes) == {"X1", "X2", "X3", "X4"}, "Z'' no lleva X5"
    esperado = (6.56 * 0.30) + (3.26 * 0.30) + (6.72 * 0.15) + (1.05 * 1.5)
    assert z.valor == pytest.approx(esperado, abs=1e-6)


def test_los_dos_modelos_no_comparten_escala():
    """Comparar un Z con un Z'' no significa nada.

    Lo que los separa no es que den números distintos —eso dependería del caso—
    sino que el MISMO número cae en zonas distintas: 1,5 es peligro en la escala
    clásica (umbral 1,81) y zona gris en la doble prima (umbral 1,10).
    """
    from modulos.forense_scores import _zona_altman

    assert _zona_altman(1.5, "clasico") == ZONA_PELIGRO
    assert _zona_altman(1.5, "doble_prima") != ZONA_PELIGRO

    # Y cada objeto juzga su peligro con el umbral de su propio modelo.
    clasico = altman_z_score(_balance_sano(), _resultados_sanos(), capitalizacion=2000.0)
    doble = altman_z_score(_balance_sano(), _resultados_sanos(), modelo="doble_prima")
    assert clasico.modelo == "clasico" and doble.modelo == "doble_prima"


# ==========================================================================
# BENEISH
# ==========================================================================


def test_beneish_necesita_dos_ejercicios():
    """Mide variación entre años: con uno solo no hay nada que medir."""
    un_ano = _balance_sano().iloc[:, [0]]
    m = beneish_m_score(un_ano, _resultados_sanos().iloc[:, [0]], _flujos_sanos().iloc[:, [0]])

    assert m.valor is None
    assert not m.evaluable
    assert m.campos_ausentes


def test_beneish_devuelve_los_ocho_indices():
    m = beneish_m_score(_balance_sano(), _resultados_sanos(), _flujos_sanos())

    assert m.evaluable
    assert set(m.indices) == {"DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "LVGI", "TATA"}


def test_una_empresa_limpia_queda_por_debajo_del_umbral():
    m = beneish_m_score(_balance_sano(), _resultados_sanos(), _flujos_sanos())
    assert not m.sospechoso()


def test_inflar_cobros_y_devengos_dispara_la_sospecha():
    """Cobros disparados y beneficio muy por encima de la caja: el patrón que
    el modelo busca."""
    balance = _balance_sano().copy()
    balance.loc["Accounts Receivable"] = [400.0, 95.0]
    resultados = _resultados_sanos().copy()
    resultados.loc["Net Income"] = [400.0, 80.0]
    flujos = _flujos_sanos().copy()
    flujos.loc["Operating Cash Flow"] = [20.0, 110.0]

    m = beneish_m_score(balance, resultados, flujos)
    assert m.evaluable
    assert m.sospechoso(), f"M={m.valor} debería superar el umbral"


def test_el_umbral_de_beneish_es_configurable():
    """La literatura usa −2,22 (conservador) y −1,78 (sensible)."""
    m = beneish_m_score(_balance_sano(), _resultados_sanos(), _flujos_sanos())
    assert m.sospechoso(umbral=-99.0)
    assert not m.sospechoso(umbral=99.0)


# ==========================================================================
# PIOTROSKI
# ==========================================================================


def test_piotroski_puntua_sobre_los_criterios_evaluables():
    f = piotroski_f_score(_balance_sano(), _resultados_sanos(), _flujos_sanos())

    assert f.evaluable
    assert 0 <= f.valor <= f.evaluados <= 9


def test_una_empresa_en_mejora_puntua_alto():
    f = piotroski_f_score(_balance_sano(), _resultados_sanos(), _flujos_sanos())

    assert f.criterios["ROA positivo"]
    assert f.criterios["ROA mejora"]
    assert f.criterios["Flujo operativo positivo"]
    assert f.criterios["Apalancamiento baja"]
    assert f.valor >= 6


def test_una_empresa_en_deterioro_puntua_bajo_y_se_marca_debil():
    balance = _balance_sano().copy()
    balance.loc["Long Term Debt"] = [400.0, 150.0]        # más deuda
    balance.loc["Current Assets"] = [200.0, 450.0]        # menos liquidez
    balance.loc["Ordinary Shares Number"] = [1300.0, 1000.0]  # dilución
    resultados = _resultados_sanos().copy()
    resultados.loc["Net Income"] = [-50.0, 80.0]          # pérdidas
    resultados.loc["Cost Of Revenue"] = [700.0, 360.0]    # margen peor
    flujos = _flujos_sanos().copy()
    flujos.loc["Operating Cash Flow"] = [-30.0, 110.0]

    f = piotroski_f_score(balance, resultados, flujos)
    assert f.valor <= 3
    assert f.debil


def test_el_denominador_se_reporta_para_no_confundir_un_4_de_4_con_un_4_de_9():
    parcial = _df({"Total Assets": [1000.0, 900.0]})
    resultados = _df({"Net Income": [100.0, 80.0]})
    flujos = _df({"Operating Cash Flow": [140.0, 110.0]})

    f = piotroski_f_score(parcial, resultados, flujos)
    assert f.evaluable
    assert f.evaluados < 9
    assert f.campos_ausentes


def test_sin_ningun_dato_no_hay_puntuacion():
    vacio = pd.DataFrame()
    f = piotroski_f_score(vacio, vacio, vacio)
    assert f.valor is None
    assert not f.evaluable
