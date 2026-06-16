"""Advanced options pricing and Greeks module."""

from __future__ import annotations

from dataclasses import dataclass
from math import log, sqrt
from typing import Literal

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from scipy.stats import norm


OptionType = Literal["call", "put"]


@dataclass(frozen=True)
class Greeks:
    """Black-Scholes option Greeks."""

    delta: float
    gamma: float
    theta: float
    vega: float


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    """Compute Black-Scholes d1 and d2."""
    d1 = (log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return d1, d2


def black_scholes_price(S: float, K: float, T: float, r: float, sigma: float, option_type: OptionType) -> float:
    """Calculate theoretical European option price using Black-Scholes.

    Args:
        S: Spot price.
        K: Strike price.
        T: Time to expiry in years.
        r: Risk-free rate as decimal.
        sigma: Implied/expected volatility as decimal.
        option_type: ``"call"`` or ``"put"``.

    Returns:
        Theoretical option price.
    """
    try:
        if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
            return 0.0
        d1, d2 = _d1_d2(S, K, T, r, sigma)
        if option_type == "call":
            return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
        return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))
    except Exception:
        return 0.0


def calculate_greeks(S: float, K: float, T: float, r: float, sigma: float, option_type: OptionType) -> Greeks:
    """Calculate Delta, Gamma, Theta and Vega for a European option."""
    try:
        if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
            return Greeks(0.0, 0.0, 0.0, 0.0)
        d1, d2 = _d1_d2(S, K, T, r, sigma)
        delta = norm.cdf(d1) if option_type == "call" else norm.cdf(d1) - 1
        gamma = norm.pdf(d1) / (S * sigma * sqrt(T))
        theta_call = (-(S * norm.pdf(d1) * sigma) / (2 * sqrt(T))) - r * K * np.exp(-r * T) * norm.cdf(d2)
        theta_put = (-(S * norm.pdf(d1) * sigma) / (2 * sqrt(T))) + r * K * np.exp(-r * T) * norm.cdf(-d2)
        theta = theta_call if option_type == "call" else theta_put
        vega = S * norm.pdf(d1) * sqrt(T)
        return Greeks(delta=float(delta), gamma=float(gamma), theta=float(theta / 365), vega=float(vega / 100))
    except Exception:
        return Greeks(0.0, 0.0, 0.0, 0.0)


@st.cache_data(ttl=1800, show_spinner=False)
def _download_option_chain(ticker: str, expiration: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download option chain from yfinance."""
    try:
        chain = yf.Ticker(ticker).option_chain(expiration)
        return chain.calls.copy(), chain.puts.copy()
    except Exception:
        return pd.DataFrame(), pd.DataFrame()


def _current_price(ticker: str) -> float:
    """Get latest price from yfinance."""
    try:
        fast_info = yf.Ticker(ticker).fast_info
        price = fast_info.get("last_price") or fast_info.get("lastPrice")
        if price:
            return float(price)
        hist = yf.Ticker(ticker).history(period="5d")
        return float(hist["Close"].dropna().iloc[-1]) if not hist.empty else 0.0
    except Exception:
        return 0.0


def build_volatility_smile(calls: pd.DataFrame, puts: pd.DataFrame, spot: float) -> go.Figure | None:
    """Build volatility smile chart from real option chain."""
    try:
        fig = go.Figure()
        for label, df, color in (("Calls", calls, "#22c55e"), ("Puts", puts, "#ef4444")):
            if df.empty or "strike" not in df.columns or "impliedVolatility" not in df.columns:
                continue
            clean = df[["strike", "impliedVolatility"]].dropna().sort_values("strike")
            clean = clean[(clean["impliedVolatility"] > 0) & (clean["impliedVolatility"] < 5)]
            if clean.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=clean["strike"],
                    y=clean["impliedVolatility"] * 100,
                    mode="lines+markers",
                    name=label,
                    line=dict(color=color, shape="spline", width=2.5),
                )
            )
        if not fig.data:
            return None
        fig.add_vline(x=spot, line_dash="dash", line_color="#facc15", annotation_text="Spot/ATM")
        fig.update_layout(
            title="Volatility Smile - Implied Volatility por Strike",
            xaxis_title="Strike",
            yaxis_title="Implied Volatility (%)",
            height=520,
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig
    except Exception:
        return None


def render_derivados(ticker: str) -> None:
    """Render advanced options dashboard."""
    st.markdown(f"### 🧮 Opciones Avanzadas: Black-Scholes & Griegas — {ticker}")
    st.caption("Pricing teórico, griegas y sonrisa de volatilidad implícita con cadena real de opciones.")

    spot = _current_price(ticker)
    if spot <= 0:
        st.error("No se pudo obtener precio spot.")
        return

    try:
        expirations = list(yf.Ticker(ticker).options)
    except Exception:
        expirations = []
    if not expirations:
        st.warning("Yahoo Finance no devolvió vencimientos de opciones para este ticker.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    expiration = c1.selectbox("Vencimiento", expirations, index=0)
    option_type_ui = c2.selectbox("Tipo", ["call", "put"], index=0)
    strike = c3.number_input("Strike", min_value=0.01, value=float(round(spot, 2)), step=1.0)
    days = c4.number_input("Días a vencimiento", min_value=1, value=30, step=1)
    sigma = c5.slider("Volatilidad usada (%)", 1.0, 200.0, 30.0, 1.0) / 100
    rate = st.slider("Tasa libre de riesgo (%)", 0.0, 10.0, 4.5, 0.25) / 100

    T = float(days) / 365
    option_type = "call" if option_type_ui == "call" else "put"
    price = black_scholes_price(spot, float(strike), T, rate, sigma, option_type)
    greeks = calculate_greeks(spot, float(strike), T, rate, sigma, option_type)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Precio teórico", f"${price:,.2f}")
    m2.metric("Delta", f"{greeks.delta:.3f}")
    m3.metric("Gamma", f"{greeks.gamma:.4f}")
    m4.metric("Theta/día", f"{greeks.theta:.4f}")
    m5.metric("Vega / 1 vol pt", f"{greeks.vega:.4f}")

    with st.spinner("Descargando cadena de opciones real..."):
        calls, puts = _download_option_chain(ticker, expiration)
        fig = build_volatility_smile(calls, puts, spot)

    if fig:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay datos suficientes de volatilidad implícita para dibujar la sonrisa.")
