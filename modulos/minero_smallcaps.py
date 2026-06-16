from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


UNIVERSO_STARTUP_LIKE: dict[str, list[str]] = {
    "IA / Automatizacion": ["SOUN", "BBAI", "PATH", "AI", "SERV", "UPST"],
    "Espacio / Defensa": ["RKLB", "LUNR", "ASTS", "ACHR", "JOBY", "PL"],
    "Computacion cuantica": ["IONQ", "RGTI", "QBTS", "QUBT", "ARQQ"],
    "Biotech / HealthTech": ["RXRX", "HIMS", "TEM", "DNA", "TWST", "SDGR"],
    "Energia / ClimateTech": ["ENVX", "BE", "SLDP", "FLNC", "AMPS", "CHPT"],
    "Fintech / Plataformas": ["SOFI", "HOOD", "AFRM", "NU", "MQ"],
}


@dataclass(frozen=True)
class FiltrosMinero:
    min_market_cap: float
    max_market_cap: float
    min_score: float
    min_growth: float
    min_liquidity_usd: float


def _normalizar_numero(valor: object, default: float = np.nan) -> float:
    try:
        numero = float(valor)
        return numero if isfinite(numero) else default
    except Exception:
        return default


def _fmt_bn(valor: float) -> str:
    if not isfinite(valor):
        return "N/D"
    return f"${valor / 1_000_000_000:,.2f}B"


def _fmt_pct(valor: float) -> str:
    if not isfinite(valor):
        return "N/D"
    return f"{valor * 100:+.1f}%"


def _leer_csv_historico(ruta_csv: Path) -> pd.DataFrame | None:
    try:
        if not ruta_csv.exists() or ruta_csv.stat().st_size == 0:
            return None
        df = pd.read_csv(ruta_csv)
        return None if df.empty else df
    except Exception:
        return None


def _obtener_info_segura(ticker: yf.Ticker) -> dict:
    try:
        info = ticker.info
        return info if isinstance(info, dict) else {}
    except Exception:
        return {}


def _obtener_historial_seguro(ticker: yf.Ticker) -> pd.DataFrame:
    try:
        hist = ticker.history(period="1y", auto_adjust=True)
        return hist if isinstance(hist, pd.DataFrame) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _score_startup(info: dict, hist: pd.DataFrame) -> dict[str, float | str]:
    market_cap = _normalizar_numero(info.get("marketCap"))
    revenue_growth = _normalizar_numero(info.get("revenueGrowth"))
    gross_margin = _normalizar_numero(info.get("grossMargins"))
    current_ratio = _normalizar_numero(info.get("currentRatio"))
    total_cash = _normalizar_numero(info.get("totalCash"), 0.0)
    total_debt = _normalizar_numero(info.get("totalDebt"), 0.0)
    free_cash_flow = _normalizar_numero(info.get("freeCashflow"))
    operating_cashflow = _normalizar_numero(info.get("operatingCashflow"))
    insider_ownership = _normalizar_numero(info.get("heldPercentInsiders"), 0.0)
    institutional_ownership = _normalizar_numero(info.get("heldPercentInstitutions"), 0.0)
    short_float = _normalizar_numero(info.get("shortPercentOfFloat"), 0.0)

    close = pd.to_numeric(hist.get("Close", pd.Series(dtype=float)), errors="coerce").dropna()
    volume = pd.to_numeric(hist.get("Volume", pd.Series(dtype=float)), errors="coerce").dropna()

    price = float(close.iloc[-1]) if not close.empty else _normalizar_numero(info.get("currentPrice"))
    ref_6m = float(close.iloc[-126]) if len(close) >= 126 else (float(close.iloc[0]) if not close.empty else np.nan)
    high_52w = float(close.max()) if not close.empty else _normalizar_numero(info.get("fiftyTwoWeekHigh"))
    momentum_6m = (price / ref_6m - 1) if isfinite(price) and isfinite(ref_6m) and ref_6m > 0 else np.nan
    distancia_max_52w = (price / high_52w - 1) if isfinite(price) and isfinite(high_52w) and high_52w > 0 else np.nan
    liquidez_media = float((volume.tail(60).mean() or 0) * price) if not volume.empty and isfinite(price) else np.nan

    score = 0.0

    if isfinite(market_cap):
        if 100_000_000 <= market_cap <= 8_000_000_000:
            score += 14
        elif market_cap <= 15_000_000_000:
            score += 7

    if isfinite(revenue_growth):
        score += min(max(revenue_growth, 0), 0.8) / 0.8 * 24
        if revenue_growth < 0:
            score -= 8

    if isfinite(gross_margin):
        score += min(max(gross_margin, 0), 0.75) / 0.75 * 16

    if total_debt <= 0 and total_cash > 0:
        score += 10
    elif total_debt > 0:
        cash_debt = total_cash / total_debt
        score += min(max(cash_debt, 0), 2.0) / 2.0 * 10

    if isfinite(current_ratio):
        score += min(max(current_ratio, 0), 4.0) / 4.0 * 8

    if isfinite(free_cash_flow) and free_cash_flow > 0:
        score += 8
    elif isfinite(operating_cashflow) and operating_cashflow > 0:
        score += 5

    if isfinite(momentum_6m):
        score += min(max(momentum_6m + 0.2, 0), 0.8) / 0.8 * 12

    if isfinite(insider_ownership):
        score += min(insider_ownership, 0.25) / 0.25 * 5

    if isfinite(institutional_ownership):
        score += min(institutional_ownership, 0.65) / 0.65 * 3

    if isfinite(short_float) and short_float > 0.18:
        score -= 6

    if isfinite(liquidez_media) and liquidez_media < 1_000_000:
        score -= 8

    score = float(min(max(score, 0), 100))
    if score >= 75:
        veredicto = "Alta conviccion"
    elif score >= 58:
        veredicto = "Vigilancia prioritaria"
    elif score >= 42:
        veredicto = "Especulativa controlada"
    else:
        veredicto = "Descartar por ahora"

    return {
        "Score": score,
        "Veredicto": veredicto,
        "Market Cap": market_cap,
        "Crecimiento Ventas": revenue_growth,
        "Margen Bruto": gross_margin,
        "Current Ratio": current_ratio,
        "Cash": total_cash,
        "Deuda": total_debt,
        "FCF": free_cash_flow,
        "Momentum 6M": momentum_6m,
        "Distancia Max 52W": distancia_max_52w,
        "Liquidez Media $": liquidez_media,
        "Insiders": insider_ownership,
        "Instituciones": institutional_ownership,
        "Short Float": short_float,
        "Precio": price,
    }


@st.cache_data(ttl=21600, show_spinner=False)
def escanear_universo_startup(tickers: tuple[str, ...]) -> pd.DataFrame:
    filas: list[dict[str, object]] = []

    for symbol in tickers:
        ticker_limpio = symbol.upper().strip()
        if not ticker_limpio:
            continue

        empresa = yf.Ticker(ticker_limpio)
        info = _obtener_info_segura(empresa)
        hist = _obtener_historial_seguro(empresa)
        metricas = _score_startup(info, hist)

        sector = info.get("sector") or "N/D"
        industria = info.get("industry") or "N/D"
        nombre = info.get("shortName") or info.get("longName") or ticker_limpio
        fila = {
            "Ticker": ticker_limpio,
            "Empresa": nombre,
            "Sector": sector,
            "Industria": industria,
            **metricas,
        }
        filas.append(fila)

    df = pd.DataFrame(filas)
    if df.empty:
        return df
    return df.sort_values(["Score", "Crecimiento Ventas", "Momentum 6M"], ascending=[False, False, False])


def _aplicar_filtros(df: pd.DataFrame, filtros: FiltrosMinero) -> pd.DataFrame:
    if df.empty:
        return df

    filtrado = df.copy()
    filtrado = filtrado[pd.to_numeric(filtrado["Score"], errors="coerce").fillna(0) >= filtros.min_score]
    filtrado = filtrado[pd.to_numeric(filtrado["Market Cap"], errors="coerce").fillna(0).between(filtros.min_market_cap, filtros.max_market_cap)]
    filtrado = filtrado[pd.to_numeric(filtrado["Crecimiento Ventas"], errors="coerce").fillna(-9) >= filtros.min_growth]
    filtrado = filtrado[pd.to_numeric(filtrado["Liquidez Media $"], errors="coerce").fillna(0) >= filtros.min_liquidity_usd]
    return filtrado


def _preparar_tabla(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    tabla = df.copy()
    tabla["Score"] = tabla["Score"].map(lambda x: f"{x:.1f}")
    tabla["Market Cap"] = tabla["Market Cap"].map(_fmt_bn)
    tabla["Crecimiento Ventas"] = tabla["Crecimiento Ventas"].map(_fmt_pct)
    tabla["Margen Bruto"] = tabla["Margen Bruto"].map(_fmt_pct)
    tabla["Momentum 6M"] = tabla["Momentum 6M"].map(_fmt_pct)
    tabla["Distancia Max 52W"] = tabla["Distancia Max 52W"].map(_fmt_pct)
    tabla["Liquidez Media $"] = tabla["Liquidez Media $"].map(lambda x: f"${x / 1_000_000:,.1f}M" if isfinite(x) else "N/D")
    tabla["Insiders"] = tabla["Insiders"].map(_fmt_pct)
    tabla["Short Float"] = tabla["Short Float"].map(_fmt_pct)
    tabla["Precio"] = tabla["Precio"].map(lambda x: f"${x:,.2f}" if isfinite(x) else "N/D")
    columnas = [
        "Ticker",
        "Empresa",
        "Score",
        "Veredicto",
        "Market Cap",
        "Crecimiento Ventas",
        "Margen Bruto",
        "Momentum 6M",
        "Liquidez Media $",
        "Insiders",
        "Short Float",
        "Precio",
    ]
    return tabla[[col for col in columnas if col in tabla.columns]]


def _universo_desde_ui() -> tuple[str, ...]:
    sectores = st.multiselect(
        "Segmentos a rastrear",
        options=list(UNIVERSO_STARTUP_LIKE.keys()),
        default=list(UNIVERSO_STARTUP_LIKE.keys()),
    )
    tickers = [ticker for sector in sectores for ticker in UNIVERSO_STARTUP_LIKE[sector]]
    extras = st.text_input("Tickers adicionales", placeholder="Ej: CRSP, DUOL, TMDX")
    if extras:
        tickers.extend([item.strip().upper() for item in extras.replace(";", ",").split(",")])
    return tuple(dict.fromkeys([ticker for ticker in tickers if ticker]))


def ejecutar_visor_smallcaps():
    st.markdown("### ⛏️ Minero de Small Caps (Joyas Ocultas)")
    st.caption(
        "Busca empresas cotizadas de perfil startup: crecimiento alto, balance financiable, liquidez suficiente, "
        "momentum sano y señales de alineación directiva. Es un filtro de ideas, no una recomendación de compra."
    )

    ruta_csv = Path("data/small_caps_oro.csv")
    historico = _leer_csv_historico(ruta_csv)
    if historico is not None:
        fecha_mod = datetime.fromtimestamp(ruta_csv.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        with st.expander(f"Snapshot previo del minero nocturno ({fecha_mod})", expanded=False):
            st.dataframe(historico, use_container_width=True, hide_index=True)

    with st.expander("Configuracion del escaneo", expanded=True):
        universo = _universo_desde_ui()
        c1, c2, c3, c4 = st.columns(4)
        min_score = c1.slider("Score minimo", 0, 100, 45, 5)
        max_cap_bn = c2.slider("Market cap max.", 0.5, 20.0, 10.0, 0.5)
        min_growth_pct = c3.slider("Crecimiento ventas min.", -50, 100, 0, 5)
        min_liq_m = c4.slider("Liquidez media min.", 0.0, 25.0, 1.0, 0.5)

    filtros = FiltrosMinero(
        min_market_cap=50_000_000,
        max_market_cap=max_cap_bn * 1_000_000_000,
        min_score=float(min_score),
        min_growth=float(min_growth_pct) / 100,
        min_liquidity_usd=min_liq_m * 1_000_000,
    )

    if not universo:
        st.warning("Selecciona al menos un segmento o introduce tickers manuales.")
        return

    ejecutar = st.button("🔎 Ejecutar escaneo startup-like", type="primary", use_container_width=True)
    auto_ejecutar = historico is None

    if ejecutar or auto_ejecutar:
        with st.spinner(f"Analizando {len(universo)} candidatos con datos de mercado y fundamentales..."):
            df = escanear_universo_startup(universo)
    else:
        st.info("Ajusta los filtros y ejecuta el escaneo cuando quieras actualizar las oportunidades.")
        return

    if df.empty:
        st.error("No se pudieron recuperar datos suficientes para el universo seleccionado.")
        return

    filtrado = _aplicar_filtros(df, filtros)
    top = filtrado.head(15)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Universo rastreado", len(df))
    c2.metric("Candidatas filtradas", len(filtrado))
    c3.metric("Mejor score", f"{df['Score'].max():.1f}")
    c4.metric("Top ticker", str(df.iloc[0]["Ticker"]))

    if top.empty:
        st.warning("Ninguna empresa supera ahora los filtros elegidos. Muestro las 10 mejores para vigilancia.")
        top = df.head(10)

    st.markdown("#### Radar de oportunidades")
    st.dataframe(_preparar_tabla(top), use_container_width=True, hide_index=True)

    candidata = top.iloc[0]
    st.markdown("#### Tesis rapida de la candidata principal")
    st.write(
        f"**{candidata['Ticker']} - {candidata['Empresa']}** combina score **{candidata['Score']:.1f}**, "
        f"crecimiento de ventas {_fmt_pct(candidata['Crecimiento Ventas'])}, margen bruto "
        f"{_fmt_pct(candidata['Margen Bruto'])} y momentum 6M {_fmt_pct(candidata['Momentum 6M'])}. "
        "La siguiente revision debe confirmar dilucion, runway de caja y proximos catalizadores de producto."
    )

    with st.expander("Como interpretar el score"):
        st.markdown(
            """
            - **Crecimiento y margen bruto:** priorizan modelos con traccion y posible escalabilidad.
            - **Caja/deuda y current ratio:** penalizan empresas que podrian necesitar ampliaciones agresivas.
            - **Momentum y liquidez:** evitan ideas iliquidas o tecnicamente rotas.
            - **Insiders/short float:** suman alineacion directiva y restan riesgo de posicionamiento extremo.
            """
        )
