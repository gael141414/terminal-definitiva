"""CAN SLIM: los siete criterios de William O'Neil, evaluables sobre datos reales.

Qué es
------
Sistema de *growth investing* que O'Neil derivó del estudio de los mayores
ganadores bursátiles desde 1953. Combina fundamentales de crecimiento con
análisis técnico y se resume en siete letras:

- **C** Current quarterly earnings: BPA trimestral interanual >= 25%, acelerando.
- **A** Annual earnings: crecimiento anual >= 25% varios años y ROE >= 17%.
- **N** New: producto, dirección o -- en clave técnica -- nuevos máximos al salir
  de una base.
- **S** Supply and demand: oferta reducida de acciones y volumen fuerte en las subidas.
- **L** Leader or laggard: comprar líderes, con fuerza relativa alta.
- **I** Institutional sponsorship: respaldo institucional creciente.
- **M** Market direction: sólo operar en tendencia alcista confirmada.

Cómo está construido aquí
-------------------------
En dos pasadas, que es como se puede escanear un mercado entero sin hacer miles
de peticiones y además reproduce el orden de trabajo del propio O'Neil:

1. **Pasada técnica** (L, N, M y parte de S) sobre el universo completo. Sale
   del OHLCV que el escáner ya descarga en lote, así que es gratis.
2. **Pasada fundamental** (C, A, I y el resto de S) sólo sobre los valores que
   sobreviven a la primera. Cada uno cuesta una petición, así que filtrar antes
   es lo que hace viable la herramienta.

Advertencia que acompaña al método
----------------------------------
La evidencia de CAN SLIM es fuerte en backtests de screens (AAII midió un 24,4%
anual entre 1998 y 2013) y floja en su implementación real: el ETF que replica
la lista IBD 50 rindió un 5,77% anual a diez años frente al 13,47% del S&P 500,
con alfa negativa. La diferencia se explica por costes, deslizamiento y por lo
difícil que es ejecutar el método. Además el filtro es muy restrictivo: en el
periodo estudiado por AAII, en cerca de un tercio de los meses pasaban tres
empresas o menos, y en un 9% no pasaba ninguna. Ver ``ADVERTENCIA_EVIDENCIA``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from modulos.canslim_bases import detectar_base, detectar_ruptura
from modulos.yahoo_resilience import safe_yfinance_info

logger = logging.getLogger(__name__)

ADVERTENCIA_EVIDENCIA = (
    "CAN SLIM rinde muy bien en backtests de screens (AAII: 24,4% anual entre 1998 y 2013) y "
    "mucho peor en su versión invertible: el ETF que replica la lista IBD 50 ha rendido un 5,77% "
    "anual a diez años frente al 13,47% del S&P 500. La diferencia son costes, deslizamiento y "
    "dificultad de ejecución. Además es un filtro muy restrictivo por diseño: es normal que en "
    "muchas sesiones no pase ninguna empresa."
)

# --- Umbrales (4ª edición del libro y criterios publicados por IBD) ---
UMBRAL_C_BPA_TRIMESTRAL = 25.0     # % interanual
UMBRAL_C_VENTAS = 20.0             # % interanual
UMBRAL_A_BPA_ANUAL = 25.0          # % anual
UMBRAL_A_ROE = 17.0                # %
UMBRAL_L_RS = 80.0                 # RS Rating 1-99
UMBRAL_L_RS_IDEAL = 90.0
UMBRAL_I_INSTITUCIONAL = 25.0      # % del capital en manos institucionales
UMBRAL_I_EXCESO = 90.0             # por encima, la acción está "sobre-poseída"
UMBRAL_S_ACCIONES_M = 50.0         # millones; O'Neil usaba 25M, relajado en la 4ª edición
UMBRAL_N_DISTANCIA_MAXIMO = -15.0  # % respecto al máximo de 52 semanas


@dataclass
class Criterio:
    """Resultado de evaluar una de las siete letras."""

    letra: str
    nombre: str
    cumple: bool | None          # None = sin datos para juzgar
    valor: str = ""
    detalle: str = ""

    @property
    def evaluable(self) -> bool:
        return self.cumple is not None


@dataclass
class ResultadoCanSlim:
    ticker: str
    criterios: dict[str, Criterio] = field(default_factory=dict)
    rs_rating: float | None = None
    ruptura: Any = None
    base: Any = None

    @property
    def cumplidos(self) -> int:
        return sum(1 for c in self.criterios.values() if c.cumple is True)

    @property
    def evaluados(self) -> int:
        return sum(1 for c in self.criterios.values() if c.evaluable)

    @property
    def puntuacion(self) -> float:
        """Porcentaje de criterios cumplidos sobre los que se pudieron evaluar.

        Se divide por los evaluables y no por siete a propósito: penalizar a una
        empresa porque Yahoo no publica su dato institucional sería confundir
        "no cumple" con "no se sabe".
        """
        if not self.evaluados:
            return 0.0
        return round(self.cumplidos / self.evaluados * 100.0, 1)

    @property
    def letras_cumplidas(self) -> str:
        """Las siete letras, en mayúscula si cumplen y en gris si no."""
        salida = []
        for letra in "CANSLIM":
            criterio = self.criterios.get(letra)
            if criterio is None or not criterio.evaluable:
                salida.append("·")
            else:
                salida.append(letra if criterio.cumple else letra.lower())
        return "".join(salida)


# ==========================================================================
# L — Fuerza relativa (RS Rating)
# ==========================================================================


def calcular_rs_bruto(cierres: pd.Series) -> float | None:
    """Fuerza relativa bruta con la ponderación de O'Neil.

    El trimestre más reciente pesa el doble que los otros tres, que es lo que
    hace que la métrica reaccione a un cambio de liderazgo en vez de premiar
    eternamente al que subió hace un año.
    """
    serie = cierres.dropna()
    if len(serie) < 252:
        return None

    actual = float(serie.iloc[-1])
    if actual <= 0:
        return None

    try:
        c63 = float(serie.iloc[-63])
        c126 = float(serie.iloc[-126])
        c189 = float(serie.iloc[-189])
        c252 = float(serie.iloc[-252])
    except (IndexError, ValueError):
        return None

    if min(c63, c126, c189, c252) <= 0:
        return None

    return (
        2.0 * (actual / c63 - 1.0)
        + (actual / c126 - 1.0)
        + (actual / c189 - 1.0)
        + (actual / c252 - 1.0)
    )


def calcular_rs_ratings(precios: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Convierte la fuerza bruta del universo en un ranking percentil de 1 a 99.

    El RS Rating es intrínsecamente **relativo**: no dice cuánto ha subido un
    valor, sino cuántos ha batido. Por eso sólo tiene sentido calculado sobre un
    universo amplio, y por eso un RS 90 significa lo mismo en un mercado alcista
    que en uno bajista (estar en el 10% mejor), que es justo lo que O'Neil quería.
    """
    brutos: dict[str, float] = {}
    for ticker, df in precios.items():
        if df is None or df.empty or "Close" not in df.columns:
            continue
        valor = calcular_rs_bruto(df["Close"])
        if valor is not None and np.isfinite(valor):
            brutos[ticker] = valor

    if len(brutos) < 20:
        # Con pocos valores el percentil no significa nada: mejor no dar una
        # cifra que aparenta precisión y no la tiene.
        return {}

    serie = pd.Series(brutos)
    percentiles = serie.rank(pct=True) * 98 + 1
    return {t: round(float(v), 1) for t, v in percentiles.items()}


# ==========================================================================
# Pasada técnica: L, N, M y volumen (parte de S)
# ==========================================================================


def evaluar_tecnicos(
    df: pd.DataFrame,
    rs_rating: float | None,
    *,
    mercado_alcista: bool | None = None,
    indice: int = -1,
) -> tuple[dict[str, Criterio], Any, Any]:
    """Evalúa las letras que sólo necesitan precio y volumen."""
    criterios: dict[str, Criterio] = {}
    posicion = indice if indice >= 0 else len(df) + indice
    fila = df.iloc[posicion]

    # --- L: líder o rezagado ---
    if rs_rating is None:
        criterios["L"] = Criterio("L", "Líder del mercado", None, detalle="Universo insuficiente para calcular el RS Rating.")
    else:
        ideal = rs_rating >= UMBRAL_L_RS_IDEAL
        criterios["L"] = Criterio(
            "L", "Líder del mercado", rs_rating >= UMBRAL_L_RS, f"RS {rs_rating:.0f}",
            detalle=(
                f"Bate al {rs_rating:.0f}% del universo en los últimos 12 meses"
                + (" (zona de líder claro)." if ideal else ".")
                if rs_rating >= UMBRAL_L_RS
                else f"Por debajo del mínimo de {UMBRAL_L_RS:.0f} que exige el método: es un rezagado."
            ),
        )

    # --- N: nuevos máximos saliendo de una base ---
    base = detectar_base(df, posicion)
    ruptura = detectar_ruptura(df, posicion)
    distancia = float(fila.get("dist_max52", np.nan))

    if ruptura is not None and not ruptura.fallida:
        criterios["N"] = Criterio(
            "N", "Nuevos máximos", True,
            f"{ruptura.base.nombre}, pivote {ruptura.base.pivote:,.2f}",
            detalle=f"Rompió con volumen {ruptura.volumen_relativo:.1f}x. {ruptura.estado}.",
        )
    elif np.isfinite(distancia) and distancia >= UMBRAL_N_DISTANCIA_MAXIMO:
        criterios["N"] = Criterio(
            "N", "Nuevos máximos", distancia >= -5.0, f"a {distancia:+.1f}% del máximo anual",
            detalle=(
                "Cotiza pegado a máximos, sin vendedores atrapados por encima."
                if distancia >= -5.0
                else "Cerca de máximos pero sin ruptura confirmada de una base."
            ),
        )
    else:
        criterios["N"] = Criterio(
            "N", "Nuevos máximos", False,
            f"a {distancia:.1f}% del máximo anual" if np.isfinite(distancia) else "sin datos",
            detalle="Lejos de máximos: no hay ruptura que comprar.",
        )

    # --- S (parte técnica): volumen en las subidas ---
    vol_rel = float(fila.get("vol_rel", np.nan))
    if np.isfinite(vol_rel):
        criterios["S"] = Criterio(
            "S", "Oferta y demanda", vol_rel >= 1.0, f"volumen {vol_rel:.1f}x",
            detalle=(
                "Volumen por encima de su media: hay demanda real detrás del movimiento."
                if vol_rel >= 1.0
                else "Volumen por debajo de la media: el movimiento no tiene respaldo."
            ),
        )

    # --- M: dirección del mercado ---
    if mercado_alcista is None:
        criterios["M"] = Criterio("M", "Dirección del mercado", None, detalle="Régimen de mercado no disponible.")
    else:
        criterios["M"] = Criterio(
            "M", "Dirección del mercado", mercado_alcista,
            "tendencia alcista" if mercado_alcista else "sin tendencia alcista confirmada",
            detalle=(
                "O'Neil sostenía que al menos la mitad del resultado depende del mercado general: "
                "tres de cada cuatro valores siguen su tendencia."
            ),
        )

    return criterios, base, ruptura


# ==========================================================================
# Pasada fundamental: C, A, I y oferta de acciones
# ==========================================================================


@st.cache_data(ttl=86400, show_spinner=False)
def _datos_fundamentales(ticker: str) -> dict[str, Any]:
    """Datos de crecimiento e institucionales de un valor. Una petición."""
    info = safe_yfinance_info(yf, ticker, context=f"canslim:{ticker}")
    if not info:
        return {}
    return {
        "crecimiento_bpa_trimestral": info.get("earningsQuarterlyGrowth"),
        "crecimiento_ventas": info.get("revenueGrowth"),
        "crecimiento_bpa": info.get("earningsGrowth"),
        "roe": info.get("returnOnEquity"),
        "acciones": info.get("sharesOutstanding"),
        "institucional": info.get("heldPercentInstitutions"),
        "sector": info.get("sector"),
        "industria": info.get("industry"),
        "nombre": info.get("shortName") or ticker,
    }


def _pct(valor: Any) -> float | None:
    """Yahoo devuelve los crecimientos en tanto por uno (1.259 = +125,9%)."""
    try:
        if valor is None or pd.isna(valor):
            return None
        return float(valor) * 100.0
    except (TypeError, ValueError):
        return None


def evaluar_fundamentales(ticker: str, datos: dict[str, Any] | None = None) -> dict[str, Criterio]:
    """Evalúa C, A, I y la parte de oferta de S."""
    datos = datos if datos is not None else _datos_fundamentales(ticker)
    criterios: dict[str, Criterio] = {}

    # --- C: beneficios del trimestre actual ---
    trimestral = _pct(datos.get("crecimiento_bpa_trimestral"))
    ventas = _pct(datos.get("crecimiento_ventas"))
    if trimestral is None:
        criterios["C"] = Criterio("C", "Beneficios trimestrales", None, detalle="Yahoo no publica el crecimiento trimestral de esta empresa.")
    else:
        cumple = trimestral >= UMBRAL_C_BPA_TRIMESTRAL
        detalle = f"BPA trimestral {trimestral:+.0f}% interanual (mínimo exigido {UMBRAL_C_BPA_TRIMESTRAL:.0f}%)."
        if ventas is not None:
            detalle += f" Ventas {ventas:+.0f}%."
            cumple = cumple and ventas >= UMBRAL_C_VENTAS
        criterios["C"] = Criterio("C", "Beneficios trimestrales", cumple, f"{trimestral:+.0f}%", detalle)

    # --- A: beneficios anuales y rentabilidad ---
    anual = _pct(datos.get("crecimiento_bpa"))
    roe = _pct(datos.get("roe"))
    if anual is None and roe is None:
        criterios["A"] = Criterio("A", "Beneficios anuales", None, detalle="Sin datos de crecimiento anual ni ROE.")
    else:
        condiciones = []
        partes = []
        if anual is not None:
            condiciones.append(anual >= UMBRAL_A_BPA_ANUAL)
            partes.append(f"crecimiento anual {anual:+.0f}%")
        if roe is not None:
            condiciones.append(roe >= UMBRAL_A_ROE)
            partes.append(f"ROE {roe:.0f}%")
        criterios["A"] = Criterio(
            "A", "Beneficios anuales", all(condiciones), ", ".join(partes),
            f"Exigido: crecimiento anual >= {UMBRAL_A_BPA_ANUAL:.0f}% y ROE >= {UMBRAL_A_ROE:.0f}%.",
        )

    # --- S: oferta de acciones ---
    acciones = datos.get("acciones")
    if acciones:
        millones = float(acciones) / 1e6
        criterios["S_oferta"] = Criterio(
            "S", "Oferta de acciones", millones <= UMBRAL_S_ACCIONES_M, f"{millones:,.0f}M acciones",
            detalle=(
                "Capital reducido: la demanda mueve el precio con más facilidad."
                if millones <= UMBRAL_S_ACCIONES_M
                else "Mucho capital en circulación. O'Neil relajó este criterio en la 4ª edición, "
                     "así que no descarta por sí solo."
            ),
        )

    # --- I: respaldo institucional ---
    institucional = _pct(datos.get("institucional"))
    if institucional is None:
        criterios["I"] = Criterio("I", "Respaldo institucional", None, detalle="Yahoo no publica el porcentaje institucional.")
    else:
        exceso = institucional >= UMBRAL_I_EXCESO
        criterios["I"] = Criterio(
            "I", "Respaldo institucional",
            UMBRAL_I_INSTITUCIONAL <= institucional < UMBRAL_I_EXCESO,
            f"{institucional:.0f}% institucional",
            detalle=(
                "Un exceso de propiedad institucional es una señal de aviso: la acción ya está "
                "'sobre-poseída' y queda menos demanda nueva por llegar."
                if exceso
                else "Respaldo institucional suficiente."
                if institucional >= UMBRAL_I_INSTITUCIONAL
                else "Poco respaldo institucional: sin ese dinero detrás, cuesta que el precio arranque."
            ),
        )

    return criterios


def combinar(
    ticker: str,
    criterios_tecnicos: dict[str, Criterio],
    criterios_fundamentales: dict[str, Criterio] | None = None,
    *,
    rs_rating: float | None = None,
    base: Any = None,
    ruptura: Any = None,
) -> ResultadoCanSlim:
    """Une ambas pasadas en un único resultado por valor."""
    criterios = dict(criterios_tecnicos)

    if criterios_fundamentales:
        oferta = criterios_fundamentales.pop("S_oferta", None)
        criterios.update(criterios_fundamentales)

        # La letra S tiene dos mitades: volumen (técnica) y oferta de acciones
        # (fundamental). Se fusionan en un único criterio en lugar de duplicar
        # la letra, que es como lo presenta el método original.
        if oferta is not None:
            volumen = criterios.get("S")
            if volumen is not None and volumen.evaluable and oferta.evaluable:
                criterios["S"] = Criterio(
                    "S", "Oferta y demanda",
                    bool(volumen.cumple and oferta.cumple),
                    f"{oferta.valor} · {volumen.valor}",
                    f"{oferta.detalle} {volumen.detalle}",
                )
            else:
                criterios["S"] = oferta

    return ResultadoCanSlim(
        ticker=ticker, criterios=criterios, rs_rating=rs_rating, base=base, ruptura=ruptura
    )


# ==========================================================================
# RS Rating histórico (para validar la estrategia sin look-ahead)
# ==========================================================================


def calcular_rs_historico(precios: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
    """Serie temporal del RS Rating de cada valor frente al universo.

    Necesario para el backtest: evaluar hoy una señal de 2022 con el RS de hoy
    sería look-ahead. Aquí el percentil de cada fecha se calcula únicamente con
    la información disponible en esa fecha (el rendimiento de los 12 meses
    anteriores de cada valor), comparando en corte transversal.

    Devuelve ``{ticker: Serie de percentiles 1-99}``.
    """
    brutos: dict[str, pd.Series] = {}

    for ticker, df in precios.items():
        if df is None or df.empty or "Close" not in df.columns:
            continue
        cierre = df["Close"].astype(float)
        if len(cierre) < 260:
            continue

        # Misma ponderación que la versión puntual: el trimestre reciente pesa doble.
        serie = (
            2.0 * (cierre / cierre.shift(63) - 1.0)
            + (cierre / cierre.shift(126) - 1.0)
            + (cierre / cierre.shift(189) - 1.0)
            + (cierre / cierre.shift(252) - 1.0)
        )
        brutos[ticker] = serie

    if len(brutos) < 20:
        return {}

    matriz = pd.DataFrame(brutos)
    # Percentil en corte transversal: en cada fecha se compara cada valor con
    # todos los demás de esa misma fecha, nunca con el futuro.
    percentiles = matriz.rank(axis=1, pct=True) * 98 + 1
    return {t: percentiles[t].dropna() for t in percentiles.columns}


def inyectar_rs(df: pd.DataFrame, serie_rs: pd.Series | None) -> pd.DataFrame:
    """Añade la columna ``rs_rating`` alineada al índice de precios."""
    datos = df.copy()
    if serie_rs is None or serie_rs.empty:
        datos["rs_rating"] = np.nan
        return datos
    datos["rs_rating"] = serie_rs.reindex(datos.index)
    return datos


# ==========================================================================
# Estrategia operable (sólo la parte técnica)
# ==========================================================================
#
# IMPORTANTE, y es una limitación de fondo: aquí sólo se implementa la mitad
# técnica de CAN SLIM (N, L, S-volumen y M). Las letras C, A e I NO se pueden
# incluir en una estrategia validable históricamente, porque Yahoo publica los
# fundamentales de HOY y no los que estaban disponibles en la fecha de cada
# señal pasada. Filtrar una señal de 2022 por el crecimiento de beneficios de
# 2026 sería look-ahead puro y produciría un backtest espectacular y falso.
#
# Por tanto: el escáner aplica los siete criterios sobre el mercado actual, pero
# la cifra de validación histórica corresponde sólo a la parte técnica.

UMBRAL_RS_ESTRATEGIA = 80.0


def evaluar_canslim_tecnico(df: pd.DataFrame, contexto: dict[str, Any] | None = None, indice: int = -1):
    """Ruptura del pivote de una base, en un líder por fuerza relativa."""
    from modulos.swing_estrategias import (
        LARGO, Senal, _acotar, _bonus_fundamental, _liquidez_suficiente, _num, _valores,
    )

    par = _valores(df, indice)
    if par is None:
        return None
    u, _p = par
    if not _liquidez_suficiente(u):
        return None

    cierre = _num(u["Close"])
    if cierre <= _num(u.get("sma200")):
        return None

    # Fuerza relativa: sólo se compran líderes. Sin la columna inyectada no se
    # puede juzgar, y se prefiere no dar señal a darla sin este filtro, que es
    # el que separa CAN SLIM de una ruptura cualquiera.
    rs = u.get("rs_rating")
    if rs is None or pd.isna(rs) or float(rs) < UMBRAL_RS_ESTRATEGIA:
        return None

    ruptura = detectar_ruptura(df, indice)
    if ruptura is None or ruptura.fallida or ruptura.extendida:
        return None

    base = ruptura.base
    motivos = [
        f"Rompe el pivote de una {base.nombre.lower()} de {base.semanas:.0f} semanas "
        f"({base.pivote:,.2f}) con volumen {ruptura.volumen_relativo:.1f}x",
        f"RS Rating {float(rs):.0f}: bate a ese porcentaje del universo en 12 meses",
        f"La base corrigió un {base.profundidad_pct:.1f}% tras un avance previo del {base.avance_previo_pct:.0f}%",
        f"Dentro de la zona de compra (a un {ruptura.extension_pct:+.1f}% del pivote). "
        f"Objetivo medido de la base: {base.objetivo_medido():,.2f}",
    ]

    fuerza = 48.0
    fuerza += min((float(rs) - UMBRAL_RS_ESTRATEGIA) * 0.6, 12)
    fuerza += min((ruptura.volumen_relativo - 1.4) * 10, 15)
    if base.tipo != "consolidacion":
        fuerza += 5
        motivos.append(f"Figura reconocible: {base.nombre.lower()}.")

    bonus, motivos_fund = _bonus_fundamental(contexto, LARGO)
    fuerza += bonus
    motivos.extend(motivos_fund)

    return Senal(
        ticker="", estrategia="canslim", nombre_estrategia="Ruptura CAN SLIM",
        direccion=LARGO, precio=cierre, atr=_num(u.get("atr14")),
        fuerza=_acotar(fuerza), motivos=motivos, fecha=df.index[indice],
        datos={
            "rs_rating": round(float(rs), 1),
            "pivote": base.pivote,
            "tipo_base": base.tipo,
            "vol_ruptura": ruptura.volumen_relativo,
            "extension_pct": ruptura.extension_pct,
            "objetivo_base": base.objetivo_medido(),
        },
    )
