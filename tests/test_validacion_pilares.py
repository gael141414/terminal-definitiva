"""Validación point-in-time de los pilares de valoración y fundamentales.

Sin red: los puntos de congelación y la reconstrucción se inyectan.
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

from modulos.validacion_pilares import (
    HORIZONTES, SIGNO_ESPERADO, ObservacionPilar, construir_observaciones,
    medir_poder_predictivo, tabla_por_decil,
)


def _precios(n: int = 900, inicio: float = 100.0, fin: float = 200.0) -> pd.Series:
    return pd.Series(np.linspace(inicio, fin, n),
                     index=pd.date_range("2020-01-01", periods=n, freq="B"))


def _cuentas_as_reported(assets=1000.0, neto=100.0):
    """Forma as-reported: 'concept' en columna, ejercicios en columnas."""
    def tabla(filas):
        return pd.DataFrame(
            [{"concept": k, "2022": v[0], "2023": v[1]} for k, v in filas.items()]
        )
    balance = tabla({
        "assets": (assets * 0.9, assets),
        "liabilities": (400.0, 380.0),
        "assetscurrent": (450.0, 500.0),
        "liabilitiescurrent": (190.0, 185.0),
        "retainedearningsaccumulateddeficit": (250.0, 300.0),
        "stockholdersequity": (520.0, 600.0),
        "accountsreceivablenetcurrent": (95.0, 100.0),
        "propertyplantandequipmentnet": (290.0, 300.0),
        "longtermdebtnoncurrent": (170.0, 150.0),
        "weightedaveragenumberofdilutedsharesoutstanding": (1000.0, 1000.0),
    })
    resultados = tabla({
        "revenuefromcontractwithcustomerexcludingassessedtax": (700.0, 800.0),
        "costofgoodsandservicessold": (360.0, 400.0),
        "operatingincomeloss": (120.0, 150.0),
        "netincomeloss": (neto * 0.8, neto),
        "sellinggeneralandadministrativeexpense": (110.0, 120.0),
    })
    flujos = tabla({
        "netcashprovidedbyusedinoperatingactivities": (110.0, 140.0),
        "depreciationdepletionandamortization": (45.0, 50.0),
    })
    return resultados, balance, flujos


def _reconstruir(ticker, as_of):
    return _cuentas_as_reported()


# ==========================================================================
# SIN LOOK-AHEAD
# ==========================================================================


def test_la_observacion_se_situa_tras_el_filing_no_en_el_cierre_del_ejercicio():
    """Las cuentas del 31 de diciembre no son públicas ese día. Situar la
    observación ahí usaría un dato que el mercado todavía no tenía."""
    puntos = [{"ticker": "T", "fiscal_year": "2023", "filing_date": "2021-02-19",
               "as_of_date": "2021-02-22"}]
    obs = construir_observaciones("T", _precios(), puntos=puntos, reconstruir=_reconstruir)

    assert len(obs) == 1
    assert obs[0].as_of == "2021-02-22"
    assert pd.Timestamp(obs[0].as_of) > pd.Timestamp(obs[0].filing_date)


def test_el_precio_de_referencia_es_el_ultimo_ANTERIOR_a_la_fecha():
    """Tomar el precio posterior metería información futura en la observación."""
    precios = _precios()
    puntos = [{"filing_date": "2022-06-01", "as_of_date": "2022-06-02"}]
    obs = construir_observaciones("T", precios, puntos=puntos, reconstruir=_reconstruir)

    fecha = pd.Timestamp("2022-06-02")
    esperado = float(precios[precios.index <= fecha].iloc[-1])
    assert obs[0].precio == pytest.approx(esperado)


def test_solo_se_incluyen_observaciones_con_retorno_ya_realizado():
    """Una observación cuyo horizonte no ha vencido no puede entrar: sesgaría
    la muestra hacia los movimientos rápidos."""
    precios = _precios(n=300)
    ultima = precios.index[-1].strftime("%Y-%m-%d")
    puntos = [{"filing_date": ultima, "as_of_date": ultima}]

    assert construir_observaciones("T", precios, puntos=puntos, reconstruir=_reconstruir) == []


def test_se_calculan_los_tres_forenses_sobre_datos_as_reported():
    """La forma as-reported trae 'concept' en columna y etiquetas XBRL en
    minúscula: una tercera orientación que hay que normalizar."""
    puntos = [{"filing_date": "2021-02-19", "as_of_date": "2021-02-22"}]
    obs = construir_observaciones("T", _precios(), puntos=puntos, reconstruir=_reconstruir)[0]

    assert obs.piotroski is not None
    assert obs.altman is not None, "el Altman doble prima no necesita capitalización"
    assert obs.beneish is not None


def test_el_piotroski_se_normaliza_por_los_criterios_evaluados():
    puntos = [{"filing_date": "2021-02-19", "as_of_date": "2021-02-22"}]
    obs = construir_observaciones("T", _precios(), puntos=puntos, reconstruir=_reconstruir)[0]

    assert 0 <= obs.piotroski_norm <= 100
    assert obs.piotroski <= 9


def test_se_miden_los_tres_horizontes():
    puntos = [{"filing_date": "2021-01-04", "as_of_date": "2021-01-05"}]
    obs = construir_observaciones("T", _precios(), puntos=puntos, reconstruir=_reconstruir)[0]

    assert set(obs.retornos) == set(HORIZONTES), (
        "si el efecto solo aparece en un horizonte y no en los vecinos, es ruido"
    )


def test_una_reconstruccion_que_falla_no_tumba_el_resto():
    def reconstruir(ticker, as_of):
        if as_of == "2022-01-05":
            raise RuntimeError("sin datos")
        return _cuentas_as_reported()

    puntos = [{"filing_date": "2022-01-04", "as_of_date": "2022-01-05"},
              {"filing_date": "2021-01-04", "as_of_date": "2021-01-05"}]
    obs = construir_observaciones("T", _precios(), puntos=puntos, reconstruir=reconstruir)

    assert len(obs) == 1


# ==========================================================================
# MEDICIÓN
# ==========================================================================


def _observaciones(n: int, relacion: str = "positiva") -> list[ObservacionPilar]:
    rng = np.random.default_rng(4)
    valores = np.linspace(0, 100, n)
    salida = []
    for i, v in enumerate(valores):
        base = v / 500 if relacion == "positiva" else -v / 500
        salida.append(ObservacionPilar(
            ticker=f"T{i % 12}", as_of=f"2022-01-{(i % 28) + 1:02d}", filing_date="",
            piotroski_norm=float(v), altman=float(v / 20), beneish=float(-v / 30),
            percentil_multiplos=float(v),
            retornos={h: float(base + rng.normal(0, 0.01)) for h in HORIZONTES},
        ))
    return salida


def test_el_signo_esperado_esta_declarado_de_antemano():
    """Sin declararlo se podría celebrar cualquier correlación mirando después
    qué signo salió."""
    assert SIGNO_ESPERADO["piotroski_norm"] == "positivo"
    assert SIGNO_ESPERADO["beneish"] == "negativo"
    assert SIGNO_ESPERADO["percentil_multiplos"] == "negativo"


def test_con_muestra_insuficiente_no_se_publica_correlacion():
    resumen = medir_poder_predictivo(_observaciones(10))

    assert not resumen["suficiente"]
    assert "nota" in resumen
    assert "piotroski_norm" not in resumen


def test_un_pilar_que_ordena_bien_sale_coherente():
    resumen = medir_poder_predictivo(_observaciones(120, "positiva"))

    assert resumen["suficiente"]
    bloque = resumen["piotroski_norm"]
    assert bloque["252d"]["spearman"] > 0.5
    assert bloque["252d"]["coherente"]


def test_un_pilar_que_ordena_al_reves_se_marca_incoherente():
    resumen = medir_poder_predictivo(_observaciones(120, "negativa"))

    bloque = resumen["piotroski_norm"]
    assert bloque["252d"]["spearman"] < 0
    assert not bloque["252d"]["coherente"], (
        "un pilar cuyo signo es el contrario del esperado no es un hallazgo positivo"
    )


def test_la_tabla_por_quintil_separa_los_extremos():
    """Una correlación pequeña puede aun así separar los extremos, que es lo que
    importa para seleccionar."""
    tabla = tabla_por_decil(_observaciones(150, "positiva"), "piotroski_norm", 252)

    assert not tabla.empty
    assert len(tabla) == 5
    assert tabla["retorno_medio_%"].iloc[-1] > tabla["retorno_medio_%"].iloc[0]


def test_sin_observaciones_las_funciones_no_rompen():
    assert medir_poder_predictivo([])["observaciones"] == 0
    assert tabla_por_decil([], "piotroski_norm").empty
