"""Comparativa relativa para Research Core.

Este módulo compara la empresa analizada contra un competidor usando un snapshot
ligero de mercado y fundamentales disponibles vía yfinance. No recalcula todavía
el ValueQuant Score completo del competidor; esa ampliación requiere descargar y
normalizar estados financieros completos del rival.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from modulos.investment_thesis import build_investment_thesis


@dataclass
class CompanySnapshot:
    """Snapshot ligero usado para comparar dos compañías."""

    ticker: str
    price: float | None = None
    market_cap: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    price_to_sales: float | None = None
    price_to_book: float | None = None
    beta: float | None = None
    profit_margin: float | None = None
    operating_margin: float | None = None
    roe: float | None = None
    revenue_growth: float | None = None
    fcf_yield: float | None = None
    dividend_yield: float | None = None
    perf_6m: float | None = None
    perf_1y: float | None = None


@dataclass
class RelativeComparison:
    """Resultado estructurado de comparación relativa."""

    primary: CompanySnapshot
    competitor: CompanySnapshot
    verdict_rows: list[dict[str, str]]
    metric_rows: list[dict[str, str]]
    limitations: list[str]


def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number
    except Exception:
        return None


def _fmt_money(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return "N/D"
    if abs(number) >= 1_000_000_000_000:
        return f"${number / 1_000_000_000_000:.2f}T"
    if abs(number) >= 1_000_000_000:
        return f"${number / 1_000_000_000:.2f}B"
    if abs(number) >= 1_000_000:
        return f"${number / 1_000_000:.2f}M"
    return f"${number:,.2f}"


def _fmt_pct(value: Any, signed: bool = False) -> str:
    number = _as_float(value)
    if number is None:
        return "N/D"
    sign = "+" if signed else ""
    return f"{number * 100:{sign}.1f}%"


def _fmt_ratio(value: Any) -> str:
    number = _as_float(value)
    return f"{number:.1f}x" if number is not None else "N/D"


def _score_attr(valuequant_score: Any, attr: str, default: Any = None) -> Any:
    if valuequant_score is None:
        return default
    return getattr(valuequant_score, attr, default)


def _component_score(valuequant_score: Any, component_name: str) -> float | None:
    components = _score_attr(valuequant_score, "components", []) or []
    target = component_name.lower()
    for component in components:
        name = str(getattr(component, "name", "")).lower()
        if target in name:
            return _as_float(getattr(component, "score", None))
    return None


def _first_info(info: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = _as_float(info.get(key))
        if value is not None:
            return value
    return None


@st.cache_data(show_spinner=False, ttl=3600)
def _fetch_yfinance_snapshot(ticker: str) -> CompanySnapshot:
    """Descarga un snapshot ligero de yfinance con tolerancia a fallos."""

    symbol = (ticker or "").strip().upper()
    if not symbol:
        return CompanySnapshot(ticker="N/D")

    try:
        import yfinance as yf
    except Exception:
        return CompanySnapshot(ticker=symbol)

    info: dict[str, Any] = {}
    hist = None
    try:
        yf_ticker = yf.Ticker(symbol)
        raw_info = yf_ticker.info
        if isinstance(raw_info, dict):
            info = raw_info
        try:
            hist = yf_ticker.history(period="1y", auto_adjust=True)
        except Exception:
            hist = None
    except Exception:
        return CompanySnapshot(ticker=symbol)

    market_cap = _first_info(info, ["marketCap"])
    free_cashflow = _first_info(info, ["freeCashflow", "free_cashflow"])
    fcf_yield = free_cashflow / market_cap if free_cashflow is not None and market_cap and market_cap > 0 else None

    perf_6m = None
    perf_1y = None
    try:
        if hist is not None and not hist.empty and "Close" in hist.columns:
            close = hist["Close"].dropna()
            if len(close) > 2:
                latest = float(close.iloc[-1])
                if len(close) >= 126 and close.iloc[-126] > 0:
                    perf_6m = latest / float(close.iloc[-126]) - 1.0
                if len(close) >= 252 and close.iloc[0] > 0:
                    perf_1y = latest / float(close.iloc[0]) - 1.0
    except Exception:
        perf_6m = None
        perf_1y = None

    return CompanySnapshot(
        ticker=symbol,
        price=_first_info(info, ["currentPrice", "regularMarketPrice", "previousClose"]),
        market_cap=market_cap,
        trailing_pe=_first_info(info, ["trailingPE"]),
        forward_pe=_first_info(info, ["forwardPE"]),
        price_to_sales=_first_info(info, ["priceToSalesTrailing12Months"]),
        price_to_book=_first_info(info, ["priceToBook"]),
        beta=_first_info(info, ["beta"]),
        profit_margin=_first_info(info, ["profitMargins"]),
        operating_margin=_first_info(info, ["operatingMargins"]),
        roe=_first_info(info, ["returnOnEquity"]),
        revenue_growth=_first_info(info, ["revenueGrowth"]),
        fcf_yield=fcf_yield,
        dividend_yield=_first_info(info, ["dividendYield"]),
        perf_6m=perf_6m,
        perf_1y=perf_1y,
    )


def _winner_higher(primary: float | None, competitor: float | None, primary_label: str, competitor_label: str) -> str:
    if primary is None or competitor is None:
        return "N/D"
    if abs(primary - competitor) < 1e-9:
        return "Empate"
    return primary_label if primary > competitor else competitor_label


def _winner_lower(primary: float | None, competitor: float | None, primary_label: str, competitor_label: str) -> str:
    if primary is None or competitor is None:
        return "N/D"
    if abs(primary - competitor) < 1e-9:
        return "Empate"
    return primary_label if primary < competitor else competitor_label


def _metric_rows(primary: CompanySnapshot, competitor: CompanySnapshot, primary_label: str, competitor_label: str) -> list[dict[str, str]]:
    return [
        {
            "Métrica": "Precio",
            primary_label: _fmt_money(primary.price),
            competitor_label: _fmt_money(competitor.price),
            "Lectura": "Referencia de mercado, no implica valoración por sí sola.",
        },
        {
            "Métrica": "Capitalización",
            primary_label: _fmt_money(primary.market_cap),
            competitor_label: _fmt_money(competitor.market_cap),
            "Lectura": "Tamaño relativo y madurez del negocio.",
        },
        {
            "Métrica": "PER trailing",
            primary_label: _fmt_ratio(primary.trailing_pe),
            competitor_label: _fmt_ratio(competitor.trailing_pe),
            "Lectura": f"Mejor múltiplo relativo: {_winner_lower(primary.trailing_pe, competitor.trailing_pe, primary_label, competitor_label)}.",
        },
        {
            "Métrica": "PER forward",
            primary_label: _fmt_ratio(primary.forward_pe),
            competitor_label: _fmt_ratio(competitor.forward_pe),
            "Lectura": f"Mejor múltiplo esperado: {_winner_lower(primary.forward_pe, competitor.forward_pe, primary_label, competitor_label)}.",
        },
        {
            "Métrica": "P/Sales",
            primary_label: _fmt_ratio(primary.price_to_sales),
            competitor_label: _fmt_ratio(competitor.price_to_sales),
            "Lectura": f"Menor precio sobre ventas: {_winner_lower(primary.price_to_sales, competitor.price_to_sales, primary_label, competitor_label)}.",
        },
        {
            "Métrica": "FCF Yield",
            primary_label: _fmt_pct(primary.fcf_yield),
            competitor_label: _fmt_pct(competitor.fcf_yield),
            "Lectura": f"Mayor rentabilidad por FCF: {_winner_higher(primary.fcf_yield, competitor.fcf_yield, primary_label, competitor_label)}.",
        },
        {
            "Métrica": "Margen neto",
            primary_label: _fmt_pct(primary.profit_margin),
            competitor_label: _fmt_pct(competitor.profit_margin),
            "Lectura": f"Mayor rentabilidad neta: {_winner_higher(primary.profit_margin, competitor.profit_margin, primary_label, competitor_label)}.",
        },
        {
            "Métrica": "Margen operativo",
            primary_label: _fmt_pct(primary.operating_margin),
            competitor_label: _fmt_pct(competitor.operating_margin),
            "Lectura": f"Mayor eficiencia operativa: {_winner_higher(primary.operating_margin, competitor.operating_margin, primary_label, competitor_label)}.",
        },
        {
            "Métrica": "ROE",
            primary_label: _fmt_pct(primary.roe),
            competitor_label: _fmt_pct(competitor.roe),
            "Lectura": f"Mayor ROE: {_winner_higher(primary.roe, competitor.roe, primary_label, competitor_label)}.",
        },
        {
            "Métrica": "Crecimiento ingresos",
            primary_label: _fmt_pct(primary.revenue_growth, signed=True),
            competitor_label: _fmt_pct(competitor.revenue_growth, signed=True),
            "Lectura": f"Mayor crecimiento reciente: {_winner_higher(primary.revenue_growth, competitor.revenue_growth, primary_label, competitor_label)}.",
        },
        {
            "Métrica": "Beta",
            primary_label: _fmt_ratio(primary.beta),
            competitor_label: _fmt_ratio(competitor.beta),
            "Lectura": f"Menor beta/riesgo de mercado: {_winner_lower(primary.beta, competitor.beta, primary_label, competitor_label)}.",
        },
        {
            "Métrica": "Rentabilidad 6m",
            primary_label: _fmt_pct(primary.perf_6m, signed=True),
            competitor_label: _fmt_pct(competitor.perf_6m, signed=True),
            "Lectura": f"Mejor momentum 6m: {_winner_higher(primary.perf_6m, competitor.perf_6m, primary_label, competitor_label)}.",
        },
        {
            "Métrica": "Rentabilidad 1a",
            primary_label: _fmt_pct(primary.perf_1y, signed=True),
            competitor_label: _fmt_pct(competitor.perf_1y, signed=True),
            "Lectura": f"Mejor momentum 1a: {_winner_higher(primary.perf_1y, competitor.perf_1y, primary_label, competitor_label)}.",
        },
    ]


def _verdict_rows(
    ticker: str,
    competitor: str,
    primary: CompanySnapshot,
    competitor_snapshot: CompanySnapshot,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
) -> list[dict[str, str]]:
    thesis = build_investment_thesis(ticker, valuequant_score, res_val, nota_buffett)
    primary_label = ticker.upper()
    competitor_label = competitor.upper()

    quality_score = _component_score(valuequant_score, "calidad")
    valuation_score = _component_score(valuequant_score, "valoración")
    risk_score = _component_score(valuequant_score, "riesgo")

    return [
        {
            "Dimensión": "Score agregado",
            primary_label: _fmt_ratio(_score_attr(valuequant_score, "final_score")) if _score_attr(valuequant_score, "final_score") is not None else "N/D",
            competitor_label: "Pendiente VQ",
            "Lectura": "Solo la empresa principal tiene ValueQuant Score completo en este flujo.",
        },
        {
            "Dimensión": "Calidad",
            primary_label: _fmt_ratio(quality_score) if quality_score is not None else "N/D",
            competitor_label: "Proxy yfinance",
            "Lectura": f"Comparar con margen neto, margen operativo y ROE. Ventaja proxy: {_winner_higher(primary.roe, competitor_snapshot.roe, primary_label, competitor_label)} en ROE.",
        },
        {
            "Dimensión": "Valoración",
            primary_label: _fmt_ratio(valuation_score) if valuation_score is not None else "N/D",
            competitor_label: "Proxy yfinance",
            "Lectura": f"La empresa principal está en régimen '{thesis.valuation_regime}'. En múltiplos, revisar PER/FCF Yield frente al competidor.",
        },
        {
            "Dimensión": "Riesgo",
            primary_label: _fmt_ratio(risk_score) if risk_score is not None else "N/D",
            competitor_label: "Proxy yfinance",
            "Lectura": f"Menor beta relativa: {_winner_lower(primary.beta, competitor_snapshot.beta, primary_label, competitor_label)}.",
        },
        {
            "Dimensión": "Momentum",
            primary_label: _fmt_pct(primary.perf_1y, signed=True),
            competitor_label: _fmt_pct(competitor_snapshot.perf_1y, signed=True),
            "Lectura": f"Mejor comportamiento anual: {_winner_higher(primary.perf_1y, competitor_snapshot.perf_1y, primary_label, competitor_label)}.",
        },
    ]


def build_relative_comparison(
    ticker: str,
    competitor: str | None,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
) -> RelativeComparison | None:
    """Construye la comparación relativa contra el competidor configurado."""

    if not competitor or not str(competitor).strip():
        return None

    primary_label = str(ticker).strip().upper()
    competitor_label = str(competitor).strip().upper()
    primary = _fetch_yfinance_snapshot(primary_label)
    competitor_snapshot = _fetch_yfinance_snapshot(competitor_label)

    return RelativeComparison(
        primary=primary,
        competitor=competitor_snapshot,
        verdict_rows=_verdict_rows(primary_label, competitor_label, primary, competitor_snapshot, valuequant_score, res_val, nota_buffett),
        metric_rows=_metric_rows(primary, competitor_snapshot, primary_label, competitor_label),
        limitations=[
            "El competidor todavía no tiene ValueQuant Score completo dentro de esta vista.",
            "Los datos de yfinance pueden diferir de FMP/SEC y deben validarse antes de decidir.",
            "La comparación usa proxies de mercado y fundamentales resumidos; no sustituye análisis financiero completo del rival.",
        ],
    )


def relative_comparison_markdown_rows(
    ticker: str,
    competitor: str | None,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
) -> list[dict[str, str]]:
    """Devuelve filas compactas para insertar la comparación en el informe Markdown."""

    comparison = build_relative_comparison(ticker, competitor, valuequant_score, res_val, nota_buffett)
    if comparison is None:
        return []

    rows = comparison.verdict_rows + comparison.metric_rows
    return rows[:18]


def render_relative_comparison(
    ticker: str,
    competitor: str | None,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
) -> None:
    """Renderiza la pestaña de comparativa relativa dentro de Research Core."""

    st.markdown("### Comparativa relativa contra competidor")
    st.caption(
        "Comparación ligera basada en ValueQuant para la empresa principal y proxies de yfinance para ambos tickers. "
        "No recalcula aún el score completo del competidor."
    )

    comparison = build_relative_comparison(ticker, competitor, valuequant_score, res_val, nota_buffett)
    if comparison is None:
        st.warning("Configura un ticker competidor para activar esta comparativa.")
        return

    primary_label = comparison.primary.ticker
    competitor_label = comparison.competitor.ticker

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"{primary_label} precio", _fmt_money(comparison.primary.price))
    c2.metric(f"{competitor_label} precio", _fmt_money(comparison.competitor.price))
    c3.metric(f"{primary_label} FCF Yield", _fmt_pct(comparison.primary.fcf_yield))
    c4.metric(f"{competitor_label} FCF Yield", _fmt_pct(comparison.competitor.fcf_yield))

    st.markdown("#### Veredicto relativo")
    st.dataframe(pd.DataFrame(comparison.verdict_rows), use_container_width=True, hide_index=True)

    st.markdown("#### Métricas comparables")
    st.dataframe(pd.DataFrame(comparison.metric_rows), use_container_width=True, hide_index=True)

    st.markdown("#### Limitaciones")
    for limitation in comparison.limitations:
        st.write(f"- {limitation}")

    st.info(
        "Lectura correcta: usa esta pestaña para orientar preguntas de análisis relativo. "
        "La decisión final debe apoyarse en estados financieros completos y valoración específica de cada compañía."
    )
