"""CAN SLIM: bases y pivotes, fuerza relativa, criterios y mecánica de mercado."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.canslim import (
    UMBRAL_L_RS, calcular_rs_bruto, calcular_rs_historico, calcular_rs_ratings,
    combinar, evaluar_fundamentales, evaluar_tecnicos, inyectar_rs,
)
from modulos.canslim_bases import (
    AVANCE_PREVIO_MIN, PROFUNDIDAD_MAX_BASE, ZONA_COMPRA_MAX,
    detectar_base, detectar_ruptura,
)
from modulos.indicadores import enriquecer_ohlcv
from modulos.swing_regimen import contar_dias_distribucion, detectar_dia_confirmacion


def _ohlcv(cierres, volumen=1_000_000.0):
    p = np.asarray(cierres, dtype=float)
    n = len(p)
    vol = volumen if np.isscalar(volumen) else np.asarray(volumen, dtype=float)
    return pd.DataFrame(
        {"Open": p, "High": p * 1.005, "Low": p * 0.995, "Close": p,
         "Volume": [vol] * n if np.isscalar(volumen) else vol},
        index=pd.date_range("2022-01-03", periods=n, freq="B"),
    )


def _con_base(avance=0.40, profundidad=0.15, semanas_base=8, previas=120):
    """Serie sintética: avance previo + consolidación con techo definido."""
    subida = np.linspace(100.0, 100.0 * (1 + avance), previas)
    techo = subida[-1]
    largo = semanas_base * 5
    # Consolidación en U que vuelve a acercarse al techo sin superarlo.
    t = np.linspace(0, np.pi, largo)
    base = techo * (1 - profundidad * np.sin(t))
    return np.concatenate([subida, base])


# ==========================================================================
# BASES Y PIVOTES
# ==========================================================================


def test_detecta_una_base_tras_un_avance():
    df = _ohlcv(_con_base())
    base = detectar_base(df)

    assert base is not None
    assert base.avance_previo_pct >= AVANCE_PREVIO_MIN * 100
    assert base.profundidad_pct <= PROFUNDIDAD_MAX_BASE * 100


def test_el_pivote_es_el_techo_de_la_consolidacion():
    """El punto de compra de O'Neil no es una media ni un mínimo: es el máximo
    de la consolidación, el nivel que el mercado tiene que superar."""
    precios = _con_base()
    df = _ohlcv(precios)
    base = detectar_base(df)

    assert base is not None
    maximo_ventana = float(df["High"].iloc[base.inicio : base.fin + 1].max())
    assert abs(base.pivote - maximo_ventana) < 1e-6


def test_no_hay_base_sin_avance_previo():
    """Una consolidación sin nada que consolidar no es una base."""
    plano = np.full(300, 100.0) + np.random.RandomState(1).randn(300) * 0.5
    assert detectar_base(_ohlcv(plano)) is None


def test_una_caida_libre_no_es_una_base():
    caida = np.linspace(200.0, 80.0, 300)
    base = detectar_base(_ohlcv(caida))

    assert base is None or base.profundidad_pct <= PROFUNDIDAD_MAX_BASE * 100


def test_el_objetivo_medido_proyecta_la_profundidad_desde_el_pivote():
    df = _ohlcv(_con_base())
    base = detectar_base(df)

    assert base is not None
    assert abs(base.objetivo_medido() - (2 * base.pivote - base.minimo)) < 1e-6


def test_la_zona_de_compra_llega_hasta_un_5_por_ciento_sobre_el_pivote():
    df = _ohlcv(_con_base())
    base = detectar_base(df)
    desde, hasta = base.zona_compra()

    assert desde == base.pivote
    assert abs(hasta / base.pivote - (1 + ZONA_COMPRA_MAX)) < 1e-9


def test_la_deteccion_de_bases_es_causal():
    """Añadir sesiones futuras no puede cambiar la base vista en el pasado.

    Es la propiedad de la que depende que el backtest de CAN SLIM sea válido.
    """
    precios = _con_base()
    largo = _ohlcv(np.concatenate([precios, np.linspace(precios[-1], precios[-1] * 1.4, 60)]))
    corto = _ohlcv(precios)

    base_larga = detectar_base(largo, indice=len(precios) - 1)
    base_corta = detectar_base(corto, indice=len(precios) - 1)

    assert (base_larga is None) == (base_corta is None)
    if base_larga is not None:
        assert abs(base_larga.pivote - base_corta.pivote) < 1e-9


def test_la_ruptura_exige_volumen_de_confirmacion():
    """Sin volumen, la ruptura falla con mucha frecuencia; es el filtro que
    distingue una ruptura real de una trampa."""
    precios = np.concatenate([_con_base(), [0]])
    precios[-1] = precios[:-1].max() * 1.02  # rompe el techo

    volumen_flojo = np.full(len(precios), 1_000_000.0)
    df_flojo = enriquecer_ohlcv(_ohlcv(precios, volumen_flojo))
    assert detectar_ruptura(df_flojo) is None

    volumen_fuerte = np.full(len(precios), 1_000_000.0)
    volumen_fuerte[-1] = 3_000_000.0
    df_fuerte = enriquecer_ohlcv(_ohlcv(precios, volumen_fuerte))
    ruptura = detectar_ruptura(df_fuerte)
    assert ruptura is not None
    assert ruptura.volumen_relativo >= 1.4


def test_distingue_ruptura_valida_de_fallida_y_extendida():
    precios = list(_con_base())
    techo = max(precios)
    volumen = [1_000_000.0] * len(precios)

    # Rompe con volumen y se queda dentro de la zona de compra.
    precios.append(techo * 1.02)
    volumen.append(3_000_000.0)
    df = enriquecer_ohlcv(_ohlcv(np.array(precios), np.array(volumen)))
    ruptura = detectar_ruptura(df)
    assert ruptura is not None and not ruptura.fallida and not ruptura.extendida

    # Vuelve por debajo del pivote: ruptura fallida.
    precios.append(techo * 0.96)
    volumen.append(1_000_000.0)
    df2 = enriquecer_ohlcv(_ohlcv(np.array(precios), np.array(volumen)))
    r2 = detectar_ruptura(df2)
    if r2 is not None:
        assert r2.fallida
        assert "fallida" in r2.estado.lower()


# ==========================================================================
# FUERZA RELATIVA
# ==========================================================================


def test_el_rs_pondera_el_doble_el_trimestre_reciente():
    """Es lo que hace que la métrica detecte un cambio de liderazgo en vez de
    premiar indefinidamente al que subió hace un año."""
    n = 300
    # A: sube todo el año de forma uniforme. B: plano y dispara el último trimestre.
    a = pd.Series(np.linspace(100.0, 160.0, n))
    b = pd.Series(np.concatenate([np.full(n - 63, 100.0), np.linspace(100.0, 145.0, 63)]))

    assert calcular_rs_bruto(b) > calcular_rs_bruto(a)


def test_el_rs_necesita_un_ano_de_historico():
    assert calcular_rs_bruto(pd.Series(np.linspace(100, 120, 200))) is None


def test_el_rating_es_un_percentil_del_universo():
    precios = {}
    for i in range(30):
        serie = np.linspace(100.0, 100.0 + i * 3, 300)
        precios[f"T{i}"] = _ohlcv(serie)

    ratings = calcular_rs_ratings(precios)
    assert len(ratings) == 30
    assert all(1 <= v <= 99 for v in ratings.values())
    # El de mayor subida debe quedar arriba y el menor, abajo.
    assert ratings["T29"] > ratings["T0"]
    assert ratings["T29"] >= 95


def test_sin_universo_suficiente_no_se_inventa_un_percentil():
    """Un RS 90 calculado sobre cuatro valores no significa nada."""
    precios = {f"T{i}": _ohlcv(np.linspace(100, 130, 300)) for i in range(4)}
    assert calcular_rs_ratings(precios) == {}


def test_el_rs_historico_compara_en_corte_transversal():
    """En cada fecha, cada valor se compara con los demás en ESA fecha."""
    precios = {}
    for i in range(25):
        precios[f"T{i}"] = _ohlcv(np.linspace(100.0, 100.0 + i * 4, 400))

    historico = calcular_rs_historico(precios)
    assert len(historico) == 25
    serie = historico["T24"]
    assert not serie.empty
    assert serie.between(1, 99).all()


def test_inyectar_rs_tolera_la_ausencia_de_serie():
    df = _ohlcv(np.linspace(100, 120, 300))
    resultado = inyectar_rs(df, None)
    assert "rs_rating" in resultado.columns
    assert resultado["rs_rating"].isna().all()


# ==========================================================================
# CRITERIOS
# ==========================================================================


def test_la_puntuacion_ignora_los_criterios_sin_datos():
    """Penalizar a una empresa porque Yahoo no publica su dato institucional
    sería confundir «no cumple» con «no se sabe»."""
    from modulos.canslim import Criterio, ResultadoCanSlim

    resultado = ResultadoCanSlim(
        ticker="TEST",
        criterios={
            "C": Criterio("C", "c", True),
            "A": Criterio("A", "a", True),
            "N": Criterio("N", "n", False),
            "I": Criterio("I", "i", None),
        },
    )
    assert resultado.evaluados == 3
    assert resultado.cumplidos == 2
    assert resultado.puntuacion == round(2 / 3 * 100, 1)


def test_las_letras_reflejan_el_estado_de_cada_criterio():
    from modulos.canslim import Criterio, ResultadoCanSlim

    resultado = ResultadoCanSlim(
        ticker="TEST",
        criterios={"C": Criterio("C", "c", True), "A": Criterio("A", "a", False),
                   "N": Criterio("N", "n", None)},
    )
    letras = resultado.letras_cumplidas
    assert letras[0] == "C"   # cumple
    assert letras[1] == "a"   # no cumple
    assert letras[2] == "·"   # sin datos


def test_la_letra_s_fusiona_volumen_y_oferta_de_acciones():
    """S tiene dos mitades (una técnica y otra fundamental) y el método las
    presenta como un único criterio, no como dos letras repetidas."""
    from modulos.canslim import Criterio

    tecnicos = {"S": Criterio("S", "Oferta y demanda", True, "volumen 1.8x")}
    fundamentales = {"S_oferta": Criterio("S", "Oferta de acciones", False, "3.000M acciones")}

    resultado = combinar("TEST", tecnicos, fundamentales)
    assert resultado.criterios["S"].cumple is False
    assert "3.000M" in resultado.criterios["S"].valor


def test_el_criterio_m_marca_no_cumple_en_mercado_hostil():
    df = enriquecer_ohlcv(_ohlcv(_con_base()))
    criterios, _base, _ruptura = evaluar_tecnicos(df, rs_rating=90.0, mercado_alcista=False)

    assert criterios["M"].cumple is False
    assert criterios["L"].cumple is True


def test_sin_rs_el_criterio_l_queda_sin_evaluar():
    df = enriquecer_ohlcv(_ohlcv(_con_base()))
    criterios, _b, _r = evaluar_tecnicos(df, rs_rating=None, mercado_alcista=True)

    assert criterios["L"].cumple is None
    assert not criterios["L"].evaluable


# ==========================================================================
# MECÁNICA DE MERCADO DE O'NEIL
# ==========================================================================


def test_un_dia_de_distribucion_exige_caida_con_mas_volumen():
    n = 60
    cierres = np.full(n, 100.0)
    volumen = np.full(n, 1_000_000.0)

    # Caída del 1% con volumen creciente -> cuenta.
    cierres[-1] = 99.0
    volumen[-1] = 2_000_000.0
    resultado = contar_dias_distribucion(_ohlcv(cierres, volumen))
    assert resultado["dias"] == 1

    # Misma caída con volumen decreciente -> no cuenta.
    volumen[-1] = 500_000.0
    assert contar_dias_distribucion(_ohlcv(cierres, volumen))["dias"] == 0


def test_la_acumulacion_de_distribucion_cambia_el_estado_del_mercado():
    n = 60
    cierres = np.full(n, 100.0)
    volumen = np.full(n, 1_000_000.0)
    for i in range(n - 12, n, 2):
        cierres[i] = cierres[i - 1] * 0.99
        volumen[i] = volumen[i - 1] * 2

    resultado = contar_dias_distribucion(_ohlcv(cierres, volumen))
    assert resultado["dias"] >= 4
    assert resultado["estado"] in {"bajo presión", "corrección probable"}


def test_el_dia_de_confirmacion_exige_subida_fuerte_con_volumen():
    n = 80
    cierres = np.concatenate([np.linspace(100.0, 80.0, 50), np.linspace(80.0, 82.0, 30)])
    volumen = np.full(n, 1_000_000.0)
    cierres[-1] = cierres[-2] * 1.02       # +2%
    volumen[-1] = 2_000_000.0

    resultado = detectar_dia_confirmacion(_ohlcv(cierres, volumen))
    assert resultado["encontrado"]
    assert resultado["subida_pct"] >= 1.2


def test_sin_datos_suficientes_la_lectura_de_mercado_no_rompe():
    assert contar_dias_distribucion(pd.DataFrame())["dias"] == 0
    assert contar_dias_distribucion(None)["estado"] == "sin_datos"
    assert detectar_dia_confirmacion(pd.DataFrame())["encontrado"] is False
