"""Rendimiento de cartera frente a un benchmark de flujos igualados.

Sin red: precios y tipos de cambio mockeados con valores redondos, elegidos para
que los resultados esperados se puedan calcular A MANO y queden pre-declarados en
el propio fixture. Si el código y la aritmética de servilleta divergen, uno de
los dos está mal y el test lo dice.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.rendimiento_cartera import (
    COMPRA, VENTA, AtribucionPosicion, Transaccion, construir_series,
    serie_unitizada, siguiente_dia_habil, tipo_de_cambio_a_eur, validar_pesos, xirr,
)

# ==========================================================================
# FIXTURE: valores elegidos para que la cuenta salga redonda
# ==========================================================================

SESIONES = pd.bdate_range("2024-01-01", "2026-09-04")

# Cuatro tramos. Los cortes coinciden con las fechas de compra para que el
# precio en cada compra sea exactamente el que se ha elegido.
CORTES = [
    (pd.Timestamp("2024-01-01"), pd.Timestamp("2025-04-02")),
    (pd.Timestamp("2025-04-03"), pd.Timestamp("2026-01-14")),
    (pd.Timestamp("2026-01-15"), pd.Timestamp("2026-06-30")),
    (pd.Timestamp("2026-07-01"), pd.Timestamp("2026-12-31")),
]

PRECIOS_USD = {                      # las acciones cotizan en dólares
    "AAPL": [125.0, 125.0, 125.0, 250.0],
    "GOOG": [200.0, 200.0, 200.0, 250.0],
    "NVDA": [62.5, 62.5, 62.5, 125.0],
}
PRECIOS_PROXY_EUR = {                # los ETF ya cotizan en euros
    "SP500": [100.0, 125.0, 150.0, 200.0],
    "MSCI_WORLD": [50.0, 62.5, 75.0, 100.0],
}

EURUSD = 1.25                        # 1,25 dólares por euro -> factor 0,8

# ---- Cálculo a mano, PRE-DECLARADO --------------------------------------
# Factor a EUR = 1/1,25 = 0,8
#   AAPL 2024-01-27 (sábado) -> 2024-01-29: 125 USD x 0,8 = 100 EUR
#        500 EUR / 100 = 5,0 participaciones · final 250x0,8=200 -> 1.000 EUR
#   GOOG 2025-04-03: 200 x 0,8 = 160 EUR · 800/160 = 5,0 · final 200 -> 1.000 EUR
#   NVDA 2026-01-15: 62,5 x 0,8 = 50 EUR · 250/50 = 5,0 · final 100 -> 500 EUR
# Invertido 1.550 EUR · Cartera 2.500 EUR
#
# Benchmark 40% SP500 / 60% MSCI World, mismo dinero el mismo día:
#   500 EUR -> SP500 200/100 = 2,0 ; WORLD 300/50 = 6,0
#   800 EUR -> SP500 320/125 = 2,56 ; WORLD 480/62,5 = 7,68
#   250 EUR -> SP500 100/150 = 0,666667 ; WORLD 150/75 = 2,0
#   Totales: SP500 5,226667 ; WORLD 15,68
#   Valor final: 5,226667x200 + 15,68x100 = 1.045,33 + 1.568,00 = 2.613,33 EUR
#
# Diferencia: 2.500 - 2.613,33 = -113,33 EUR (la cartera PIERDE contra el índice)
#
# Atribución:
#   AAPL 1.000 vs 2,0x200+6,0x100 = 1.000        -> alfa    0,00
#   GOOG 1.000 vs 2,56x200+7,68x100 = 1.280      -> alfa -280,00
#   NVDA   500 vs 0,666667x200+2,0x100 = 333,33  -> alfa +166,67
#   Suma de alfas = -113,33, que debe cuadrar con la diferencia total.
INVERTIDO_ESPERADO = 1550.0
CARTERA_ESPERADA = 2500.0
BENCHMARK_ESPERADO = 2613.3333
ALFA_ESPERADO = {"AAPL": 0.0, "GOOG": -280.0, "NVDA": 166.6667}


def _escalonada(valores: list[float]) -> pd.Series:
    serie = pd.Series(index=SESIONES, dtype=float)
    for (inicio, fin), valor in zip(CORTES, valores):
        serie.loc[(serie.index >= inicio) & (serie.index <= fin)] = valor
    return serie.ffill().bfill()


def _fx() -> pd.Series:
    return pd.Series(EURUSD, index=SESIONES)


def _precios_eur() -> dict[str, pd.Series]:
    factor = tipo_de_cambio_a_eur(_fx(), "USD")
    return {t: _escalonada(v) * factor for t, v in PRECIOS_USD.items()}


def _proxies_eur() -> dict[str, pd.Series]:
    return {n: _escalonada(v) for n, v in PRECIOS_PROXY_EUR.items()}


PESOS = {"SP500": 0.40, "MSCI_WORLD": 0.60}
TRANSACCIONES = [
    Transaccion("AAPL", 500.0, date(2024, 1, 27)),
    Transaccion("GOOG", 800.0, date(2025, 4, 3)),
    Transaccion("NVDA", 250.0, date(2026, 1, 15)),
]


@pytest.fixture
def resultado():
    return construir_series(TRANSACCIONES, _precios_eur(), _proxies_eur(), PESOS)


# ==========================================================================
# ACEPTACIÓN: el ejemplo completo
# ==========================================================================


def test_las_participaciones_reconstruyen_el_importe_invertido(resultado):
    """Identidad básica: importe = participaciones x precio en la fecha de
    compra. Si no cuadra al céntimo, hay un bug de FX o de convención de precio.
    """
    for posicion in resultado.posiciones:
        reconstruido = posicion.participaciones * posicion.precio_entrada_eur
        assert reconstruido == pytest.approx(posicion.invertido_eur, abs=0.01)


def test_las_participaciones_son_las_calculadas_a_mano(resultado):
    por_ticker = {p.ticker: p for p in resultado.posiciones}
    assert por_ticker["AAPL"].participaciones == pytest.approx(5.0)
    assert por_ticker["GOOG"].participaciones == pytest.approx(5.0)
    assert por_ticker["NVDA"].participaciones == pytest.approx(5.0)


def test_las_unidades_del_benchmark_son_las_calculadas_a_mano(resultado):
    assert resultado.unidades_benchmark["SP500"] == pytest.approx(5.226667, abs=1e-5)
    assert resultado.unidades_benchmark["MSCI_WORLD"] == pytest.approx(15.68, abs=1e-5)


def test_las_unidades_del_benchmark_reconstruyen_cada_aportacion(resultado):
    """Mismo guardarraíl que para la cartera: el dinero que entra en el índice
    tiene que ser exactamente el mismo que entra en la cartera."""
    proxies = _proxies_eur()
    for posicion in resultado.posiciones:
        fecha = pd.Timestamp(posicion.fecha_efectiva)
        invertido_indice = sum(
            (PESOS[n] * posicion.invertido_eur / float(proxies[n].loc[fecha])) * float(proxies[n].loc[fecha])
            for n in PESOS
        )
        assert invertido_indice == pytest.approx(posicion.invertido_eur, abs=0.01)


def test_los_valores_finales_son_los_calculados_a_mano(resultado):
    r = resultado.resumen
    assert r["total_invertido_eur"] == pytest.approx(INVERTIDO_ESPERADO, abs=0.01)
    assert r["valor_cartera_eur"] == pytest.approx(CARTERA_ESPERADA, abs=0.01)
    assert r["valor_benchmark_eur"] == pytest.approx(BENCHMARK_ESPERADO, abs=0.01)


def test_la_cartera_pierde_contra_el_indice_en_este_ejemplo(resultado):
    """El resultado es negativo a propósito: un test que solo comprueba el caso
    favorable no detecta un signo invertido."""
    assert resultado.resumen["diferencia_eur"] == pytest.approx(-113.33, abs=0.02)
    assert resultado.resumen["diferencia_pct"] < 0


def test_la_atribucion_por_posicion_coincide_con_el_calculo_a_mano(resultado):
    por_ticker = {a.ticker: a for a in resultado.atribucion}
    for ticker, alfa in ALFA_ESPERADO.items():
        assert por_ticker[ticker].alfa_eur == pytest.approx(alfa, abs=0.02), ticker

    assert not por_ticker["GOOG"].bate_al_indice
    assert por_ticker["NVDA"].bate_al_indice


def test_la_suma_de_alfas_cuadra_con_la_diferencia_total(resultado):
    """Si la atribución no suma la diferencia, se está contando dos veces algún
    flujo o perdiendo una posición por el camino."""
    suma = sum(a.alfa_eur for a in resultado.atribucion)
    assert suma == pytest.approx(resultado.resumen["diferencia_eur"], abs=0.05)


def test_el_xirr_del_benchmark_supera_al_de_la_cartera(resultado):
    """Mismos flujos y valor final mayor: la TIR del benchmark tiene que ser
    mayor. Si sale al revés, el XIRR está mal montado."""
    a, b = resultado.resumen["xirr_cartera"], resultado.resumen["xirr_benchmark"]
    assert a is not None and b is not None
    assert b > a
    assert 0 < a < 2.0


# ==========================================================================
# ANTI-BUG SILENCIOSO
# ==========================================================================


def test_el_cambio_de_divisa_divide_no_multiplica():
    """EURUSD=X cotiza DÓLARES POR EURO. Multiplicar en vez de dividir infla
    cada posición estadounidense un 35%, y como el benchmark en EUR no lleva FX,
    el sesgo cae entero del lado de la cartera: parecería batir al índice."""
    par = pd.Series([1.25], index=pd.to_datetime(["2026-01-02"]))
    factor = tipo_de_cambio_a_eur(par, "USD")

    assert float(factor.iloc[0]) == pytest.approx(0.8)
    assert 100.0 * float(factor.iloc[0]) == pytest.approx(80.0), (
        "100 USD a 1,25 USD/EUR son 80 EUR, no 125"
    )
    assert float(factor.iloc[0]) < 1.0, "con el euro más fuerte que el dólar el factor baja de 1"


def test_una_serie_ya_en_euros_no_se_convierte():
    assert tipo_de_cambio_a_eur(pd.Series([1.25]), "EUR") is None


def test_una_fecha_no_bursatil_se_desplaza_y_queda_avisado(resultado):
    """2024-01-27 fue sábado. Desplazarla en silencio escondería compras mal
    fechadas."""
    aapl = next(p for p in resultado.posiciones if p.ticker == "AAPL")
    assert aapl.fecha_efectiva == date(2024, 1, 29)
    assert any("no fue día de cotización" in a for a in resultado.avisos)


def test_los_pesos_deben_sumar_uno():
    """Con 0,9 el benchmark invertiría solo el 90% del dinero y la cartera
    ganaría un 10% gratis."""
    validar_pesos({"SP500": 0.4, "MSCI_WORLD": 0.6})

    with pytest.raises(ValueError, match="suman"):
        validar_pesos({"SP500": 0.4, "MSCI_WORLD": 0.5})
    with pytest.raises(ValueError):
        validar_pesos({})
    with pytest.raises(ValueError):
        validar_pesos({"SP500": -0.2, "MSCI_WORLD": 1.2})


def test_un_ticker_sin_precios_se_excluye_con_aviso_no_se_inventa():
    transacciones = TRANSACCIONES + [Transaccion("FANTASMA", 300.0, date(2025, 6, 2))]
    r = construir_series(transacciones, _precios_eur(), _proxies_eur(), PESOS)

    assert {p.ticker for p in r.posiciones} == {"AAPL", "GOOG", "NVDA"}
    assert any("FANTASMA" in a for a in r.avisos)
    # El dinero de la posición excluida NO entra en el invertido: contarlo
    # hundiría la rentabilidad con capital que nunca se pudo valorar.
    assert r.resumen["total_invertido_eur"] == pytest.approx(INVERTIDO_ESPERADO, abs=0.01)


def test_las_metricas_de_riesgo_se_calculan_sobre_la_serie_unitizada(resultado):
    """Sobre la serie de VALOR, una aportación de 800 EUR a una cartera de 500
    parecería un +160% diario y volaría la volatilidad y el Sharpe."""
    valor = resultado.series["valor_cartera"]
    unitizada = resultado.series["unitizada_cartera"]

    # Se miran las FECHAS DE APORTACIÓN concretas, no el máximo de la serie: el
    # fixture tiene además un salto de precio real, y mezclarlo confundiría un
    # movimiento de mercado legítimo con el escalón de meter dinero.
    for posicion in resultado.posiciones:
        fecha = pd.Timestamp(posicion.fecha_efectiva)
        if fecha == valor.index[0]:
            continue                      # la primera aportación no tiene día previo
        salto_valor = float(valor.pct_change().loc[fecha])
        salto_unitizado = abs(float(unitizada.pct_change().loc[fecha]))

        assert salto_valor > 0.15, (
            f"{posicion.ticker}: la serie de VALOR debe reflejar la aportación"
        )
        assert salto_unitizado < 1e-6, (
            f"{posicion.ticker}: la unitizada NO puede contar la aportación como "
            f"rentabilidad (salió {salto_unitizado:.4%})"
        )

    vol = resultado.resumen["riesgo_cartera"]["vol_%"]
    assert 0 < vol < 200, f"volatilidad implausible ({vol}%): ¿se midió sobre la serie con aportaciones?"


def test_la_serie_unitizada_no_cuenta_una_aportacion_como_ganancia():
    valores = pd.Series([100.0, 100.0, 300.0, 300.0],
                        index=pd.bdate_range("2026-01-01", periods=4))
    aportes = pd.Series([0.0, 0.0, 200.0, 0.0], index=valores.index)

    unitizada = serie_unitizada(valores, aportes)
    assert float(unitizada.iloc[-1]) == pytest.approx(100.0), (
        "meter 200 sobre 100 y no moverse el mercado es un 0% de rentabilidad"
    )


def test_la_rentabilidad_usa_el_mismo_denominador_en_ambos_lados(resultado):
    """Cartera y benchmark deben dividirse por el MISMO capital desplegado; con
    denominadores distintos la comparación no significa nada."""
    fila = resultado.series.iloc[-1]
    esperado_cartera = (fila["valor_cartera"] - fila["invertido_acum"]) / fila["invertido_acum"] * 100
    esperado_bench = (fila["valor_benchmark"] - fila["invertido_acum"]) / fila["invertido_acum"] * 100

    assert fila["ret_cartera_pct"] == pytest.approx(esperado_cartera, abs=1e-6)
    assert fila["ret_benchmark_pct"] == pytest.approx(esperado_bench, abs=1e-6)


def test_ninguna_posicion_aporta_valor_antes_de_su_fecha_de_compra(resultado):
    """NVDA se compra en 2026: en 2024 la cartera no puede incluirla."""
    antes = resultado.series.loc[resultado.series.index < "2025-01-01"]
    # Solo AAPL: 5 participaciones x 100 EUR = 500
    assert float(antes["valor_cartera"].iloc[0]) == pytest.approx(500.0, abs=0.01)
    assert float(antes["invertido_acum"].iloc[0]) == pytest.approx(500.0, abs=0.01)


def test_una_venta_se_ignora_con_aviso_en_el_caso_base():
    transacciones = TRANSACCIONES + [Transaccion("AAPL", 100.0, date(2026, 3, 2), tipo=VENTA)]
    r = construir_series(transacciones, _precios_eur(), _proxies_eur(), PESOS)

    assert any("Venta" in a for a in r.avisos)
    assert r.resumen["total_invertido_eur"] == pytest.approx(INVERTIDO_ESPERADO, abs=0.01)


def test_sin_transacciones_se_devuelve_un_resultado_vacio_no_una_excepcion():
    r = construir_series([], _precios_eur(), _proxies_eur(), PESOS)
    assert not r.valido
    assert r.avisos


# ==========================================================================
# XIRR
# ==========================================================================


def test_el_xirr_de_un_caso_conocido():
    """1.000 EUR que valen 1.100 un año después: en torno al 10%."""
    r = xirr([(date(2024, 1, 1), -1000.0), (date(2025, 1, 1), 1100.0)])
    assert r == pytest.approx(0.10, abs=0.005)


def test_el_xirr_pondera_por_tiempo_no_solo_por_importe():
    """El mismo beneficio en la mitad de tiempo es una TIR mayor."""
    lento = xirr([(date(2024, 1, 1), -1000.0), (date(2026, 1, 1), 1100.0)])
    rapido = xirr([(date(2024, 1, 1), -1000.0), (date(2025, 1, 1), 1100.0)])
    assert rapido > lento


def test_sin_cambio_de_signo_no_hay_xirr():
    """Solo aportaciones, sin valor final: no existe tasa que iguale nada."""
    assert xirr([(date(2024, 1, 1), -1000.0), (date(2025, 1, 1), -500.0)]) is None
    assert xirr([(date(2024, 1, 1), -1000.0)]) is None


def test_una_perdida_da_xirr_negativo():
    r = xirr([(date(2024, 1, 1), -1000.0), (date(2025, 1, 1), 500.0)])
    assert r is not None and r < 0


# ==========================================================================
# UTILIDADES
# ==========================================================================


def test_el_siguiente_dia_habil_no_retrocede():
    indice = pd.bdate_range("2026-01-05", periods=10)
    assert siguiente_dia_habil(indice, date(2026, 1, 3)) == pd.Timestamp("2026-01-05")
    assert siguiente_dia_habil(indice, date(2026, 1, 6)) == pd.Timestamp("2026-01-06")


def test_una_fecha_posterior_al_historico_devuelve_none():
    """Devolver la última sesión disponible fecharía la compra en un día
    equivocado sin que se note."""
    indice = pd.bdate_range("2026-01-05", periods=10)
    assert siguiente_dia_habil(indice, date(2030, 1, 1)) is None
