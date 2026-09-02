import html

import pandas as pd
import streamlit as st

from modulos.sec_fmp_cross_validation import (
    DISCREPANCY,
    MATCH,
    NOT_COMPARABLE,
    PERIOD_MISALIGNED,
    SEVERE_DISCREPANCY_PCT,
    SOURCE_ESTIMADO,
)
from modulos.tool_catalog import obtener_herramientas_por_grupo_consolidado
from modulos.tool_consolidation import CONSOLIDATION_GROUPS, get_navigation_groups_ordered
from modulos.html_markdown import escribir_html


def render_navigation_group_card(group_key: str, *, index: int | None = None) -> None:
    """Tarjeta de grupo de navegación (mockup docs/design/research_core_navegacion_kpi.html, sección 1a).

    Muestra hasta 3 herramientas del grupo y un contador "+ N más". El grupo
    "utilities_postmvp" (oculto por defecto) usa el contenedor punteado en vez
    de la tarjeta sólida, igual que en el mockup.
    """
    group = CONSOLIDATION_GROUPS.get(group_key)
    if group is None:
        return

    tools = obtener_herramientas_por_grupo_consolidado(group_key)
    from modulos.app_assets import strip_visual_prefix

    if group.hidden_unless_complete:
        st.markdown(
            f"""
            <div style="border:1px dashed rgba(147,164,187,0.22); border-radius:12px; padding:20px 22px;
                        display:flex; flex-direction:column; gap:8px; justify-content:center; height:100%;">
                <span style="font-weight:600; font-size:13.5px; color:#93a4bb;">{html.escape(strip_visual_prefix(group.name))}</span>
                <span style="font-size:12px; color:#5b6a80; line-height:1.5;">
                    {len(tools)} herramientas accesorias, ocultas por defecto. Visibles solo en modo «Completo».
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    ordinal = f"{index:02d}" if index is not None else ""
    preview = tools[:3]
    remaining = len(tools) - len(preview)
    items_html = "".join(f"<span>{html.escape(strip_visual_prefix(str(t['label'])))}</span>" for t in preview)
    if remaining > 0:
        items_html += f"<span style='color:#5b6a80;'>+ {remaining} más</span>"

    escribir_html(f"""
        <div class="vq-group-card" style="background:rgba(18,25,38,0.92); border:1px solid rgba(147,164,187,0.1); border-radius:12px;
                    padding:20px 22px; display:flex; flex-direction:column; gap:12px; height:100%;">
            <div style="display:flex; align-items:baseline; gap:10px;">
                <span style="font-family:'JetBrains Mono',monospace; color:#37c6e6; font-size:13px;">{ordinal}</span>
                <span style="font-weight:700; font-size:15px;">{html.escape(strip_visual_prefix(group.name))}</span>
                <span style="margin-left:auto; font-size:11px; color:#5b6a80;">{len(tools)}</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:6px; font-size:12.5px; color:#93a4bb;">
                {items_html}
            </div>
        </div>
        """)


def render_navigation_groups_grid() -> None:
    """Rejilla 3x2 de tarjetas de grupo (mockup 1a), en el orden de prioridad de producto."""
    groups = get_navigation_groups_ordered()
    cols = st.columns(3)
    for i, group in enumerate(groups):
        with cols[i % 3]:
            render_navigation_group_card(group.key, index=(i + 1) if not group.hidden_unless_complete else None)


# Alias de estados heredados de la firma anterior (app.py los sigue usando) al
# vocabulario de 5 estados del mockup. "no_disponible" no tiene alias porque es
# nuevo: antes un dato ausente se colaba como "neutral" con valor "N/A" a mano
# en cada call site.
_LEGACY_STATUS_ALIASES = {
    "neutral": "normal",
    "positive": "favorable",
    "warning": "advertencia",
    "negative": "riesgo",
}

# Tokens visuales exactos del mockup docs/design/research_core_navegacion_kpi.html
# (sección 1b, "Tarjeta KPI estandarizada — 5 estados").
_KPI_STATUS_STYLES = {
    "normal": {
        "card_bg": "rgba(18,25,38,0.92)",
        "border": "1px solid rgba(147,164,187,0.12)",
        "left_edge": "none",
        "label_color": "#93a4bb",
        "value_color": "#eef4ff",
        "delta_color": "#37c6e6",
        "badge": None,
    },
    "favorable": {
        "card_bg": "rgba(18,25,38,0.92)",
        "border": "1px solid rgba(61,220,151,0.45)",
        "left_edge": "inset 3px 0 0 #3ddc97",
        "label_color": "#93a4bb",
        "value_color": "#3ddc97",
        "delta_color": "#3ddc97",
        "badge": ("FAVORABLE", "#3ddc97", "rgba(61,220,151,0.12)", "rgba(61,220,151,0.3)"),
    },
    "advertencia": {
        "card_bg": "rgba(18,25,38,0.92)",
        "border": "1px solid rgba(245,176,76,0.45)",
        "left_edge": "inset 3px 0 0 #f5b04c",
        "label_color": "#93a4bb",
        "value_color": "#f5b04c",
        "delta_color": "#f5b04c",
        "badge": ("VIGILAR", "#f5b04c", "rgba(245,176,76,0.12)", "rgba(245,176,76,0.3)"),
    },
    "riesgo": {
        "card_bg": "rgba(18,25,38,0.92)",
        "border": "1px solid rgba(243,108,108,0.5)",
        "left_edge": "inset 3px 0 0 #f36c6c",
        "label_color": "#93a4bb",
        "value_color": "#f36c6c",
        "delta_color": "#f36c6c",
        "badge": ("RIESGO", "#f36c6c", "rgba(243,108,108,0.12)", "rgba(243,108,108,0.35)"),
    },
    "no_disponible": {
        "card_bg": "rgba(13,17,26,0.7)",
        "border": "1px dashed rgba(147,164,187,0.28)",
        "left_edge": "none",
        "label_color": "#5b6a80",
        "value_color": "#5b6a80",
        "delta_color": "#5b6a80",
        "badge": ("SIN DATOS", "#93a4bb", "rgba(147,164,187,0.1)", "rgba(147,164,187,0.2)"),
    },
}


def _is_missing(value: object) -> bool:
    """None o NaN. Un guard financiero (patrimonio negativo, ROIC, etc.) que
    devuelve None/NaN debe caer aquí, no en un "0" o "N/A" genérico."""
    if value is None:
        return True
    if isinstance(value, float) and value != value:  # NaN != NaN
        return True
    return False


def kpi_status_from_thresholds(
    value: float | None,
    *,
    warning: float,
    danger: float,
    higher_is_worse: bool = True,
) -> str:
    """Clasifica un valor en normal/advertencia/riesgo a partir de dos umbrales.

    Ejemplo con los umbrales ya centralizados en modulos/config.py — el mismo
    par de niveles ámbar/rojo que ya usan escanear_vulnerabilidades y
    calcular_score_buffett para Deuda/Capital (higher_is_worse=True es el
    sentido por defecto: cuanto más alto, peor)::

        from modulos.config import DEBT_EQUITY_WARNING, DEBT_EQUITY_RED_FLAG
        status = kpi_status_from_thresholds(
            deuda_capital, warning=DEBT_EQUITY_WARNING, danger=DEBT_EQUITY_RED_FLAG,
        )

    Con ``higher_is_worse=False`` se invierte el sentido (p. ej. un ratio de
    cobertura o un margen donde los valores BAJOS son el problema).

    ``value`` None/NaN devuelve directamente ``"no_disponible"`` para que el
    resultado se pueda pasar tal cual como ``status=`` de ``render_kpi_card``
    sin que cada call site repita el chequeo de ausencia — aunque
    ``render_kpi_card`` ya fuerza ese estado igualmente si ``value`` llega
    vacío, así que esto es solo para que el status ya venga "correcto" antes
    de decidir el texto del detalle.
    """
    if _is_missing(value):
        return "no_disponible"
    if higher_is_worse:
        if value > danger:
            return "riesgo"
        if value > warning:
            return "advertencia"
        return "normal"
    if value < danger:
        return "riesgo"
    if value < warning:
        return "advertencia"
    return "normal"


def render_kpi_card(
    label: str,
    value: object,
    detail: str = "",
    status: str = "normal",
    *,
    delta: str | None = None,
    tag: str | None = None,
    no_data_detail: str = "fuente no disponible para este campo · excluido del score",
) -> None:
    """Tarjeta KPI estandarizada de 5 estados (mockup docs/design/research_core_navegacion_kpi.html, 1b).

    - ``normal``: valor + delta neutro en cian, sin juicio de valor.
    - ``favorable`` / ``advertencia`` / ``riesgo``: borde + filo izquierdo y
      badge del color correspondiente; usar cuando el KPI cruza un umbral
      conocido (p. ej. modulos.config.DEBT_EQUITY_WARNING/RED_FLAG).
    - ``no_disponible``: se fuerza automáticamente cuando ``value`` es
      ``None``/``NaN`` (el resultado típico de un guard financiero: patrimonio
      negativo, capital invertido <= 0, dato ausente en balance/cashflow) —
      nunca se muestra un "0" o "N/A" ambiguo, siempre "n/d" con borde
      punteado y la nota de exclusión del score.

    Acepta los alias de estado de la firma anterior (neutral/positive/
    warning/negative) para no romper a los call sites existentes.
    """
    resolved_status = _LEGACY_STATUS_ALIASES.get(status, status)

    if _is_missing(value):
        resolved_status = "no_disponible"
        value_display = "n/d"
        detail_text = no_data_detail
    else:
        resolved_status = resolved_status if resolved_status in _KPI_STATUS_STYLES else "normal"
        value_display = str(value)
        detail_text = detail

    style = _KPI_STATUS_STYLES[resolved_status]

    tag_html = ""
    if resolved_status == "normal" and tag:
        tag_html = (
            f"<span style='margin-left:auto; font-size:10px; color:#5b6a80; "
            f"font-family:\"JetBrains Mono\",monospace;'>{html.escape(str(tag))}</span>"
        )
    elif style["badge"]:
        badge_text, badge_color, badge_bg, badge_border = style["badge"]
        tag_html = (
            f"<span style='margin-left:auto; font-size:10px; font-weight:700; color:{badge_color}; "
            f"background:{badge_bg}; border:1px solid {badge_border}; padding:2px 8px; "
            f"border-radius:99px; letter-spacing:0.06em;'>{html.escape(badge_text)}</span>"
        )

    delta_html = ""
    if delta and resolved_status != "no_disponible":
        delta_html = (
            f"<span style='font-size:12.5px; font-weight:600; "
            f"color:{style['delta_color']};'>{html.escape(str(delta))}</span>"
        )

    escribir_html(f"""
        <div class="vq-kpi-card" style="background:{style['card_bg']}; border:{style['border']}; box-shadow:{style['left_edge']};
                    border-radius:12px; padding:18px 20px; display:flex; flex-direction:column; gap:8px;">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:11px; font-weight:600; letter-spacing:0.1em; color:{style['label_color']};
                            text-transform:uppercase;">{html.escape(str(label))}</span>
                {tag_html}
            </div>
            <div style="display:flex; align-items:baseline; gap:10px;">
                <span style="font-size:30px; font-weight:800; font-family:'JetBrains Mono',monospace;
                            letter-spacing:-0.02em; color:{style['value_color']};">{html.escape(value_display)}</span>
                {delta_html}
            </div>
            <div style="font-size:11.5px; color:#5b6a80;">{html.escape(str(detail_text))}</div>
        </div>
        """)


def pillar_semantic_color(score: float | None) -> str:
    """Color semántico por score (mockup 1c: col = s>=75 verde : s>=60 cian : s>=45 ámbar : rojo)."""
    if score is None:
        return "#5b6a80"
    if score >= 75:
        return "#3ddc97"
    if score >= 60:
        return "#37c6e6"
    if score >= 45:
        return "#f5b04c"
    return "#f36c6c"


def render_pillar_card(name: str, weight_pct: float, score: float | None, *, detail: str = "") -> None:
    """Tarjeta de pilar del ValueQuant Score (mockup 1c, tier 3: rejilla 4x2).

    Hermana de render_kpi_card (misma paleta y radios) pero con estructura
    propia: badge de peso + barra de progreso, que no encaja en los 5 estados
    estándar de KPI (esto no es un "KPI con estado", es la descomposición de
    un score compuesto).
    """
    color = pillar_semantic_color(score)
    score_display = f"{score:.0f}" if score is not None else "n/d"
    pct = max(0.0, min(100.0, score)) if score is not None else 0.0

    st.markdown(
        f"""
        <div style="background:rgba(18,25,38,0.92); border:1px solid rgba(147,164,187,0.1); border-radius:11px;
                    padding:15px 18px; display:flex; flex-direction:column; gap:9px; height:100%;">
            <div style="display:flex; align-items:baseline; gap:8px; min-height:32px;">
                <span style="font-size:11px; font-weight:600; letter-spacing:0.06em; color:#93a4bb;
                            text-transform:uppercase; line-height:1.35;">{html.escape(str(name))}</span>
                <span style="margin-left:auto; font-family:'JetBrains Mono',monospace; font-size:10.5px; color:#4f8cff;
                            background:rgba(79,140,255,0.1); border:1px solid rgba(79,140,255,0.25); padding:1px 7px;
                            border-radius:99px; flex:none;">{weight_pct:.0f}%</span>
            </div>
            <div style="display:flex; align-items:baseline; gap:6px;">
                <span style="font-family:'JetBrains Mono',monospace; font-size:24px; font-weight:800;
                            color:{color};">{html.escape(score_display)}</span>
                <span style="font-size:10.5px; color:#5b6a80;">/100{(' · ' + html.escape(detail)) if detail else ''}</span>
            </div>
            <div style="height:5px; border-radius:99px; background:rgba(147,164,187,0.12); overflow:hidden;">
                <div style="height:100%; width:{pct:.0f}%; background:{color}; border-radius:99px;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --- Tabla de verificación cruzada SEC↔FMP (Sub-fase 2, Modo Auditoría) -----
# Hermana de render_kpi_card (misma paleta de 5 colores) pero con estructura
# de tabla, no de tarjeta suelta: aquí lo relevante es comparar muchas filas
# (métrica × año) a la vez, algo que una rejilla de tarjetas haría demasiado
# larga para una lista que puede superar las 30-40 filas.

_CROSS_VALIDATION_STATUS_LABELS = {
    "favorable": "✅ Coincide",
    "advertencia": "⚠️ Discrepancia",
    "riesgo": "🔴 Discrepancia",
    "no_disponible": "⬜ No comparable",
    "informativo": "🔵 Periodo no alineado",
}

_CROSS_VALIDATION_ROW_COLORS = {
    _CROSS_VALIDATION_STATUS_LABELS["favorable"]: "rgba(61,220,151,0.12)",
    _CROSS_VALIDATION_STATUS_LABELS["advertencia"]: "rgba(245,176,76,0.12)",
    _CROSS_VALIDATION_STATUS_LABELS["riesgo"]: "rgba(243,108,108,0.12)",
    _CROSS_VALIDATION_STATUS_LABELS["no_disponible"]: "rgba(147,164,187,0.10)",
    _CROSS_VALIDATION_STATUS_LABELS["informativo"]: "rgba(55,198,230,0.14)",
}


def cross_validation_row_status(comparison) -> str:
    """Traduce una ``MetricComparison`` (modulos.sec_fmp_cross_validation) al
    vocabulario de color ya usado por render_kpi_card.

    - ``coincide`` -> ``favorable`` (verde).
    - ``no_comparable`` -> ``no_disponible`` (gris): un dato ausente en un
      lado NUNCA se muestra como discrepancia (ni como "0% de diferencia" ni
      como "100% de discrepancia") — mismo principio de "nunca cero
      artificial" que en los guards financieros.
    - ``periodo_no_alineado`` -> ``informativo`` (cian, distinto de rojo/ámbar
      a propósito): las fechas de fin de periodo no coinciden, así que
      cualquier diferencia de valor no es de fiar como discrepancia real —
      mezclarlo visualmente con una discrepancia real haría parecer un
      problema de datos algo que puede ser solo un restatement o un cambio
      de año fiscal.
    - ``discrepancia`` -> ``riesgo`` si la diferencia relativa supera
      ``SEVERE_DISCREPANCY_PCT``, ``advertencia`` si no.
    """
    if comparison.classification == MATCH:
        return "favorable"
    if comparison.classification == NOT_COMPARABLE:
        return "no_disponible"
    if comparison.classification == PERIOD_MISALIGNED:
        return "informativo"
    # DISCREPANCY: diff_pct casi siempre presente aquí (solo es None cuando
    # FMP=0, ver _diff_pct) — sin él no se puede juzgar severidad, así que se
    # trata como advertencia (nunca se escala a riesgo sin evidencia numérica).
    diff = comparison.diff_pct
    if diff is not None and abs(diff) > SEVERE_DISCREPANCY_PCT:
        return "riesgo"
    return "advertencia"


def _formatear_valor_cross_validation(value: float | None) -> str:
    return "n/d" if value is None else f"{value:,.2f}"


def _formatear_diff_cross_validation(value: float | None) -> str:
    return "n/d" if value is None else f"{value:+.2f}%"


def _formatear_fuente_cross_validation(source: str) -> str:
    """Marca discreta de procedencia (Fase 8): en blanco para "real" (la
    mayoría de celdas) y un símbolo corto para "estimado" -- nunca un color
    nuevo, para no competir con la clasificación coincide/discrepancia/riesgo
    que ya usa color en toda la fila."""
    return "≈ estimado" if source == SOURCE_ESTIMADO else ""


def cross_validation_dataframe(comparisons: list) -> pd.DataFrame:
    """Prepara el DataFrame de presentación a partir de la lista de
    ``MetricComparison`` que devuelve ``comparar_estados_financieros``.

    Función pura (sin Streamlit) para que la lógica de qué se le pasa al
    componente de tabla sea testeable de forma aislada. Incluye la columna
    ``_status`` (no se muestra en pantalla) para que los tests puedan
    verificar la clasificación visual sin parsear el texto del badge.
    """
    filas = []
    for comp in comparisons:
        status = cross_validation_row_status(comp)
        filas.append({
            "Métrica": comp.metric,
            "Año": comp.year,
            "FMP": _formatear_valor_cross_validation(comp.fmp_value),
            "Fuente FMP": _formatear_fuente_cross_validation(comp.fmp_source),
            "SEC": _formatear_valor_cross_validation(comp.sec_value),
            "Fuente SEC": _formatear_fuente_cross_validation(comp.sec_source),
            "Diferencia %": _formatear_diff_cross_validation(comp.diff_pct),
            "Estado": _CROSS_VALIDATION_STATUS_LABELS[status],
            "Nota": comp.note,
            "_status": status,
        })
    return pd.DataFrame(
        filas,
        columns=["Métrica", "Año", "FMP", "Fuente FMP", "SEC", "Fuente SEC", "Diferencia %", "Estado", "Nota", "_status"],
    )


def _style_cross_validation_row(row: pd.Series) -> list[str]:
    color = _CROSS_VALIDATION_ROW_COLORS.get(row.get("Estado", ""), "")
    return [f"background-color: {color}" if color else ""] * len(row)


def render_cross_validation_table(comparisons: list) -> None:
    """Tabla de verificación cruzada SEC↔FMP (Modo Auditoría, Auditoría
    Forense). Una fila por métrica/año comparado, coloreada por estado."""
    if not comparisons:
        st.info("SEC EDGAR no tiene métricas comparables con FMP para esta empresa en el rango de años consultado.")
        return

    df = cross_validation_dataframe(comparisons)

    orden_resumen = ["favorable", "riesgo", "advertencia", "informativo", "no_disponible"]
    conteos = df["_status"].value_counts()
    resumen = " · ".join(
        f"{_CROSS_VALIDATION_STATUS_LABELS[status]}: {conteos[status]}"
        for status in orden_resumen
        if status in conteos.index
    )
    if resumen:
        st.caption(resumen)

    visible_cols = ["Métrica", "Año", "FMP", "Fuente FMP", "SEC", "Fuente SEC", "Diferencia %", "Estado", "Nota"]
    st.dataframe(
        df[visible_cols].style.apply(_style_cross_validation_row, axis=1),
        use_container_width=True,
        hide_index=True,
    )


# --- Resumen SEC en Watchlist y Modo Auditoría (Sub-fase 3c) ----------------
# Consume modulos.sec_validation_store.sec_validation_summary(ticker) — el
# resumen compacto que persiste el job nocturno (Sub-fase 3b). Reutiliza el
# mismo vocabulario de color que la tabla de verificación cruzada (favorable/
# riesgo/advertencia/informativo) más un quinto estado, "sin_verificar", que
# NUNCA se confunde con "favorable": un ticker que jamás ha tenido una corrida
# correcta (ni el job nocturno ni Modo Auditoría en vivo) no es lo mismo que
# uno que se verificó y coincide — mismo principio de "nunca cero artificial"
# que en los guards financieros, aplicado aquí a "ausencia de verificación"
# en vez de a un valor numérico.

_SEC_WATCHLIST_STATUS_LABELS = {
    "favorable": "✅ Coincide",
    "advertencia": "🟡 {n} discrepancia(s)",
    "riesgo": "🔴 {n} discrepancia(s)",
    "informativo": "🔵 Periodo no alineado",
    "sin_verificar": "⚪ Sin verificar",
}


def sec_validation_watchlist_status(summary: dict) -> str:
    """Traduce el resumen compacto (``last_sec_validation`` en watchlist.json,
    vía ``sec_validation_summary``) al estado visual de la columna "SEC" en
    Watchlist.

    ``sin_verificar`` cubre tanto "nunca se intentó" como "se intentó pero
    nunca tuvo éxito" — en ambos casos no hay ningún resultado real que
    mostrar, así que es deliberadamente el mismo estado (gris), distinto de
    los otros cuatro que sí reflejan un resultado real.
    """

    if not summary or not summary.get("last_successful_check_at"):
        return "sin_verificar"

    discrepancy_count = int(summary.get("discrepancy_count") or 0)
    period_misaligned_count = int(summary.get("period_misaligned_count") or 0)

    if discrepancy_count > 0:
        worst = summary.get("worst_diff_pct")
        if worst is not None and abs(worst) > SEVERE_DISCREPANCY_PCT:
            return "riesgo"
        return "advertencia"
    if period_misaligned_count > 0:
        return "informativo"
    return "favorable"


def sec_validation_watchlist_label(summary: dict) -> str:
    """Texto de la columna "SEC" en Watchlist (mismo patrón que Bucket Score
    en modulos/watchlist.py: emoji + texto corto, sin estilo de celda)."""

    status = sec_validation_watchlist_status(summary)
    template = _SEC_WATCHLIST_STATUS_LABELS[status]
    if status in ("advertencia", "riesgo"):
        return template.format(n=int(summary.get("discrepancy_count") or 0))
    return template


def format_last_sec_validation_caption(summary: dict) -> str:
    """Caption sobre el toggle "Verificar contra SEC EDGAR" (Modo Auditoría,
    Auditoría Forense) resumiendo la última corrida del job nocturno sin
    disparar el fetch en vivo — ese toggle sigue funcionando exactamente
    igual, esto es solo información adicional.

    Distingue explícitamente tres situaciones que nunca deben confundirse:
    nunca intentado, intentado pero sin éxito nunca (se ve el código de
    fallo, no un resultado inventado), y con éxito (se ve el resultado real,
    con una nota aparte si el intento MÁS RECIENTE falló después de ese
    último éxito — para no aparentar más frescura de la que hay).
    """

    if not summary or not summary.get("last_attempt_at"):
        return "Nunca verificado por el job nocturno — usa el interruptor para verificar en vivo ahora."

    if not summary.get("last_successful_check_at"):
        codigo = summary.get("last_attempt_status_code") or "desconocido"
        return (
            f"El job nocturno lo intentó el {summary.get('last_attempt_at')} pero falló ({codigo}); "
            "nunca se completó una verificación correcta — usa el interruptor para verificar en vivo."
        )

    discrepancias = int(summary.get("discrepancy_count") or 0)
    periodo_no_alineado = int(summary.get("period_misaligned_count") or 0)
    if discrepancias == 0 and periodo_no_alineado == 0:
        detalle = "sin discrepancias"
    else:
        partes = []
        if discrepancias:
            partes.append(f"{discrepancias} discrepancia(s)")
        if periodo_no_alineado:
            partes.append(f"{periodo_no_alineado} con periodo no alineado")
        detalle = " y ".join(partes)

    aviso_fallo = ""
    if summary.get("last_attempt_status_code"):
        aviso_fallo = (
            f" (aviso: el intento más reciente, {summary.get('last_attempt_at')}, falló — "
            "esto es lo último que se pudo verificar con éxito)"
        )

    return (
        f"Última validación nocturna: {summary.get('last_successful_check_at')}, {detalle}{aviso_fallo} "
        "— pulsa el interruptor para re-verificar en vivo."
    )

# ==========================================================================
# AVISOS Y LISTAS DEL SISTEMA
# ==========================================================================

_TONOS_AVISO = {
    "neutro": ("#93a4bb", "rgba(147,164,187,.10)", "rgba(147,164,187,.28)", "info-circle"),
    "favorable": ("#10e39a", "rgba(16,227,154,.10)", "rgba(16,227,154,.30)", "check-circle"),
    "aviso": ("#fbbf24", "rgba(251,191,36,.10)", "rgba(251,191,36,.30)", "exclamation-triangle"),
    "riesgo": ("#fb5e6d", "rgba(251,94,109,.10)", "rgba(251,94,109,.30)", "shield-exclamation"),
    "accion": ("#3b82f6", "rgba(59,130,246,.10)", "rgba(59,130,246,.32)", "compass"),
}


def render_aviso(texto: str, tono: str = "neutro", titulo: str | None = None) -> None:
    """Aviso con la identidad del sistema.

    Sustituye a ``st.info``/``st.success``/``st.warning``/``st.error``, que
    traen su propio azul, verde, ámbar y rojo del tema por defecto de Streamlit
    y conviven mal con la paleta del terminal: el mismo concepto acababa
    pintado de dos colores distintos según quién lo dibujara.
    """
    color, fondo, borde, icono = _TONOS_AVISO.get(tono, _TONOS_AVISO["neutro"])
    cabecera = (
        f"<div style='font-weight:700; color:{color}; margin-bottom:2px;'>"
        f"{html.escape(str(titulo))}</div>"
        if titulo else ""
    )
    escribir_html(
        f"""
        <div style="display:flex; gap:10px; align-items:flex-start;
                    background:{fondo}; border:1px solid {borde};
                    border-left:3px solid {color}; border-radius:10px;
                    padding:12px 14px; margin:8px 0;">
            <i class="bi bi-{icono}" style="color:{color}; font-size:15px; line-height:1.5;"></i>
            <div style="font-size:.9rem; line-height:1.55; color:#c3cede;">
                {cabecera}{html.escape(str(texto))}
            </div>
        </div>
        """
    )


def render_lista_puntos(puntos, tono: str = "neutro") -> None:
    """Lista de conclusiones con jerarquía visual.

    El contenido de la tesis se volcaba con ``st.write("- " + texto)``: una
    lista plana de markdown, sin jerarquía ni ritmo, que a partir de cuatro
    puntos se lee como un muro. Aquí cada punto es una fila con su marca.
    """
    puntos = [str(p) for p in (puntos or []) if str(p).strip()]
    if not puntos:
        return

    color = _TONOS_AVISO.get(tono, _TONOS_AVISO["neutro"])[0]
    filas = "".join(
        f"<li style='display:flex; gap:10px; align-items:flex-start; padding:7px 0;"
        f" border-bottom:1px solid rgba(147,164,187,.10);'>"
        f"<span style='color:{color}; font-size:15px; line-height:1.4;'>&#8226;</span>"
        f"<span style='font-size:.9rem; line-height:1.55; color:#c3cede;'>{html.escape(p)}</span>"
        f"</li>"
        for p in puntos
    )
    escribir_html(f"<ul style='list-style:none; padding:0; margin:4px 0 0;'>{filas}</ul>")


def render_titulo_seccion(texto: str, icono: str = "dot", nivel: str = "h4") -> None:
    """Título de sección con azulejo de icono en vez de emoji."""
    escribir_html(
        f"""
        <div style="display:flex; align-items:center; gap:12px; margin:18px 0 10px;">
            <span class="vq-azulejo"><i class="bi bi-{html.escape(icono)}"></i></span>
            <{nivel} style="margin:0; font-size:1.02rem; font-weight:700;">{html.escape(str(texto))}</{nivel}>
        </div>
        """
    )
