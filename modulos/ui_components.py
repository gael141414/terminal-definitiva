import html
import streamlit as st

from modulos.tool_catalog import obtener_herramientas_por_grupo_consolidado
from modulos.tool_consolidation import CONSOLIDATION_GROUPS, get_navigation_groups_ordered


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

    st.markdown(
        f"""
        <div style="background:rgba(18,25,38,0.92); border:1px solid rgba(147,164,187,0.1); border-radius:12px;
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
        """,
        unsafe_allow_html=True,
    )


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

    st.markdown(
        f"""
        <div style="background:{style['card_bg']}; border:{style['border']}; box-shadow:{style['left_edge']};
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
        """,
        unsafe_allow_html=True,
    )