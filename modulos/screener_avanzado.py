"""Advanced multi-factor stock screener powered by FMP.

The module first tries Financial Modeling Prep's stock-screener endpoint. Current
FMP keys may not have access to legacy v3 screener endpoints, so the renderer has
a deterministic liquid-universe fallback and still enriches candidates with FMP
fundamental data when available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import yfinance as yf

from modulos.fmp_api import BASE_URL, FMP_API_KEY, REQUEST_TIMEOUT


SCREENER_ENDPOINT = f"{BASE_URL}/stock-screener"
KEY_METRICS_ENDPOINT = f"{BASE_URL}/key-metrics/{{ticker}}"


SECTORES_FMP = [
    "Technology",
    "Healthcare",
    "Financial Services",
    "Consumer Cyclical",
    "Communication Services",
    "Industrials",
    "Consumer Defensive",
    "Energy",
    "Basic Materials",
    "Real Estate",
    "Utilities",
]


FALLBACK_UNIVERSE: dict[str, list[str]] = {
    "Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "CSCO", "QCOM", "TXN", "AMAT", "MU", "INTC"],
    "Healthcare": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "AMGN", "ISRG", "PFE", "DHR", "BMY"],
    "Financial Services": ["JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "AXP", "BLK", "C", "SCHW", "SPGI"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "BKNG", "TJX", "ORLY"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "TMUS", "VZ", "T", "CMCSA", "EA", "TTWO"],
    "Industrials": ["CAT", "GE", "HON", "UNP", "RTX", "DE", "UPS", "LMT", "BA", "ETN", "WM"],
    "Consumer Defensive": ["WMT", "COST", "PG", "KO", "PEP", "PM", "MDLZ", "CL", "MO", "KMB"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL"],
    "Basic Materials": ["LIN", "SHW", "APD", "ECL", "NEM", "FCX", "DOW", "DD", "NUE", "MLM"],
    "Real Estate": ["PLD", "AMT", "EQIX", "WELL", "SPG", "O", "DLR", "PSA", "CCI", "VICI"],
    "Utilities": ["NEE", "SO", "DUK", "CEG", "AEP", "SRE", "D", "EXC", "XEL", "PEG"],
}


@dataclass(frozen=True)
class ScreenerFilters:
    """Filters accepted by the FMP stock-screener endpoint."""

    market_cap_min: int
    sectors: tuple[str, ...]
    dividend_yield_min: float
    beta_min: float
    beta_max: float
    pe_min: float
    pe_max: float
    roe_min: float
    limit: int


def _safe_float(value: Any, default: float = np.nan) -> float:
    """Convert arbitrary value to float without raising."""
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except Exception:
        return default


def _request_json(url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Perform a GET request and return a list payload."""
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return payload
        return []
    except Exception:
        return []


def _fallback_universe_dataframe(filters: ScreenerFilters) -> pd.DataFrame:
    """Build a liquid-stock fallback universe when FMP screener is unavailable."""
    rows: list[dict[str, Any]] = []
    sectors = filters.sectors or tuple(SECTORES_FMP)
    for sector in sectors:
        for symbol in FALLBACK_UNIVERSE.get(sector, []):
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                fast = getattr(ticker, "fast_info", {}) or {}
                market_cap = _safe_float(info.get("marketCap") or fast.get("market_cap"))
                price = _safe_float(info.get("currentPrice") or fast.get("last_price") or fast.get("lastPrice"))
                beta = _safe_float(info.get("beta"), 1.0)
                dividend_yield = _safe_float(info.get("dividendYield"), 0.0)
                if market_cap < filters.market_cap_min or beta < filters.beta_min or beta > filters.beta_max:
                    continue
                if dividend_yield * 100 < filters.dividend_yield_min:
                    continue
                rows.append(
                    {
                        "symbol": symbol,
                        "companyName": info.get("shortName") or info.get("longName") or symbol,
                        "sector": info.get("sector") or sector,
                        "marketCap": market_cap,
                        "price": price,
                        "beta": beta,
                        "lastAnnualDividend": dividend_yield * price if price and not np.isnan(price) else np.nan,
                    }
                )
            except Exception:
                continue
    return pd.DataFrame(rows).head(filters.limit)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fmp_screener(filters: ScreenerFilters) -> pd.DataFrame:
    """Download stock screener rows from FMP with a robust fallback."""
    try:
        rows: list[dict[str, Any]] = []
        sector_list = filters.sectors or tuple(SECTORES_FMP)
        for sector in sector_list:
            params: dict[str, Any] = {
                "apikey": FMP_API_KEY,
                "marketCapMoreThan": filters.market_cap_min,
                "dividendMoreThan": filters.dividend_yield_min / 100,
                "betaMoreThan": filters.beta_min,
                "betaLowerThan": filters.beta_max,
                "sector": sector,
                "isEtf": "false",
                "isFund": "false",
                "isActivelyTrading": "true",
                "limit": max(10, min(filters.limit, 1000)),
            }
            rows.extend(_request_json(SCREENER_ENDPOINT, params))

        if not rows:
            return _fallback_universe_dataframe(filters)

        df = pd.DataFrame(rows).drop_duplicates(subset=["symbol"])
        for column in ("marketCap", "price", "beta", "lastAnnualDividend", "volume"):
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")
        return df.head(filters.limit)
    except Exception:
        return _fallback_universe_dataframe(filters)


@st.cache_data(ttl=86400, show_spinner=False)
def enrich_with_quality_metrics(symbols: tuple[str, ...]) -> pd.DataFrame:
    """Fetch P/E, ROE, ROIC and earnings yield for a set of symbols."""
    from modulos.fmp_api import extraer_datos_fundamentales_fmp, obtener_cotizacion_fmp

    records: list[dict[str, Any]] = []
    for symbol in symbols:
        pe = roe = roic = earnings_yield = np.nan
        try:
            _, _, _, metrics = extraer_datos_fundamentales_fmp(symbol, 1)
            if metrics is not None and not metrics.empty:
                latest = metrics.iloc[-1]
                roe = _safe_float(latest.get("returnOnEquity") or latest.get("roe"))
                roic = _safe_float(latest.get("returnOnInvestedCapital") or latest.get("roic"))
                earnings_yield = _safe_float(latest.get("earningsYield"))
            price = obtener_cotizacion_fmp(symbol)
            if price:
                # Use FMP income statement EPS when possible.
                is_df, _, _, _ = extraer_datos_fundamentales_fmp(symbol, 1)
                if is_df is not None and not is_df.empty:
                    eps_col = "epsdiluted" if "epsdiluted" in is_df.columns else "eps"
                    if eps_col in is_df.columns:
                        eps = _safe_float(is_df[eps_col].dropna().iloc[-1])
                        pe = price / eps if eps and eps > 0 else np.nan
                        earnings_yield = eps / price if price > 0 and (np.isnan(earnings_yield) or earnings_yield == 0) else earnings_yield
            if np.isnan(pe) or np.isnan(roe):
                info = yf.Ticker(symbol).info or {}
                pe = pe if not np.isnan(pe) else _safe_float(info.get("trailingPE") or info.get("forwardPE"))
                roe = roe if not np.isnan(roe) else _safe_float(info.get("returnOnEquity"))
                earnings_yield = earnings_yield if not np.isnan(earnings_yield) else (1 / pe if pe and pe > 0 else np.nan)
        except Exception:
            pass
        records.append({"symbol": symbol, "peRatio": pe, "roe": roe, "roic": roic, "earningsYield": earnings_yield})
    return pd.DataFrame(records)


def apply_multifactor_score(df: pd.DataFrame, filters: ScreenerFilters) -> pd.DataFrame:
    """Apply Greenblatt-style ranking: high Earnings Yield + high ROIC."""
    if df.empty:
        return df
    result = df.copy()
    symbols = tuple(result["symbol"].dropna().astype(str).head(filters.limit).tolist())
    enrichment = enrich_with_quality_metrics(symbols)
    if not enrichment.empty:
        result = result.merge(enrichment, on="symbol", how="left")

    result["peRatio"] = pd.to_numeric(result.get("peRatio"), errors="coerce")
    result["roe"] = pd.to_numeric(result.get("roe"), errors="coerce")
    result["roic"] = pd.to_numeric(result.get("roic"), errors="coerce")
    result["earningsYield"] = pd.to_numeric(result.get("earningsYield"), errors="coerce")
    result["roic"] = result["roic"].fillna(result["roe"])
    result["earningsYield"] = result["earningsYield"].fillna(1 / result["peRatio"].replace(0, np.nan))

    if "lastAnnualDividend" in result.columns and "price" in result.columns:
        result["dividendYield"] = (result["lastAnnualDividend"] / result["price"]).replace([np.inf, -np.inf], np.nan)
    else:
        result["dividendYield"] = np.nan

    result = result[
        result["peRatio"].between(filters.pe_min, filters.pe_max, inclusive="both")
        & (result["roe"].fillna(-999) >= filters.roe_min / 100)
    ].copy()
    if result.empty:
        return result

    result["earningsYieldRank"] = result["earningsYield"].rank(ascending=False, method="min")
    result["roicRank"] = result["roic"].rank(ascending=False, method="min")
    result["magicFormulaScore"] = result["earningsYieldRank"] + result["roicRank"]
    result["roePct"] = result["roe"] * 100
    result["roicPct"] = result["roic"] * 100
    result["earningsYieldPct"] = result["earningsYield"] * 100
    result["dividendYieldPct"] = result["dividendYield"] * 100
    return result.sort_values("magicFormulaScore", ascending=True)


def render_screener_avanzado() -> None:
    """Render the institutional multi-factor screener."""
    st.markdown("### 🌐 Screener Global Multi-Factor")
    st.caption("Filtra acciones por fundamentales y ordena por una aproximación de Magic Formula: Earnings Yield + ROIC.")

    with st.sidebar.expander("Filtros Screener Avanzado", expanded=True):
        market_cap_min = st.slider("Market Cap mínimo ($B)", 0.1, 500.0, 1.0, 0.5)
        sectors = st.multiselect("Sector", SECTORES_FMP, default=["Technology", "Healthcare", "Financial Services"])
        dividend_yield_min = st.slider("Dividend Yield mínimo (%)", 0.0, 10.0, 0.0, 0.25)
        beta_range = st.slider("Beta", 0.0, 3.0, (0.0, 2.0), 0.1)
        pe_range = st.slider("Price / Earnings", 0.0, 80.0, (1.0, 35.0), 1.0)
        roe_min = st.slider("ROE mínimo (%)", -50.0, 100.0, 10.0, 1.0)
        limit = st.slider("Máximo de empresas a enriquecer", 10, 250, 60, 5)

    filters = ScreenerFilters(
        market_cap_min=int(market_cap_min * 1_000_000_000),
        sectors=tuple(sectors),
        dividend_yield_min=float(dividend_yield_min),
        beta_min=float(beta_range[0]),
        beta_max=float(beta_range[1]),
        pe_min=float(pe_range[0]),
        pe_max=float(pe_range[1]),
        roe_min=float(roe_min),
        limit=int(limit),
    )

    with st.spinner("Descargando universo FMP y calculando ranking multi-factor..."):
        raw = fetch_fmp_screener(filters)
        ranked = apply_multifactor_score(raw, filters)

    if ranked.empty:
        st.warning("No se encontraron compañías que cumplan los filtros o FMP/Yahoo no devolvieron ratios suficientes.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Candidatas", len(ranked))
    c2.metric("Top Magic Formula", str(ranked.iloc[0]["symbol"]))
    c3.metric("ROIC top", f"{ranked.iloc[0].get('roicPct', np.nan):.1f}%")

    visible = [column for column in ["symbol", "companyName", "sector", "marketCap", "price", "beta", "peRatio", "roePct", "roicPct", "earningsYieldPct", "dividendYieldPct", "magicFormulaScore"] if column in ranked.columns]
    st.dataframe(
        ranked[visible].style.format({"marketCap": "${:,.0f}", "price": "${:,.2f}", "beta": "{:.2f}", "peRatio": "{:.1f}x", "roePct": "{:.1f}%", "roicPct": "{:.1f}%", "earningsYieldPct": "{:.1f}%", "dividendYieldPct": "{:.1f}%", "magicFormulaScore": "{:.0f}"}),
        use_container_width=True,
        hide_index=True,
    )

    plot_df = ranked.dropna(subset=["roePct", "peRatio", "marketCap"]).copy()
    if not plot_df.empty:
        fig = px.scatter(plot_df, x="roePct", y="peRatio", size="marketCap", color="sector", hover_name="symbol", hover_data={"companyName": True, "roicPct": ":.1f", "earningsYieldPct": ":.1f"}, labels={"roePct": "ROE (%)", "peRatio": "P/E", "marketCap": "Market Cap"}, title="Mapa Multi-Factor: ROE vs P/E", size_max=55)
        fig.update_layout(height=560, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
