"""Motor de comparación SEC↔FMP (Sub-fase 1 del bloque SEC↔FMP).

Alinea y clasifica las diferencias entre las métricas que ya calculan, cada
una por su lado, income_analyzer.py/balance_analyzer.py/cashflow_analyzer.py
para la ruta FMP y para la ruta SEC/XBRL ("_legacy") — no reimplementa esos
cálculos, solo compara sus resultados. No decide nada de presentación/UI
(eso es la Sub-fase 2, Modo Auditoría en Auditoría Forense).

Alineación por año Y por fecha real de periodo
------------------------------------------------
Alinear solo por la etiqueta de año ("2024" == "2024") no es seguro: un 10-K
puede reexpresar (restatement) un año anterior, o una empresa puede cambiar
su cierre de año fiscal, así que la MISMA etiqueta de año puede referirse a
periodos distintos en FMP y en SEC. Por eso, cuando ambas fuentes exponen la
fecha real de fin de periodo, se verifica que coincidan (dentro de
``DEFAULT_PERIOD_TOLERANCE_DAYS``) antes de tratar una diferencia de valor
como una discrepancia real:

- FMP: se deriva del índice real (``pd.DatetimeIndex``) del DataFrame crudo
  (``fmp_period_end_dates``) — siempre disponible, ya que
  ``modulos/fmp_api.py`` indexa por ``date``.
- SEC: se lee de ``df.attrs["period_end_dates"]``, que ``downloader.py``
  adjunta a los tres DataFrames que devuelve (Sub-fase 1). **Solo está
  disponible en un fetch fresco** — ``df.attrs`` no sobrevive un roundtrip
  por el cache en disco (``cache_datos/*.csv``), así que una lectura desde
  cache no tendrá esta señal hasta que se refresque. Cuando falta (de
  cualquiera de los dos lados), el motor degrada de forma explícita a
  alineación solo por año (``period_verified=False``, sin nota de
  desalineamiento) en vez de fallar o fingir certeza que no tiene.

Bandas de tolerancia
---------------------
``DEFAULT_TOLERANCE_PCT = 2.0`` (diferencia porcentual RELATIVA:
``(sec - fmp) / abs(fmp) * 100``): el cruce empírico ya realizado (Sub-fase 0,
Apple) mostró coincidencia exacta a 2 decimales en Margen Bruto/Neto, SG&A y
ROE. Un ±2% relativo absorbe ruido de redondeo o pequeñas diferencias de
categorización de partidas (p. ej. qué sub-gastos entran en SG&A) sin dejar
de marcar como discrepancia una diferencia real de datos, que en la práctica
tiende a ser un orden de magnitud mayor.

``DEFAULT_PERIOD_TOLERANCE_DAYS = 20``: los cierres de año fiscal de
52/53-semanas (como el de Apple, a finales de septiembre) se desplazan unos
días de un ejercicio a otro sin que eso sea un restatement ni un cambio de
año fiscal real (ver fechas reales de Apple: 2021-09-25, 2022-09-24,
2023-09-30, 2024-09-28, 2025-09-27). 20 días da margen de sobra para ese
ruido de calendario sin dejar pasar un desalineamiento real de trimestre/año.

Clasificaciones
-----------------
- ``coincide``: ambos lados tienen valor y la diferencia relativa está
  dentro de la banda de tolerancia.
- ``discrepancia``: ambos lados tienen valor pero la diferencia relativa la
  excede.
- ``no_comparable``: uno de los dos lados es NaN/None. Nunca se trata como
  0% de diferencia ni como discrepancia del 100% — mismo principio de
  "nunca cero artificial" que en los guards financieros.
- ``periodo_no_alineado``: ambos lados tienen valor, pero sus fechas de fin
  de periodo (cuando ambas están disponibles) difieren más de lo que
  explica el ruido de calendario — posible restatement o cambio de año
  fiscal. No se clasifica como discrepancia real porque no hay garantía de
  estar comparando el mismo periodo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from financials.balance_analyzer import analizar_balance
from financials.cashflow_analyzer import analizar_flujo_efectivo
from financials.income_analyzer import _statement_index_as_years, analizar_cuenta_resultados

MATCH = "coincide"
DISCREPANCY = "discrepancia"
NOT_COMPARABLE = "no_comparable"
PERIOD_MISALIGNED = "periodo_no_alineado"

ALL_CLASSIFICATIONS = {MATCH, DISCREPANCY, NOT_COMPARABLE, PERIOD_MISALIGNED}

DEFAULT_TOLERANCE_PCT = 2.0
DEFAULT_PERIOD_TOLERANCE_DAYS = 20

# ±10% relativo como corte discrepancia leve/grave — usado tanto por la
# presentación (modulos/ui_components.py, tabla de Modo Auditoría y columna
# "SEC" de Watchlist) como por la severidad de alertas (modulos/watchlist_alerts.py):
# vive aquí, en el módulo de dominio, no en una capa de presentación, para que
# ambos consumidores compartan una única fuente de verdad. El cruce empírico ya
# hecho (Sub-fases 0 y 1) muestra que FMP y SEC coinciden casi exactos para una
# empresa bien cubierta como Apple, así que una diferencia por encima de la
# banda de tolerancia (±2%) pero todavía moderada (hasta ±10%) es más probable
# que sea categorización de partidas o redondeo agresivo que un error real de
# datos; por encima de ±10% ya es difícil de explicar por ruido y merece la
# señal de severidad alta.
SEVERE_DISCREPANCY_PCT = 10.0


SOURCE_REAL = "real"
SOURCE_ESTIMADO = "estimado"


@dataclass(frozen=True)
class MetricComparison:
    """Resultado de comparar una métrica/año concretos entre FMP y SEC."""

    metric: str
    year: str
    fmp_value: float | None
    sec_value: float | None
    diff_pct: float | None
    classification: str
    period_verified: bool = False
    fmp_period_end: str | None = None
    sec_period_end: str | None = None
    note: str = ""
    # Granularidad por campo (Fase 8): "real" (dato reportado) o "estimado"
    # (paso por un fallback/proxy conocido -- ver "estimado" en
    # analizar_cuenta_resultados/analizar_balance/analizar_flujo_efectivo).
    # Default "real": una métrica sin fallback rastreado no tiene forma de
    # ser otra cosa.
    fmp_source: str = SOURCE_REAL
    sec_source: str = SOURCE_REAL


def _to_float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def fmp_period_end_dates(df: pd.DataFrame | None) -> dict[str, str]:
    """Deriva ``{año: fecha_iso}`` del índice real (DatetimeIndex) de un
    estado FMP crudo (el que devuelve ``extraer_datos_fundamentales_fmp``,
    no el DataFrame de ratios ya calculado).

    Usa el mismo criterio que ``income_analyzer._statement_index_as_years``
    para derivar la etiqueta de año a partir de la fecha, de forma que
    coincida exactamente con el índice que usan los DataFrames de ratios
    (``_years_from_statement``/``_fmp_series`` ya aplican esa misma regla).
    Si dos filas caen en la misma etiqueta de año, se conserva la última
    (orden ascendente), igual que ``_fmp_series`` con ``.groupby().last()``.
    """
    if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return {}
    años = _statement_index_as_years(df)
    return {
        str(year): fecha.strftime("%Y-%m-%d")
        for fecha, year in zip(df.index, años)
        if pd.notna(fecha) and pd.notna(year)
    }


def _verificar_periodo(
    fmp_date: str | None,
    sec_date: str | None,
    tolerance_days: int,
) -> tuple[bool, str]:
    """Compara dos fechas ISO. Devuelve ``(period_verified, nota)``.

    ``period_verified=False`` sin nota significa "no se pudo verificar"
    (falta alguna fecha) — no es lo mismo que "se verificó y no coincide"
    (``False`` con nota explicando el desalineamiento).
    """
    if not fmp_date or not sec_date:
        return False, ""
    try:
        delta_days = abs((pd.Timestamp(fmp_date) - pd.Timestamp(sec_date)).days)
    except (ValueError, TypeError):
        return False, ""
    if delta_days <= tolerance_days:
        return True, ""
    return False, (
        f"fechas de fin de periodo no coinciden (posible restatement o "
        f"cambio de año fiscal): FMP={fmp_date} SEC={sec_date}"
    )


def _diff_pct(fmp_val: float, sec_val: float) -> float | None:
    """Diferencia porcentual relativa a FMP. ``None`` si FMP es 0 (relativo
    indefinido; se resuelve aparte en ``_comparar_valor``)."""
    if fmp_val == 0:
        return None
    return (sec_val - fmp_val) / abs(fmp_val) * 100


def _comparar_valor(
    metric: str,
    year: str,
    fmp_val_raw: object,
    sec_val_raw: object,
    fmp_date: str | None,
    sec_date: str | None,
    period_verified: bool,
    period_note: str,
    tolerance_pct: float,
    fmp_source: str = SOURCE_REAL,
    sec_source: str = SOURCE_REAL,
) -> MetricComparison:
    fmp_val = _to_float_or_none(fmp_val_raw)
    sec_val = _to_float_or_none(sec_val_raw)

    if fmp_val is None or sec_val is None:
        lado_ausente = "FMP" if fmp_val is None else "SEC"
        nota = f"concepto no encontrado en {lado_ausente}"
        if period_note:
            nota = f"{nota}; {period_note}"
        return MetricComparison(
            metric=metric, year=year, fmp_value=fmp_val, sec_value=sec_val,
            diff_pct=None, classification=NOT_COMPARABLE,
            period_verified=period_verified, fmp_period_end=fmp_date, sec_period_end=sec_date,
            note=nota, fmp_source=fmp_source, sec_source=sec_source,
        )

    if period_note:
        # Ambos lados tienen valor, pero no hay garantía de que sea el mismo
        # periodo: no se etiqueta como discrepancia real.
        return MetricComparison(
            metric=metric, year=year, fmp_value=fmp_val, sec_value=sec_val,
            diff_pct=_diff_pct(fmp_val, sec_val), classification=PERIOD_MISALIGNED,
            period_verified=False, fmp_period_end=fmp_date, sec_period_end=sec_date,
            note=period_note, fmp_source=fmp_source, sec_source=sec_source,
        )

    diff = _diff_pct(fmp_val, sec_val)
    if diff is None:
        coincide = sec_val == 0
        nota = "" if coincide else f"FMP=0.0: diferencia relativa no definida (diferencia absoluta={sec_val - fmp_val:.4g})"
        return MetricComparison(
            metric=metric, year=year, fmp_value=fmp_val, sec_value=sec_val,
            diff_pct=None, classification=MATCH if coincide else DISCREPANCY,
            period_verified=period_verified, fmp_period_end=fmp_date, sec_period_end=sec_date,
            note=nota, fmp_source=fmp_source, sec_source=sec_source,
        )

    clasificacion = MATCH if abs(diff) <= tolerance_pct else DISCREPANCY
    nota = "" if clasificacion == MATCH else f"diferencia de {diff:+.2f}% (banda de tolerancia: ±{tolerance_pct}%)"
    return MetricComparison(
        metric=metric, year=year, fmp_value=fmp_val, sec_value=sec_val,
        diff_pct=diff, classification=clasificacion,
        period_verified=period_verified, fmp_period_end=fmp_date, sec_period_end=sec_date,
        note=nota, fmp_source=fmp_source, sec_source=sec_source,
    )


def _source_label(estimado: dict[str, pd.Series] | None, metric: str, year: str) -> str:
    """Traduce el dict "estimado" de un analizador (Fase 8) a "real"/"estimado"
    para una métrica/año concretos. Sin entrada para esa columna (fallback no
    rastreado) o sin dato para ese año -> "real" (nunca se inventa un
    "estimado" que el analizador no marcó explícitamente)."""
    if not estimado:
        return SOURCE_REAL
    serie = estimado.get(metric)
    if serie is None:
        return SOURCE_REAL
    try:
        es_estimado = bool(serie.get(year, False))
    except Exception:
        return SOURCE_REAL
    return SOURCE_ESTIMADO if es_estimado else SOURCE_REAL


def comparar_metricas(
    fmp_ratios: pd.DataFrame | None,
    sec_ratios: pd.DataFrame | None,
    *,
    fmp_period_end: dict[str, str] | None = None,
    sec_period_end: dict[str, str] | None = None,
    fmp_estimado: dict[str, pd.Series] | None = None,
    sec_estimado: dict[str, pd.Series] | None = None,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    period_tolerance_days: int = DEFAULT_PERIOD_TOLERANCE_DAYS,
) -> list[MetricComparison]:
    """Compara dos DataFrames de ratios ya calculados (salida de
    ``analizar_cuenta_resultados``/``analizar_balance``/``analizar_flujo_efectivo``,
    en cualquier combinación FMP/SEC) para las métricas y años que comparten.

    Alinea por nombre de columna (concepto) y por etiqueta de índice (año),
    nunca por posición — ``fmp_ratios``/``sec_ratios`` pueden tener distinto
    número de columnas o de años sin que eso rompa nada; simplemente no se
    genera comparación para lo que no comparten.

    ``fmp_estimado``/``sec_estimado`` (Fase 8, opcionales): el dict
    ``"estimado"`` que ya devuelven los analizadores, usado para poblar
    ``fmp_source``/``sec_source`` de cada ``MetricComparison``.
    """
    if fmp_ratios is None or fmp_ratios.empty or sec_ratios is None or sec_ratios.empty:
        return []

    metricas_comunes = [c for c in fmp_ratios.columns if c in sec_ratios.columns]
    años_comunes = sorted(set(fmp_ratios.index.astype(str)) & set(sec_ratios.index.astype(str)))

    fmp_period_end = fmp_period_end or {}
    sec_period_end = sec_period_end or {}

    resultados: list[MetricComparison] = []
    for year in años_comunes:
        fmp_date = fmp_period_end.get(year)
        sec_date = sec_period_end.get(year)
        period_verified, period_note = _verificar_periodo(fmp_date, sec_date, period_tolerance_days)
        for metric in metricas_comunes:
            resultados.append(_comparar_valor(
                metric, year,
                fmp_ratios.loc[year, metric], sec_ratios.loc[year, metric],
                fmp_date, sec_date, period_verified, period_note, tolerance_pct,
                fmp_source=_source_label(fmp_estimado, metric, year),
                sec_source=_source_label(sec_estimado, metric, year),
            ))
    return resultados


def comparar_estados_financieros(
    *,
    df_is_fmp: pd.DataFrame | None,
    df_cf_fmp: pd.DataFrame | None,
    df_bs_fmp: pd.DataFrame | None,
    df_is_sec: pd.DataFrame | None,
    df_cf_sec: pd.DataFrame | None,
    df_bs_sec: pd.DataFrame | None,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    period_tolerance_days: int = DEFAULT_PERIOD_TOLERANCE_DAYS,
) -> list[MetricComparison]:
    """Orquesta la comparación completa a partir de los datos ya extraídos
    por ambas rutas: FMP vía ``extraer_datos_fundamentales_fmp`` (4-tupla
    is/bs/cf/metrics — aquí solo hacen falta los 3 estados), SEC vía
    ``downloader.obtener_estados_financieros``.

    Reutiliza tal cual los analyzers existentes (mismo cálculo FMP/_legacy
    de siempre); esta función no computa ningún ratio, solo los compara.
    """
    resultados: list[MetricComparison] = []

    fmp_income = analizar_cuenta_resultados(df_is_fmp, df_cf_fmp)
    sec_income = analizar_cuenta_resultados(df_is_sec, df_cf_sec)
    if fmp_income and sec_income:
        resultados.extend(comparar_metricas(
            fmp_income["ratios"], sec_income["ratios"],
            fmp_period_end=fmp_period_end_dates(df_is_fmp),
            sec_period_end=(df_is_sec.attrs.get("period_end_dates") if df_is_sec is not None else None),
            fmp_estimado=fmp_income.get("estimado"), sec_estimado=sec_income.get("estimado"),
            tolerance_pct=tolerance_pct, period_tolerance_days=period_tolerance_days,
        ))

    fmp_balance = analizar_balance(df_bs_fmp, df_is_fmp)
    sec_balance = analizar_balance(df_bs_sec, df_is_sec)
    if fmp_balance and sec_balance:
        resultados.extend(comparar_metricas(
            fmp_balance["ratios"], sec_balance["ratios"],
            fmp_period_end=fmp_period_end_dates(df_bs_fmp),
            sec_period_end=(df_bs_sec.attrs.get("period_end_dates") if df_bs_sec is not None else None),
            fmp_estimado=fmp_balance.get("estimado"), sec_estimado=sec_balance.get("estimado"),
            tolerance_pct=tolerance_pct, period_tolerance_days=period_tolerance_days,
        ))

    fmp_cashflow = analizar_flujo_efectivo(df_cf_fmp, df_is_fmp)
    sec_cashflow = analizar_flujo_efectivo(df_cf_sec, df_is_sec)
    if fmp_cashflow and sec_cashflow:
        resultados.extend(comparar_metricas(
            fmp_cashflow["ratios"], sec_cashflow["ratios"],
            fmp_period_end=fmp_period_end_dates(df_cf_fmp),
            sec_period_end=(df_cf_sec.attrs.get("period_end_dates") if df_cf_sec is not None else None),
            fmp_estimado=fmp_cashflow.get("estimado"), sec_estimado=sec_cashflow.get("estimado"),
            tolerance_pct=tolerance_pct, period_tolerance_days=period_tolerance_days,
        ))

    return resultados
