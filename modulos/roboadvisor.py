from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from roboadvisor_engine import (
    AlpacaBrokerSimulator,
    BrokerAPIError,
    FinancialEngineError,
    PortfolioOptimizer,
    RISK_PROFILE_QUESTIONS,
    RiskProfiler,
    calculate_drift_rebalancing,
)


def ejecutar_roboadvisor() -> None:
    """Renders the Streamlit adapter for the Robo-Advisor engine."""
    st.markdown("### Robo-Advisor Institucional")
    st.caption(
        "Motor cuantitativo sin IA generativa: perfilado, Markowitz, rebalanceo por drift "
        "y broker sandbox estilo Alpaca."
    )

    tab_profile, tab_optimizer, tab_rebalance, tab_broker = st.tabs(
        ["Perfil de riesgo", "Frontera eficiente", "Rebalanceo", "Broker sandbox"]
    )

    with tab_profile:
        _render_risk_profile()
    with tab_optimizer:
        _render_markowitz_optimizer()
    with tab_rebalance:
        _render_rebalance_engine()
    with tab_broker:
        _render_broker_sandbox()


def _render_risk_profile() -> None:
    profiler = RiskProfiler()

    st.markdown("#### Test KYC cuantitativo")
    with st.form("risk_profile_form"):
        answers: dict[str, str] = {}
        for question_id, question in RISK_PROFILE_QUESTIONS.items():
            options = list(question["options"].keys())
            answers[question_id] = st.radio(
                str(question["question"]),
                options,
                format_func=lambda option, q=question: q["options"][option]["label"],
                horizontal=False,
            )
        submitted = st.form_submit_button("Calcular perfil", type="primary")

    if submitted:
        try:
            st.session_state["risk_profile_result"] = profiler.calculate_score(answers)
        except FinancialEngineError as exc:
            st.error(str(exc))

    result = st.session_state.get("risk_profile_result")
    if not result:
        return

    allocation = result["recommended_asset_allocation"]
    allocation_df = pd.DataFrame(
        {"Clase de activo": allocation.keys(), "Peso": allocation.values()}
    )

    col_score, col_category, col_model = st.columns(3)
    col_score.metric("Score total", f"{result['score_total']:.1f}/100")
    col_category.metric("Categoria", result["risk_category"])
    col_model.metric("Perfil 1-10", result["score_1_to_10"])

    fig = px.pie(
        allocation_df,
        names="Clase de activo",
        values="Peso",
        hole=0.55,
        color_discrete_sequence=["#36d399", "#60a5fa", "#fbbf24", "#c084fc"],
    )
    fig.update_traces(textinfo="percent+label", textposition="inside")
    fig.update_layout(
        height=390,
        margin=dict(t=20, b=20, l=0, r=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E5E7EB"),
    )

    c_chart, c_table = st.columns([1.2, 1])
    c_chart.plotly_chart(fig, use_container_width=True)
    c_table.dataframe(
        allocation_df.style.format({"Peso": "{:.1%}"}),
        use_container_width=True,
        hide_index=True,
    )

    if result["warnings"]:
        for warning in result["warnings"]:
            st.warning(warning)

    with st.expander("JSON del perfil y trazabilidad"):
        st.json(result)


def _render_markowitz_optimizer() -> None:
    st.markdown("#### Optimizador Markowitz con SciPy")

    controls, output = st.columns([0.85, 1.15])
    with controls:
        uploaded_file = st.file_uploader(
            "CSV de retornos o precios historicos",
            type=["csv"],
            help="Columnas: tickers de ETFs. Filas: fechas u observaciones.",
        )
        csv_contains_prices = st.checkbox("El CSV contiene precios, no retornos")
        risk_free_rate = st.number_input(
            "Tasa libre de riesgo anual (%)",
            min_value=0.0,
            max_value=15.0,
            value=2.0,
            step=0.25,
        )
        frontier_points = st.slider("Puntos de frontera", 10, 80, 35)
        run_optimizer = st.button("Optimizar cartera", type="primary", use_container_width=True)

    returns_or_prices = _load_optimizer_input(uploaded_file)
    with output:
        st.dataframe(
            returns_or_prices.tail(8).style.format("{:.4f}"),
            use_container_width=True,
        )

    if not run_optimizer:
        return

    try:
        optimizer = (
            PortfolioOptimizer.from_price_history(
                returns_or_prices,
                risk_free_rate=risk_free_rate / 100,
            )
            if csv_contains_prices and uploaded_file is not None
            else PortfolioOptimizer(
                returns_or_prices,
                risk_free_rate=risk_free_rate / 100,
            )
        )
        max_sharpe = optimizer.maximize_sharpe()
        min_vol = optimizer.minimize_volatility()
        frontier = optimizer.efficient_frontier(points=frontier_points)
    except FinancialEngineError as exc:
        st.error(str(exc))
        return

    frontier_fig = go.Figure()
    frontier_fig.add_trace(
        go.Scatter(
            x=frontier["volatility"],
            y=frontier["expected_return"],
            mode="lines+markers",
            marker=dict(color=frontier["sharpe_ratio"], colorscale="Viridis", size=8),
            line=dict(color="#38bdf8", width=2),
            name="Frontera eficiente",
        )
    )
    frontier_fig.add_trace(
        go.Scatter(
            x=[max_sharpe.volatility],
            y=[max_sharpe.expected_return],
            mode="markers",
            marker=dict(color="#22c55e", size=16, symbol="star"),
            name="Max Sharpe",
        )
    )
    frontier_fig.add_trace(
        go.Scatter(
            x=[min_vol.volatility],
            y=[min_vol.expected_return],
            mode="markers",
            marker=dict(color="#f59e0b", size=13, symbol="diamond"),
            name="Min volatilidad",
        )
    )
    frontier_fig.update_layout(
        height=460,
        xaxis_title="Volatilidad anualizada",
        yaxis_title="Retorno esperado anualizado",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=30, b=20, l=10, r=10),
    )
    st.plotly_chart(frontier_fig, use_container_width=True)

    c1, c2 = st.columns(2)
    c1.markdown("##### Max Sharpe")
    c1.json(max_sharpe.to_dict())
    c2.markdown("##### Minima volatilidad")
    c2.json(min_vol.to_dict())


def _render_rebalance_engine() -> None:
    st.markdown("#### Rebalanceo automatico por bandas de tolerancia")
    default_current = {"SPY": 0.68, "BND": 0.20, "GLD": 0.07, "VNQ": 0.05}
    default_target = {"SPY": 0.60, "BND": 0.30, "GLD": 0.05, "VNQ": 0.05}

    c1, c2, c3 = st.columns([1, 1, 0.7])
    with c1:
        current_raw = st.text_area(
            "Pesos actuales",
            value=json.dumps(default_current, indent=2),
            height=170,
        )
    with c2:
        target_raw = st.text_area(
            "Pesos objetivo",
            value=json.dumps(default_target, indent=2),
            height=170,
        )
    with c3:
        portfolio_value = st.number_input(
            "Valor cartera",
            min_value=1_000.0,
            value=100_000.0,
            step=1_000.0,
        )
        tolerance = st.number_input(
            "Banda drift (%)",
            min_value=0.0,
            max_value=25.0,
            value=5.0,
            step=0.5,
        )
        min_trade = st.number_input(
            "Orden minima",
            min_value=0.0,
            value=50.0,
            step=10.0,
        )

    if not st.button("Calcular ordenes de rebalanceo", type="primary"):
        return

    try:
        trades = calculate_drift_rebalancing(
            current_weights=_parse_weight_map(current_raw),
            target_weights=_parse_weight_map(target_raw),
            portfolio_value=portfolio_value,
            tolerance_bands=tolerance / 100,
            min_trade_value=min_trade,
        )
    except (json.JSONDecodeError, ValueError, FinancialEngineError) as exc:
        st.error(f"Entrada invalida: {exc}")
        return

    if not trades:
        st.success("La cartera esta dentro de las bandas. No hay ordenes necesarias.")
        return

    trades_df = pd.DataFrame([trade.to_dict() for trade in trades])
    st.dataframe(
        trades_df.style.format(
            {
                "current_weight": "{:.1%}",
                "target_weight": "{:.1%}",
                "drift": "{:+.1%}",
                "notional": "${:,.2f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_broker_sandbox() -> None:
    st.markdown("#### Simulador de API de corretaje estilo Alpaca")
    broker = _get_broker()

    c_cash, c_equity, c_orders = st.columns(3)
    try:
        equity = broker.portfolio_value()
    except BrokerAPIError:
        equity = broker.cash
    c_cash.metric("Cash", f"${broker.cash:,.2f}")
    c_equity.metric("Equity", f"${equity:,.2f}")
    c_orders.metric("Ordenes", len(broker.orders))

    with st.expander("Actualizar precios de mercado", expanded=True):
        with st.form("broker_price_form"):
            p1, p2 = st.columns([1, 1])
            symbol_price = p1.text_input("Ticker", value="SPY").upper().strip()
            price = p2.number_input("Precio", min_value=0.01, value=500.0, step=1.0)
            if st.form_submit_button("Guardar precio"):
                try:
                    broker.update_market_price(symbol_price, price)
                    st.success(f"Precio actualizado: {symbol_price} = ${price:,.2f}")
                except BrokerAPIError as exc:
                    st.error(str(exc))

    with st.form("market_order_form"):
        o1, o2, o3, o4 = st.columns([1, 0.8, 0.8, 1])
        symbol = o1.text_input("Simbolo", value="SPY").upper().strip()
        side = o2.selectbox("Side", ["buy", "sell"])
        amount_mode = o3.selectbox("Modo", ["notional", "quantity"])
        amount = o4.number_input("Importe / cantidad", min_value=0.0001, value=1_000.0)
        submitted = st.form_submit_button("Enviar Market Order", type="primary")

    if submitted:
        try:
            order = broker.submit_market_order(
                symbol=symbol,
                side=side,  # type: ignore[arg-type]
                notional=amount if amount_mode == "notional" else None,
                quantity=amount if amount_mode == "quantity" else None,
            )
            st.success(f"Orden ejecutada: {order.side.upper()} {order.symbol}")
            st.json(order.to_dict())
        except BrokerAPIError as exc:
            st.error(str(exc))

    positions = broker.positions_frame()
    if positions.empty:
        st.info("No hay posiciones abiertas en el sandbox.")
    else:
        st.dataframe(
            positions.style.format(
                {
                    "quantity": "{:.4f}",
                    "average_price": "${:,.2f}",
                    "last_price": "${:,.2f}",
                    "market_value": "${:,.2f}",
                    "unrealized_pnl": "${:,.2f}",
                    "unrealized_pnl_pct": "{:+.2%}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    if broker.orders:
        orders_df = pd.DataFrame([order.to_dict() for order in broker.orders[-10:]])
        st.dataframe(orders_df, use_container_width=True, hide_index=True)

    if st.button("Reset broker sandbox"):
        st.session_state["broker_simulator"] = AlpacaBrokerSimulator()
        st.rerun()


def _get_broker() -> AlpacaBrokerSimulator:
    broker = st.session_state.get("broker_simulator")
    if not isinstance(broker, AlpacaBrokerSimulator):
        broker = AlpacaBrokerSimulator()
        st.session_state["broker_simulator"] = broker
    return broker


def _load_optimizer_input(uploaded_file: Any) -> pd.DataFrame:
    if uploaded_file is None:
        return _demo_etf_returns()

    df = pd.read_csv(uploaded_file, index_col=0)
    df = df.apply(pd.to_numeric, errors="coerce").dropna(how="all")
    df.columns = [str(column).upper() for column in df.columns]
    return df.dropna(how="any")


@st.cache_data(show_spinner=False)
def _demo_etf_returns() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    assets = ["SPY", "BND", "GLD", "VNQ"]
    annual_returns = np.array([0.085, 0.035, 0.050, 0.065])
    annual_volatility = np.array([0.18, 0.06, 0.15, 0.20])
    correlations = np.array(
        [
            [1.00, -0.15, 0.05, 0.65],
            [-0.15, 1.00, 0.10, -0.05],
            [0.05, 0.10, 1.00, 0.00],
            [0.65, -0.05, 0.00, 1.00],
        ]
    )
    daily_volatility = annual_volatility / np.sqrt(252)
    daily_covariance = correlations * np.outer(daily_volatility, daily_volatility)
    daily_returns = annual_returns / 252
    index = pd.date_range(end=pd.Timestamp.today().normalize(), periods=756, freq="B")
    simulated_returns = rng.multivariate_normal(daily_returns, daily_covariance, len(index))
    return pd.DataFrame(simulated_returns, index=index, columns=assets)


def _parse_weight_map(raw_json: str) -> dict[str, float]:
    parsed = json.loads(raw_json)
    if not isinstance(parsed, dict):
        raise ValueError("Se esperaba un objeto JSON con pesos por ticker.")
    return {str(symbol).upper().strip(): float(weight) for symbol, weight in parsed.items()}
