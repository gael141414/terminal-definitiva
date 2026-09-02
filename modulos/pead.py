"""PEAD: deriva de precios tras la publicación de resultados.

Qué es
------
Post-Earnings Announcement Drift. Cuando una empresa publica un beneficio muy
por encima de lo esperado, el precio no incorpora la sorpresa de golpe: sigue
derivando en esa dirección durante semanas. Es una de las anomalías de mercado
mejor documentadas (Bernard y Thomas, 1989) y ha sobrevivido décadas de
publicación académica, que es más de lo que puede decirse de casi cualquier
regla técnica.

La explicación habitual es de comportamiento: el mercado reacciona de forma
insuficiente a la información nueva, sobre todo en empresas menos seguidas por
analistas.

Cómo encaja aquí
----------------
El resto de estrategias sólo necesitan OHLCV. Esta necesita además el calendario
histórico de resultados, que es un dato externo y con coste de red. Para no
romper el diseño causal por índice del resto del sistema, ese calendario se
convierte en **columnas alineadas al índice de precios**: en la fila i sólo
aparece información de resultados ya publicados antes de i.

Detalle que decide la validez del backtest: las empresas publican DESPUÉS del
cierre (yfinance marca las 16:00), así que la primera sesión en la que esa
información se puede operar es la SIGUIENTE. Tratar el día del anuncio como
operable sería look-ahead puro y dispararía artificialmente los resultados.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from modulos.yahoo_resilience import safe_yfinance_fetch

logger = logging.getLogger(__name__)

# Ventana en la que se considera que la deriva sigue "fresca". Pasado ese plazo
# la información ya está descontada y entrar es perseguir un movimiento hecho.
DIAS_FRESCURA = 5

# Sorpresa mínima para considerar el resultado relevante. Por debajo de esto la
# desviación entra dentro del ruido de estimación de los analistas.
SORPRESA_MINIMA_PCT = 5.0


@st.cache_data(ttl=86400, show_spinner=False)
def obtener_historico_earnings(ticker: str) -> pd.DataFrame:
    """Calendario histórico de resultados con sorpresa, ordenado por fecha.

    Devuelve un DataFrame vacío si Yahoo no lo publica (ETFs, empresas recién
    salidas a bolsa) en vez de lanzar.
    """
    simbolo = str(ticker or "").strip().upper()
    if not simbolo:
        return pd.DataFrame()

    try:
        yf_ticker = yf.Ticker(simbolo)
    except Exception:
        return pd.DataFrame()

    datos, status = safe_yfinance_fetch(
        lambda: yf_ticker.earnings_dates,
        empty_value=pd.DataFrame(),
        context=f"pead:earnings_dates:{simbolo}",
    )
    if status != "ok" or not isinstance(datos, pd.DataFrame) or datos.empty:
        return pd.DataFrame()

    df = datos.copy()
    df.index = pd.to_datetime(df.index, errors="coerce", utc=True)
    df = df[df.index.notna()].sort_index()
    if df.empty:
        return pd.DataFrame()

    # Se normaliza a fecha sin zona horaria para poder cruzarla con el índice de
    # precios, que viene sin tz o con la de la bolsa según el símbolo.
    df["fecha"] = df.index.tz_convert("UTC").tz_localize(None).normalize()

    columna_sorpresa = next((c for c in df.columns if "Surprise" in str(c)), None)
    columna_reportado = next((c for c in df.columns if "Reported" in str(c)), None)

    df["sorpresa_pct"] = pd.to_numeric(df[columna_sorpresa], errors="coerce") if columna_sorpresa else np.nan
    df["eps_reportado"] = pd.to_numeric(df[columna_reportado], errors="coerce") if columna_reportado else np.nan

    # Sólo interesan los resultados ya publicados: los futuros no tienen sorpresa.
    return df[["fecha", "sorpresa_pct", "eps_reportado"]].dropna(subset=["sorpresa_pct"]).reset_index(drop=True)


def enriquecer_con_earnings(precios: pd.DataFrame, earnings: pd.DataFrame) -> pd.DataFrame:
    """Añade al DataFrame de precios las columnas de la última publicación previa.

    Columnas resultantes:
      - ``dias_desde_earnings``: sesiones transcurridas desde la última publicación.
      - ``sorpresa_pct``: desviación del BPA reportado frente al consenso.
      - ``reaccion_earnings_pct``: cuánto se movió el precio en la primera sesión
        operable tras el anuncio. Es lo que distingue "buen resultado" de "buen
        resultado que además el mercado se ha creído".
    """
    df = precios.copy()
    df["dias_desde_earnings"] = np.nan
    df["sorpresa_pct"] = np.nan
    df["reaccion_earnings_pct"] = np.nan

    if earnings is None or earnings.empty or df.empty:
        return df

    indice = pd.to_datetime(df.index)
    if getattr(indice, "tz", None) is not None:
        indice = indice.tz_convert("UTC").tz_localize(None)
    indice = indice.normalize()

    cierres = df["Close"].to_numpy(dtype=float)
    n = len(df)

    for _, evento in earnings.iterrows():
        fecha = evento["fecha"]
        # Primera sesión ESTRICTAMENTE posterior al anuncio: se publica tras el
        # cierre, así que el propio día del anuncio no es operable.
        posteriores = np.flatnonzero(indice > fecha)
        if posteriores.size == 0:
            continue
        primera = int(posteriores[0])

        reaccion = np.nan
        if primera >= 1 and cierres[primera - 1] > 0:
            reaccion = (cierres[primera] / cierres[primera - 1] - 1.0) * 100.0

        # La información vale desde la primera sesión operable hasta el siguiente
        # anuncio; el bucle avanza en orden, así que un evento posterior
        # sobrescribe al anterior de forma natural.
        for j in range(primera, n):
            df.iat[j, df.columns.get_loc("dias_desde_earnings")] = j - primera
            df.iat[j, df.columns.get_loc("sorpresa_pct")] = float(evento["sorpresa_pct"])
            df.iat[j, df.columns.get_loc("reaccion_earnings_pct")] = reaccion

    return df


def evaluar_pead(df: pd.DataFrame, contexto: dict[str, Any] | None = None, indice: int = -1):
    """Estrategia PEAD: comprar la deriva tras una sorpresa positiva creída.

    Se importa aquí dentro para evitar un ciclo de importación con
    ``swing_estrategias``, que a su vez registra esta función en el catálogo.
    """
    from modulos.swing_estrategias import LARGO, Senal, _acotar, _liquidez_suficiente, _num, _valores

    par = _valores(df, indice)
    if par is None:
        return None
    u, _p = par
    if not _liquidez_suficiente(u):
        return None

    dias = u.get("dias_desde_earnings")
    if dias is None or pd.isna(dias) or not (0 <= float(dias) <= DIAS_FRESCURA):
        return None

    sorpresa = _num(u.get("sorpresa_pct"), 0.0)
    if sorpresa < SORPRESA_MINIMA_PCT:
        return None

    # El mercado tiene que haberse creído el resultado. Una sorpresa positiva con
    # el precio cayendo suele significar que la guía futura o la calidad del
    # beneficio decepcionaron, y ahí la deriva se produce a la baja.
    reaccion = _num(u.get("reaccion_earnings_pct"), 0.0)
    if reaccion <= 0:
        return None

    cierre = _num(u["Close"])
    if cierre <= _num(u.get("sma200")):
        return None

    motivos = [
        f"Sorpresa positiva en resultados: BPA un {sorpresa:.1f}% sobre el consenso",
        f"El mercado lo validó con un {reaccion:+.1f}% en la primera sesión tras el anuncio",
        f"Publicado hace {int(float(dias))} sesión(es): la deriva sigue en su ventana útil",
        "El precio está sobre su media de 200: la sorpresa llega sobre una tendencia sana",
    ]

    fuerza = 50.0
    fuerza += min(sorpresa * 0.8, 20)
    fuerza += min(reaccion * 1.5, 15)
    if float(dias) <= 2:
        fuerza += 5
        motivos.append("Entrada temprana en la ventana de deriva")

    from modulos.swing_estrategias import _bonus_fundamental

    bonus, motivos_fund = _bonus_fundamental(contexto, LARGO)
    fuerza += bonus
    motivos.extend(motivos_fund)

    return Senal(
        ticker="", estrategia="pead", nombre_estrategia="Deriva post-resultados",
        direccion=LARGO, precio=cierre, atr=_num(u.get("atr14")),
        fuerza=_acotar(fuerza), motivos=motivos, fecha=df.index[indice],
        datos={"sorpresa_pct": round(sorpresa, 1), "reaccion_pct": round(reaccion, 2),
               "dias_desde_earnings": int(float(dias))},
    )
