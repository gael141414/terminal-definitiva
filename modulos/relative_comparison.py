"""Comparativa relativa para Research Core.

Este módulo compara la empresa analizada contra un competidor usando:
- ValueQuant Score completo de la empresa principal.
- ValueQuant Score calculado bajo demanda para el competidor.
- Snapshot ligero de mercado/fundamentales vía yfinance para ambas compañías.

La comparativa sigue siendo una herramienta de orientación: el score del competidor
se calcula con el mismo motor, pero debe validarse con datos normalizados y una
valoración específica antes de tomar decisiones de inversión.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from balance_analyzer import analizar_balance
from cashflow_analyzer import analizar_flujo_efectivo
from income_analyzer import analizar_cuenta_resultados
from valuator import valorar_empresa
from modulos.investment_thesis import build_investment_thesis
from modulos.scoring_engine import calcular_valuequant_score
from modulos.utils import calcular_score_buffett, cargar_datos


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
class CompetitorScoreBundle:
    """Score completo calculado bajo demanda para el competidor."""

    ticker: str
    years: int
    valuequant_score: Any | None = None
    buffett_score: float | None = None
    res_val: dict[str, Any] | None = None
    data_available: bool = False
    error: str | None = None


@dataclass
class RelativeComparison:
    """Resultado estructurado de comparación relativa."""

    primary: CompanySnapshot
    competitor: CompanySnapshot
    competitor_score: CompetitorScoreBundle | None
    verdict_rows: list[dict[str, str]]
    metric_rows: list[dict[str, str]]
    component_rows: list[dict[str, str]]
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


def _fmt_score(value: Any) -> str:
    number = _as_float(value)
    return f"{number:.1f}/100" if number is not None else "N/D"


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


@st.cache_data(show_spinner=False, ttl=3600)
def _build_competitor_valuequant(ticker: str, years: int = 5) -> CompetitorScoreBundle:
    """Calcula ValueQuant Score completo del competidor usando el pipeline financiero existente."""

    symbol = (ticker or "").strip().upper()
    if not symbol:
        return CompetitorScoreBundle(ticker="N/D", years=years, error="Ticker competidor no configurado.")

    try:
        is_df, bs_df, cf_df, metrics_df = cargar_datos(symbol, years)
        if is_df is None or bs_df is None or cf_df is None:
            return CompetitorScoreBundle(
                ticker=symbol,
                years=years,
                data_available=False,
                error="FMP no devolvió estados financieros completos para el competidor.",
            )

        res_is = analizar_cuenta_resultados(is_df, cf_df)
        res_bs = analizar_balance(bs_df, is_df)
        res_cf = analizar_flujo_efectivo(cf_df, is_df)
        res_val = valorar_empresa(is_df, bs_df, cf_df, metrics_df, symbol)

        buffett_score = calcular_score_buffett(
            res_is["ratios"],
            res_bs["ratios"],
            res_cf["ratios"],
        )
        valuequant_score = calcular_valuequant_score(
            ticker=symbol,
            is_df=is_df,
            bs_df=bs_df,
            cf_df=cf_df,
            res_is=res_is,
            res_bs=res_bs,
            res_cf=res_cf,
            res_val=res_val,
        )

        return CompetitorScoreBundle(
            ticker=symbol,
            years=years,
            valuequant_score=valuequant_score,
            buffett_score=float(buffett_score) if buffett_score is not None else None,
            res_val=res_val,
            data_available=True,
            error=None,
        )
    except Exception as exc:
        return CompetitorScoreBundle(
            ticker=symbol,
            years=years,
            data_available=False,
            error=f"{type(exc).__name__}: {exc}",
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
    competitor_score: CompetitorScoreBundle | None,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
) -> list[dict[str, str]]:
    thesis = build_investment_thesis(ticker, valuequant_score, res_val, nota_buffett)
    primary_label = ticker.upper()
    competitor_label = competitor.upper()
    competitor_vq = competitor_score.valuequant_score if competitor_score and competitor_score.data_available else None

    primary_final = _score_attr(valuequant_score, "final_score")
    competitor_final = _score_attr(competitor_vq, "final_score")
    primary_quality = _component_score(valuequant_score, "calidad")
    competitor_quality = _component_score(competitor_vq, "calidad")
    primary_valuation = _component_score(valuequant_score, "valoración")
    competitor_valuation = _component_score(competitor_vq, "valoración")
    primary_risk = _component_score(valuequant_score, "riesgo")
    competitor_risk = _component_score(competitor_vq, "riesgo")
    primary_growth = _component_score(valuequant_score, "crecimiento")
    competitor_growth = _component_score(competitor_vq, "crecimiento")

    return [
        {
            "Dimensión": "Score agregado",
            primary_label: _fmt_score(primary_final),
            competitor_label: _fmt_score(competitor_final),
            "Lectura": f"Ventaja ValueQuant: {_winner_higher(primary_final, competitor_final, primary_label, competitor_label)}.",
        },
        {
            "Dimensión": "Calidad fundamental",
            primary_label: _fmt_score(primary_quality),
            competitor_label: _fmt_score(competitor_quality),
            "Lectura": f"Mayor calidad cuantitativa: {_winner_higher(primary_quality, competitor_quality, primary_label, competitor_label)}.",
        },
        {
            "Dimensión": "Valoración",
            primary_label: _fmt_score(primary_valuation),
            competitor_label: _fmt_score(competitor_valuation),
            "Lectura": f"Mejor valoración cuantitativa: {_winner_higher(primary_valuation, competitor_valuation, primary_label, competitor_label)}. Régimen principal: {thesis.valuation_regime}.",
        },
        {
            "Dimensión": "Riesgo y forense",
            primary_label: _fmt_score(primary_risk),
            competitor_label: _fmt_score(competitor_risk),
            "Lectura": f"Mejor perfil de riesgo: {_winner_higher(primary_risk, competitor_risk, primary_label, competitor_label)}.",
        },
        {
            "Dimensión": "Crecimiento",
            primary_label: _fmt_score(primary_growth),
            competitor_label: _fmt_score(competitor_growth),
            "Lectura": f"Mejor crecimiento cuantitativo: {_winner_higher(primary_growth, competitor_growth, primary_label, competitor_label)}.",
        },
        {
            "Dimensión": "Momentum 1 año",
            primary_label: _fmt_pct(primary.perf_1y, signed=True),
            competitor_label: _fmt_pct(competitor_snapshot.perf_1y, signed=True),
            "Lectura": f"Mejor comportamiento anual: {_winner_higher(primary.perf_1y, competitor_snapshot.perf_1y, primary_label, competitor_label)}.",
        },
    ]


def _component_comparison_rows(valuequant_score: Any, competitor_score: CompetitorScoreBundle | None) -> list[dict[str, str]]:
    competitor_vq = competitor_score.valuequant_score if competitor_score and competitor_score.data_available else None
    if valuequant_score is None or competitor_vq is None:
        return []

    rows: list[dict[str, str]] = []
    primary_components = _score_attr(valuequant_score, "components", []) or []
    competitor_components = _score_attr(competitor_vq, "components", []) or []
    competitor_by_name = {str(getattr(component, "name", "")): component for component in competitor_components}

    primary_ticker = "Empresa principal"
    competitor_ticker = competitor_score.ticker
    for component in primary_components:
        name = str(getattr(component, "name", "N/D"))
        other = competitor_by_name.get(name)
        primary_score = _as_float(getattr(component, "score", None))
        competitor_component_score = _as_float(getattr(other, "score", None)) if other is not None else None
        rows.append(
            {
                "Componente": name,
                primary_ticker: _fmt_score(primary_score),
                competitor_ticker: _fmt_score(competitor_component_score),
                "Ventaja": _winner_higher(primary_score, competitor_component_score, primary_ticker, competitor_ticker),
            }
        )
    return rows


def build_relative_comparison(
    ticker: str,
    competitor: str | None,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
    years: int = 5,
) -> RelativeComparison | None:
    """Construye la comparación relativa contra el competidor configurado."""

    if not competitor or not str(competitor).strip():
        return None

    primary_label = str(ticker).strip().upper()
    competitor_label = str(competitor).strip().upper()
    primary = _fetch_yfinance_snapshot(primary_label)
    competitor_snapshot = _fetch_yfinance_snapshot(competitor_label)
    competitor_score = _build_competitor_valuequant(competitor_label, years)

    limitations = [
        "El score del competidor se calcula bajo demanda con el mismo pipeline, pero no reemplaza una revisión manual del rival.",
        "Los datos de yfinance pueden diferir de FMP/SEC y deben validarse antes de decidir.",
        "La comparación de valoración depende de supuestos y puede cambiar si el DCF del competidor no está suficientemente cubierto.",
    ]
    if competitor_score.error:
        limitations.insert(0, f"Score completo del competidor no disponible: {competitor_score.error}")

    return RelativeComparison(
        primary=primary,
        competitor=competitor_snapshot,
        competitor_score=competitor_score,
        verdict_rows=_verdict_rows(
            primary_label,
            competitor_label,
            primary,
            competitor_snapshot,
            valuequant_score,
            competitor_score,
            res_val,
            nota_buffett,
        ),
        metric_rows=_metric_rows(primary, competitor_snapshot, primary_label, competitor_label),
        component_rows=_component_comparison_rows(valuequant_score, competitor_score),
        limitations=limitations,
    )


def _normalize_rows_for_report(rows: list[dict[str, str]], primary_label: str, competitor_label: str) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for row in rows:
        title = row.get("Dimensión") or row.get("Métrica") or row.get("Componente") or "N/D"
        normalized.append(
            {
                "Bloque": title,
                primary_label: row.get(primary_label) or row.get("Empresa principal") or "N/D",
                competitor_label: row.get(competitor_label) or row.get(competitor_label.upper()) or row.get(competitor_label.lower()) or "N/D",
                "Lectura": row.get("Lectura") or row.get("Ventaja") or "",
            }
        )
    return normalized


def relative_comparison_markdown_rows(
    ticker: str,
    competitor: str | None,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
    years: int = 5,
) -> list[dict[str, str]]:
    """Devuelve filas compactas para insertar la comparación en el informe Markdown."""

    comparison = build_relative_comparison(ticker, competitor, valuequant_score, res_val, nota_buffett, years)
    if comparison is None:
        return []

    primary_label = comparison.primary.ticker
    competitor_label = comparison.competitor.ticker
    rows = comparison.verdict_rows + comparison.component_rows[:4] + comparison.metric_rows[:10]
    return _normalize_rows_for_report(rows, primary_label, competitor_label)[:20]


def render_relative_comparison(
    ticker: str,
    competitor: str | None,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
    years: int = 5,
) -> None:
    """Renderiza la pestaña de comparativa relativa dentro de Research Core."""

    st.markdown("### Comparativa relativa contra competidor")
    st.caption(
        "Comparación con ValueQuant Score completo calculado bajo demanda para el competidor, "
        "más proxies de mercado y múltiplos vía yfinance."
    )

    if not competitor or not str(competitor).strip():
        st.warning("Configura un ticker competidor para activar esta comparativa.")
        return

    with st.spinner(f"Calculando score relativo de {ticker.upper()} vs {competitor.upper()}..."):
        comparison = build_relative_comparison(ticker, competitor, valuequant_score, res_val, nota_buffett, years)

    if comparison is None:
        st.warning("Configura un ticker competidor para activar esta comparativa.")
        return

    primary_label = comparison.primary.ticker
    competitor_label = comparison.competitor.ticker
    competitor_vq = comparison.competitor_score.valuequant_score if comparison.competitor_score and comparison.competitor_score.data_available else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"{primary_label} VQ", _fmt_score(_score_attr(valuequant_score, "final_score")))
    c2.metric(f"{competitor_label} VQ", _fmt_score(_score_attr(competitor_vq, "final_score")))
    c3.metric(f"{primary_label} FCF Yield", _fmt_pct(comparison.primary.fcf_yield))
    c4.metric(f"{competitor_label} FCF Yield", _fmt_pct(comparison.competitor.fcf_yield))

    if comparison.competitor_score and comparison.competitor_score.error:
        st.warning(f"Score completo del competidor incompleto: {comparison.competitor_score.error}")

    st.markdown("#### Veredicto relativo")
    st.dataframe(pd.DataFrame(comparison.verdict_rows), use_container_width=True, hide_index=True)

    if comparison.component_rows:
        st.markdown("#### Desglose ValueQuant por componente")
        st.dataframe(pd.DataFrame(comparison.component_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No hay desglose completo de componentes para el competidor.")

    st.markdown("#### Métricas comparables de mercado")
    st.dataframe(pd.DataFrame(comparison.metric_rows), use_container_width=True, hide_index=True)

    st.markdown("#### Limitaciones")
    for limitation in comparison.limitations:
        st.write(f"- {limitation}")

    st.info(
        "Lectura correcta: usa esta pestaña para decidir cuál merece prioridad de análisis. "
        "No es todavía un ranking validado; falta backtesting transversal del score."
    )
