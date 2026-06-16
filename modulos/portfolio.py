"""Portfolio risk and Markowitz optimization module."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from scipy.optimize import minimize


TRADING_DAYS = 252


@dataclass(frozen=True)
class PortfolioOptimizationResult:
    """Container for optimized portfolio results."""

    allocation: pd.DataFrame
    expected_return: float
    volatility: float
    sharpe_ratio: float


def _clean_tickers(tickers: Sequence[str]) -> list[str]:
    """Normalize ticker input."""
    return list(dict.fromkeys([str(t).upper().strip() for t in tickers if str(t).strip()]))


@st.cache_data(ttl=3600, show_spinner=False)
def _download_prices(tickers: tuple[str, ...], period: str = "1y") -> pd.DataFrame:
    """Download adjusted close prices from Yahoo Finance."""
    try:
        raw = yf.download(list(tickers), period=period, auto_adjust=True, progress=False, threads=True)
        if raw.empty:
            return pd.DataFrame()
        close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) and "Close" in raw.columns.get_level_values(0) else raw
        if isinstance(close, pd.Series):
            close = close.to_frame(tickers[0])
        return close.ffill().dropna(axis=1, how="any")
    except Exception:
        return pd.DataFrame()


def _daily_returns(tickers: Sequence[str], period: str = "1y") -> pd.DataFrame:
    """Return daily percentage returns for tickers."""
    clean = tuple(_clean_tickers(tickers))
    prices = _download_prices(clean, period=period)
    if prices.empty:
        return pd.DataFrame()
    return prices.pct_change().dropna(how="any")


def plot_correlation_matrix(tickers: Sequence[str]) -> go.Figure | None:
    """Plot Pearson correlation matrix for one year of daily returns.

    Args:
        tickers: List of tickers to compare.

    Returns:
        Plotly Heatmap figure or ``None`` if insufficient data.
    """
    try:
        returns = _daily_returns(tickers, period="1y")
        if returns.empty or returns.shape[1] < 2:
            return None
        corr = returns.corr()
        fig = go.Figure(
            data=go.Heatmap(
                z=corr.values,
                x=corr.columns,
                y=corr.index,
                zmin=-1,
                zmax=1,
                colorscale=[
                    [0.0, "#16a34a"],
                    [0.5, "#facc15"],
                    [1.0, "#dc2626"],
                ],
                text=np.round(corr.values, 2),
                texttemplate="%{text}",
                hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>",
            )
        )
        fig.update_layout(
            title="Matriz de Correlación Pearson",
            height=520,
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig
    except Exception:
        return None


def detectar_correlaciones_altas(tickers: Sequence[str], threshold: float = 0.85) -> list[str]:
    """Detect pairs with dangerously high correlation."""
    returns = _daily_returns(tickers, period="1y")
    if returns.empty or returns.shape[1] < 2:
        return []
    corr = returns.corr()
    warnings: list[str] = []
    columns = list(corr.columns)
    for i, left in enumerate(columns):
        for right in columns[i + 1 :]:
            value = float(corr.loc[left, right])
            if value > threshold:
                warnings.append(f"{left} y {right} tienen correlación {value:.2f}. Estás apostando al mismo caballo.")
    return warnings


def calcular_frontera_eficiente(tickers: Sequence[str], capital_euros: float) -> pd.DataFrame:
    """Optimize portfolio weights to maximize Sharpe ratio.

    A cash component is included as a risk-free asset, capped at 35%, so the
    optimizer can leave part of the capital in liquidity when risk-adjusted
    returns do not compensate volatility.

    Args:
        tickers: Risk asset tickers.
        capital_euros: Capital to allocate.

    Returns:
        DataFrame with ticker, weight and euro allocation.
    """
    try:
        returns = _daily_returns(tickers, period="1y")
        if returns.empty or returns.shape[1] < 2:
            return pd.DataFrame()

        assets = list(returns.columns)
        mean_returns = returns.mean().to_numpy() * TRADING_DAYS
        cov = returns.cov().to_numpy() * TRADING_DAYS
        risk_free_rate = 0.03
        n_assets = len(assets)

        def portfolio_metrics(weights: np.ndarray) -> tuple[float, float, float]:
            risky_weights = weights[:n_assets]
            cash_weight = weights[-1]
            expected = float(risky_weights @ mean_returns + cash_weight * risk_free_rate)
            variance = float(risky_weights.T @ cov @ risky_weights)
            vol = float(np.sqrt(max(variance, 1e-12)))
            sharpe = (expected - risk_free_rate) / vol
            return expected, vol, sharpe

        def objective(weights: np.ndarray) -> float:
            return -portfolio_metrics(weights)[2]

        bounds = [(0.0, 1.0)] * n_assets + [(0.0, 0.35)]
        constraints = [{"type": "eq", "fun": lambda weights: np.sum(weights) - 1.0}]
        x0 = np.array([0.9 / n_assets] * n_assets + [0.1])
        result = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints)
        if not result.success:
            return pd.DataFrame()

        expected, vol, sharpe = portfolio_metrics(result.x)
        labels = assets + ["LIQUIDEZ"]
        allocation = pd.DataFrame(
            {
                "Ticker": labels,
                "Peso": result.x,
                "Capital EUR": result.x * float(capital_euros),
                "Retorno esperado cartera": expected,
                "Volatilidad cartera": vol,
                "Sharpe": sharpe,
            }
        )
        return allocation
    except Exception:
        return pd.DataFrame()


def render_portfolio_manager(lista_tickers_watchlist: Sequence[str] | None = None) -> None:
    """Render the Streamlit portfolio manager.

    Args:
        lista_tickers_watchlist: Optional tickers from current watchlist.
    """
    st.markdown("### ⚖️ Portfolio Manager & Correlaciones")
    st.caption("Evalúa diversificación real y calcula una asignación Markowitz con liquidez.")

    defaults = list(lista_tickers_watchlist or ["AAPL", "MSFT", "NVDA", "AMD"])
    tickers_raw = st.text_input("Tickers", value=", ".join(defaults))
    capital = st.number_input("Capital disponible (€)", min_value=100.0, value=10_000.0, step=500.0)
    tickers = _clean_tickers(tickers_raw.replace(";", ",").split(","))

    if len(tickers) < 2:
        st.warning("Introduce al menos dos tickers.")
        return

    if not st.button("Analizar cartera", type="primary", use_container_width=True):
        return

    with st.spinner("Calculando correlaciones y frontera eficiente..."):
        fig = plot_correlation_matrix(tickers)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("No se pudieron descargar retornos suficientes para la matriz.")
            return

        for warning in detectar_correlaciones_altas(tickers):
            st.warning(warning)

        allocation = calcular_frontera_eficiente(tickers, capital)
        if allocation.empty:
            st.error("No se pudo resolver la optimización Markowitz.")
            return

        metrics = allocation.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Retorno esperado", f"{metrics['Retorno esperado cartera']:.2%}")
        c2.metric("Volatilidad", f"{metrics['Volatilidad cartera']:.2%}")
        c3.metric("Sharpe", f"{metrics['Sharpe']:.2f}")

        st.dataframe(
            allocation[["Ticker", "Peso", "Capital EUR"]].style.format(
                {"Peso": "{:.2%}", "Capital EUR": "€{:,.2f}"}
            ),
            use_container_width=True,
            hide_index=True,
        )

        pie = go.Figure(
            data=go.Pie(
                labels=allocation["Ticker"],
                values=allocation["Peso"],
                hole=0.5,
            )
        )
        pie.update_layout(height=380, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(pie, use_container_width=True)
