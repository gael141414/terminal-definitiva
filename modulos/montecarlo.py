"""Monte Carlo portfolio projection engine."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import plotly.graph_objects as go
import streamlit as st


TRADING_DAYS = 252


@dataclass(frozen=True)
class MonteCarloPercentiles:
    """Percentile paths extracted from simulated portfolio paths."""

    p5: np.ndarray
    p50: np.ndarray
    p95: np.ndarray
    final_var_95: float


def simulate_monte_carlo(
    initial_portfolio_value: float,
    expected_return: float,
    volatility: float,
    years: int,
    num_simulations: int = 1000,
) -> np.ndarray:
    """Simulate GBM portfolio paths using vectorized NumPy.

    Args:
        initial_portfolio_value: Starting portfolio value.
        expected_return: Annual expected return as decimal.
        volatility: Annual volatility as decimal.
        years: Projection horizon in years.
        num_simulations: Number of Monte Carlo paths.

    Returns:
        2D array with shape ``(years * 252 + 1, num_simulations)``.
    """
    try:
        initial = float(initial_portfolio_value)
        mu = float(expected_return)
        sigma = max(float(volatility), 0.0001)
        horizon = max(int(years), 1)
        simulations = max(int(num_simulations), 100)
        steps = horizon * TRADING_DAYS
        dt = 1 / TRADING_DAYS

        random_shocks = np.random.default_rng().standard_normal((steps, simulations))
        drift = (mu - 0.5 * sigma**2) * dt
        diffusion = sigma * np.sqrt(dt) * random_shocks
        log_returns = drift + diffusion
        paths = np.empty((steps + 1, simulations), dtype=float)
        paths[0] = initial
        paths[1:] = initial * np.exp(np.cumsum(log_returns, axis=0))
        return paths
    except Exception:
        return np.empty((0, 0), dtype=float)


def extract_percentiles(paths: np.ndarray) -> MonteCarloPercentiles | None:
    """Extract P5/P50/P95 and 95% VaR threshold from paths."""
    try:
        if paths.size == 0 or paths.ndim != 2:
            return None
        p5 = np.percentile(paths, 5, axis=1)
        p50 = np.percentile(paths, 50, axis=1)
        p95 = np.percentile(paths, 95, axis=1)
        return MonteCarloPercentiles(p5=p5, p50=p50, p95=p95, final_var_95=float(p5[-1]))
    except Exception:
        return None


def build_fan_chart(percentiles: MonteCarloPercentiles) -> go.Figure:
    """Build a Plotly fan chart using P5/P50/P95 paths."""
    x_axis = np.arange(len(percentiles.p50)) / TRADING_DAYS
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=percentiles.p95,
            mode="lines",
            line=dict(width=0, color="rgba(34,197,94,0.1)"),
            name="P95",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=percentiles.p5,
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(34,197,94,0.18)",
            line=dict(width=0, color="rgba(34,197,94,0.1)"),
            name="Rango P5-P95",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=percentiles.p50,
            mode="lines",
            line=dict(color="#22c55e", width=3),
            name="Escenario base P50",
        )
    )
    fig.update_layout(
        title="Fan Chart Monte Carlo",
        xaxis_title="Años",
        yaxis_title="Valor de cartera",
        height=540,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
    )
    return fig


def render_montecarlo() -> None:
    """Render Streamlit Monte Carlo simulator."""
    st.markdown("### 🎲 Simulador de Monte Carlo")
    st.caption("Proyecta futuros posibles con Movimiento Browniano Geométrico y mide VaR de jubilación/cartera.")

    c1, c2, c3, c4 = st.columns(4)
    initial = c1.number_input("Valor inicial", min_value=1_000.0, value=100_000.0, step=5_000.0)
    expected_return = c2.slider("Retorno esperado anual (%)", -10.0, 25.0, 7.0, 0.5) / 100
    volatility = c3.slider("Volatilidad anual (%)", 1.0, 80.0, 18.0, 1.0) / 100
    years = c4.slider("Años", 1, 40, 10)
    simulations = st.slider("Simulaciones", 1_000, 20_000, 10_000, 1_000)

    if not st.button("Simular futuros posibles", type="primary", use_container_width=True):
        return

    with st.spinner("Simulando trayectorias GBM..."):
        paths = simulate_monte_carlo(initial, expected_return, volatility, years, simulations)
        percentiles = extract_percentiles(paths)

    if percentiles is None:
        st.error("No se pudo ejecutar la simulación.")
        return

    final_p50 = float(percentiles.p50[-1])
    final_p95 = float(percentiles.p95[-1])
    success_probability = float(np.mean(paths[-1] >= initial))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("VaR 95% año final", f"${percentiles.final_var_95:,.0f}")
    m2.metric("Escenario base P50", f"${final_p50:,.0f}")
    m3.metric("Escenario optimista P95", f"${final_p95:,.0f}")
    m4.metric("Prob. no perder capital", f"{success_probability:.1%}")
    st.info(f"En el 5% de los peores escenarios, la cartera caerá por debajo de **${percentiles.final_var_95:,.0f}** en el año {years}.")
    st.plotly_chart(build_fan_chart(percentiles), use_container_width=True)
