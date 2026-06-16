from __future__ import annotations

import numpy as np
import pandas as pd

from income_analyzer import _fmp_series, _is_fmp_statement, _safe_ratio, _years_from_statement, extraer_dato_robusto
from modulos.fmp_api import obtener_cotizacion_fmp


def valorar_empresa(
    is_df: pd.DataFrame | None,
    bs_df: pd.DataFrame | None,
    cf_df: pd.DataFrame | None,
    metrics_df: pd.DataFrame | str | None = None,
    ticker_symbol: str | None = None,
) -> dict[str, float | int | None] | None:
    """Valora una empresa usando FMP y metricas institucionales.

    ``metrics_df`` acepta tambien un string para conservar compatibilidad con
    llamadas antiguas del tipo ``valorar_empresa(is_df, bs_df, cf_df, "AAPL")``.
    """
    if isinstance(metrics_df, str) and ticker_symbol is None:
        ticker_symbol = metrics_df
        metrics_df = None

    if is_df is None or is_df.empty or bs_df is None or bs_df.empty:
        return None

    if _is_fmp_statement(is_df):
        return _valorar_empresa_fmp(is_df, bs_df, cf_df, metrics_df, ticker_symbol)

    return _valorar_empresa_legacy(is_df, bs_df, cf_df, ticker_symbol)


def _valorar_empresa_fmp(
    is_df: pd.DataFrame,
    bs_df: pd.DataFrame,
    cf_df: pd.DataFrame | None,
    metrics_df: pd.DataFrame | None,
    ticker_symbol: str | None,
) -> dict[str, float | int | None] | None:
    years = _years_from_statement(is_df)
    if len(years) < 2:
        return None

    net_income = _fmp_series(is_df, ["netIncome"], years)
    revenue = _fmp_series(is_df, ["revenue"], years)
    free_cash_flow = _fmp_series(cf_df, ["freeCashFlow"], years) if cf_df is not None else pd.Series(np.nan, index=years, dtype=float)
    dividends_paid = (
        _fmp_series(cf_df, ["dividendsPaid", "netDividendsPaid", "commonDividendsPaid"], years)
        if cf_df is not None
        else pd.Series(np.nan, index=years, dtype=float)
    )
    equity = _fmp_series(bs_df, ["totalStockholdersEquity", "totalEquity"], years)
    shares = _first_available_series(
        [
            _fmp_series(is_df, ["weightedAverageShsOutDil", "weightedAverageShsOut"], years),
            _fmp_series(metrics_df, ["sharesOutstanding"], years) if metrics_df is not None else None,
        ],
        years,
    )
    eps = _first_available_series(
        [
            _fmp_series(is_df, ["epsdiluted", "eps"], years),
            _fmp_series(metrics_df, ["netIncomePerShare"], years) if metrics_df is not None else None,
            net_income / shares.replace(0, np.nan),
        ],
        years,
    )

    eps = eps.replace([np.inf, -np.inf], np.nan).dropna()
    if len(eps) < 2:
        return None

    year_start = int(str(eps.index[0])[:4])
    year_end = int(str(eps.index[-1])[:4])
    eps_initial = float(eps.iloc[0])
    eps_current = float(eps.iloc[-1])
    n_years = max(len(eps) - 1, 1)

    if eps_initial > 0 and eps_current > 0:
        cagr_historico = (eps_current / eps_initial) ** (1 / n_years) - 1
    else:
        cagr_historico = 0.05

    fcf_per_share = (free_cash_flow / shares.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    fcf_per_share_current = _last_valid(fcf_per_share)
    revenue_cagr = _cagr_series(revenue)
    fcf_per_share_cagr = _cagr_series(fcf_per_share)

    roe_series = _first_available_series(
        [
            _normalize_return_series(_fmp_series(metrics_df, ["roe", "returnOnEquity"], years)) if metrics_df is not None else None,
            _safe_ratio(net_income, _average_balance_series(equity)),
        ],
        years,
    )
    roe_medio = float(roe_series.dropna().tail(5).mean()) if not roe_series.dropna().empty else 0.10

    roic_series = (
        _normalize_return_series(_fmp_series(metrics_df, ["roic", "returnOnInvestedCapital", "returnOnCapitalEmployed"], years))
        if metrics_df is not None
        else pd.Series(np.nan, index=years, dtype=float)
    )

    pe_actual = _last_metric(metrics_df, ["peRatio", "priceEarningsRatio"])
    pb_actual = _last_metric(metrics_df, ["pbRatio", "ptbRatio"])
    pfcf_actual = _last_metric(metrics_df, ["pfcfRatio", "pfcf"])
    earnings_yield_metric = _normalize_return_value(_last_metric(metrics_df, ["earningsYield"]))
    fcf_yield_metric = _normalize_return_value(_last_metric(metrics_df, ["freeCashFlowYield"]))
    dividend_yield = _normalize_return_value(_last_metric(metrics_df, ["dividendYield"]))
    payout_ratio = _normalize_return_value(_last_metric(metrics_df, ["payoutRatio"]))
    acciones_actuales = _last_valid(shares)
    market_cap = _last_metric(metrics_df, ["marketCap"])
    enterprise_value = _last_metric(metrics_df, ["enterpriseValue"])
    graham_number_metric = _last_metric(metrics_df, ["grahamNumber"])

    precio_actual = obtener_cotizacion_fmp(ticker_symbol) if ticker_symbol else 0.0
    if not precio_actual and market_cap and acciones_actuales:
        precio_actual = float(market_cap / acciones_actuales)

    equity_actual = _last_valid(equity)
    fcf_actual = _last_valid(free_cash_flow)
    dividends_actual = abs(_last_valid(dividends_paid) or 0.0)

    if not pe_actual and precio_actual and eps_current:
        pe_actual = precio_actual / eps_current
    if not pb_actual and market_cap and equity_actual and equity_actual > 0:
        pb_actual = market_cap / equity_actual
    if not pfcf_actual and market_cap and fcf_actual and fcf_actual > 0:
        pfcf_actual = market_cap / fcf_actual

    earnings_yield = earnings_yield_metric or ((eps_current / precio_actual) if precio_actual and eps_current else None)
    if not fcf_yield_metric and precio_actual and fcf_per_share_current:
        fcf_yield_metric = fcf_per_share_current / precio_actual
    if not dividend_yield and market_cap and dividends_actual:
        dividend_yield = dividends_actual / market_cap

    if (not payout_ratio or pd.isna(payout_ratio)) and dividend_yield and earnings_yield:
        payout_ratio = float(np.clip(dividend_yield / earnings_yield, 0.0, 1.0))
    if (not payout_ratio or pd.isna(payout_ratio)) and dividends_actual and _last_valid(net_income):
        payout_ratio = dividends_actual / (_last_valid(net_income) or np.nan)
    payout_ratio = float(np.clip(payout_ratio if payout_ratio is not None else 0.0, 0.0, 1.0))

    per_futuro = _per_asumido_desde_metricas(roe_medio, cagr_historico, roic_series)
    tasa_libre_riesgo = 0.045
    beta = 1.0
    tasa_descuento_capm = max(tasa_libre_riesgo + beta * 0.055, 0.07)

    g_estimado = _crecimiento_normalizado(
        market_cap=market_cap,
        revenue_cagr=revenue_cagr,
        eps_cagr=cagr_historico,
        fcf_per_share_cagr=fcf_per_share_cagr,
    )
    terminal_growth = min(0.025, max(0.015, g_estimado * 0.45))
    g_pct = g_estimado * 100

    bvps = (equity_actual / acciones_actuales) if equity_actual and acciones_actuales else None
    graham_value = _graham_number(eps_current, bvps, graham_number_metric)
    div_yield_pct = dividend_yield * 100 if dividend_yield else 0
    lynch_pe = float(np.clip(g_pct + div_yield_pct, 5.0, 25.0))
    lynch_value = eps_current * lynch_pe if eps_current > 0 else 0
    owner_earnings_ps = fcf_per_share_current if fcf_per_share_current and fcf_per_share_current > 0 else eps_current
    epv_value = owner_earnings_ps / tasa_descuento_capm if owner_earnings_ps > 0 else 0
    dcf_value = calcular_dcf_fcf_por_accion(owner_earnings_ps, g_estimado, tasa_descuento_capm, terminal_growth)
    precio_seguridad_25 = dcf_value * 0.75 if dcf_value else 0

    return {
        "año_inicio": year_start,
        "año_fin": year_end,
        "eps_actual": eps_current,
        "fcf_actual": float(fcf_actual) if fcf_actual else None,
        "fcf_per_share": float(fcf_per_share_current) if fcf_per_share_current else None,
        "cagr_historico": float(cagr_historico),
        "revenue_cagr": float(revenue_cagr) if revenue_cagr is not None and not pd.isna(revenue_cagr) else None,
        "fcf_per_share_cagr": float(fcf_per_share_cagr) if fcf_per_share_cagr is not None and not pd.isna(fcf_per_share_cagr) else None,
        "roe": float(roe_medio),
        "roic": float(roic_series.dropna().tail(5).mean()) if not roic_series.dropna().empty else None,
        "per_asumido": per_futuro,
        "precio_actual": float(precio_actual) if precio_actual else None,
        "earnings_yield": float(earnings_yield) if earnings_yield is not None else None,
        "tasa_libre_riesgo": tasa_libre_riesgo,
        "acciones_actuales": float(acciones_actuales) if acciones_actuales else None,
        "beta": beta,
        "crecimiento_sostenible": g_estimado,
        "terminal_growth": terminal_growth,
        "tasa_descuento_capm": tasa_descuento_capm,
        "graham_value": float(graham_value),
        "lynch_value": float(lynch_value),
        "lynch_pe": lynch_pe,
        "epv_value": float(epv_value),
        "dcf_value": float(dcf_value),
        "precio_seguridad_25": float(precio_seguridad_25),
        "pe_actual": float(pe_actual) if pe_actual else None,
        "pb_actual": float(pb_actual) if pb_actual else None,
        "pfcf_actual": float(pfcf_actual) if pfcf_actual else None,
        "dividend_yield": float(dividend_yield) if dividend_yield else None,
        "fcf_yield": float(fcf_yield_metric) if fcf_yield_metric else None,
        "market_cap": float(market_cap) if market_cap else None,
        "enterprise_value": float(enterprise_value) if enterprise_value else None,
    }


def _valorar_empresa_legacy(
    is_df: pd.DataFrame,
    bs_df: pd.DataFrame,
    cf_df: pd.DataFrame | None,
    ticker_symbol: str | None = None,
) -> dict[str, float | int | None] | None:
    years_is = sorted([c for c in is_df.columns if str(c).isdigit() and len(str(c)) == 4])
    years_bs = sorted([c for c in bs_df.columns if str(c).isdigit() and len(str(c)) == 4])
    years = sorted(list(set(years_is) & set(years_bs)))
    if len(years) < 2:
        return None

    net_income = extraer_dato_robusto(is_df, ["NetIncomeLoss", "ProfitLoss", "Net income", "Net earnings"], years)
    free_cash_flow = (
        extraer_dato_robusto(cf_df, ["FreeCashFlow", "Free Cash Flow", "freeCashFlow"], years)
        if cf_df is not None
        else pd.Series(np.nan, index=years, dtype=float)
    )
    revenue = extraer_dato_robusto(is_df, ["Revenue", "TotalRevenue", "revenue", "SalesRevenueNet"], years)
    equity = extraer_dato_robusto(
        bs_df,
        ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "Total Equity", "Total stockholders' equity"],
        years,
    )
    shares = extraer_dato_robusto(
        is_df,
        ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic", "diluted shares", "basic shares"],
        years,
    )

    if net_income.isna().all() or shares.replace(0, np.nan).isna().all():
        return None

    eps = (net_income / shares.replace(0, np.nan)).dropna()
    if len(eps) < 2:
        return None

    eps_initial = float(eps.iloc[0])
    eps_current = float(eps.iloc[-1])
    cagr_historico = (
        (eps_current / eps_initial) ** (1 / max(len(eps) - 1, 1)) - 1
        if eps_initial > 0 and eps_current > 0
        else 0.05
    )
    roe_series = net_income / _average_balance_series(equity).replace(0, np.nan)
    roe_medio = float(roe_series.dropna().mean()) if not roe_series.dropna().empty else 0.10
    acciones_actuales = _last_valid(shares)
    precio_actual = obtener_cotizacion_fmp(ticker_symbol) if ticker_symbol else 0.0
    earnings_yield = (eps_current / precio_actual) if precio_actual else None
    fcf_per_share = (free_cash_flow / shares.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    fcf_per_share_current = _last_valid(fcf_per_share)

    per_futuro = _per_asumido_desde_metricas(roe_medio, cagr_historico, None)
    tasa_libre_riesgo = 0.045
    beta = 1.0
    tasa_descuento_capm = max(tasa_libre_riesgo + beta * 0.055, 0.07)
    g_estimado = _crecimiento_normalizado(
        market_cap=None,
        revenue_cagr=_cagr_series(revenue),
        eps_cagr=cagr_historico,
        fcf_per_share_cagr=_cagr_series(fcf_per_share),
    )
    terminal_growth = min(0.025, max(0.015, g_estimado * 0.45))
    g_pct = g_estimado * 100
    equity_actual = _last_valid(equity)
    bvps = (equity_actual / acciones_actuales) if equity_actual and acciones_actuales else None
    owner_earnings_ps = fcf_per_share_current if fcf_per_share_current and fcf_per_share_current > 0 else eps_current
    dcf_value = calcular_dcf_fcf_por_accion(owner_earnings_ps, g_estimado, tasa_descuento_capm, terminal_growth)
    lynch_pe = float(np.clip(g_pct, 5.0, 25.0))

    return {
        "año_inicio": int(str(eps.index[0])[:4]),
        "año_fin": int(str(eps.index[-1])[:4]),
        "eps_actual": eps_current,
        "fcf_per_share": float(fcf_per_share_current) if fcf_per_share_current else None,
        "cagr_historico": float(cagr_historico),
        "revenue_cagr": float(_cagr_series(revenue)) if _cagr_series(revenue) is not None and not pd.isna(_cagr_series(revenue)) else None,
        "fcf_per_share_cagr": float(_cagr_series(fcf_per_share)) if _cagr_series(fcf_per_share) is not None and not pd.isna(_cagr_series(fcf_per_share)) else None,
        "roe": float(roe_medio),
        "per_asumido": per_futuro,
        "precio_actual": float(precio_actual) if precio_actual else None,
        "earnings_yield": float(earnings_yield) if earnings_yield is not None else None,
        "tasa_libre_riesgo": tasa_libre_riesgo,
        "acciones_actuales": float(acciones_actuales) if acciones_actuales else None,
        "beta": beta,
        "crecimiento_sostenible": g_estimado,
        "terminal_growth": terminal_growth,
        "tasa_descuento_capm": tasa_descuento_capm,
        "graham_value": float(_graham_number(eps_current, bvps, None)),
        "lynch_value": float(eps_current * lynch_pe) if eps_current > 0 else 0,
        "lynch_pe": lynch_pe,
        "epv_value": float(owner_earnings_ps / tasa_descuento_capm) if owner_earnings_ps > 0 else 0,
        "dcf_value": float(dcf_value),
        "precio_seguridad_25": float(dcf_value * 0.75 if dcf_value else 0),
    }


def calcular_dcf_fcf_por_accion(
    fcf_por_accion: float | None,
    crecimiento: float,
    tasa_descuento: float,
    crecimiento_terminal: float = 0.025,
    anios: int = 10,
) -> float:
    """Calcula valor intrinseco por accion con DCF de FCF/FCFE por accion."""
    fcf = float(fcf_por_accion or 0.0)
    if fcf <= 0:
        return 0.0

    g = float(np.clip(crecimiento, -0.20, 0.30))
    r = float(max(tasa_descuento, 0.04))
    terminal_g = float(np.clip(crecimiento_terminal, -0.02, min(0.04, r - 0.01)))

    valor = 0.0
    flujo = fcf
    for year in range(1, anios + 1):
        flujo *= 1 + g
        valor += flujo / ((1 + r) ** year)

    terminal_value = flujo * (1 + terminal_g) / max(r - terminal_g, 0.01)
    valor += terminal_value / ((1 + r) ** anios)
    return float(max(valor, 0.0))


def calcular_crecimiento_implicito_dcf(
    precio_actual: float | None,
    fcf_por_accion: float | None,
    tasa_descuento: float,
    crecimiento_terminal: float = 0.025,
    anios: int = 10,
) -> float | None:
    """Resuelve por busqueda binaria el crecimiento que justifica el precio actual."""
    precio = float(precio_actual or 0.0)
    fcf = float(fcf_por_accion or 0.0)
    if precio <= 0 or fcf <= 0:
        return None

    low, high = -0.20, 0.30
    for _ in range(80):
        mid = (low + high) / 2
        valor = calcular_dcf_fcf_por_accion(fcf, mid, tasa_descuento, crecimiento_terminal, anios)
        if valor < precio:
            low = mid
        else:
            high = mid
    return float((low + high) / 2)


def _cagr_series(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    clean = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 2:
        return None
    initial = float(clean.iloc[0])
    current = float(clean.iloc[-1])
    periods = max(len(clean) - 1, 1)
    if initial <= 0 or current <= 0:
        return None
    return float((current / initial) ** (1 / periods) - 1)


def _crecimiento_normalizado(
    market_cap: float | None,
    revenue_cagr: float | None,
    eps_cagr: float | None,
    fcf_per_share_cagr: float | None,
) -> float:
    """Evita que ROE distorsionado por recompras infle el crecimiento de maduras."""
    componentes = []
    pesos = []
    for valor, peso in (
        (revenue_cagr, 0.30),
        (eps_cagr, 0.35),
        (fcf_per_share_cagr, 0.35),
    ):
        if valor is not None and not pd.isna(valor):
            componentes.append(float(np.clip(valor, -0.10, 0.25)) * peso)
            pesos.append(peso)

    if not componentes:
        crecimiento = 0.03
    else:
        crecimiento = sum(componentes) / sum(pesos)

    cap = 0.16
    if market_cap:
        if market_cap >= 1_000_000_000_000:
            cap = 0.08
        elif market_cap >= 200_000_000_000:
            cap = 0.10
        elif market_cap >= 50_000_000_000:
            cap = 0.12

    return float(np.clip(crecimiento, 0.0, cap))


def _graham_number(eps: float | None, bvps: float | None, graham_metric: float | None) -> float:
    """Graham Number clasico: sqrt(22.5 * EPS * BVPS)."""
    if graham_metric and graham_metric > 0:
        return float(graham_metric)
    if eps and eps > 0 and bvps and bvps > 0:
        return float(np.sqrt(22.5 * eps * bvps))
    return 0.0


def _first_available_series(
    candidates: list[pd.Series | None],
    years: list[str],
) -> pd.Series:
    result = pd.Series(np.nan, index=years, dtype=float)
    for candidate in candidates:
        if candidate is None:
            continue
        candidate = pd.to_numeric(candidate, errors="coerce").reindex(years)
        result = result.fillna(candidate)
    return result


def _average_balance_series(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce").sort_index()
    average = (series + series.shift(1)) / 2
    return average.fillna(series)


def _last_valid(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    clean = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return None
    value = float(clean.iloc[-1])
    return value if value != 0 else None


def _last_metric(metrics_df: pd.DataFrame | None, columns: list[str]) -> float | None:
    if metrics_df is None or metrics_df.empty:
        return None
    years = _years_from_statement(metrics_df)
    serie = _fmp_series(metrics_df, columns, years)
    return _last_valid(serie)


def _normalize_return_series(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    return series.where(series.abs() <= 2, series / 100)


def _normalize_return_value(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    value = float(value)
    return value if abs(value) <= 2 else value / 100


def _per_asumido_desde_metricas(
    roe_medio: float,
    cagr_historico: float,
    roic_series: pd.Series | None,
) -> int:
    roic_medio = None
    if roic_series is not None:
        clean_roic = pd.to_numeric(roic_series, errors="coerce").dropna()
        if not clean_roic.empty:
            roic_medio = float(clean_roic.tail(5).mean())

    quality_return = max(roe_medio or 0.0, roic_medio or 0.0)
    if quality_return > 0.30 and cagr_historico > 0.15:
        return 25
    if quality_return > 0.15 and cagr_historico > 0.08:
        return 20
    if quality_return > 0.10 and cagr_historico > 0:
        return 15
    return 10
