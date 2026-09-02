"""Calendario de resultados (earnings) para los tickers en seguimiento.

Responde a una pregunta operativa concreta: *¿a cuál de mis empresas le tocan
resultados esta semana?* — el evento que más mueve el precio a corto plazo y el
que conviene tener delante antes de abrir o ampliar una posición.

Fuente: ``yf.Ticker(...).calendar`` para la próxima fecha y la estimación de
consenso, y ``.earnings_history`` para el histórico de sorpresas. Ambas van
detrás de la capa de resiliencia y de una caché de 6 horas: son datos que
cambian como mucho una vez al día, así que no tiene sentido volver a pedirlos en
cada rerun de Streamlit.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Iterable

import pandas as pd
import streamlit as st
import yfinance as yf

from modulos.config import COLOR_TEXT_MUTED, COLOR_WARNING
from modulos.yahoo_resilience import safe_yfinance_fetch

# Ventana en la que un earnings se considera "inminente" y se resalta.
DIAS_ALERTA_EARNINGS = 7


def _primera_fecha(valor: Any) -> dt.date | None:
    """Normaliza el campo 'Earnings Date', que llega como fecha suelta o lista."""
    if valor is None:
        return None
    if isinstance(valor, (list, tuple)):
        fechas = [_primera_fecha(v) for v in valor]
        fechas = [f for f in fechas if f is not None]
        return min(fechas) if fechas else None
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    try:
        convertida = pd.to_datetime(valor, errors="coerce")
        return None if pd.isna(convertida) else convertida.date()
    except Exception:
        return None


def _float_o_none(valor: Any) -> float | None:
    try:
        if valor is None or (isinstance(valor, float) and pd.isna(valor)):
            return None
        return float(valor)
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=21600, show_spinner=False)
def obtener_earnings_ticker(ticker: str) -> dict[str, Any]:
    """Próximo earnings + histórico de sorpresas de un ticker.

    Devuelve siempre un dict (nunca lanza). ``fecha`` es ``None`` cuando Yahoo no
    publica una próxima fecha, caso habitual en ETFs y en empresas ya reportadas.
    """
    simbolo = str(ticker or "").strip().upper()
    vacio: dict[str, Any] = {
        "ticker": simbolo,
        "nombre": simbolo,
        "fecha": None,
        "eps_estimado": None,
        "eps_anterior": None,
        "sorpresa_media_pct": None,
        "estado": "sin_datos",
    }
    if not simbolo:
        return vacio

    try:
        yf_ticker = yf.Ticker(simbolo)
    except Exception:
        return vacio

    calendario, status_cal = safe_yfinance_fetch(
        lambda: yf_ticker.calendar,
        empty_value={},
        context=f"earnings_calendar:calendar:{simbolo}",
    )
    if status_cal != "ok" or not isinstance(calendario, dict):
        calendario = {}

    historico, status_hist = safe_yfinance_fetch(
        lambda: yf_ticker.earnings_history,
        empty_value=pd.DataFrame(),
        context=f"earnings_calendar:history:{simbolo}",
    )
    if status_hist != "ok" or not isinstance(historico, pd.DataFrame):
        historico = pd.DataFrame()

    eps_anterior = None
    sorpresa_media = None
    if not historico.empty:
        if "epsActual" in historico.columns:
            reales = pd.to_numeric(historico["epsActual"], errors="coerce").dropna()
            if not reales.empty:
                eps_anterior = float(reales.iloc[-1])
        if "surprisePercent" in historico.columns:
            sorpresas = pd.to_numeric(historico["surprisePercent"], errors="coerce").dropna()
            if not sorpresas.empty:
                # yfinance devuelve la sorpresa en tanto por uno (0.1273 = +12,73 %).
                sorpresa_media = float(sorpresas.tail(4).mean()) * 100

    nombre = simbolo
    if isinstance(calendario, dict):
        nombre = str(calendario.get("shortName") or simbolo)

    return {
        "ticker": simbolo,
        "nombre": nombre,
        "fecha": _primera_fecha(calendario.get("Earnings Date")),
        "eps_estimado": _float_o_none(calendario.get("Earnings Average")),
        "eps_anterior": eps_anterior,
        "sorpresa_media_pct": sorpresa_media,
        "estado": "ok" if calendario or not historico.empty else "sin_datos",
    }


def construir_tabla_earnings(tickers: Iterable[str], hoy: dt.date | None = None) -> pd.DataFrame:
    """Tabla ordenada por proximidad del próximo earnings.

    Separada del render para poder testearla sin Streamlit. Los tickers sin fecha
    conocida se mantienen al final en vez de descartarse: que Yahoo no publique
    fecha no significa que el ticker no importe.
    """
    referencia = hoy or dt.date.today()
    filas: list[dict[str, Any]] = []

    for ticker in tickers:
        datos = obtener_earnings_ticker(ticker)
        fecha = datos.get("fecha")
        dias = (fecha - referencia).days if isinstance(fecha, dt.date) else None

        filas.append(
            {
                "Ticker": datos["ticker"],
                "Nombre": datos["nombre"],
                "Fecha earnings": fecha,
                "Días": dias,
                "EPS estimado": datos["eps_estimado"],
                "EPS anterior": datos["eps_anterior"],
                "Sorpresa media (%)": datos["sorpresa_media_pct"],
                "Inminente": dias is not None and 0 <= dias <= DIAS_ALERTA_EARNINGS,
            }
        )

    if not filas:
        return pd.DataFrame()

    df = pd.DataFrame(filas)
    # Sin fecha -> al final: se ordena por una clave auxiliar, no por la columna
    # visible, para no ensuciar la tabla con un valor centinela.
    df["_orden"] = df["Días"].apply(lambda d: 10**6 if d is None else (d if d >= 0 else 10**5 + abs(d)))
    df = df.sort_values("_orden").drop(columns=["_orden"]).reset_index(drop=True)
    return df


def _estilo_fila(fila: pd.Series, inminente: bool) -> list[str]:
    """Resalta en ámbar los earnings dentro de la ventana de alerta.

    El estilo debe devolver exactamente tantos elementos como columnas tenga la
    fila VISIBLE, no las del DataFrame de origen (que lleva además la columna
    auxiliar "Inminente"): ese desajuste hace que pandas rechace el styler.
    """
    if inminente:
        return [f"background-color: rgba(245, 176, 76, 0.16); color: {COLOR_WARNING}; font-weight: 600;"] * len(fila)
    return [""] * len(fila)


def mostrar_calendario_earnings(tickers: Iterable[str] | None = None) -> None:
    """Subsección de calendario de resultados dentro de «Mi Watchlist»."""

    st.markdown("### 🗓️ Calendario de resultados")

    lista = [str(t).strip().upper() for t in (tickers or []) if str(t).strip()]
    if not lista:
        st.info("Añade tickers a la watchlist para ver su calendario de resultados.")
        return

    with st.spinner("Consultando próximas fechas de resultados..."):
        df = construir_tabla_earnings(lista)

    if df.empty:
        st.warning("No se pudo recuperar el calendario de resultados de ninguno de los tickers.")
        return

    inminentes = df[df["Inminente"]]
    if not inminentes.empty:
        nombres = ", ".join(inminentes["Ticker"].tolist())
        st.warning(f"⚠️ Resultados en los próximos {DIAS_ALERTA_EARNINGS} días: **{nombres}**")

    sin_fecha = int(df["Fecha earnings"].isna().sum())

    visible = df.drop(columns=["Inminente"]).copy()
    visible["Fecha earnings"] = visible["Fecha earnings"].apply(
        lambda f: f.strftime("%d/%m/%Y") if isinstance(f, dt.date) else "n/d"
    )
    visible["Días"] = visible["Días"].apply(lambda d: "n/d" if d is None else f"{int(d)}")

    st.dataframe(
        visible.style.apply(
            lambda fila: _estilo_fila(fila, bool(df.loc[fila.name, "Inminente"])),
            axis=1,
        ).format(
            {
                "EPS estimado": lambda v: f"{v:.2f}" if isinstance(v, (int, float)) and pd.notna(v) else "n/d",
                "EPS anterior": lambda v: f"{v:.2f}" if isinstance(v, (int, float)) and pd.notna(v) else "n/d",
                "Sorpresa media (%)": lambda v: f"{v:+.1f}%" if isinstance(v, (int, float)) and pd.notna(v) else "n/d",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    pie = (
        "Sorpresa media = desviación del BPA real frente al consenso en los últimos 4 trimestres. "
        f"En ámbar, los resultados dentro de {DIAS_ALERTA_EARNINGS} días."
    )
    if sin_fecha:
        pie += f" {sin_fecha} ticker(s) sin fecha publicada por Yahoo."
    st.caption(pie)
