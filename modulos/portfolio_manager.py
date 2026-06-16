from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from roboadvisor_engine import FinancialEngineError, PortfolioOptimizer


WATCHLIST_PATH = Path("data/watchlist.json")


def _tickers_watchlist() -> list[str]:
    try:
        data = json.loads(WATCHLIST_PATH.read_text())
        if isinstance(data, dict):
            return [str(k).upper() for k in data.keys()]
        if isinstance(data, list):
            return [str(item.get("ticker", item)).upper() for item in data]
    except Exception:
        pass
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def descargar_precios(tickers: tuple[str, ...], period: str) -> pd.DataFrame:
    data = yf.download(list(tickers), period=period, auto_adjust=True, progress=False, threads=True)
    if data.empty:
        return pd.DataFrame()
    close = data["Close"] if isinstance(data.columns, pd.MultiIndex) and "Close" in data.columns.get_level_values(0) else data
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    close = close.dropna(how="all").ffill().dropna(axis=1, how="any")
    return close


def _max_drawdown(series: pd.Series) -> float:
    cummax = series.cummax()
    dd = series / cummax - 1
    return float(dd.min())


def ejecutar_portfolio_manager():
    st.markdown("### ⚖️ Creador y Optimizador de Carteras")
    st.caption("Correlación, concentración y frontera eficiente con tickers de tu watchlist o cartera manual.")

    defaults = _tickers_watchlist() or ["AAPL", "MSFT", "NVDA", "AMD", "SPY"]
    tickers_raw = st.text_input("Tickers de cartera", value=", ".join(defaults))
    capital = st.number_input("Capital a asignar", min_value=100.0, value=10_000.0, step=500.0)
    period = st.selectbox("Histórico", ["1y", "2y", "3y", "5y"], index=2)
    rf = st.number_input("Tasa libre de riesgo anual (%)", min_value=0.0, max_value=10.0, value=4.0, step=0.25)

    tickers = tuple(dict.fromkeys([t.strip().upper() for t in tickers_raw.replace(";", ",").split(",") if t.strip()]))
    if len(tickers) < 2:
        st.warning("Introduce al menos 2 tickers.")
        return

    if not st.button("Optimizar cartera", type="primary", use_container_width=True):
        return

    with st.spinner("Descargando precios y resolviendo frontera eficiente..."):
        prices = descargar_precios(tickers, period)
        if prices.empty or prices.shape[1] < 2:
            st.error("No hay suficientes precios válidos para optimizar.")
            return

        returns = prices.pct_change().dropna()
        corr = returns.corr()
        avg_corr = float(corr.where(~np.eye(len(corr), dtype=bool)).stack().mean())

        c1, c2, c3 = st.columns(3)
        c1.metric("Activos válidos", prices.shape[1])
        c2.metric("Correlación media", f"{avg_corr:.2f}")
        c3.metric("Capital", f"${capital:,.0f}")

        if avg_corr > 0.75:
            st.error("Peligro: la cartera está muy correlacionada. Probablemente no estás diversificando de verdad.")
        elif avg_corr > 0.55:
            st.warning("Diversificación moderada: varios activos se mueven de forma parecida.")
        else:
            st.success("Correlación razonable: hay diversificación estadística.")

        fig_corr = px.imshow(
            corr,
            text_auto=".2f",
            color_continuous_scale="RdBu_r",
            zmin=-1,
            zmax=1,
            title="Matriz de Correlación",
        )
        fig_corr.update_layout(height=500, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_corr, use_container_width=True)

        try:
            optimizer = PortfolioOptimizer(returns, risk_free_rate=rf / 100)
            max_sharpe = optimizer.maximize_sharpe()
            min_vol = optimizer.minimize_volatility()
            frontier = optimizer.efficient_frontier(points=35)
        except FinancialEngineError as exc:
            st.error(str(exc))
            return

        weights = pd.Series(max_sharpe.weights).sort_values(ascending=False)
        allocation = (weights * capital).rename("Asignación $")
        table = pd.DataFrame({"Peso": weights, "Asignación $": allocation})

        portfolio_curve = (1 + returns[weights.index].mul(weights, axis=1).sum(axis=1)).cumprod()
        benchmark_curve = (1 + returns[weights.index].mean(axis=1)).cumprod()
        dd = _max_drawdown(portfolio_curve)

        c4, c5, c6 = st.columns(3)
        c4.metric("Retorno esperado", f"{max_sharpe.expected_return:.2%}")
        c5.metric("Volatilidad", f"{max_sharpe.volatility:.2%}")
        c6.metric("Max Drawdown sim.", f"{dd:.2%}")

        st.markdown("#### Pesos óptimos Max Sharpe")
        st.dataframe(table.style.format({"Peso": "{:.2%}", "Asignación $": "${:,.2f}"}), use_container_width=True)

        fig_frontier = go.Figure()
        fig_frontier.add_trace(go.Scatter(x=frontier["volatility"], y=frontier["expected_return"], mode="lines", name="Frontera"))
        fig_frontier.add_trace(go.Scatter(x=[max_sharpe.volatility], y=[max_sharpe.expected_return], mode="markers", marker=dict(size=15, color="#22c55e"), name="Max Sharpe"))
        fig_frontier.add_trace(go.Scatter(x=[min_vol.volatility], y=[min_vol.expected_return], mode="markers", marker=dict(size=13, color="#f59e0b"), name="Min Vol"))
        fig_frontier.update_layout(height=420, xaxis_title="Volatilidad", yaxis_title="Retorno esperado", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_frontier, use_container_width=True)

        curve_df = pd.DataFrame({"Cartera optimizada": portfolio_curve, "Equal Weight": benchmark_curve})
        fig_curve = px.line(curve_df, title="Backtest de pesos sobre el histórico descargado")
        fig_curve.update_layout(height=420, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_curve, use_container_width=True)
