from __future__ import annotations

import html
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from modulos.app_assets import asset_to_data_uri, strip_visual_prefix
from modulos.app_navigation import TOOL_UI_ICONS
from modulos.company_data_helpers import obtener_tickers_filtrados
from modulos.tool_catalog import TOOL_CATALOG
from modulos.tool_consolidation import get_navigation_groups_ordered
from modulos.ui_components import render_navigation_groups_grid
from modulos.market_widgets import (
    analizar_rotacion_sectores,
    obtener_market_snapshot,
    obtener_market_treemap_data,
    obtener_ultimas_noticias,
)
from modulos.html_markdown import escribir_html

MAX_TICKERS_RECIENTES = 3


def _resolver_ticker_buscado(query: str) -> str:
    """Resuelve texto libre (ticker o nombre) contra el catálogo real de la SEC.

    Mismo criterio de fallback que ya usa la búsqueda de ETF en app.py: si no
    hay coincidencia exacta ni por nombre, se usa el texto tal cual en
    mayúsculas -- nunca se bloquea la búsqueda por no estar en el catálogo
    filtrado (algunos tickers válidos quedan fuera de ese filtro)."""
    query_norm = query.strip().upper()
    if not query_norm:
        return query_norm

    try:
        lista_tickers = obtener_tickers_filtrados()
    except Exception:
        lista_tickers = []

    coincidencia_ticker = next(
        (item for item in lista_tickers if item.split(" - ")[0].strip().upper() == query_norm),
        None,
    )
    if coincidencia_ticker:
        return coincidencia_ticker.split(" - ")[0].strip()

    coincidencia_nombre = next(
        (item for item in lista_tickers if query_norm in item.split(" - ", 1)[-1].upper()),
        None,
    )
    if coincidencia_nombre:
        return coincidencia_nombre.split(" - ")[0].strip()

    return query_norm


def _activar_research_core(query: str) -> None:
    """Resuelve la búsqueda de la tarjeta hero y salta directo al Research Core
    ya analizado -- mismas claves de session_state que usa hoy app.py para el
    flujo de herramientas de empresa (empresa_analizada/ticker_analizado/
    competidor_analizado/años_analizados), así el chequeo existente de
    "empresa_no_analizada" ya viene satisfecho en el primer render."""
    ticker = _resolver_ticker_buscado(query)
    if not ticker:
        return

    recientes = [t for t in st.session_state.get("vq_recent_tickers", []) if t != ticker]
    st.session_state["vq_recent_tickers"] = [ticker] + recientes[: MAX_TICKERS_RECIENTES - 1]

    st.session_state["vq_research_core_activo"] = True
    st.session_state["empresa_analizada"] = True
    st.session_state["ticker_analizado"] = ticker
    st.session_state["competidor_analizado"] = ""
    st.session_state["años_analizados"] = 5
    st.rerun()


def render_research_core_hero() -> None:
    """Tarjeta hero de ancho completo (mockup docs/design/research_core_navegacion_kpi.html,
    sección 1a): Research Core como puerta de entrada dominante, con buscador
    funcional (no decorativo) de ticker o nombre de empresa. Un Analizar aquí
    salta directo al Research Core ya resuelto -- ver app.py, donde "Home" se
    convierte en el propio Research Core mientras la búsqueda esté activa, en
    vez de tratar Research Core como una pestaña más."""
    recientes = st.session_state.get("vq_recent_tickers", [])

    # Un <div> abierto en un st.markdown NO envuelve a los widgets siguientes:
    # Streamlit pinta cada elemento en su propio contenedor y el navegador
    # autocierra el <div>. La tarjeta salía vacía (ese rectángulo con borde) y
    # las columnas quedaban fuera, sin el padding que les correspondía. El
    # contenedor nativo sí contiene de verdad; el estilo se le aplica por CSS
    # a través de la marca .vq-hero-marca.
    with st.container(border=True):
        st.markdown('<span class="vq-hero-marca"></span>', unsafe_allow_html=True)
        col_izquierda, col_derecha = st.columns([1.7, 1], gap="large")

        with col_izquierda:
            st.markdown(
                """
                <div style="display:flex; align-items:center; gap:10px; margin-bottom:4px;">
                    <span style="font-size:10.5px; font-weight:700; letter-spacing:0.14em; color:var(--vq-cyan); text-transform:uppercase;">Experiencia principal</span>
                    <span style="height:1px; width:36px; background:rgba(34,211,238,0.4); display:inline-block;"></span>
                </div>
                <div style="font-size:1.7rem; font-weight:800; letter-spacing:-0.01em; color:#FFFFFF;">Research Core</div>
                <div style="font-size:.92rem; color:var(--vq-text-soft); max-width:520px; line-height:1.5; margin-top:6px;">
                    Análisis fundamental completo de una empresa: score global, valoración, calidad, riesgo y veredicto en una sola mesa de trabajo.
                </div>
                """,
                unsafe_allow_html=True,
            )
            if recientes:
                st.markdown(
                    "<div style='font-size:.72rem; color:var(--vq-muted); margin:.7rem 0 .3rem;'>Recientes:</div>",
                    unsafe_allow_html=True,
                )
                cols_pills = st.columns(len(recientes))
                for i, tk in enumerate(recientes):
                    with cols_pills[i]:
                        if st.button(tk, key=f"vq_hero_recent_{tk}", use_container_width=True):
                            _activar_research_core(tk)

        with col_derecha:
            with st.form("vq_hero_search_form", border=False):
                query = st.text_input(
                    "Ticker o nombre de empresa",
                    placeholder="Ticker o nombre de empresa…",
                    label_visibility="collapsed",
                )
                submitted = st.form_submit_button("Analizar", type="primary", use_container_width=True)
            st.caption("Enter para abrir el resumen ejecutivo")
            if submitted and query.strip():
                _activar_research_core(query)


def render_module_showcase(limit: int = 9) -> None:
    """Muestra la navegación consolidada en 6 grupos (mockup 1a: hub + rejilla de grupos).

    Sustituye el listado plano de las primeras ``limit`` herramientas del
    catálogo por la rejilla de grupos de modulos.tool_consolidation, que sí
    refleja la reorganización en Market Terminal / Discovery Engine /
    Historical Lab / Portfolio & Risk / Automatización & Watchlist +
    Utilidades & Post-MVP (oculta salvo modo «Completo»). ``limit`` se
    mantiene en la firma por compatibilidad pero ya no aplica: la rejilla
    siempre muestra los grupos completos, no un subconjunto de herramientas.
    """
    total_tools = len(TOOL_CATALOG)
    total_groups = len(get_navigation_groups_ordered())

    st.markdown(
        "<div class='vq-section-title'><i class='bi bi-grid-1x2'></i> Herramientas especializadas</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='font-size:12px; color:#5b6a80; margin:-8px 0 12px;'>"
        f"{total_tools} herramientas · {total_groups} grupos · Research Core es la puerta de entrada principal</div>",
        unsafe_allow_html=True,
    )
    render_navigation_groups_grid()



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

    # Hero Principal. El sangrado a cero ya no hace falta como truco:
    # escribir_html aplana el bloque antes de entregárselo a Markdown.
    escribir_html(f"""<section class="vq-home-hero" style="--home-bg: {bg_style};">
<div class="vq-home-content">
{logo_html}
<h1 class="vq-home-title">ValueQuant Terminal</h1>
<p class="vq-home-subtitle">Research fundamental, riesgo, timing cuantitativo y automatización de alertas en una mesa de análisis unificada.</p>
</div>
</section>""")

    # 1. RELOJES DE MERCADO (Market Status Bar)
    ahora_utc = datetime.now(timezone.utc)
    
    # NYSE: hora local de Nueva York (EST/EDT, con cambio de horario automático). Abierto: lunes a viernes de 09:30 a 16:00 local.
    ny_time = ahora_utc.astimezone(ZoneInfo("America/New_York"))
    ny_open = (0 <= ny_time.weekday() <= 4) and (time(9, 30) <= ny_time.time() <= time(16, 0))

    # LSE: hora local de Londres (GMT/BST, con cambio de horario automático). Abierto: lunes a viernes de 08:00 a 16:30 local.
    lon_time = ahora_utc.astimezone(ZoneInfo("Europe/London"))
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

    render_research_core_hero()
    render_module_showcase()

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
                source = html.escape(noticia.get("source", "") or "")

                image_url = noticia.get("image")
                img_src = html.escape(image_url) if image_url and len(image_url) > 5 else logo_uri

                source_badge = (
                    f"<div class='vq-news-source' style='font-size:0.7rem; letter-spacing:0.04em; text-transform:uppercase; opacity:0.65; margin-bottom:2px;'>{source}</div>"
                    if source else ""
                )
                # HTML Compactado con estilos in-line (object-fit: cover) para que la imagen quede perfecta
                news_html += f"<a class='vq-news-card' href='{url}' target='_blank' rel='noopener noreferrer' style='text-decoration:none;'><img src='{img_src}' alt='News image' onerror=\"this.src='{logo_uri}'\" style='width: 100%; height: 140px; object-fit: cover; border-radius: 6px 6px 0 0; border-bottom: 1px solid rgba(148, 163, 184, 0.1);'><div class='vq-news-body'>{source_badge}<div class='vq-news-date'>{date}</div><div class='vq-news-title'>{title}</div></div></a>"
                
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
