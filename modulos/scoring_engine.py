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
except Exception:
    analizar_sentimiento_noticias = None


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
    final_score: float
    confidence: float
    components: list[ScoreComponent]
    red_flags: list[str]
    positives: list[str]
    negatives: list[str]
    verdict: str

    def component(self, name: str) -> ScoreComponent | None:
        for c in self.components:
            if c.name == name:
                return c
        return None

    def to_dataframe(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for c in self.components:
            rows.append(
                {
                    "Bloque": c.name,
                    "Score": round(c.score, 1),
                    "Peso": f"{c.weight * 100:.0f}%",
                    "Confianza": f"{c.confidence * 100:.0f}%",
                    "Penalización": round(c.penalty, 1),
                    "Herramientas": ", ".join(c.source_tools),
                }
            )
        return pd.DataFrame(rows)


# =============================================================================
# HELPERS NUMÉRICOS
# =============================================================================

def _is_valid(x: Any) -> bool:
    try:
        return x is not None and not pd.isna(x) and np.isfinite(float(x))
    except Exception:
        return False


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    if not _is_valid(x):
        return 50.0
    return float(max(lo, min(hi, float(x))))


def _score_linear(value: Any, low: float, high: float, inverse: bool = False) -> float:
    """Normaliza value a 0-100. Si inverse=True, menor es mejor."""
    if not _is_valid(value):
        return 50.0
    value = float(value)
    if high == low:
        return 50.0
    raw = (value - low) / (high - low) * 100
    raw = 100 - raw if inverse else raw
    return _clamp(raw)


def _safe_mean(values: list[float | None], default: float = 50.0) -> float:
    clean = [float(v) for v in values if _is_valid(v)]
    if not clean:
        return default
    return float(np.mean(clean))


def _get_series(df: pd.DataFrame | None, col: str) -> pd.Series:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty or col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def _last(df: pd.DataFrame | None, col: str) -> float | None:
    s = _get_series(df, col)
    return float(s.iloc[-1]) if not s.empty else None


def _avg_recent(df: pd.DataFrame | None, col: str, n: int = 3) -> float | None:
    s = _get_series(df, col)
    return float(s.tail(n).mean()) if not s.empty else None


def _positive_ratio(df: pd.DataFrame | None, col: str, n: int = 5) -> float | None:
    s = _get_series(df, col).tail(n)
    if s.empty:
        return None
    return float((s > 0).mean())


def _cagr_from_statement(df: pd.DataFrame | None, col: str) -> float | None:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty or col not in df.columns:
        return None
    s = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(s) < 2:
        return None
    first = float(s.iloc[0])
    last = float(s.iloc[-1])
    years = max(len(s) - 1, 1)
    if first <= 0 or last <= 0:
        return None
    return float((last / first) ** (1 / years) - 1)


def _first_available(mapping: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    if not isinstance(mapping, dict):
        return default
    for k in keys:
        v = mapping.get(k)
        if _is_valid(v):
            return v
    return default


@st.cache_data(ttl=1800, show_spinner=False)
def _market_data_snapshot(ticker: str) -> dict[str, Any]:
    """Datos de mercado ligeros. Si Yahoo falla, devuelve defaults neutrales."""
    out: dict[str, Any] = {
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
        "options_put_call_proxy": None,
        "insider_pct": None,
        "inst_pct": None,
        "short_ratio": None,
    }

    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        out["beta"] = info.get("beta")
        out["market_cap"] = info.get("marketCap")
        out["sector"] = info.get("sector")
        out["insider_pct"] = (info.get("heldPercentInsiders") or 0) * 100
        out["inst_pct"] = (info.get("heldPercentInstitutions") or 0) * 100
        out["short_ratio"] = info.get("shortRatio")

        hist = tk.history(period="18mo", interval="1d", auto_adjust=True)
        if hist is not None and not hist.empty and "Close" in hist.columns:
            close = hist["Close"].dropna()
            if len(close) >= 220:
                ret = close.pct_change().dropna()
                out["ret_6m"] = float(close.iloc[-1] / close.iloc[-126] - 1) if len(close) > 126 else None
                out["ret_1y"] = float(close.iloc[-1] / close.iloc[-252] - 1) if len(close) > 252 else None
                out["vol_1y"] = float(ret.tail(252).std() * math.sqrt(252)) if not ret.empty else None
                running_max = close.tail(252).cummax()
                dd = (close.tail(252) / running_max) - 1
                out["max_drawdown_1y"] = float(dd.min())
                sma50 = close.rolling(50).mean().iloc[-1]
                sma200 = close.rolling(200).mean().iloc[-1]
                out["sma50_above_sma200"] = bool(sma50 > sma200) if _is_valid(sma50) and _is_valid(sma200) else None
                out["price_above_sma200"] = bool(close.iloc[-1] > sma200) if _is_valid(sma200) else None

                delta = close.diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, np.nan)
                rsi = 100 - (100 / (1 + rs))
                out["rsi"] = float(rsi.dropna().iloc[-1]) if not rsi.dropna().empty else None

        # Proxy sectorial simple: rendimiento 3m del ETF sectorial vs SPY.
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
        etf = sector_to_etf.get(str(out.get("sector") or ""))
        if etf:
            h_sector = yf.Ticker(etf).history(period="4mo", interval="1d", auto_adjust=True)["Close"].dropna()
            h_spy = yf.Ticker("SPY").history(period="4mo", interval="1d", auto_adjust=True)["Close"].dropna()
            if len(h_sector) > 63 and len(h_spy) > 63:
                sec_ret = float(h_sector.iloc[-1] / h_sector.iloc[-63] - 1)
                spy_ret = float(h_spy.iloc[-1] / h_spy.iloc[-63] - 1)
                out["sector_rel_3m"] = sec_ret - spy_ret
    except Exception:
        pass

    return out


# =============================================================================
# COMPONENTES DE SCORE
# =============================================================================

def _quality_component(r_is: pd.DataFrame, r_bs: pd.DataFrame, r_cf: pd.DataFrame) -> ScoreComponent:
    mb = _avg_recent(r_is, "Margen Bruto %", 3)
    mn = _avg_recent(r_is, "Margen Neto %", 3)
    roe = _avg_recent(r_bs, "ROE %", 3)
    roic = _avg_recent(r_bs, "ROIC %", 3)
    fcf_pos = _positive_ratio(r_cf, "Free Cash Flow (B USD)", 5)
    capex = _avg_recent(r_cf, "CAPEX % sobre Beneficio", 3)

    sub = {
        "margen_bruto": _score_linear(mb, 20, 60),
        "margen_neto": _score_linear(mn, 5, 25),
        "roe": _score_linear(roe, 8, 25),
        "roic": _score_linear(roic, 6, 25),
        "fcf_recurrencia": (fcf_pos * 100) if _is_valid(fcf_pos) else 50,
        "capex_ligero": _score_linear(capex, 60, 15, inverse=False),  # al revés via low>high no funciona bien; corregimos debajo
    }
    sub["capex_ligero"] = _score_linear(capex, 15, 60, inverse=True)

    score = _safe_mean([
        sub["margen_bruto"] * 0.13,
        sub["margen_neto"] * 0.17,
        sub["roe"] * 0.20,
        sub["roic"] * 0.25,
        sub["fcf_recurrencia"] * 0.15,
        sub["capex_ligero"] * 0.10,
    ], default=50) / _safe_mean([0.13, 0.17, 0.20, 0.25, 0.15, 0.10], default=1)

    positives, negatives = [], []
    if _is_valid(roic) and roic >= 15:
        positives.append(f"ROIC medio reciente atractivo ({roic:.1f}%).")
    elif _is_valid(roic):
        negatives.append(f"ROIC medio reciente limitado ({roic:.1f}%).")
    if _is_valid(mn) and mn >= 15:
        positives.append(f"Margen neto sólido ({mn:.1f}%).")
    elif _is_valid(mn):
        negatives.append(f"Margen neto estrecho ({mn:.1f}%).")
    if _is_valid(fcf_pos) and fcf_pos >= 0.8:
        positives.append("Free Cash Flow positivo en la mayoría de años recientes.")
    elif _is_valid(fcf_pos):
        negatives.append("La generación de Free Cash Flow no es suficientemente recurrente.")

    confidence = np.mean([_is_valid(x) for x in [mb, mn, roe, roic, fcf_pos, capex]])
    return ScoreComponent(
        name="Calidad fundamental",
        score=_clamp(score),
        weight=0.30,
        confidence=float(max(confidence, 0.45)),
        positives=positives,
        negatives=negatives,
        source_tools=["Análisis Fundamental", "Resumen Ejecutivo", "Visor de Gurús"],
    )


def _valuation_component(r_cf: pd.DataFrame, res_val: dict[str, Any] | None) -> ScoreComponent:
    res_val = res_val or {}
    precio = _first_available(res_val, ["precio_actual"])
    fair_values = [
        _first_available(res_val, ["dcf_value"]),
        _first_available(res_val, ["epv_value"]),
        _first_available(res_val, ["graham_value"]),
        _first_available(res_val, ["lynch_value"]),
    ]
    fair_values = [float(v) for v in fair_values if _is_valid(v) and float(v) > 0]
    fair_value = float(np.median(fair_values)) if fair_values else None

    margin_score = 50.0
    margin_safety = None
    if _is_valid(precio) and _is_valid(fair_value) and precio > 0:
        margin_safety = (fair_value - float(precio)) / float(precio)
        margin_score = _score_linear(margin_safety, -0.35, 0.35)

    earnings_yield = _first_available(res_val, ["earnings_yield"])
    risk_free = _first_available(res_val, ["tasa_libre_riesgo"], 0.045)
    spread_score = 50.0
    if _is_valid(earnings_yield) and _is_valid(risk_free):
        spread_score = _score_linear(float(earnings_yield) - float(risk_free), -0.02, 0.06)

    fcf_yield = _first_available(res_val, ["fcf_yield"])
    fcf_yield_score = _score_linear(fcf_yield, 0.00, 0.08) if _is_valid(fcf_yield) else 50.0

    pe = _first_available(res_val, ["pe_actual"])
    pfcf = _first_available(res_val, ["pfcf_actual"])
    multiples_score = _safe_mean([
        _score_linear(pe, 35, 10, inverse=False) if _is_valid(pe) else None,
        _score_linear(pfcf, 35, 10, inverse=False) if _is_valid(pfcf) else None,
    ], default=50)
    # Corregimos: para múltiplos menor es mejor.
    multiples_score = _safe_mean([
        _score_linear(pe, 10, 35, inverse=True) if _is_valid(pe) else None,
        _score_linear(pfcf, 10, 35, inverse=True) if _is_valid(pfcf) else None,
    ], default=50)

    score = margin_score * 0.45 + spread_score * 0.25 + fcf_yield_score * 0.20 + multiples_score * 0.10

    positives, negatives = [], []
    if _is_valid(margin_safety) and margin_safety >= 0.15:
        positives.append(f"Margen de seguridad estimado positivo ({margin_safety*100:.1f}%).")
    elif _is_valid(margin_safety) and margin_safety < -0.15:
        negatives.append(f"Cotización exigente frente al valor razonable estimado ({margin_safety*100:.1f}%).")
    if _is_valid(earnings_yield) and _is_valid(risk_free) and earnings_yield > risk_free:
        positives.append("Earnings yield superior a la tasa libre de riesgo.")
    elif _is_valid(earnings_yield) and _is_valid(risk_free):
        negatives.append("Earnings yield inferior o poco superior a la tasa libre de riesgo.")

    confidence = np.mean([_is_valid(precio), _is_valid(fair_value), _is_valid(earnings_yield), _is_valid(fcf_yield)])
    return ScoreComponent(
        name="Valoración",
        score=_clamp(score),
        weight=0.22,
        confidence=float(max(confidence, 0.35)),
        positives=positives,
        negatives=negatives,
        source_tools=["Análisis Fundamental", "Valoración DCF", "Test Buffett"],
    )


def _risk_forensic_component(r_is: pd.DataFrame, r_bs: pd.DataFrame, r_cf: pd.DataFrame, market: dict[str, Any]) -> ScoreComponent:
    deuda = _last(r_bs, "Deuda / Capital")
    caja_neta = _last(r_bs, "Caja Neta (B USD)")
    fcf = _last(r_cf, "Free Cash Flow (B USD)")
    roic = _last(r_bs, "ROIC %")
    mn = _last(r_is, "Margen Neto %")
    intereses = _last(r_is, "Intereses % (s/OpInc)")
    beta = market.get("beta")
    max_dd = market.get("max_drawdown_1y")

    solvency = _score_linear(deuda, 0.2, 1.8, inverse=True) if _is_valid(deuda) else 50
    cash = _score_linear(caja_neta, -25, 25) if _is_valid(caja_neta) else 50
    fcf_score = 85 if _is_valid(fcf) and fcf > 0 else 25 if _is_valid(fcf) else 50
    roic_score = _score_linear(roic, 4, 18) if _is_valid(roic) else 50
    margin_score = _score_linear(mn, 3, 18) if _is_valid(mn) else 50
    interest_score = _score_linear(intereses, 40, 5, inverse=False) if _is_valid(intereses) else 50
    interest_score = _score_linear(intereses, 5, 40, inverse=True) if _is_valid(intereses) else 50
    beta_score = _score_linear(beta, 0.7, 1.8, inverse=True) if _is_valid(beta) else 50
    dd_score = _score_linear(abs(max_dd), 0.10, 0.55, inverse=True) if _is_valid(max_dd) else 50

    score = (
        solvency * 0.22 + cash * 0.10 + fcf_score * 0.16 + roic_score * 0.14 +
        margin_score * 0.12 + interest_score * 0.10 + beta_score * 0.08 + dd_score * 0.08
    )

    red_flags, negatives, positives = [], [], []
    penalty = 0.0
    if _is_valid(deuda) and deuda > 1.5:
        red_flags.append(f"Deuda/Capital elevada ({deuda:.2f}x).")
        penalty += 6
    if _is_valid(fcf) and fcf < 0:
        red_flags.append(f"Free Cash Flow negativo en el último año ({fcf:.2f}B).")
        penalty += 8
    if _is_valid(roic) and roic < 7:
        red_flags.append(f"ROIC bajo frente a coste de capital razonable ({roic:.1f}%).")
        penalty += 5
    if _is_valid(mn) and mn < 5:
        red_flags.append(f"Margen neto crítico ({mn:.1f}%).")
        penalty += 4
    if _is_valid(beta) and beta > 1.7:
        negatives.append(f"Beta elevada ({beta:.2f}).")
    if not red_flags:
        positives.append("Sin red flags contables críticas en los ratios básicos.")

    confidence = np.mean([_is_valid(x) for x in [deuda, caja_neta, fcf, roic, mn, beta, max_dd]])
    return ScoreComponent(
        name="Riesgo y forense",
        score=_clamp(score),
        weight=0.15,
        confidence=float(max(confidence, 0.45)),
        penalty=penalty,
        positives=positives,
        negatives=negatives,
        red_flags=red_flags,
        source_tools=["Auditoría Forense", "Cisnes Negros", "Radar de Coberturas"],
    )


def _growth_component(is_df: pd.DataFrame, r_is: pd.DataFrame, res_val: dict[str, Any] | None, market: dict[str, Any]) -> ScoreComponent:
    res_val = res_val or {}
    revenue_cagr = _first_available(res_val, ["revenue_cagr"])
    eps_cagr = _first_available(res_val, ["cagr_historico"])
    fcf_ps_cagr = _first_available(res_val, ["fcf_per_share_cagr"])
    sustainable_g = _first_available(res_val, ["crecimiento_sostenible"])
    net_income_growth = _avg_recent(r_is, "Crecimiento Benef. Neto %", 3)

    # Fallback si valuator no pudo calcular CAGR.
    if not _is_valid(revenue_cagr):
        revenue_cagr = _cagr_from_statement(is_df, "revenue")

    scores = [
        _score_linear(revenue_cagr, -0.03, 0.12) if _is_valid(revenue_cagr) else None,
        _score_linear(eps_cagr, -0.05, 0.15) if _is_valid(eps_cagr) else None,
        _score_linear(fcf_ps_cagr, -0.05, 0.15) if _is_valid(fcf_ps_cagr) else None,
        _score_linear(sustainable_g, 0.00, 0.10) if _is_valid(sustainable_g) else None,
        _score_linear(net_income_growth, -10, 20) if _is_valid(net_income_growth) else None,
    ]
    score = _safe_mean(scores, default=55)

    positives, negatives = [], []
    if _is_valid(revenue_cagr) and revenue_cagr >= 0.08:
        positives.append(f"CAGR de ingresos atractivo ({revenue_cagr*100:.1f}%).")
    elif _is_valid(revenue_cagr) and revenue_cagr < 0:
        negatives.append(f"Ingresos en contracción ({revenue_cagr*100:.1f}% CAGR).")
    if _is_valid(eps_cagr) and eps_cagr >= 0.10:
        positives.append(f"Crecimiento de BPA sólido ({eps_cagr*100:.1f}% CAGR).")
    elif _is_valid(eps_cagr) and eps_cagr < 0:
        negatives.append(f"BPA histórico decreciente ({eps_cagr*100:.1f}% CAGR).")

    confidence = np.mean([_is_valid(x) for x in [revenue_cagr, eps_cagr, fcf_ps_cagr, sustainable_g, net_income_growth]])
    return ScoreComponent(
        name="Crecimiento y catalizadores",
        score=_clamp(score),
        weight=0.10,
        confidence=float(max(confidence, 0.35)),
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

    buyback_score = 50
    if _is_valid(buybacks) and _is_valid(fcf) and fcf > 0:
        buyback_score = _score_linear(buybacks / fcf, 0.0, 0.6)
    dividend_score = 65 if _is_valid(dividends) and dividends > 0 else 50
    capex_score = _score_linear(capex, 15, 60, inverse=True) if _is_valid(capex) else 50
    fcf_yield_score = _score_linear(fcf_yield, 0.00, 0.08) if _is_valid(fcf_yield) else 50
    insider_score = _score_linear(insider_pct, 0.1, 8.0) if _is_valid(insider_pct) else 50

    score = buyback_score * 0.25 + dividend_score * 0.10 + capex_score * 0.20 + fcf_yield_score * 0.25 + insider_score * 0.20

    positives, negatives = [], []
    if _is_valid(buybacks) and buybacks > 0:
        positives.append("La empresa recompra acciones de forma reciente.")
    if _is_valid(fcf_yield) and fcf_yield >= 0.04:
        positives.append(f"FCF yield razonable ({fcf_yield*100:.1f}%).")
    elif _is_valid(fcf_yield):
        negatives.append(f"FCF yield reducido ({fcf_yield*100:.1f}%).")
    if _is_valid(insider_pct) and insider_pct >= 3:
        positives.append(f"Insiders con participación significativa ({insider_pct:.1f}%).")

    confidence = np.mean([_is_valid(x) for x in [buybacks, fcf, capex, fcf_yield, insider_pct]])
    return ScoreComponent(
        name="Asignación de capital e insiders",
        score=_clamp(score),
        weight=0.08,
        confidence=float(max(confidence, 0.35)),
        positives=positives,
        negatives=negatives,
        source_tools=["Visor de Gurús", "Rastreador de Insiders", "Análisis Fundamental"],
    )


def _momentum_component(market: dict[str, Any]) -> ScoreComponent:
    ret_6m = market.get("ret_6m")
    ret_1y = market.get("ret_1y")
    rsi = market.get("rsi")
    vol = market.get("vol_1y")
    sma50_above_sma200 = market.get("sma50_above_sma200")
    price_above_sma200 = market.get("price_above_sma200")

    ret_score = _safe_mean([
        _score_linear(ret_6m, -0.20, 0.35) if _is_valid(ret_6m) else None,
        _score_linear(ret_1y, -0.30, 0.50) if _is_valid(ret_1y) else None,
    ], default=50)
    trend_score = _safe_mean([
        80 if sma50_above_sma200 is True else 35 if sma50_above_sma200 is False else None,
        75 if price_above_sma200 is True else 35 if price_above_sma200 is False else None,
    ], default=50)

    # RSI óptimo en zona saludable, no en sobrecompra extrema.
    rsi_score = 50
    if _is_valid(rsi):
        rsi = float(rsi)
        if 45 <= rsi <= 65:
            rsi_score = 85
        elif 35 <= rsi < 45 or 65 < rsi <= 75:
            rsi_score = 65
        elif rsi < 30:
            rsi_score = 45
        else:
            rsi_score = 35

    vol_score = _score_linear(vol, 0.15, 0.55, inverse=True) if _is_valid(vol) else 50
    score = ret_score * 0.30 + trend_score * 0.35 + rsi_score * 0.20 + vol_score * 0.15

    positives, negatives = [], []
    if sma50_above_sma200 is True and price_above_sma200 is True:
        positives.append("Tendencia técnica primaria favorable.")
    elif sma50_above_sma200 is False or price_above_sma200 is False:
        negatives.append("Momentum técnico débil o deteriorado.")
    if _is_valid(rsi) and float(rsi) > 75:
        negatives.append(f"RSI en sobrecompra ({float(rsi):.1f}).")

    confidence = np.mean([_is_valid(x) for x in [ret_6m, ret_1y, rsi, vol]])
    return ScoreComponent(
        name="Momentum y timing",
        score=_clamp(score),
        weight=0.05,
        confidence=float(max(confidence, 0.25)),
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

    positives, negatives = [], []
    if _is_valid(sector_rel_3m) and sector_rel_3m > 0.03:
        positives.append("El sector bate al mercado a 3 meses.")
    elif _is_valid(sector_rel_3m) and sector_rel_3m < -0.03:
        negatives.append("El sector está rezagado frente al mercado a 3 meses.")

    confidence = np.mean([_is_valid(sector_rel_3m), _is_valid(beta)])
    return ScoreComponent(
        name="Macro, sector y liquidez",
        score=_clamp(score),
        weight=0.05,
        confidence=float(max(confidence, 0.25)),
        positives=positives,
        negatives=negatives,
        source_tools=["Radar Macro", "Reloj Económico", "Monitor de Liquidez"],
    )


def _alternative_component(ticker: str, market: dict[str, Any]) -> ScoreComponent:
    sentiment_score = 55.0
    positives, negatives = [], []
    confidence_items = []

    if analizar_sentimiento_noticias is not None:
        try:
            _, polaridad_media = analizar_sentimiento_noticias(ticker)
            if _is_valid(polaridad_media):
                sentiment_score = _score_linear(float(polaridad_media), -0.25, 0.25)
                confidence_items.append(True)
                if polaridad_media > 0.12:
                    positives.append("Sentimiento reciente de noticias favorable.")
                elif polaridad_media < -0.12:
                    negatives.append("Sentimiento reciente de noticias negativo.")
        except Exception:
            confidence_items.append(False)

    short_ratio = market.get("short_ratio")
    short_score = _score_linear(short_ratio, 1, 8, inverse=True) if _is_valid(short_ratio) else 55
    if _is_valid(short_ratio) and short_ratio > 6:
        negatives.append(f"Short ratio elevado ({short_ratio:.1f}).")

    score = sentiment_score * 0.60 + short_score * 0.40
    confidence = np.mean(confidence_items + [_is_valid(short_ratio)]) if confidence_items else (0.4 if _is_valid(short_ratio) else 0.25)
    return ScoreComponent(
        name="Opciones, alt data y NLP",
        score=_clamp(score),
        weight=0.05,
        confidence=float(max(confidence, 0.20)),
        positives=positives,
        negatives=negatives,
        source_tools=["Opciones Avanzadas", "Alt Data & Congreso", "Earnings Call NLP"],
    )


# =============================================================================
# API PRINCIPAL
# =============================================================================

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
    """
    Calcula la nota global ValueQuant de una empresa.

    Filosofía:
    - El antiguo Buffett Score pasa a ser solo calidad fundamental.
    - La nota global pondera calidad, valoración, riesgo, crecimiento, capital allocation,
      momentum, macro y señales alternativas.
    - Cada componente tiene peso y confianza. Si faltan datos, baja la confianza en lugar de romper la app.
    """
    r_is = (res_is or {}).get("ratios") if isinstance(res_is, dict) else None
    r_bs = (res_bs or {}).get("ratios") if isinstance(res_bs, dict) else None
    r_cf = (res_cf or {}).get("ratios") if isinstance(res_cf, dict) else None

    if r_is is None:
        r_is = pd.DataFrame()
    if r_bs is None:
        r_bs = pd.DataFrame()
    if r_cf is None:
        r_cf = pd.DataFrame()

    market = _market_data_snapshot(ticker)

    components = [
        _quality_component(r_is, r_bs, r_cf),
        _valuation_component(r_cf, res_val),
        _risk_forensic_component(r_is, r_bs, r_cf, market),
        _growth_component(is_df if is_df is not None else pd.DataFrame(), r_is, res_val, market),
        _capital_allocation_component(r_cf, res_val, market),
        _momentum_component(market),
        _macro_component(market),
        _alternative_component(ticker, market),
    ]

    # -------------------------------------------------------------------------
    # CALIBRACIÓN INSTITUCIONAL DEL MODELO
    # -------------------------------------------------------------------------
    # 1. Si la empresa tiene calidad excepcional, evitamos que una valoración
    #    exigente destruya completamente la nota global. No significa que esté
    #    barata, solo que una empresa premium puede merecer cierta prima.
    quality_component = next(
        (c for c in components if c.name == "Calidad fundamental"),
        None
    )

    valuation_component = next(
        (c for c in components if c.name == "Valoración"),
        None
    )

    macro_component = next(
        (c for c in components if c.name == "Macro, sector y liquidez"),
        None
    )

    if (
        quality_component is not None
        and valuation_component is not None
        and quality_component.score >= 85
    ):
        valuation_component.score = max(valuation_component.score, 25)

        if not any("prima de calidad" in n.lower() for n in valuation_component.negatives):
            valuation_component.negatives.append(
                "Valoración exigente, pero parcialmente compensada por calidad fundamental excepcional."
            )

    # 2. El bloque macro/sector es contexto, no tesis principal.
    #    Aunque el sector esté fuerte, no debe empujar artificialmente la nota.
    if macro_component is not None:
        macro_component.score = min(macro_component.score, 85)

    numerator = sum(c.contribution for c in components)
    denominator = sum(c.effective_weight for c in components)
    gross_score = numerator / denominator if denominator else 50.0
    total_penalty = sum(c.penalty for c in components)
    final_score = _clamp(gross_score - total_penalty)

    raw_confidence = float(
        _clamp((denominator / sum(c.weight for c in components)) * 100, 0, 100) / 100
    )

    # Mientras varias herramientas funcionen mediante proxies cuantitativos y no
    # mediante salidas estructuradas propias, limitamos la confianza máxima.
    confidence = min(raw_confidence, 0.86)

    red_flags = [flag for c in components for flag in c.red_flags]
    positives = [p for c in components for p in c.positives]
    negatives = [n for c in components for n in c.negatives]

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

    return ValueQuantScore(
        final_score=round(final_score, 1),
        confidence=round(confidence, 2),
        components=components,
        red_flags=red_flags,
        positives=positives[:8],
        negatives=negatives[:8],
        verdict=verdict,
    )


def render_valuequant_score_card(score: ValueQuantScore) -> None:
    """Render compacto para Streamlit. Úsalo en Resumen Ejecutivo y Fundamental."""
    if score is None:
        st.warning("No se pudo calcular el ValueQuant Score.")
        return

    color = "#22C55E" if score.final_score >= 75 else "#F59E0B" if score.final_score >= 50 else "#EF4444"
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
                Nota global institucional
            </div>
            <div style="display:flex;align-items:end;gap:.55rem;margin-top:.35rem;">
                <div style="font-size:3.1rem;line-height:1;font-weight:850;color:{color};">
                    {score.final_score:.1f}
                </div>
                <div style="font-size:1rem;color:#CBD5E1;margin-bottom:.35rem;">/100</div>
            </div>
            <div style="margin-top:.45rem;color:#F4F7FB;font-weight:750;">{score.verdict}</div>
            <div style="margin-top:.25rem;color:#8C9AAF;font-size:.86rem;">
                Confianza del modelo: {score.confidence*100:.0f}% · Basado en fundamentales, valoración, riesgo, momentum y proxies macro.
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
