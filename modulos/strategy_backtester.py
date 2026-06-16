from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _max_drawdown(curve: pd.Series) -> float:
    return float((curve / curve.cummax() - 1).min())


@st.cache_data(ttl=3600, show_spinner=False)
def _descargar_close(ticker: str, period: str) -> pd.Series:
    data = yf.download(ticker, period=period, auto_adjust=True, progress=False, threads=False)
    if data.empty:
        return pd.Series(dtype=float)
    close = data["Close"] if "Close" in data else data.squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return pd.to_numeric(close, errors="coerce").dropna()


def _signal_mean_reversion(close: pd.Series) -> pd.Series:
    rsi = _rsi(close)
    ma = close.rolling(20).mean()
    std = close.rolling(20).std()
    lower = ma - 2 * std
    exit_line = ma
    raw = pd.Series(0, index=close.index, dtype=float)
    raw[(rsi < 30) & (close < lower)] = 1
    raw[(rsi > 55) | (close > exit_line)] = 0
    return raw.replace(0, np.nan).ffill().fillna(0)


def _signal_trend(close: pd.Series) -> pd.Series:
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    return (ema50 > ema200).astype(float)


def _signal_squeeze(close: pd.Series) -> pd.Series:
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    width = (4 * std20 / ma20).replace([np.inf, -np.inf], np.nan)
    squeeze = width < width.rolling(120).quantile(0.2)
    breakout = close > close.rolling(20).max().shift(1)
    raw = pd.Series(0, index=close.index, dtype=float)
    raw[squeeze & breakout] = 1
    raw[close < ma20] = 0
    return raw.replace(0, np.nan).ffill().fillna(0)


def _backtest(close: pd.Series, signal: pd.Series, initial_capital: float, fee_bps: float) -> dict:
    returns = close.pct_change().fillna(0)
    position = signal.reindex(close.index).fillna(0).shift(1).fillna(0)
    trades = position.diff().abs().fillna(0)
    strategy_returns = position * returns - trades * (fee_bps / 10000)
    curve = initial_capital * (1 + strategy_returns).cumprod()
    buy_hold = initial_capital * (1 + returns).cumprod()

    trade_entries = position.diff().fillna(0) > 0
    trade_exits = position.diff().fillna(0) < 0
    entry_prices = close[trade_entries].reset_index(drop=True)
    exit_prices = close[trade_exits].reset_index(drop=True)
    n = min(len(entry_prices), len(exit_prices))
    trade_returns = (exit_prices.iloc[:n].values / entry_prices.iloc[:n].values) - 1 if n else np.array([])

    return {
        "curve": curve,
        "buy_hold": buy_hold,
        "total_return": float(curve.iloc[-1] / initial_capital - 1),
        "buy_hold_return": float(buy_hold.iloc[-1] / initial_capital - 1),
        "max_drawdown": _max_drawdown(curve),
        "trades": int(trades.sum() / 2),
        "win_rate": float((trade_returns > 0).mean()) if len(trade_returns) else 0.0,
    }


def ejecutar_strategy_backtester(ticker_input: str):
    st.markdown(f"### 🧪 Motor de Backtesting Técnico: {ticker_input}")
    st.caption("Prueba si tus señales técnicas habrían ganado dinero antes de confiar en ellas.")

    c1, c2, c3 = st.columns(3)
    strategy = c1.selectbox("Estrategia", ["Reversión a la media", "Trend Following", "Squeeze Breakout"])
    period = c2.selectbox("Histórico", ["1y", "2y", "5y", "10y"], index=2)
    initial = c3.number_input("Capital inicial", min_value=1000.0, value=10_000.0, step=1000.0)
    fee_bps = st.slider("Coste por operación (bps)", 0.0, 50.0, 5.0, 1.0)

    if not st.button("Ejecutar backtest", type="primary", use_container_width=True):
        return

    with st.spinner("Simulando compras y ventas históricas..."):
        close = _descargar_close(ticker_input, period)
        if close.empty or len(close) < 250:
            st.error("No hay suficiente histórico para ejecutar el backtest.")
            return

        if strategy == "Reversión a la media":
            signal = _signal_mean_reversion(close)
        elif strategy == "Trend Following":
            signal = _signal_trend(close)
        else:
            signal = _signal_squeeze(close)

        result = _backtest(close, signal, initial, fee_bps)

        c4, c5, c6, c7 = st.columns(4)
        c4.metric("Estrategia", f"{result['total_return']:.1%}")
        c5.metric("Buy & Hold", f"{result['buy_hold_return']:.1%}")
        c6.metric("Acierto trades", f"{result['win_rate']:.1%}")
        c7.metric("Max Drawdown", f"{result['max_drawdown']:.1%}")

        if result["total_return"] > result["buy_hold_return"]:
            st.success("La estrategia batió a comprar y mantener en este periodo.")
        else:
            st.warning("La estrategia no batió a comprar y mantener en este periodo.")

        curve_df = pd.DataFrame({"Estrategia": result["curve"], "Buy & Hold": result["buy_hold"]})
        fig = px.line(curve_df, title=f"Equity Curve - {strategy}")
        fig.update_layout(height=500, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Señal operativa"):
            debug = pd.DataFrame({"Close": close, "Signal": signal}).tail(250)
            st.dataframe(debug, use_container_width=True)
