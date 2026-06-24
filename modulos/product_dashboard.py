"""Panel de arquitectura de producto para ValueQuant Terminal.

Este módulo convierte el mapa interno de herramientas en una vista operativa dentro
de la app. No ejecuta análisis financiero; ayuda a auditar producto, priorización y
estado MVP/post-MVP.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd
import streamlit as st

from modulos.tool_catalog import TOOL_CATALOG, obtener_catalogo_mvp, obtener_modos_navegacion
from modulos.tool_consolidation import CONSOLIDATION_GROUPS, get_consolidation_groups_ordered


_STATUS_LABELS = {
    "core": "Core",
    "merge": "A fusionar",
    "assistant": "Asistente / Academy",
    "utility": "Utilidad",
    "deprecated": "Deprecada",
}

_STATUS_PRIORITY = {
    "core": 1,
    "merge": 2,
    "assistant": 3,
    "utility": 4,
    "deprecated": 5,
}


def _build_tools_df() -> pd.DataFrame:
    """Construye una tabla tabular auditable a partir del catálogo."""

    rows: list[dict[str, Any]] = []
    for tool in TOOL_CATALOG:
        rows.append(
            {
                "Herramienta": tool.get("label", ""),
                "Bloque actual": tool.get("bloque", ""),
                "Grupo objetivo": tool.get("consolidation_name", "Sin asignar"),
                "Estado": _STATUS_LABELS.get(str(tool.get("consolidation_status", "merge")), str(tool.get("consolidation_status", "merge"))),
                "MVP": "Sí" if tool.get("visible_in_mvp") else "No",
                "Input": tool.get("input_mode", ""),
                "Descripción": tool.get("descripcion", ""),
                "Orden": int(tool.get("consolidation_order", 999)),
                "_grupo_key": tool.get("consolidation_group", "unassigned"),
                "_estado_raw": tool.get("consolidation_status", "merge"),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["_estado_order"] = df["_estado_raw"].map(_STATUS_PRIORITY).fillna(99).astype(int)
        df = df.sort_values(["Grupo objetivo", "_estado_order", "Orden", "Herramienta"])
    return df


def _metric_card(label: str, value: int | str, caption: str) -> None:
    st.markdown(
        f"""
        <div style="
            padding: 1rem 1.1rem;
            border-radius: 18px;
            background: rgba(18,25,38,.92);
            border: 1px solid rgba(55,198,230,.18);
            box-shadow: 0 14px 34px rgba(0,0,0,.18);
            height: 100%;
        ">
            <div style="font-size:.76rem; color:#8fa3bf; text-transform:uppercase; letter-spacing:.08em;">{label}</div>
            <div style="font-size:1.75rem; font-weight:800; color:#f8fbff; margin-top:.15rem;">{value}</div>
            <div style="font-size:.84rem; color:#9aaabd; margin-top:.2rem;">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_header(total_tools: int, mvp_tools: int, core_tools: int, merge_tools: int) -> None:
    st.markdown("## 🧭 Mapa del Producto")
    st.caption(
        "Vista interna para convertir ValueQuant Terminal en un producto: módulos core, herramientas a fusionar, MVP y post-MVP."
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _metric_card("Herramientas", total_tools, "Inventario actual")
    with col2:
        _metric_card("MVP", mvp_tools, "Candidatas a producto inicial")
    with col3:
        _metric_card("Core", core_tools, "Capacidades nucleares")
    with col4:
        _metric_card("A fusionar", merge_tools, "Reducir complejidad")


def _render_navigation_modes() -> None:
    st.markdown("### Modos de navegación")
    cols = st.columns(len(obtener_modos_navegacion()))
    for col, mode in zip(cols, obtener_modos_navegacion(), strict=False):
        with col:
            st.markdown(
                f"""
                <div style="
                    padding:.95rem;
                    border-radius:16px;
                    background:rgba(10,15,24,.72);
                    border:1px solid rgba(255,255,255,.08);
                    min-height:125px;
                ">
                    <div style="font-weight:800; color:#f8fbff;">{mode['label']}</div>
                    <div style="font-size:.78rem; color:#37c6e6; margin:.2rem 0 .45rem;">{mode['badge']}</div>
                    <div style="font-size:.86rem; color:#9aaabd; line-height:1.35;">{mode['caption']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_group_cards(df: pd.DataFrame) -> None:
    st.markdown("### Arquitectura objetivo")

    for group in get_consolidation_groups_ordered():
        group_df = df[df["_grupo_key"] == group.key].copy()
        if group_df.empty:
            continue

        status_counter = Counter(group_df["_estado_raw"])
        mvp_count = int((group_df["MVP"] == "Sí").sum())
        target = group.target_module or "Pendiente"

        with st.expander(
            f"{group.name} · {len(group_df)} herramientas · MVP {mvp_count}",
            expanded=group.priority <= 2,
        ):
            st.markdown(f"**Área:** {group.strategic_area}")
            st.markdown(f"**Objetivo:** {group.description}")
            st.markdown(f"**Módulo objetivo:** `{target}`")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Core", status_counter.get("core", 0))
            c2.metric("A fusionar", status_counter.get("merge", 0))
            c3.metric("Asistente", status_counter.get("assistant", 0))
            c4.metric("Utilidad", status_counter.get("utility", 0))

            display_df = group_df[["Herramienta", "Estado", "MVP", "Input", "Descripción"]].reset_index(drop=True)
            st.dataframe(display_df, use_container_width=True, hide_index=True)


def _render_priority_tables(df: pd.DataFrame) -> None:
    st.markdown("### Priorización")

    tab_mvp, tab_merge, tab_post = st.tabs(["MVP", "A fusionar", "Post-MVP"])

    with tab_mvp:
        mvp_df = df[df["MVP"] == "Sí"][["Herramienta", "Grupo objetivo", "Estado", "Input"]].reset_index(drop=True)
        st.dataframe(mvp_df, use_container_width=True, hide_index=True)

    with tab_merge:
        merge_df = df[df["_estado_raw"] == "merge"][["Herramienta", "Grupo objetivo", "MVP", "Descripción"]].reset_index(drop=True)
        st.dataframe(merge_df, use_container_width=True, hide_index=True)

    with tab_post:
        post_df = df[df["MVP"] == "No"][["Herramienta", "Grupo objetivo", "Estado", "Descripción"]].reset_index(drop=True)
        st.dataframe(post_df, use_container_width=True, hide_index=True)


def _render_recommendations(df: pd.DataFrame) -> None:
    grouped = defaultdict(list)
    for _, row in df.iterrows():
        grouped[str(row["Grupo objetivo"])].append(str(row["Herramienta"]))

    st.markdown("### Lectura ejecutiva")
    st.info(
        "La app ya tiene suficiente amplitud funcional. La prioridad no es añadir más herramientas, sino convertir grupos redundantes en flujos únicos: Research Core, Discovery Engine, Historical Lab y Portfolio & Decision Center."
    )

    st.markdown(
        """
        **Siguiente decisión de producto:** mantener la navegación completa para desarrollo, pero diseñar el MVP alrededor de cuatro flujos:

        1. **Analizar empresa** → Resumen, Fundamental, Forense, Valoración, NLP.
        2. **Encontrar oportunidades** → Screener, Small Caps, Multibaggers, Insiders.
        3. **Validar históricamente** → Backtesting y futura validación del ValueQuant Score.
        4. **Gestionar decisión** → Watchlist, cartera, Monte Carlo y alertas.
        """
    )


def render_product_dashboard() -> None:
    """Renderiza el panel interno de arquitectura de producto."""

    df = _build_tools_df()
    if df.empty:
        st.warning("No hay herramientas registradas en el catálogo.")
        return

    total_tools = len(df)
    mvp_tools = len(obtener_catalogo_mvp())
    core_tools = int((df["_estado_raw"] == "core").sum())
    merge_tools = int((df["_estado_raw"] == "merge").sum())

    _render_header(total_tools, mvp_tools, core_tools, merge_tools)
    st.divider()
    _render_navigation_modes()
    st.divider()
    _render_group_cards(df)
    st.divider()
    _render_priority_tables(df)
    st.divider()
    _render_recommendations(df)
