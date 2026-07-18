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


def render_kpi_card(label: str, value: str, detail: str = "", status: str = "neutral") -> None:
    """Tarjeta KPI visual para métricas ejecutivas."""
    status_class = {
        "positive": "vq-badge-success",
        "warning": "vq-badge-warning",
        "negative": "",
        "neutral": "",
    }.get(status, "")

    badge_text = {
        "positive": "Favorable",
        "warning": "Vigilancia",
        "negative": "Riesgo",
        "neutral": "Neutral",
    }.get(status, "Neutral")

    st.markdown(
        f"""
        <article class="vq-market-card">
            <div class="vq-market-label">{html.escape(str(label))}</div>
            <div class="vq-market-value">{html.escape(str(value))}</div>
            <div style="display:flex; align-items:center; justify-content:space-between; gap:.75rem; margin-top:.75rem;">
                <span style="color:var(--vq-muted); font-size:.82rem;">{html.escape(str(detail))}</span>
                <span class="vq-badge {status_class}">{html.escape(str(badge_text))}</span>
            </div>
        </article>
        """,
        unsafe_allow_html=True,
    )