from __future__ import annotations

import re

import numpy as np
import pandas as pd


META_COLUMNS = {
    "symbol", "reportedCurrency", "cik", "fillingDate", "acceptedDate",
    "calendarYear", "period", "link", "finalLink",
}


def _clean_numeric_block(df_block: pd.DataFrame) -> pd.DataFrame:
    rep = {r",": "", r"\$": "", r"—": "", r"–": "", r"%": ""}
    cleaned = df_block.astype(str).replace(rep, regex=True)
    cleaned = cleaned.replace(r"^\((.*)\)$", r"-\1", regex=True)
    return cleaned.apply(pd.to_numeric, errors="coerce")


def extraer_dato_robusto(
    df: pd.DataFrame | None,
    terminos: list[str],
    cols: list[str],
    verbose: bool = False,
) -> pd.Series:
    """Extrae una fila numerica desde estados legacy tipo SEC/Yahoo.

    Se mantiene por compatibilidad con scripts antiguos. El flujo principal de
    la aplicacion ya usa columnas FMP normalizadas.
    """
    if df is None or df.empty:
        return pd.Series([np.nan] * len(cols), index=cols, dtype=float)

    meta_cols = [c for c in ["standard_concept", "concept", "label"] if c in df.columns]
    if not meta_cols:
        return _fmp_series(df, terminos, _years_from_statement(df), default=np.nan)

    escaped_terms = [re.escape(t) for t in terminos]
    patron_exacto = r"(?i)^(?:[a-zA-Z0-9\-]+_)?(" + "|".join(escaped_terms) + r")$"

    for meta in meta_cols:
        col_data = df[meta]
        if isinstance(col_data, pd.DataFrame):
            col_data = col_data.iloc[:, 0]
        mask = col_data.astype(str).str.match(patron_exacto, na=False)
        if mask.any():
            block = df.loc[mask, cols]
            res = _clean_numeric_block(block)
            res["nulos"] = res.isnull().sum(axis=1)
            res["len"] = col_data.loc[mask].astype(str).str.len().values
            return res.sort_values(["nulos", "len"]).drop(columns=["nulos", "len"]).iloc[0]

    patron_loose = r"(?i)(" + "|".join(escaped_terms) + r")"
    mask_loose = pd.Series(False, index=df.index)

    for meta in meta_cols:
        col_data = df[meta]
        if isinstance(col_data, pd.DataFrame):
            col_data = col_data.iloc[:, 0]
        mask_loose = mask_loose | col_data.astype(str).str.contains(
            patron_loose, na=False, regex=True
        )

    if mask_loose.any():
        block = df.loc[mask_loose, cols]
        res = _clean_numeric_block(block)
        res["nulos"] = res.isnull().sum(axis=1)
        return res.sort_values(["nulos"]).drop(columns=["nulos"]).iloc[0]

    return pd.Series([np.nan] * len(cols), index=cols, dtype=float)


def _is_fmp_statement(df: pd.DataFrame | None) -> bool:
    if df is None or df.empty:
        return False
    known_columns = {
        "revenue", "grossProfit", "operatingIncome", "netIncome",
        "costOfRevenue", "sellingGeneralAndAdministrativeExpenses",
    }
    return bool(known_columns & set(df.columns))


def _years_from_statement(df: pd.DataFrame | None) -> list[str]:
    if df is None or df.empty:
        return []
    if isinstance(df.index, pd.DatetimeIndex):
        return sorted(df.index.year.astype(str).unique().tolist())
    if "calendarYear" in df.columns:
        years = pd.to_numeric(df["calendarYear"], errors="coerce").dropna().astype(int)
        return sorted(years.astype(str).unique().tolist())
    return sorted([str(c) for c in df.columns if str(c).isdigit() and len(str(c)) == 4])


def _statement_index_as_years(df: pd.DataFrame) -> pd.Index:
    if isinstance(df.index, pd.DatetimeIndex):
        return pd.Index(df.index.year.astype(str), name="year")
    if "calendarYear" in df.columns:
        years = pd.to_numeric(df["calendarYear"], errors="coerce")
        return pd.Index(years.astype("Int64").astype(str), name="year")
    return pd.Index(df.index.astype(str), name="year")


def _fmp_series(
    df: pd.DataFrame | None,
    columns: list[str],
    years: list[str],
    default: float = np.nan,
) -> pd.Series:
    if df is None or df.empty or not years:
        return pd.Series(default, index=years, dtype=float)

    for column in columns:
        if column in df.columns:
            serie = pd.to_numeric(df.get(column), errors="coerce")
            serie.index = _statement_index_as_years(df)
            serie = serie.groupby(level=0).last()
            return serie.reindex(years).astype(float)

    return pd.Series(default, index=years, dtype=float)


def analizar_cuenta_resultados(
    df: pd.DataFrame | None,
    cf_df: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame] | None:
    """Analiza la cuenta de resultados usando columnas FMP normalizadas."""
    if df is None or df.empty:
        return None

    if not _is_fmp_statement(df):
        return _analizar_cuenta_resultados_legacy(df, cf_df)

    years = _years_from_statement(df)
    if not years:
        return None

    ventas = _fmp_series(df, ["revenue"], years)
    margen_bruto = _fmp_series(df, ["grossProfit"], years)
    cogs = _fmp_series(df, ["costOfRevenue"], years, default=0.0)
    margen_bruto = margen_bruto.fillna(ventas - cogs)

    vga = _fmp_series(
        df,
        [
            "sellingGeneralAndAdministrativeExpenses",
            "generalAndAdministrativeExpenses",
            "sellingAndMarketingExpenses",
        ],
        years,
        default=0.0,
    ).fillna(0.0)
    id_gasto = _fmp_series(df, ["researchAndDevelopmentExpenses"], years, default=0.0).fillna(0.0)
    depreciacion = _fmp_series(
        cf_df,
        ["depreciationAndAmortization", "depreciationAndAmortizationExpense"],
        years,
        default=np.nan,
    ).abs()
    intereses = _fmp_series(df, ["interestExpense", "interestAndDebtExpense"], years, default=np.nan).abs()
    op_income = _fmp_series(df, ["operatingIncome"], years)
    beneficio_neto = _fmp_series(df, ["netIncome"], years)

    df_ratios = pd.DataFrame(index=years)
    df_ratios["Margen Bruto %"] = _safe_ratio(margen_bruto, ventas, multiplier=100)
    df_ratios["SG&A % (s/MB)"] = _safe_ratio(vga, margen_bruto, multiplier=100)
    df_ratios["I+D % (s/MB)"] = _safe_ratio(id_gasto, margen_bruto, multiplier=100)
    df_ratios["Depreciación % (s/MB)"] = _safe_ratio(depreciacion, margen_bruto, multiplier=100)
    df_ratios["Intereses % (s/OpInc)"] = _safe_ratio(intereses, op_income, multiplier=100)
    df_ratios["Margen Neto %"] = _safe_ratio(beneficio_neto, ventas, multiplier=100)
    df_ratios["Crecimiento Benef. Neto %"] = beneficio_neto.sort_index().pct_change(fill_method=None) * 100

    return {"ratios": df_ratios.replace([np.inf, -np.inf], np.nan).clip(-1000, 1000).round(2)}


def _safe_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
    multiplier: float = 1.0,
) -> pd.Series:
    return (numerator / denominator.replace(0, np.nan) * multiplier).replace(
        [np.inf, -np.inf],
        np.nan,
    )


def _analizar_cuenta_resultados_legacy(
    df: pd.DataFrame,
    cf_df: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame] | None:
    cols = sorted([c for c in df.columns if str(c).isdigit() and len(str(c)) == 4])
    if not cols:
        return None

    ventas = extraer_dato_robusto(
        df,
        [
            "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomer", "SalesRevenueNet",
            "SalesRevenueGoodsNet", "SalesRevenueServicesNet", "TotalRevenues",
            "Net sales", "Total Revenues", "Net revenues",
        ],
        cols,
    )
    margen_bruto = extraer_dato_robusto(df, ["GrossProfit", "Gross margin", "Gross profit"], cols)
    cogs = extraer_dato_robusto(
        df,
        ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices", "Cost of sales", "Cost of revenues"],
        cols,
    )
    if margen_bruto.isna().all() and not cogs.isna().all():
        margen_bruto = ventas - cogs.fillna(0)

    vga = extraer_dato_robusto(
        df,
        ["SellingGeneralAndAdministrativeExpense", "GeneralAndAdministrativeExpense", "SellingAndMarketingExpense", "Selling, general", "SG&A"],
        cols,
    )
    id_gasto = extraer_dato_robusto(df, ["ResearchAndDevelopmentExpense", "Research and development", "R&D"], cols)

    if cf_df is not None:
        cols_cf = sorted([c for c in cf_df.columns if str(c).isdigit() and len(str(c)) == 4])
        depreciacion = extraer_dato_robusto(
            cf_df,
            ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretion", "Depreciation", "Amortization"],
            cols_cf,
        ).abs().reindex(cols)
        intereses = extraer_dato_robusto(
            cf_df,
            ["InterestPaidNet", "Cash paid for interest", "InterestExpense", "InterestExpenseDebt", "InterestAndDebtExpense", "InterestPaid", "Interest expense"],
            cols_cf,
        ).abs().reindex(cols)
    else:
        depreciacion = extraer_dato_robusto(df, ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "Depreciation"], cols).abs()
        intereses = pd.Series([np.nan] * len(cols), index=cols)

    op_income = extraer_dato_robusto(df, ["OperatingIncomeLoss", "Operating income", "Income from operations"], cols)
    beneficio_neto = extraer_dato_robusto(
        df,
        ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss", "Net income", "Net earnings"],
        cols,
    )

    df_ratios = pd.DataFrame(index=cols)
    df_ratios["Margen Bruto %"] = _safe_ratio(margen_bruto, ventas, multiplier=100)
    df_ratios["SG&A % (s/MB)"] = _safe_ratio(vga, margen_bruto, multiplier=100)
    df_ratios["I+D % (s/MB)"] = _safe_ratio(id_gasto, margen_bruto, multiplier=100)
    df_ratios["Depreciación % (s/MB)"] = _safe_ratio(depreciacion, margen_bruto, multiplier=100)
    df_ratios["Intereses % (s/OpInc)"] = _safe_ratio(intereses, op_income, multiplier=100)
    df_ratios["Margen Neto %"] = _safe_ratio(beneficio_neto, ventas, multiplier=100)
    df_ratios["Crecimiento Benef. Neto %"] = beneficio_neto[sorted(cols)].pct_change(fill_method=None) * 100

    return {"ratios": df_ratios.replace([np.inf, -np.inf], np.nan).clip(-1000, 1000).round(2)}
