from __future__ import annotations

import html
from datetime import datetime, time, timedelta, timezone

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from modulos.app_assets import asset_to_data_uri, strip_visual_prefix
from modulos.app_navigation import TOOL_UI_ICONS
from modulos.tool_catalog import TOOL_CATALOG
from modulos.market_widgets import (
    analizar_rotacion_sectores,
    obtener_market_snapshot,
    obtener_market_treemap_data,
    obtener_ultimas_noticias,
)


def render_module_showcase(limit: int = 9) -> None:
    """Muestra módulos principales en la home como tarjetas de producto."""
    destacados = TOOL_CATALOG[:limit]

    cards = ""
    for tool in destacados:
        label_original = tool["label"]
        label = strip_visual_prefix(label_original)
        icon = TOOL_UI_ICONS.get(label_original, "grid")
        bloque = strip_visual_prefix(tool["bloque"])
        desc = tool["descripcion"]
        input_mode = tool["input_mode"]

        if input_mode == "company":
            mode_label = "Empresa"
        elif input_mode == "standalone":
            mode_label = "Autónomo"
        elif input_mode == "etf":
            mode_label = "ETF / Fondo"
        else:
            mode_label = "Módulo"

        # HTML Compactado sin saltos de línea para evitar el Bug de Streamlit
        cards += f"<article class='vq-module-card'><div class='vq-module-icon'><i class='bi bi-{html.escape(icon)}'></i></div><div class='vq-module-eyebrow'>{html.escape(bloque)} · {html.escape(mode_label)}</div><div class='vq-module-title'>{html.escape(label)}</div><div class='vq-module-desc'>{html.escape(desc)}</div></article>"

    st.markdown(
        "<div class='vq-section-title'><i class='bi bi-grid-1x2'></i> Módulos principales</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div class='vq-module-grid'>{cards}</div>",
        unsafe_allow_html=True,
    )



def render_market_treemap(df: pd.DataFrame) -> go.Figure:
    """Construye el mapa de calor de mercado de la Home con una figura Plotly autocontenida."""
    required_columns = {"Ticker", "Sector", "MarketCap", "Rendimiento_Diario"}
    if df is None or df.empty or not required_columns.issubset(df.columns):
        return go.Figure()

    plot_df = df[["Ticker", "Sector", "MarketCap", "Rendimiento_Diario"]].copy()
    plot_df["MarketCap"] = pd.to_numeric(plot_df["MarketCap"], errors="coerce").fillna(0)
    plot_df["Rendimiento_Diario"] = pd.to_numeric(plot_df["Rendimiento_Diario"], errors="coerce").fillna(0)
    plot_df = plot_df[plot_df["MarketCap"] > 0]

    if plot_df.empty:
        return go.Figure()

    sector_df = (
        plot_df.groupby("Sector", as_index=False)
        .agg(MarketCap=("MarketCap", "sum"), Rendimiento_Diario=("Rendimiento_Diario", "mean"))
        .sort_values("MarketCap", ascending=False)
    )

    labels = ["Mercado"] + sector_df["Sector"].astype(str).tolist() + plot_df["Ticker"].astype(str).tolist()
    parents = [""] + ["Mercado"] * len(sector_df) + plot_df["Sector"].astype(str).tolist()
    values = [float(plot_df["MarketCap"].sum())] + sector_df["MarketCap"].astype(float).tolist() + plot_df["MarketCap"].astype(float).tolist()
    colors = [0.0] + sector_df["Rendimiento_Diario"].astype(float).tolist() + plot_df["Rendimiento_Diario"].astype(float).tolist()

    fig = go.Figure(
        go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            marker=dict(
                colors=colors,
                colorscale=[
                    [0.0, "#ef5b6b"],
                    [0.5, "#202938"],
                    [1.0, "#36c486"],
                ],
                cmin=-5,
                cmax=5,
                line=dict(width=1, color="rgba(15,23,42,0.75)"),
            ),
            textinfo="label+value",
            hovertemplate="<b>%{label}</b><br>Capitalización relativa: %{value:,.0f}<br>Rendimiento: %{color:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#CBD5E1", size=12),
        margin=dict(l=0, r=0, t=0, b=0),
        height=440,
    )
    return fig

def render_home_page(logo_path, home_bg_path) -> None:
    """Pantalla inicial institucional con identidad visual, mercado, estado de bolsas y termómetro sectorial."""
    logo_uri = asset_to_data_uri(logo_path)
    bg_uri = asset_to_data_uri(home_bg_path)
    bg_style = f"url('{bg_uri}')" if bg_uri else "linear-gradient(135deg, #09111f, #05070b)"
    logo_html = f"<img class='vq-home-logo' src='{logo_uri}' alt='ValueQuant Terminal'>" if logo_uri else ""

    # Hero Principal (Ajustado al margen izquierdo estricto para evitar bugs de markdown)
    st.markdown(
f"""<section class="vq-home-hero" style="--home-bg: {bg_style};">
<div class="vq-home-content">
{logo_html}
<h1 class="vq-home-title">ValueQuant Terminal</h1>
<p class="vq-home-subtitle">Research fundamental, riesgo, timing cuantitativo y automatización de alertas en una mesa de análisis unificada.</p>
</div>
</section>""",
        unsafe_allow_html=True,
    )

    # 1. RELOJES DE MERCADO (Market Status Bar)
    ahora_utc = datetime.now(timezone.utc)
    
    # NYSE: EDT (UTC-4) en mayo. Abierto: lunes a viernes de 09:30 a 16:00 local.
    ny_time = ahora_utc - timedelta(hours=4)
    ny_open = (0 <= ny_time.weekday() <= 4) and (time(9, 30) <= ny_time.time() <= time(16, 0))
    
    # LSE: BST (UTC+1) en mayo. Abierto: lunes a viernes de 08:00 a 16:30 local.
    lon_time = ahora_utc + timedelta(hours=1)
    lon_open = (0 <= lon_time.weekday() <= 4) and (time(8, 0) <= lon_time.time() <= time(16, 30))
    
    # TSE: JST (UTC+9). Abierto: lunes a viernes de 09:00-11:30 y 12:30-15:00 local.
    tok_time = ahora_utc + timedelta(hours=9)
    tok_open = (0 <= tok_time.weekday() <= 4) and (
        (time(9, 0) <= tok_time.time() <= time(11, 30)) or 
        (time(12, 30) <= tok_time.time() <= time(15, 0))
    )
    
    status_ny = "<span style='color: #36c486;'>●</span> OPEN" if ny_open else "<span style='color: #ef5b6b;'>●</span> CLOSED"
    status_lon = "<span style='color: #36c486;'>●</span> OPEN" if lon_open else "<span style='color: #ef5b6b;'>●</span> CLOSED"
    status_tok = "<span style='color: #36c486;'>●</span> OPEN" if tok_open else "<span style='color: #ef5b6b;'>●</span> CLOSED"

    st.markdown(
f"<div style='display: flex; gap: 2rem; justify-content: center; background: #111827; padding: 0.55rem; border-radius: 10px; border: 1px solid rgba(148, 163, 184, 0.12); margin-top: -0.6rem; margin-bottom: 1.6rem; font-size: 0.82rem; font-weight: 700; color: #93a4bb;'>"
f"<div>NYSE (New York): <strong style='color:#eef4ff;'>{status_ny}</strong></div>"
f"<div>LSE (London): <strong style='color:#eef4ff;'>{status_lon}</strong></div>"
f"<div>TSE (Tokyo): <strong style='color:#eef4ff;'>{status_tok}</strong></div>"
f"</div>",
        unsafe_allow_html=True
    )

    # 2. GRID DE MERCADO (Con VIX y US 10Y integrados)
    snapshot = obtener_market_snapshot()
    if snapshot:
        cards = "".join(
f"<article class='vq-market-card'>"
f"<div class='vq-market-label'>{html.escape(item['nombre'])}</div>"
f"<div class='vq-market-value'>{html.escape(item['precio'])}</div>"
f"<div class='{item['clase']}' style='font-weight:800; margin-top:.25rem;'>{html.escape(item['cambio'])}</div>"
f"</article>"
            for item in snapshot
        )
        st.markdown("<div class='vq-section-title'><h2 style='margin:0;'><i class='bi bi-activity'></i> Resumen de mercado</h2></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='vq-market-grid'>{cards}</div>", unsafe_allow_html=True)

    st.markdown("<div class='vq-section-title'><h2 style='margin:0;'><i class='bi bi-grid-3x3-gap'></i> Mapa de calor del mercado</h2></div>", unsafe_allow_html=True)
    try:
        df_treemap = obtener_market_treemap_data()
        if df_treemap is not None and not df_treemap.empty:
            st.plotly_chart(render_market_treemap(df_treemap), use_container_width=True)
        else:
            st.info("No hay datos suficientes para construir el mapa de calor en este momento.")
    except Exception as exc:
        st.warning(f"No se pudo renderizar el mapa de calor: {exc}")

    # 3. LAYOUT DOBLE COLUMNA: NOTICIAS VS ROTACIÓN SECTORIAL
    col_noticias, col_sectores = st.columns([2.2, 1.2])

    with col_noticias:
        noticias = obtener_ultimas_noticias(6)
        st.markdown("<div class='vq-section-title'><h2 style='margin:0;'><i class='bi bi-newspaper'></i> Últimas noticias financieras</h2></div>", unsafe_allow_html=True)
        if noticias:
            news_html = ""
            for noticia in noticias:
                title = html.escape(noticia.get("title", "Noticia financiera"))
                date = html.escape(noticia.get("date", ""))[:32]
                url = html.escape(noticia.get("url", "#"))
                
                image_url = noticia.get("image")
                img_src = html.escape(image_url) if image_url and len(image_url) > 5 else logo_uri
                
                # HTML Compactado con estilos in-line (object-fit: cover) para que la imagen quede perfecta
                news_html += f"<a class='vq-news-card' href='{url}' target='_blank' rel='noopener noreferrer' style='text-decoration:none;'><img src='{img_src}' alt='News image' onerror=\"this.src='{logo_uri}'\" style='width: 100%; height: 140px; object-fit: cover; border-radius: 6px 6px 0 0; border-bottom: 1px solid rgba(148, 163, 184, 0.1);'><div class='vq-news-body'><div class='vq-news-date'>{date}</div><div class='vq-news-title'>{title}</div></div></a>"
                
            st.markdown(f"<div class='vq-news-grid'>{news_html}</div>", unsafe_allow_html=True)

    with col_sectores:
        st.markdown("<div class='vq-section-title'><h2 style='margin:0;'><i class='bi bi-pie-chart-fill'></i> Rotación Sectorial (1 Mes)</h2></div>", unsafe_allow_html=True)
        try:
            df_sectores = analizar_rotacion_sectores() # Llama a la función de tu ecosistema
            if df_sectores is not None and not df_sectores.empty:
                df_plot = df_sectores.sort_values(by="1 Mes (%)", ascending=True)
                colores = ["#36c486" if x >= 0 else "#ef5b6b" for x in df_plot["1 Mes (%)"]]
                
                fig = go.Figure(go.Bar(
                    x=df_plot["1 Mes (%)"],
                    y=df_plot["Sector"],
                    orientation='h',
                    marker_color=colores,
                    text=df_plot["1 Mes (%)"].round(2).astype(str) + "%",
                    textposition='auto',
                    hovertemplate="Sector: %{y}<br>Rendimiento: %{x:.2f}%<extra></extra>"
                ))
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter", color="#CBD5E1", size=11),
                    margin=dict(l=10, r=10, t=10, b=10),
                    showlegend=False,
                    height=440,
                )
                fig.update_xaxes(showgrid=False, zeroline=True, zerolinecolor="rgba(148, 163, 184, 0.2)")
                fig.update_yaxes(showgrid=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Datos de rotación sectorial no disponibles actualmente.")
        except Exception as e:
            st.caption(f"Panel sectorial en mantenimiento: {e}")
