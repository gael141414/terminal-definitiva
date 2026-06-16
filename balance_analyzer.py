from __future__ import annotations

import numpy as np
import pandas as pd

from income_analyzer import (
    _fmp_series,
    _is_fmp_statement,
    _safe_ratio,
    _years_from_statement,
    extraer_dato_robusto,
)


def _is_fmp_balance(df: pd.DataFrame | None) -> bool:
    if df is None or df.empty:
        return False
    known_columns = {
        "totalAssets", "totalStockholdersEquity", "totalDebt",
        "cashAndCashEquivalents", "retainedEarnings",
    }
    return bool(known_columns & set(df.columns))


def analizar_balance(
    bs_df: pd.DataFrame | None,
    is_df: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame] | None:
    """Analiza balance con columnas FMP y conserva fallback legacy."""
    if bs_df is None or bs_df.empty:
        return None

    if not _is_fmp_balance(bs_df):
        return _analizar_balance_legacy(bs_df, is_df)

    years = _years_from_statement(bs_df)
    if not years:
        return None

    patrimonio = _fmp_series(bs_df, ["totalStockholdersEquity", "totalEquity"], years)
    activos = _fmp_series(bs_df, ["totalAssets"], years)

    deuda_total = _fmp_series(bs_df, ["totalDebt"], years, default=np.nan)
    if deuda_total.isna().all():
        deuda_total = (
            _fmp_series(bs_df, ["shortTermDebt"], years, default=0.0).fillna(0.0)
            + _fmp_series(bs_df, ["longTermDebt"], years, default=0.0).fillna(0.0)
        )

    deuda_largo = _fmp_series(bs_df, ["longTermDebt"], years, default=0.0).fillna(0.0)
    caja_total = _fmp_series(bs_df, ["cashAndShortTermInvestments"], years, default=np.nan)
    if caja_total.isna().all():
        caja_total = (
            _fmp_series(bs_df, ["cashAndCashEquivalents"], years, default=0.0).fillna(0.0)
            + _fmp_series(bs_df, ["shortTermInvestments"], years, default=0.0).fillna(0.0)
            + _fmp_series(bs_df, ["longTermInvestments"], years, default=0.0).fillna(0.0)
        )

    ganancias_retenidas = _fmp_series(bs_df, ["retainedEarnings"], years)
    ppe = _fmp_series(bs_df, ["propertyPlantEquipmentNet"], years)

    df_bal_ratios = pd.DataFrame(index=years)

    if is_df is not None and _is_fmp_statement(is_df):
        beneficio_neto = _fmp_series(is_df, ["netIncome"], years)
        ventas = _fmp_series(is_df, ["revenue"], years)
        op_income = _fmp_series(is_df, ["operatingIncome"], years)
        tax_expense = _fmp_series(is_df, ["incomeTaxExpense"], years, default=np.nan)
        ebt = _fmp_series(is_df, ["incomeBeforeTax"], years, default=np.nan)

        equity_avg = _average_balance_series(patrimonio)
        activos_avg = _average_balance_series(activos)

        df_bal_ratios["ROE %"] = _safe_ratio(beneficio_neto, equity_avg, multiplier=100)
        df_bal_ratios["DuPont: Margen Neto %"] = _safe_ratio(beneficio_neto, ventas, multiplier=100)
        df_bal_ratios["DuPont: Rotación Activos"] = _safe_ratio(ventas, activos_avg)
        df_bal_ratios["DuPont: Apalancamiento"] = _safe_ratio(activos_avg, equity_avg)

        tax_rate = (tax_expense / ebt.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
        tax_rate = tax_rate.clip(lower=0.0, upper=0.35).fillna(0.21)
        nopat = op_income * (1 - tax_rate)
        capital_invertido = patrimonio.fillna(0.0) + deuda_total.fillna(0.0) - caja_total.fillna(0.0)
        capital_invertido = capital_invertido.where(capital_invertido > 0, patrimonio + deuda_total)
        capital_invertido_avg = _average_balance_series(capital_invertido)

        df_bal_ratios["ROIC %"] = _safe_ratio(nopat, capital_invertido_avg, multiplier=100)
        df_bal_ratios["Años para pagar Deuda LP"] = _safe_ratio(deuda_largo, beneficio_neto)
        df_bal_ratios["Carga PP&E (PP&E/Benef.)"] = _safe_ratio(ppe, beneficio_neto)

    df_bal_ratios["Deuda / Capital"] = _safe_ratio(deuda_total, patrimonio)
    df_bal_ratios["Caja Neta (B USD)"] = (caja_total.fillna(0.0) - deuda_total.fillna(0.0)) / 1e9
    df_bal_ratios["Crecimiento Gan. Retenidas %"] = (
        ganancias_retenidas.sort_index().diff()
        / ganancias_retenidas.sort_index().shift(1).abs().replace(0, np.nan)
        * 100
    )

    return {"ratios": df_bal_ratios.replace([np.inf, -np.inf], np.nan).round(2)}


def _average_balance_series(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce").sort_index()
    average = (series + series.shift(1)) / 2
    return average.fillna(series)


def _analizar_balance_legacy(
    bs_df: pd.DataFrame,
    is_df: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame] | None:
    cols_bs = sorted([c for c in bs_df.columns if str(c).isdigit() and len(str(c)) == 4])
    if not cols_bs:
        return None

    patrimonio = extraer_dato_robusto(
        bs_df,
        ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "Total Equity", "Total stockholders' equity"],
        cols_bs,
    )
    activos = extraer_dato_robusto(bs_df, ["Assets", "Total assets", "Total Assets"], cols_bs)

    deuda_largo = extraer_dato_robusto(
        bs_df,
        ["LongTermDebtNoncurrent", "LongTermDebt", "UnsecuredDebt", "Term debt", "Long-term debt"],
        cols_bs,
    ).fillna(0)
    deuda_total = deuda_largo
    deuda_total += extraer_dato_robusto(bs_df, ["CommercialPaper", "Commercial Paper"], cols_bs).fillna(0)
    deuda_total += extraer_dato_robusto(bs_df, ["LongTermDebtCurrent", "Current portion of long-term debt"], cols_bs).fillna(0)
    deuda_total += extraer_dato_robusto(bs_df, ["ShortTermBorrowings", "Short-term debt"], cols_bs).fillna(0)

    caja_total = extraer_dato_robusto(
        bs_df,
        ["CashAndCashEquivalentsAtCarryingValue", "Cash and cash equivalents"],
        cols_bs,
    ).fillna(0)
    caja_total += extraer_dato_robusto(
        bs_df,
        ["MarketableSecuritiesCurrent", "ShortTermInvestments", "Short-term marketable securities"],
        cols_bs,
    ).fillna(0)
    caja_total += extraer_dato_robusto(
        bs_df,
        ["MarketableSecuritiesNoncurrent", "Long-term marketable securities"],
        cols_bs,
    ).fillna(0)

    ganancias_retenidas = extraer_dato_robusto(
        bs_df,
        ["RetainedEarningsAccumulatedDeficit", "RetainedEarnings", "Retained earnings", "Accumulated deficit"],
        cols_bs,
    )
    ppe = extraer_dato_robusto(
        bs_df,
        ["PropertyPlantAndEquipmentNet", "Property, plant and equipment, net", "Property and equipment, net"],
        cols_bs,
    )

    df_bal_ratios = pd.DataFrame(index=cols_bs)

    if is_df is not None:
        cols_is = [c for c in is_df.columns if str(c).isdigit() and len(str(c)) == 4]
        beneficio_neto = extraer_dato_robusto(is_df, ["NetIncomeLoss", "Net income"], cols_is).reindex(cols_bs)
        ventas = extraer_dato_robusto(is_df, ["RevenueFromContractWithCustomer", "SalesRevenueNet", "Net sales"], cols_is).reindex(cols_bs)
        op_income = extraer_dato_robusto(is_df, ["OperatingIncomeLoss", "Operating income"], cols_is).reindex(cols_bs)
        tax_expense = extraer_dato_robusto(is_df, ["IncomeTaxExpenseBenefit", "Income tax expense"], cols_is).reindex(cols_bs)
        ebt = extraer_dato_robusto(is_df, ["IncomeBeforeIncomeTaxes", "Income before income taxes"], cols_is).reindex(cols_bs)

        equity_avg = _average_balance_series(patrimonio)
        activos_avg = _average_balance_series(activos)
        tax_rate = (tax_expense / ebt.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).clip(0, 0.35).fillna(0.21)
        nopat = op_income * (1 - tax_rate)
        capital_invertido_avg = _average_balance_series(patrimonio.fillna(0.0) + deuda_total.fillna(0.0))

        df_bal_ratios["ROE %"] = _safe_ratio(beneficio_neto, equity_avg, multiplier=100)
        df_bal_ratios["DuPont: Margen Neto %"] = _safe_ratio(beneficio_neto, ventas, multiplier=100)
        df_bal_ratios["DuPont: Rotación Activos"] = _safe_ratio(ventas, activos_avg)
        df_bal_ratios["DuPont: Apalancamiento"] = _safe_ratio(activos_avg, equity_avg)
        df_bal_ratios["ROIC %"] = _safe_ratio(nopat, capital_invertido_avg, multiplier=100)
        df_bal_ratios["Años para pagar Deuda LP"] = _safe_ratio(deuda_largo, beneficio_neto)
        df_bal_ratios["Carga PP&E (PP&E/Benef.)"] = _safe_ratio(ppe, beneficio_neto)

    df_bal_ratios["Deuda / Capital"] = _safe_ratio(deuda_total, patrimonio)
    df_bal_ratios["Caja Neta (B USD)"] = (caja_total - deuda_total) / 1e9
    df_bal_ratios["Crecimiento Gan. Retenidas %"] = (
        ganancias_retenidas.sort_index().diff()
        / ganancias_retenidas.sort_index().shift(1).abs().replace(0, np.nan)
        * 100
    )

    return {"ratios": df_bal_ratios.replace([np.inf, -np.inf], np.nan).round(2)}
