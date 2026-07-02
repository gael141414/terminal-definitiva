from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import math

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

try:
    from modulos.utils import analizar_sentimiento_noticias
except Exception:  # evita romper la app si el módulo NLP falla
    analizar_sentimiento_noticias = None


MODEL_VERSION = "VQ_SCORE_1.1"
CONFIDENCE_CAP = 0.86


@dataclass
class ScoreComponent:
    """Componente individual de scoring normalizado a 0-100."""
    name: str
    score: float
    weight: float
    confidence: float = 1.0
    penalty: float = 0.0
    positives: list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    source_tools: list[str] = field(default_factory=list)

    @property
    def effective_weight(self) -> float:
        return float(self.weight) * float(self.confidence)

    @property
    def contribution(self) -> float:
        return float(self.score) * self.effective_weight


@dataclass
class ValueQuantScore:
    """Resultado agregado del scoring institucional."""
    final_score: float
    confidence: float
    components: list[ScoreComponent]
    red_flags: list[str]
    positives: list[str]
    negatives: list[str]
    verdict: str
    model_version: str = MODEL_VERSION
    data_coverage: float = 0.0
    predictive_confidence: float | None = None

    def component(self, name: str) -> ScoreComponent | None:
        for component in self.components:
            if component.name == name:
                return component
        return None

    def to_dataframe(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for component in self.components:
            rows.append(
                {
                    "Bloque": component.name,
                    "Score": round(component.score, 1),
                    "Peso": f"{component.weight * 100:.0f}%",
                    "Confianza": f"{component.confidence * 100:.0f}%",
                    "Penalización": round(component.penalty, 1),
                    "Herramientas": ", ".join(component.source_tools),
                }
            )
        return pd.DataFrame(rows)


# =============================================================================
# Helpers numéricos
# =============================================================================


def _is_valid(value: Any) -> bool:
    try:
        return value is not None and not pd.isna(value) and np.isfinite(float(value))
    except Exception:
        return False


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    if not _is_valid(value):
        return 50.0
    return float(max(lo, min(hi, float(value))))


def _score_linear(value: Any, low: float, high: float, inverse: bool = False) -> float:
    """Normaliza value a 0-100. Si inverse=True, menor es mejor."""
    if not _is_valid(value) or high == low:
        return 50.0
    raw = (float(value) - low) / (high - low) * 100
    if inverse:
        raw = 100 - raw
    return _clamp(raw)


def _weighted_mean(items: list[tuple[float | None, float]], default: float = 50.0) -> float:
    clean = [(float(value), float(weight)) for value, weight in items if _is_valid(value) and weight > 0]
    if not clean:
        return default
    numerator = sum(value * weight for value, weight in clean)
    denominator = sum(weight for _, weight in clean)
    return float(numerator / denominator) if denominator else default


def _mean(values: list[float | None], default: float = 50.0) -> float:
    clean = [float(value) for value in values if _is_valid(value)]
    return float(np.mean(clean)) if clean else default


def _get_series(df: pd.DataFrame | None, column: str) -> pd.Series:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty or column not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def _last(df: pd.DataFrame | None, column: str) -> float | None:
    series = _get_series(df, column)
    return float(series.iloc[-1]) if not series.empty else None


def _avg_recent(df: pd.DataFrame | None, column: str, n: int = 3) -> float | None:
    series = _get_series(df, column)
    return float(series.tail(n).mean()) if not series.empty else None


def _positive_ratio(df: pd.DataFrame | None, column: str, n: int = 5) -> float | None:
    series = _get_series(df, column).tail(n)
    if series.empty:
        return None
    return float((series > 0).mean())


def _cagr_from_statement(df: pd.DataFrame | None, column: str) -> float | None:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty or column not in df.columns:
        return None
    series = pd.to_numeric(df[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(series) < 2:
        return None
    first = float(series.iloc[0])
    last = float(series.iloc[-1])
    years = max(len(series) - 1, 1)
    if first <= 0 or last <= 0:
        return None
    return float((last / first) ** (1 / years) - 1)


def _first_available(mapping: dict[str, Any] | None, keys: list[str], default: Any = None) -> Any:
    if not isinstance(mapping, dict):
        return default
    for key in keys:
        value = mapping.get(key)
        if _is_valid(value):
            return value
    return default


def _coverage(*values: Any, floor: float = 0.25) -> float:
    if not values:
        return floor
    return float(max(np.mean([_is_valid(value) for value in values]), floor))


@st.cache_data(ttl=1800, show_spinner=False)
def _market_data_snapshot(ticker: str) -> dict[str, Any]:
    """Obtiene datos de mercado ligeros. Si Yahoo falla, devuelve defaults neutrales."""
    output: dict[str, Any] = {
        "beta": None,
        "market_cap": None,
        "sector": None,
        "rsi": None,
        "ret_6m": None,
        "ret_1y": None,
        "vol_1y": None,
        "max_drawdown_1y": None,
        "sma50_above_sma200": None,
        "price_above_sma200": None,
        "sector_rel_3m": None,
        "insider_pct": None,
        "inst_pct": None,
        "short_ratio": None,
    }

    try:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info or {}
        output["beta"] = info.get("beta")
        output["market_cap"] = info.get("marketCap")
        output["sector"] = info.get("sector")
        output["insider_pct"] = (info.get("heldPercentInsiders") or 0) * 100
        output["inst_pct"] = (info.get("heldPercentInstitutions") or 0) * 100
        output["short_ratio"] = info.get("shortRatio")

        hist = yf_ticker.history(period="18mo", interval="1d", auto_adjust=True)
        if hist is not None and not hist.empty and "Close" in hist.columns:
            close = hist["Close"].dropna()
            if len(close) >= 220:
                returns = close.pct_change().dropna()
                output["ret_6m"] = float(close.iloc[-1] / close.iloc[-126] - 1) if len(close) > 126 else None
                output["ret_1y"] = float(close.iloc[-1] / close.iloc[-252] - 1) if len(close) > 252 else None
                output["vol_1y"] = float(returns.tail(252).std() * math.sqrt(252)) if not returns.empty else None
                running_max = close.tail(252).cummax()
                drawdown = (close.tail(252) / running_max) - 1
                output["max_drawdown_1y"] = float(drawdown.min())

                sma50 = close.rolling(50).mean().iloc[-1]
                sma200 = close.rolling(200).mean().iloc[-1]
                output["sma50_above_sma200"] = bool(sma50 > sma200) if _is_valid(sma50) and _is_valid(sma200) else None
                output["price_above_sma200"] = bool(close.iloc[-1] > sma200) if _is_valid(sma200) else None

                delta = close.diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, np.nan)
                rsi = 100 - (100 / (1 + rs))
                output["rsi"] = float(rsi.dropna().iloc[-1]) if not rsi.dropna().empty else None

        sector_to_etf = {
            "Technology": "XLK",
            "Communication Services": "XLC",
            "Financial Services": "XLF",
            "Healthcare": "XLV",
            "Consumer Cyclical": "XLY",
            "Consumer Defensive": "XLP",
            "Industrials": "XLI",
            "Energy": "XLE",
            "Utilities": "XLU",
            "Real Estate": "XLRE",
            "Basic Materials": "XLB",
        }
        sector_etf = sector_to_etf.get(str(output.get("sector") or ""))
        if sector_etf:
            sector_close = yf.Ticker(sector_etf).history(period="4mo", interval="1d", auto_adjust=True)["Close"].dropna()
            spy_close = yf.Ticker("SPY").history(period="4mo", interval="1d", auto_adjust=True)["Close"].dropna()
            if len(sector_close) > 63 and len(spy_close) > 63:
                sector_return = float(sector_close.iloc[-1] / sector_close.iloc[-63] - 1)
                spy_return = float(spy_close.iloc[-1] / spy_close.iloc[-63] - 1)
                output["sector_rel_3m"] = sector_return - spy_return
    except Exception:
        pass

    return output


# =============================================================================
# Componentes de score
# =============================================================================


def _quality_component(r_is: pd.DataFrame, r_bs: pd.DataFrame, r_cf: pd.DataFrame) -> ScoreComponent:
    gross_margin = _avg_recent(r_is, "Margen Bruto %", 3)
    net_margin = _avg_recent(r_is, "Margen Neto %", 3)
    roe = _avg_recent(r_bs, "ROE %", 3)
    roic = _avg_recent(r_bs, "ROIC %", 3)
    fcf_positive_ratio = _positive_ratio(r_cf, "Free Cash Flow (B USD)", 5)
    capex = _avg_recent(r_cf, "CAPEX % sobre Beneficio", 3)

    score = _weighted_mean(
        [
            (_score_linear(gross_margin, 20, 60), 0.13),
            (_score_linear(net_margin, 5, 25), 0.17),
            (_score_linear(roe, 8, 25), 0.20),
            (_score_linear(roic, 6, 25), 0.25),
            ((fcf_positive_ratio * 100) if _is_valid(fcf_positive_ratio) else None, 0.15),
            (_score_linear(capex, 15, 60, inverse=True), 0.10),
        ],
        default=50,
    )

    positives: list[str] = []
    negatives: list[str] = []

    if _is_valid(roic) and roic >= 15:
        positives.append(f"ROIC medio reciente atractivo ({roic:.1f}%).")
    elif _is_valid(roic):
        negatives.append(f"ROIC medio reciente limitado ({roic:.1f}%).")

    if _is_valid(net_margin) and net_margin >= 15:
        positives.append(f"Margen neto sólido ({net_margin:.1f}%).")
    elif _is_valid(net_margin):
        negatives.append(f"Margen neto estrecho ({net_margin:.1f}%).")

    if _is_valid(fcf_positive_ratio) and fcf_positive_ratio >= 0.8:
        positives.append("Free Cash Flow positivo en la mayoría de años recientes.")
    elif _is_valid(fcf_positive_ratio):
        negatives.append("La generación de Free Cash Flow no es suficientemente recurrente.")

    return ScoreComponent(
        name="Calidad fundamental",
        score=_clamp(score),
        weight=0.30,
        confidence=_coverage(gross_margin, net_margin, roe, roic, fcf_positive_ratio, capex, floor=0.45),
        positives=positives,
        negatives=negatives,
        source_tools=["Análisis Fundamental", "Resumen Ejecutivo", "Visor de Gurús"],
    )


def _valuation_component(res_val: dict[str, Any] | None) -> ScoreComponent:
    res_val = res_val or {}
    price = _first_available(res_val, ["precio_actual"])
    fair_values = [
        _first_available(res_val, ["dcf_value", "valor_dcf", "valor_intrinseco"]),
        _first_available(res_val, ["epv_value", "valor_epv"]),
        _first_available(res_val, ["graham_value", "valor_graham"]),
        _first_available(res_val, ["lynch_value", "valor_lynch"]),
    ]
    fair_values = [float(value) for value in fair_values if _is_valid(value) and float(value) > 0]
    fair_value = float(np.median(fair_values)) if fair_values else None

    margin_safety = None
    margin_score = 50.0
    if _is_valid(price) and _is_valid(fair_value) and float(price) > 0:
        margin_safety = (float(fair_value) - float(price)) / float(price)
        margin_score = _score_linear(margin_safety, -0.35, 0.35)

    earnings_yield = _first_available(res_val, ["earnings_yield"])
    risk_free = _first_available(res_val, ["tasa_libre_riesgo"], 0.045)
    spread_score = 50.0
    if _is_valid(earnings_yield) and _is_valid(risk_free):
        spread_score = _score_linear(float(earnings_yield) - float(risk_free), -0.02, 0.06)

    fcf_yield = _first_available(res_val, ["fcf_yield"])
    fcf_yield_score = _score_linear(fcf_yield, 0.00, 0.08) if _is_valid(fcf_yield) else None

    pe = _first_available(res_val, ["pe_actual", "per_actual"])
    pfcf = _first_available(res_val, ["pfcf_actual", "price_to_fcf"])
    multiples_score = _mean(
        [
            _score_linear(pe, 10, 35, inverse=True) if _is_valid(pe) else None,
            _score_linear(pfcf, 10, 35, inverse=True) if _is_valid(pfcf) else None,
        ],
        default=50,
    )

    score = _weighted_mean(
        [
            (margin_score, 0.45),
            (spread_score, 0.25),
            (fcf_yield_score, 0.20),
            (multiples_score, 0.10),
        ],
        default=50,
    )

    positives: list[str] = []
    negatives: list[str] = []
    if _is_valid(margin_safety) and margin_safety >= 0.15:
        positives.append(f"Margen de seguridad estimado positivo ({margin_safety * 100:.1f}%).")
    elif _is_valid(margin_safety) and margin_safety < -0.15:
        negatives.append(f"Cotización exigente frente al valor razonable estimado ({margin_safety * 100:.1f}%).")

    if _is_valid(earnings_yield) and _is_valid(risk_free) and earnings_yield > risk_free:
        positives.append("Earnings yield superior a la tasa libre de riesgo.")
    elif _is_valid(earnings_yield) and _is_valid(risk_free):
        negatives.append("Earnings yield inferior o poco superior a la tasa libre de riesgo.")

    return ScoreComponent(
        name="Valoración",
        score=_clamp(score),
        weight=0.22,
        confidence=_coverage(price, fair_value, earnings_yield, fcf_yield, pe, pfcf, floor=0.35),
        positives=positives,
        negatives=negatives,
        source_tools=["Análisis Fundamental", "Valoración DCF", "Test Buffett"],
    )


def _risk_forensic_component(r_is: pd.DataFrame, r_bs: pd.DataFrame, r_cf: pd.DataFrame, market: dict[str, Any]) -> ScoreComponent:
    debt_to_capital = _last(r_bs, "Deuda / Capital")
    net_cash = _last(r_bs, "Caja Neta (B USD)")
    fcf = _last(r_cf, "Free Cash Flow (B USD)")
    roic = _last(r_bs, "ROIC %")
    net_margin = _last(r_is, "Margen Neto %")
    interest_burden = _last(r_is, "Intereses % (s/OpInc)")
    beta = market.get("beta")
    max_drawdown = market.get("max_drawdown_1y")

    score = _weighted_mean(
        [
            (_score_linear(debt_to_capital, 0.2, 1.8, inverse=True), 0.22),
            (_score_linear(net_cash, -25, 25), 0.10),
            (85 if _is_valid(fcf) and fcf > 0 else 25 if _is_valid(fcf) else None, 0.16),
            (_score_linear(roic, 4, 18), 0.14),
            (_score_linear(net_margin, 3, 18), 0.12),
            (_score_linear(interest_burden, 5, 40, inverse=True), 0.10),
            (_score_linear(beta, 0.7, 1.8, inverse=True), 0.08),
            (_score_linear(abs(max_drawdown), 0.10, 0.55, inverse=True) if _is_valid(max_drawdown) else None, 0.08),
        ],
        default=50,
    )

    penalty = 0.0
    positives: list[str] = []
    negatives: list[str] = []
    red_flags: list[str] = []

    if _is_valid(debt_to_capital) and debt_to_capital > 1.5:
        red_flags.append(f"Deuda/Capital elevada ({debt_to_capital:.2f}x).")
        penalty += 6
    if _is_valid(fcf) and fcf < 0:
        red_flags.append(f"Free Cash Flow negativo en el último año ({fcf:.2f}B).")
        penalty += 8
    if _is_valid(roic) and roic < 7:
        red_flags.append(f"ROIC bajo frente a coste de capital razonable ({roic:.1f}%).")
        penalty += 5
    if _is_valid(net_margin) and net_margin < 5:
        red_flags.append(f"Margen neto crítico ({net_margin:.1f}%).")
        penalty += 4
    if _is_valid(beta) and beta > 1.7:
        negatives.append(f"Beta elevada ({beta:.2f}).")
    if not red_flags:
        positives.append("Sin red flags contables críticas en los ratios básicos.")

    return ScoreComponent(
        name="Riesgo y forense",
        score=_clamp(score),
        weight=0.15,
        confidence=_coverage(debt_to_capital, net_cash, fcf, roic, net_margin, beta, max_drawdown, floor=0.45),
        penalty=penalty,
        positives=positives,
        negatives=negatives,
        red_flags=red_flags,
        source_tools=["Auditoría Forense", "Cisnes Negros", "Radar de Coberturas"],
    )


def _growth_component(is_df: pd.DataFrame, r_is: pd.DataFrame, res_val: dict[str, Any] | None) -> ScoreComponent:
    res_val = res_val or {}
    revenue_cagr = _first_available(res_val, ["revenue_cagr"])
    eps_cagr = _first_available(res_val, ["cagr_historico", "eps_cagr"])
    fcf_per_share_cagr = _first_available(res_val, ["fcf_per_share_cagr"])
    sustainable_growth = _first_available(res_val, ["crecimiento_sostenible"])
    net_income_growth = _avg_recent(r_is, "Crecimiento Benef. Neto %", 3)

    if not _is_valid(revenue_cagr):
        revenue_cagr = _cagr_from_statement(is_df, "revenue")

    score = _mean(
        [
            _score_linear(revenue_cagr, -0.03, 0.12) if _is_valid(revenue_cagr) else None,
            _score_linear(eps_cagr, -0.05, 0.15) if _is_valid(eps_cagr) else None,
            _score_linear(fcf_per_share_cagr, -0.05, 0.15) if _is_valid(fcf_per_share_cagr) else None,
            _score_linear(sustainable_growth, 0.00, 0.10) if _is_valid(sustainable_growth) else None,
            _score_linear(net_income_growth, -10, 20) if _is_valid(net_income_growth) else None,
        ],
        default=55,
    )

    positives: list[str] = []
    negatives: list[str] = []
    if _is_valid(revenue_cagr) and revenue_cagr >= 0.08:
        positives.append(f"CAGR de ingresos atractivo ({revenue_cagr * 100:.1f}%).")
    elif _is_valid(revenue_cagr) and revenue_cagr < 0:
        negatives.append(f"Ingresos en contracción ({revenue_cagr * 100:.1f}% CAGR).")

    if _is_valid(eps_cagr) and eps_cagr >= 0.10:
        positives.append(f"Crecimiento de BPA sólido ({eps_cagr * 100:.1f}% CAGR).")
    elif _is_valid(eps_cagr) and eps_cagr < 0:
        negatives.append(f"BPA histórico decreciente ({eps_cagr * 100:.1f}% CAGR).")

    return ScoreComponent(
        name="Crecimiento y catalizadores",
        score=_clamp(score),
        weight=0.10,
        confidence=_coverage(revenue_cagr, eps_cagr, fcf_per_share_cagr, sustainable_growth, net_income_growth, floor=0.35),
        positives=positives,
        negatives=negatives,
        source_tools=["Proyección IA", "Radar Multibaggers", "Earnings Call NLP"],
    )


def _capital_allocation_component(r_cf: pd.DataFrame, res_val: dict[str, Any] | None, market: dict[str, Any]) -> ScoreComponent:
    res_val = res_val or {}
    buybacks = _avg_recent(r_cf, "Recompras (B USD)", 3)
    dividends = _avg_recent(r_cf, "Dividendos (B USD)", 3)
    fcf = _avg_recent(r_cf, "Free Cash Flow (B USD)", 3)
    capex = _avg_recent(r_cf, "CAPEX % sobre Beneficio", 3)
    fcf_yield = _first_available(res_val, ["fcf_yield"])
    insider_pct = market.get("insider_pct")

    buyback_score = None
    if _is_valid(buybacks) and _is_valid(fcf) and fcf > 0:
        buyback_score = _score_linear(buybacks / fcf, 0.0, 0.6)

    dividend_score = 65 if _is_valid(dividends) and dividends > 0 else 50

    score = _weighted_mean(
        [
            (buyback_score, 0.25),
            (dividend_score, 0.10),
            (_score_linear(capex, 15, 60, inverse=True), 0.20),
            (_score_linear(fcf_yield, 0.00, 0.08) if _is_valid(fcf_yield) else None, 0.25),
            (_score_linear(insider_pct, 0.1, 8.0), 0.20),
        ],
        default=50,
    )

    positives: list[str] = []
    negatives: list[str] = []
    if _is_valid(buybacks) and buybacks > 0:
        positives.append("La empresa recompra acciones de forma reciente.")
    if _is_valid(fcf_yield) and fcf_yield >= 0.04:
        positives.append(f"FCF yield razonable ({fcf_yield * 100:.1f}%).")
    elif _is_valid(fcf_yield):
        negatives.append(f"FCF yield reducido ({fcf_yield * 100:.1f}%).")
    if _is_valid(insider_pct) and insider_pct >= 3:
        positives.append(f"Insiders con participación significativa ({insider_pct:.1f}%).")

    return ScoreComponent(
        name="Asignación de capital e insiders",
        score=_clamp(score),
        weight=0.08,
        confidence=_coverage(buybacks, fcf, capex, fcf_yield, insider_pct, floor=0.35),
        positives=positives,
        negatives=negatives,
        source_tools=["Visor de Gurús", "Rastreador de Insiders", "Análisis Fundamental"],
    )


def _momentum_component(market: dict[str, Any]) -> ScoreComponent:
    ret_6m = market.get("ret_6m")
    ret_1y = market.get("ret_1y")
    rsi = market.get("rsi")
    volatility = market.get("vol_1y")
    sma50_above_sma200 = market.get("sma50_above_sma200")
    price_above_sma200 = market.get("price_above_sma200")

    ret_score = _mean(
        [
            _score_linear(ret_6m, -0.20, 0.35) if _is_valid(ret_6m) else None,
            _score_linear(ret_1y, -0.30, 0.50) if _is_valid(ret_1y) else None,
        ],
        default=50,
    )
    trend_score = _mean(
        [
            80 if sma50_above_sma200 is True else 35 if sma50_above_sma200 is False else None,
            75 if price_above_sma200 is True else 35 if price_above_sma200 is False else None,
        ],
        default=50,
    )

    rsi_score = 50
    if _is_valid(rsi):
        rsi_value = float(rsi)
        if 45 <= rsi_value <= 65:
            rsi_score = 85
        elif 35 <= rsi_value < 45 or 65 < rsi_value <= 75:
            rsi_score = 65
        elif rsi_value < 30:
            rsi_score = 45
        else:
            rsi_score = 35

    score = _weighted_mean(
        [
            (ret_score, 0.30),
            (trend_score, 0.35),
            (rsi_score, 0.20),
            (_score_linear(volatility, 0.15, 0.55, inverse=True), 0.15),
        ],
        default=50,
    )

    positives: list[str] = []
    negatives: list[str] = []
    if sma50_above_sma200 is True and price_above_sma200 is True:
        positives.append("Tendencia técnica primaria favorable.")
    elif sma50_above_sma200 is False or price_above_sma200 is False:
        negatives.append("Momentum técnico débil o deteriorado.")
    if _is_valid(rsi) and float(rsi) > 75:
        negatives.append(f"RSI en sobrecompra ({float(rsi):.1f}).")

    return ScoreComponent(
        name="Momentum y timing",
        score=_clamp(score),
        weight=0.05,
        confidence=_coverage(ret_6m, ret_1y, rsi, volatility, floor=0.25),
        positives=positives,
        negatives=negatives,
        source_tools=["Técnico y Opciones", "Máquina del Tiempo", "Backtesting Estrategias"],
    )


def _macro_component(market: dict[str, Any]) -> ScoreComponent:
    sector_rel_3m = market.get("sector_rel_3m")
    beta = market.get("beta")
    rel_score = _score_linear(sector_rel_3m, -0.10, 0.10) if _is_valid(sector_rel_3m) else 55
    beta_macro_score = _score_linear(beta, 0.8, 1.6, inverse=True) if _is_valid(beta) else 55
    score = rel_score * 0.65 + beta_macro_score * 0.35

    positives: list[str] = []
    negatives: list[str] = []
    if _is_valid(sector_rel_3m) and sector_rel_3m > 0.03:
        positives.append("El sector bate al mercado a 3 meses.")
    elif _is_valid(sector_rel_3m) and sector_rel_3m < -0.03:
        negatives.append("El sector está rezagado frente al mercado a 3 meses.")

    return ScoreComponent(
        name="Macro, sector y liquidez",
        score=_clamp(score),
        weight=0.05,
        confidence=_coverage(sector_rel_3m, beta, floor=0.25),
        positives=positives,
        negatives=negatives,
        source_tools=["Radar Macro", "Reloj Económico", "Monitor de Liquidez"],
    )


def _alternative_component(ticker: str, market: dict[str, Any]) -> ScoreComponent:
    sentiment_score = 55.0
    positives: list[str] = []
    negatives: list[str] = []
    confidence_items: list[bool] = []

    if analizar_sentimiento_noticias is not None:
        try:
            _, average_polarity = analizar_sentimiento_noticias(ticker)
            if _is_valid(average_polarity):
                sentiment_score = _score_linear(float(average_polarity), -0.25, 0.25)
                confidence_items.append(True)
                if average_polarity > 0.12:
                    positives.append("Sentimiento reciente de noticias favorable.")
                elif average_polarity < -0.12:
                    negatives.append("Sentimiento reciente de noticias negativo.")
        except Exception:
            confidence_items.append(False)

    short_ratio = market.get("short_ratio")
    short_score = _score_linear(short_ratio, 1, 8, inverse=True) if _is_valid(short_ratio) else 55
    if _is_valid(short_ratio) and short_ratio > 6:
        negatives.append(f"Short ratio elevado ({short_ratio:.1f}).")

    score = sentiment_score * 0.60 + short_score * 0.40
    confidence = _coverage(short_ratio, floor=0.25)
    if confidence_items:
        confidence = float(max(np.mean(confidence_items + [_is_valid(short_ratio)]), 0.20))

    return ScoreComponent(
        name="Opciones, alt data y NLP",
        score=_clamp(score),
        weight=0.05,
        confidence=confidence,
        positives=positives,
        negatives=negatives,
        source_tools=["Opciones Avanzadas", "Alt Data & Congreso", "Earnings Call NLP"],
    )


# =============================================================================
# API principal
# =============================================================================


def _apply_model_calibration(components: list[ScoreComponent]) -> None:
    """Calibración defensiva del scoring para reducir falsa precisión."""
    quality_component = next((c for c in components if c.name == "Calidad fundamental"), None)
    valuation_component = next((c for c in components if c.name == "Valoración"), None)
    macro_component = next((c for c in components if c.name == "Macro, sector y liquidez"), None)

    if quality_component is not None and valuation_component is not None and quality_component.score >= 85:
        valuation_component.score = max(valuation_component.score, 25)
        if not any("calidad fundamental excepcional" in item.lower() for item in valuation_component.negatives):
            valuation_component.negatives.append(
                "Valoración exigente, pero parcialmente compensada por calidad fundamental excepcional."
            )

    if macro_component is not None:
        macro_component.score = min(macro_component.score, 85)



def _apply_quality_gates(
    final_score: float,
    data_coverage: float,
    confidence: float,
    components: list[ScoreComponent],
    red_flags: list[str],
    negatives: list[str],
) -> tuple[float, str | None]:
    """Aplica límites defensivos para evitar falsa precisión con baja cobertura."""

    gate_reason: str | None = None

    critical_components = [
        component
        for component in components
        if component.name in {"Calidad fundamental", "Valoración", "Riesgo y forense"}
    ]
    low_critical_coverage = any(component.confidence < 0.45 for component in critical_components)

    if data_coverage < 0.35:
        capped = min(final_score, 49.0)
        gate_reason = "Datos insuficientes para emitir una conclusión fuerte."
        red_flags.append("Cobertura de datos crítica: el score queda bloqueado como máximo en zona neutral-débil.")
    elif data_coverage < 0.55:
        capped = min(final_score, 59.0)
        gate_reason = "Cobertura parcial: la conclusión queda limitada por calidad de datos."
        negatives.append("Cobertura de datos parcial: la lectura del score requiere cautela.")
    elif confidence < 0.60 or low_critical_coverage:
        capped = min(final_score, 69.0)
        gate_reason = "Confianza operativa limitada en bloques críticos."
        negatives.append("Confianza operativa limitada en uno o varios bloques críticos del score.")
    else:
        capped = final_score

    return capped, gate_reason



def calcular_valuequant_score(
    ticker: str,
    is_df: pd.DataFrame | None,
    bs_df: pd.DataFrame | None,
    cf_df: pd.DataFrame | None,
    res_is: dict[str, pd.DataFrame] | None,
    res_bs: dict[str, pd.DataFrame] | None,
    res_cf: dict[str, pd.DataFrame] | None,
    res_val: dict[str, Any] | None = None,
) -> ValueQuantScore:
    """Calcula la nota global ValueQuant de una empresa.

    El antiguo Buffett Score queda conceptualmente como subnota de calidad.
    Esta nota pondera calidad, valoración, riesgo, crecimiento, asignación de capital,
    momentum, macro y señales alternativas. No es una recomendación automática.
    """
    r_is = (res_is or {}).get("ratios") if isinstance(res_is, dict) else pd.DataFrame()
    r_bs = (res_bs or {}).get("ratios") if isinstance(res_bs, dict) else pd.DataFrame()
    r_cf = (res_cf or {}).get("ratios") if isinstance(res_cf, dict) else pd.DataFrame()

    if r_is is None:
        r_is = pd.DataFrame()
    if r_bs is None:
        r_bs = pd.DataFrame()
    if r_cf is None:
        r_cf = pd.DataFrame()

    market = _market_data_snapshot(ticker)

    components = [
        _quality_component(r_is, r_bs, r_cf),
        _valuation_component(res_val),
        _risk_forensic_component(r_is, r_bs, r_cf, market),
        _growth_component(is_df if is_df is not None else pd.DataFrame(), r_is, res_val),
        _capital_allocation_component(r_cf, res_val, market),
        _momentum_component(market),
        _macro_component(market),
        _alternative_component(ticker, market),
    ]

    _apply_model_calibration(components)

    numerator = sum(component.contribution for component in components)
    denominator = sum(component.effective_weight for component in components)
    gross_score = numerator / denominator if denominator else 50.0
    total_penalty = sum(component.penalty for component in components)
    final_score = _clamp(gross_score - total_penalty)

    total_weight = sum(component.weight for component in components) or 1.0
    data_coverage = float(_clamp((denominator / total_weight) * 100, 0, 100) / 100)
    confidence = min(data_coverage, CONFIDENCE_CAP)

    red_flags = [flag for component in components for flag in component.red_flags]
    positives = [item for component in components for item in component.positives]
    negatives = [item for component in components for item in component.negatives]

    gated_score, gate_reason = _apply_quality_gates(
        final_score=final_score,
        data_coverage=data_coverage,
        confidence=confidence,
        components=components,
        red_flags=red_flags,
        negatives=negatives,
    )
    final_score = _clamp(gated_score)

    if final_score >= 80:
        verdict = "Excelente"
    elif final_score >= 65:
        verdict = "Atractiva con matices"
    elif final_score >= 50:
        verdict = "Neutral / exigente"
    elif final_score >= 35:
        verdict = "Débil"
    else:
        verdict = "Alto riesgo"

    if gate_reason:
        verdict = f"{verdict} · calidad de datos limitada"

    return ValueQuantScore(
        final_score=round(final_score, 1),
        confidence=round(confidence, 2),
        data_coverage=round(data_coverage, 2),
        predictive_confidence=None,
        components=components,
        red_flags=red_flags,
        positives=positives[:8],
        negatives=negatives[:8],
        verdict=verdict,
        model_version=MODEL_VERSION,
    )


def render_valuequant_score_card(score: ValueQuantScore) -> None:
    """Render compacto para Streamlit. Úsalo en Resumen Ejecutivo y Fundamental."""
    if score is None:
        st.warning("No se pudo calcular el ValueQuant Score.")
        return

    color = "#22C55E" if score.final_score >= 75 else "#F59E0B" if score.final_score >= 50 else "#EF4444"
    predictive_text = (
        "Pendiente de validar con backtesting histórico"
        if score.predictive_confidence is None
        else f"{score.predictive_confidence * 100:.0f}%"
    )

    st.markdown(
        f"""
        <div style="
            border: 1px solid rgba(148,163,184,.18);
            border-radius: 16px;
            padding: 1.1rem 1.25rem;
            background: rgba(16,23,34,.88);
            box-shadow: 0 12px 30px rgba(0,0,0,.22);
        ">
            <div style="font-size:.78rem;color:#8C9AAF;font-weight:800;text-transform:uppercase;">
                Nota global institucional · {score.model_version}
            </div>
            <div style="display:flex;align-items:end;gap:.55rem;margin-top:.35rem;">
                <div style="font-size:3.1rem;line-height:1;font-weight:850;color:{color};">
                    {score.final_score:.1f}
                </div>
                <div style="font-size:1rem;color:#CBD5E1;margin-bottom:.35rem;">/100</div>
            </div>
            <div style="margin-top:.45rem;color:#F4F7FB;font-weight:750;">{score.verdict}</div>
            <div style="margin-top:.25rem;color:#8C9AAF;font-size:.86rem;line-height:1.45;">
                Cobertura de datos: {score.data_coverage * 100:.0f}% · Confianza operativa: {score.confidence * 100:.0f}%<br>
                Confianza predictiva: {predictive_text}. Basado en fundamentales, valoración, riesgo, momentum y proxies macro.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Desglose del ValueQuant Score", expanded=False):
        st.dataframe(score.to_dataframe(), use_container_width=True, hide_index=True)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Motores positivos**")
            if score.positives:
                for item in score.positives[:6]:
                    st.markdown(f"- {item}")
            else:
                st.caption("Sin catalizadores positivos destacados.")
        with col_b:
            st.markdown("**Riesgos / matices**")
            items = score.red_flags[:6] or score.negatives[:6]
            if items:
                for item in items:
                    st.markdown(f"- {item}")
            else:
                st.caption("Sin riesgos críticos destacados.")
