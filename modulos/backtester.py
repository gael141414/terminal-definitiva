"""Vectorbt-powered quantitative backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf


@dataclass(frozen=True)
class BacktestResult:
    """Backtest metrics and equity curves."""

    win_rate: float
    total_return_strategy: float
    total_return_benchmark: float
    equity_curve: pd.Series
    benchmark_curve: pd.Series


@st.cache_data(ttl=3600, show_spinner=False)
def _download_close(ticker: str) -> pd.Series:
    """Download five years of adjusted close prices."""
    try:
        data = yf.download(ticker, period="5y", auto_adjust=True, progress=False, threads=False)
        if data.empty:
            return pd.Series(dtype=float)
        close = data["Close"] if "Close" in data else data.squeeze()
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return pd.to_numeric(close, errors="coerce").dropna()
    except Exception:
        return pd.Series(dtype=float)


def _zscore_signals(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Build mean-reversion Z-Score entries and exits."""
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    zscore = (close - sma20) / std20.replace(0, pd.NA)
    entries = (zscore.shift(1) >= -2.0) & (zscore < -2.0)
    exits = (zscore.shift(1) <= 0.0) & (zscore > 0.0)
    return entries.fillna(False), exits.fillna(False), zscore


def run_zscore_backtest(ticker: str, initial_cash: float = 10_000.0) -> BacktestResult | None:
    """Run Z-Score mean-reversion strategy using vectorbt.

    Args:
        ticker: Stock ticker.
        initial_cash: Starting capital.

    Returns:
        BacktestResult or ``None`` if data/vectorbt is unavailable.
    """
    try:
        import vectorbt as vbt

        close = _download_close(ticker)
        if close.empty or len(close) < 252:
            return None

        entries, exits, _ = _zscore_signals(close)
        portfolio = vbt.Portfolio.from_signals(
            close,
            entries=entries,
            exits=exits,
            init_cash=initial_cash,
            fees=0.0005,
            freq="1D",
        )

        equity_curve = portfolio.value()
        benchmark_curve = initial_cash * (close / close.iloc[0])
        total_return_strategy = float(equity_curve.iloc[-1] / initial_cash - 1)
        total_return_benchmark = float(benchmark_curve.iloc[-1] / initial_cash - 1)

        try:
            win_rate = float(portfolio.trades.win_rate())
        except Exception:
            win_rate = 0.0

        return BacktestResult(
            win_rate=win_rate,
            total_return_strategy=total_return_strategy,
            total_return_benchmark=total_return_benchmark,
            equity_curve=equity_curve,
            benchmark_curve=benchmark_curve,
        )
    except Exception:
        return None


def plot_equity_curves(result: BacktestResult) -> go.Figure:
    """Create Plotly equity curve comparison."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result.equity_curve.index,
            y=result.equity_curve,
            name="Estrategia Z-Score",
            line=dict(color="#22c55e", width=3),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result.benchmark_curve.index,
            y=result.benchmark_curve,
            name="Benchmark Buy & Hold",
            line=dict(color="rgba(220,220,220,0.65)", width=2),
        )
    )
    fig.update_layout(
        title="Equity Curve: Estrategia vs Comprar y Mantener",
        height=500,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        yaxis_title="Capital",
    )
    return fig


def render_backtesting_engine(ticker: str) -> None:
    """Render Streamlit backtesting module."""
    st.markdown(f"### 🧪 Backtesting Engine: {ticker}")
    st.caption("Estrategia de Reversión a la Media por Z-Score con vectorbt.")

    initial_cash = st.number_input("Capital inicial", min_value=1_000.0, value=10_000.0, step=1_000.0)

    with st.spinner("Ejecutando simulación vectorizada con vectorbt..."):
        result = run_zscore_backtest(ticker, initial_cash)

    if result is None:
        st.error("No se pudo ejecutar vectorbt o no hay suficiente histórico de precios.")
        st.info("Asegúrate de tener `vectorbt` instalado en el entorno: `pip install vectorbt`.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Win Rate", f"{result.win_rate:.2%}")
    c2.metric("Total Return Estrategia", f"{result.total_return_strategy:.2%}")
    c3.metric("Total Return Benchmark", f"{result.total_return_benchmark:.2%}")

    if result.total_return_strategy > result.total_return_benchmark:
        st.success("La estrategia batió a comprar y mantener en el periodo analizado.")
    else:
        st.warning("La estrategia no batió a comprar y mantener en el periodo analizado.")

    st.plotly_chart(plot_equity_curves(result), use_container_width=True)
