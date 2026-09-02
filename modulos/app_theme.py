from __future__ import annotations

import streamlit as st


def inject_terminal_theme() -> None:
    """Sistema visual único para ValueQuant Terminal: dark institutional, sobrio y escalable."""
    st.markdown(
        """
        <style>
            @import url('https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css');
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

            /* ---------------------------------------------------------------
               SISTEMA DE DISEÑO ValueQuant — capa de tokens.
               Los nombres de token (--vq-*) se mantienen a propósito: unos 40
               módulos y todas las clases .vq-* ya los consumen, así que la
               identidad visual se cambia aquí, en un único punto, sin tocar el
               resto del terminal. Los valores son los del sistema definitivo
               (mismos hex que modulos/config.py, que alimenta los gráficos).
               --------------------------------------------------------------- */
            :root {
                --vq-bg: #070a0f;
                --vq-bg-soft: #0d1117;
                --vq-panel: #121926;
                --vq-panel-elevated: #18202f;
                --vq-panel-muted: #0d1117;
                --vq-sidebar: #0d1117;

                --vq-border: rgba(147, 164, 187, .35);
                --vq-border-soft: rgba(147, 164, 187, .20);

                --vq-text: #e8edf5;
                --vq-text-soft: #c3cede;
                --vq-muted: #93a4bb;

                --vq-primary: #4f8cff;
                --vq-primary-hover: #6fa3ff;
                --vq-primary-soft: rgba(79, 140, 255, .14);
                --vq-cyan: #37c6e6;

                --vq-green: #3ddc97;
                --vq-red: #f36c6c;
                --vq-amber: #f5b04c;

                --vq-radius-sm: 8px;
                --vq-radius-md: 10px;
                --vq-radius-lg: 12px;

                /* El sistema pide bordes sutiles, no sombras duras: las sombras
                   quedan neutralizadas en vez de eliminadas para no romper las
                   ~30 reglas que ya referencian estas dos variables. */
                --vq-shadow-soft: none;
                --vq-shadow-card: none;
            }

            html, body, .stApp, [class*="css"] {
                font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
                letter-spacing: 0 !important;
            }

            .stApp {
                background:
                    radial-gradient(circle at 12% 0%, rgba(79, 140, 255, .08), transparent 34rem),
                    radial-gradient(circle at 88% 10%, rgba(55, 198, 230, .05), transparent 30rem),
                    var(--vq-bg) !important;
                color: var(--vq-text) !important;
            }

            #MainMenu,
            header,
            footer,
            [data-testid="stToolbar"],
            [data-testid="stDecoration"],
            [data-testid="stStatusWidget"] {
                visibility: hidden !important;
                height: 0 !important;
            }

            [data-testid="stSidebar"],
            [data-testid="collapsedControl"] {
                display: none !important;
                visibility: hidden !important;
                width: 0 !important;
            }

            .block-container {
                padding-top: 5.4rem !important;
                padding-left: clamp(1rem, 2vw, 2.4rem) !important;
                padding-right: clamp(1rem, 2vw, 2.4rem) !important;
                padding-bottom: 2rem !important;
                max-width: 1560px !important;
            }

            h1, h2, h3, h4 {
                color: var(--vq-text) !important;
                font-weight: 750 !important;
                letter-spacing: -0.03em !important;
                background: none !important;
                -webkit-background-clip: initial !important;
                -webkit-text-fill-color: initial !important;
            }

            p, span, label, div {
                letter-spacing: 0 !important;
            }

            /* ============================= */
            /* TICKER TAPE */
            /* ============================= */

            .vq-ticker-fixed {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                z-index: 99999;
                height: 32px;
                display: flex;
                align-items: center;
                overflow: hidden;
                background: var(--vq-bg);
                border-bottom: 1px solid rgba(148, 163, 184, .16);
            }

            .vq-ticker-track {
                width: 100%;
                overflow: hidden;
                white-space: nowrap;
            }

            .vq-ticker-content {
                display: inline-flex;
                align-items: center;
                min-width: max-content;
                animation: vq-ticker-scroll 48s linear infinite;
            }

            .vq-ticker-track:hover .vq-ticker-content {
                animation-play-state: paused;
            }

            .vq-tape-item {
                display: inline-flex;
                align-items: center;
                gap: .42rem;
                padding: 0 1.25rem;
                color: var(--vq-text-soft);
                font-size: .78rem;
                font-weight: 600;
                border-right: 1px solid rgba(255, 255, 255, .06);
            }

            .vq-tape-item strong {
                color: #FFFFFF;
                font-weight: 800;
            }

            .is-up { color: var(--vq-green) !important; }
            .is-down { color: var(--vq-red) !important; }
            .is-flat { color: var(--vq-muted) !important; }

            @keyframes vq-ticker-scroll {
                0% { transform: translate3d(0, 0, 0); }
                100% { transform: translate3d(-50%, 0, 0); }
            }

            /* ============================= */
            /* NAVBAR */
            /* ============================= */

            .vq-nav-shell {
                position: fixed;
                top: 32px;
                left: 0;
                right: 0;
                z-index: 99998;
                padding: .58rem clamp(1rem, 2vw, 2.4rem) .62rem;
                background: rgba(8, 11, 16, .92);
                border-bottom: 1px solid var(--vq-border-soft);
                backdrop-filter: blur(18px);
                -webkit-backdrop-filter: blur(18px);
            }

            .vq-brand-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 1rem;
                margin-bottom: .45rem;
            }

            .vq-brand {
                display: flex;
                align-items: center;
                gap: .7rem;
                color: #FFFFFF;
                font-size: .98rem;
                font-weight: 800;
            }

            .vq-brand img {
                width: 30px;
                height: 30px;
                object-fit: contain;
                border-radius: 8px;
            }

            .vq-session-pill {
                display: inline-flex;
                align-items: center;
                gap: .45rem;
                padding: .34rem .72rem;
                border-radius: 999px;
                color: var(--vq-text-soft);
                background: rgba(16, 23, 34, .86);
                border: 1px solid var(--vq-border-soft);
                font-size: .76rem;
                font-weight: 650;
            }

            .nav-link {
                border-radius: 8px !important;
                border: 1px solid transparent !important;
                margin: 0 .12rem !important;
                color: var(--vq-muted) !important;
                transition: background .16s ease, color .16s ease, border-color .16s ease !important;
            }

            .nav-link:hover {
                background: rgba(148, 163, 184, .08) !important;
                color: var(--vq-text) !important;
            }

            .nav-link.active {
                background: var(--vq-primary-soft) !important;
                color: #FFFFFF !important;
                border-color: rgba(59, 130, 246, .34) !important;
                box-shadow: none !important;
            }

            /* ============================= */
            /* CONTROL PANEL */
            /* ============================= */

            .vq-control-panel {
                margin: 1rem 0 1.25rem;
                padding: 1rem;
                border-radius: var(--vq-radius-md);
                background: rgba(16, 23, 34, .86);
                border: 1px solid var(--vq-border-soft);
                box-shadow: var(--vq-shadow-card);
            }

            .vq-tool-caption {
                margin-top: .55rem;
                color: var(--vq-muted);
                font-size: .88rem;
                line-height: 1.5;
            }

            .vq-context-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                gap: 1rem;
                margin: 1.1rem 0 1rem;
                padding: 1rem 1.1rem;
                border-radius: var(--vq-radius-md);
                border: 1px solid var(--vq-border-soft);
                background:
                    linear-gradient(180deg, rgba(20, 29, 43, .96), rgba(13, 21, 32, .96));
                box-shadow: var(--vq-shadow-card);
            }

            .vq-context-eyebrow {
                color: var(--vq-muted);
                font-size: .72rem;
                font-weight: 800;
                text-transform: uppercase;
                margin-bottom: .35rem;
            }

            .vq-context-title {
                color: var(--vq-text);
                font-size: clamp(1.35rem, 2vw, 2rem);
                font-weight: 800;
                letter-spacing: -0.04em;
                margin: 0;
            }

            .vq-context-subtitle {
                margin-top: .35rem;
                color: var(--vq-muted);
                font-size: .9rem;
            }

            .vq-context-badges {
                display: flex;
                gap: .45rem;
                flex-wrap: wrap;
                justify-content: flex-end;
            }

            .vq-badge {
                display: inline-flex;
                align-items: center;
                gap: .35rem;
                padding: .34rem .62rem;
                border-radius: 999px;
                font-size: .74rem;
                font-weight: 750;
                border: 1px solid var(--vq-border-soft);
                background: rgba(15, 23, 42, .85);
                color: var(--vq-text-soft);
                white-space: nowrap;
            }

            .vq-badge-primary {
                border-color: rgba(59, 130, 246, .35);
                background: rgba(59, 130, 246, .12);
                color: var(--vq-primary);
            }

            .vq-badge-success {
                border-color: rgba(34, 197, 94, .32);
                background: rgba(34, 197, 94, .10);
                color: var(--vq-green);
            }

            .vq-badge-warning {
                border-color: rgba(245, 158, 11, .32);
                background: rgba(245, 158, 11, .10);
                color: var(--vq-amber);
            }

            /* ============================= */
            /* HOME */
            /* ============================= */

            .vq-home-hero {
                position: relative;
                min-height: 420px;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
                border: 1px solid var(--vq-border-soft);
                border-radius: var(--vq-radius-lg);
                background-image:
                    linear-gradient(180deg, rgba(5, 8, 13, .55), rgba(5, 8, 13, .96)),
                    var(--home-bg);
                background-size: cover;
                background-position: center;
                box-shadow: var(--vq-shadow-soft);
            }

            .vq-home-hero::before {
                content: "";
                position: absolute;
                inset: 0;
                background:
                    radial-gradient(circle at 50% 20%, rgba(59, 130, 246, .20), transparent 34rem),
                    linear-gradient(90deg, rgba(8, 11, 16, .78), rgba(8, 11, 16, .20), rgba(8, 11, 16, .78));
            }

            .vq-home-content {
                position: relative;
                z-index: 1;
                width: min(980px, calc(100% - 2rem));
                text-align: center;
                padding: 3rem 1.5rem;
            }

            .vq-home-logo {
                width: min(150px, 36vw);
                height: auto;
                margin-bottom: 1.3rem;
                filter: drop-shadow(0 16px 34px rgba(0, 0, 0, .55));
            }

            .vq-home-kicker {
                display: inline-flex;
                align-items: center;
                gap: .45rem;
                margin-bottom: .9rem;
                padding: .35rem .75rem;
                border-radius: 999px;
                background: rgba(59, 130, 246, .14);
                border: 1px solid rgba(59, 130, 246, .32);
                color: var(--vq-primary);
                font-size: .75rem;
                font-weight: 800;
                text-transform: uppercase;
            }

            .vq-home-title {
                margin: 0;
                font-size: clamp(2.25rem, 5vw, 5rem);
                line-height: .95;
                font-weight: 850;
                letter-spacing: -0.07em;
                color: #FFFFFF;
            }

            .vq-home-subtitle {
                margin: 1.1rem auto 0;
                max-width: 760px;
                color: var(--vq-text-soft);
                font-size: clamp(1rem, 1.35vw, 1.14rem);
                line-height: 1.65;
            }

            .vq-research-hero {
                position: relative;
                border-radius: var(--vq-radius-lg);
                padding: 1px;
                margin: 1.4rem 0 1.7rem;
                background: linear-gradient(120deg, rgba(59, 130, 246, .65), rgba(34, 211, 238, .45) 45%, rgba(59, 130, 246, .12));
                box-shadow: var(--vq-shadow-soft);
            }

            .vq-research-hero-inner {
                border-radius: calc(var(--vq-radius-lg) - 1px);
                background: linear-gradient(160deg, rgba(20, 29, 43, .98), rgba(11, 17, 26, .98));
                padding: 1.7rem 2rem;
            }

            .vq-section-title {
                display: flex;
                align-items: center;
                gap: .55rem;
                margin: 1.7rem 0 .65rem;
                color: #FFFFFF;
                font-size: 1.16rem;
                font-weight: 800;
                letter-spacing: -0.02em;
            }

            .vq-section-title i {
                color: var(--vq-primary);
            }

            .vq-market-grid,
            .vq-news-grid,
            .vq-module-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 1rem;
                margin-top: 1rem;
            }

            .vq-market-card,
            .vq-news-card,
            .vq-module-card,
            .vq-empty-state {
                background: rgba(16, 23, 34, .86);
                border: 1px solid var(--vq-border-soft);
                border-radius: var(--vq-radius-md);
                box-shadow: var(--vq-shadow-card);
            }

            .vq-market-card {
                padding: 1rem;
                transition: transform .16s ease, border-color .16s ease, background .16s ease;
            }

            .vq-market-card:hover,
            .vq-module-card:hover,
            .vq-news-card:hover {
                transform: translateY(-2px);
                border-color: rgba(59, 130, 246, .35);
                background: rgba(20, 29, 43, .94);
            }

            .vq-market-label,
            .vq-news-date,
            .vq-module-eyebrow {
                color: var(--vq-muted);
                font-size: .74rem;
                font-weight: 800;
                text-transform: uppercase;
            }

            .vq-market-value {
                margin-top: .35rem;
                color: #FFFFFF;
                font-size: 1.36rem;
                font-weight: 820;
                letter-spacing: -0.04em;
            }

            .vq-module-card {
                padding: 1rem;
                min-height: 150px;
                transition: transform .16s ease, border-color .16s ease, background .16s ease;
            }

            .vq-module-icon {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 34px;
                height: 34px;
                border-radius: 10px;
                margin-bottom: .75rem;
                color: var(--vq-primary);
                background: rgba(59, 130, 246, .14);
                border: 1px solid rgba(59, 130, 246, .28);
            }

            .vq-module-title {
                color: #FFFFFF;
                font-size: .98rem;
                font-weight: 800;
                margin-bottom: .45rem;
            }

            .vq-module-desc {
                color: var(--vq-muted);
                font-size: .86rem;
                line-height: 1.5;
            }

            .vq-news-card {
                display: block;
                overflow: hidden;
                text-decoration: none !important;
                transition: transform .16s ease, border-color .16s ease, background .16s ease;
            }

            .vq-news-card img {
                width: 100%;
                height: 128px;
                object-fit: cover;
                background: var(--vq-panel);
                filter: saturate(.9) contrast(1.04);
                border-radius: 6px 6px 0 0;
            }

            .vq-news-body {
                padding: .95rem;
            }

            .vq-news-title {
                margin: .35rem 0 0;
                color: var(--vq-text);
                font-size: .94rem;
                line-height: 1.38;
                font-weight: 750;
            }

            /* ============================= */
            /* STREAMLIT COMPONENTS */
            /* ============================= */

            div[data-testid="stMetric"],
            div[data-testid="metric-container"] {
                background: rgba(16, 23, 34, .86) !important;
                border: 1px solid var(--vq-border-soft) !important;
                border-radius: var(--vq-radius-md) !important;
                padding: 1rem !important;
                box-shadow: var(--vq-shadow-card) !important;
            }

            [data-testid="stMetricLabel"] {
                color: var(--vq-muted) !important;
                font-size: .82rem !important;
                font-weight: 650 !important;
            }

            [data-testid="stMetricValue"] {
                color: var(--vq-text) !important;
                font-size: 1.45rem !important;
                font-weight: 800 !important;
                letter-spacing: -0.04em !important;
            }

            .stButton > button {
                border-radius: var(--vq-radius-sm) !important;
                background: var(--vq-panel-elevated) !important;
                color: var(--vq-text) !important;
                border: 1px solid rgba(148, 163, 184, .20) !important;
                box-shadow: none !important;
                font-weight: 750 !important;
                letter-spacing: 0 !important;
                transition: transform .14s ease, background .14s ease, border-color .14s ease !important;
            }

            .stButton > button:hover {
                transform: translateY(-1px) !important;
                background: var(--vq-panel-elevated) !important;
                border-color: rgba(59, 130, 246, .45) !important;
            }

            .stButton > button[kind="primary"] {
                background: var(--vq-primary) !important;
                border-color: var(--vq-primary) !important;
                color: #FFFFFF !important;
            }

            .stTextInput input,
            .stNumberInput input,
            .stSelectbox [data-baseweb="select"] {
                background: var(--vq-bg-soft) !important;
                border: 1px solid var(--vq-border-soft) !important;
                border-radius: var(--vq-radius-sm) !important;
                color: var(--vq-text) !important;
                box-shadow: none !important;
            }

            .stTextInput input {
                text-align: left !important;
                letter-spacing: 0 !important;
                font-size: .95rem !important;
            }

            .stTextInput input:focus,
            .stNumberInput input:focus {
                border-color: rgba(59, 130, 246, .65) !important;
                box-shadow: 0 0 0 1px rgba(59, 130, 246, .28) !important;
            }

            .stAlert {
                border-radius: var(--vq-radius-md) !important;
                border: 1px solid var(--vq-border-soft) !important;
                background: rgba(16, 23, 34, .92) !important;
            }

            div[data-testid="stDataFrame"] > div {
                border: 1px solid var(--vq-border-soft) !important;
                border-radius: var(--vq-radius-md) !important;
                background: rgba(16, 23, 34, .86) !important;
                box-shadow: var(--vq-shadow-card) !important;
            }

            div[data-baseweb="tab-list"] {
                gap: 6px !important;
                border-bottom: 1px solid var(--vq-border-soft) !important;
            }

            div[data-baseweb="tab"] {
                background: transparent !important;
                border: 0 !important;
                color: var(--vq-muted) !important;
                border-radius: 0 !important;
            }

            div[data-baseweb="tab"][aria-selected="true"] {
                color: var(--vq-text) !important;
                border-bottom: 2px solid var(--vq-primary) !important;
            }

            ::-webkit-scrollbar {
                width: 9px;
                height: 9px;
            }

            ::-webkit-scrollbar-track {
                background: var(--vq-bg);
            }

            ::-webkit-scrollbar-thumb {
                background: var(--vq-border);
                border-radius: 999px;
                border: 2px solid var(--vq-bg);
            }

            ::-webkit-scrollbar-thumb:hover {
                background: var(--vq-border);
            }

            @media (max-width: 900px) {
                .block-container {
                    padding-top: 6.2rem !important;
                    padding-left: 1rem !important;
                    padding-right: 1rem !important;
                }

                .vq-brand-row {
                    align-items: flex-start;
                    flex-direction: column;
                    gap: .45rem;
                }

                .vq-market-grid,
                .vq-news-grid,
                .vq-module-grid {
                    grid-template-columns: 1fr;
                }

                .vq-context-header {
                    flex-direction: column;
                }

                .vq-context-badges {
                    justify-content: flex-start;
                }

                .vq-home-hero {
                    min-height: 380px;
                }

                .vq-research-hero-inner {
                    padding: 1.3rem 1.4rem;
                }

                .vq-tape-item {
                    padding: 0 1rem;
                }
            }

            /* ===============================================================
               COMPONENTES NATIVOS DE STREAMLIT
               El sistema de diseño se aplicaba hasta ahora sobre todo a las
               clases propias .vq-*, dejando los widgets nativos con el tema por
               defecto de Streamlit: por eso convivían dos estéticas en la misma
               pantalla (una card .vq- junto a un st.dataframe azul claro).
               Este bloque los alinea con el mismo sistema.
               =============================================================== */

            /* 1. SIDEBAR ------------------------------------------------- */
            section[data-testid="stSidebar"] > div,
            section[data-testid="stSidebar"] {
                background: var(--vq-sidebar) !important;
                border-right: 1px solid var(--vq-border-soft) !important;
            }
            section[data-testid="stSidebar"] hr {
                border-color: var(--vq-border-soft) !important;
                opacity: 1 !important;
            }
            section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
            section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
            section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
                color: var(--vq-text) !important;
                letter-spacing: .01em;
            }

            /* 2. MÉTRICAS ------------------------------------------------ */
            /* Valor siempre en blanco; el color lo lleva el delta, que es quien
               comunica dirección. Streamlit ya marca el signo en el atributo
               data-testid, así que no hace falta tocar Python para colorear. */
            [data-testid="stMetric"] {
                background: var(--vq-panel) !important;
                border: 1px solid var(--vq-border) !important;
                border-radius: var(--vq-radius-md) !important;
                padding: .85rem 1rem !important;
            }
            [data-testid="stMetricValue"] {
                color: #FFFFFF !important;
                font-weight: 700 !important;
                letter-spacing: -.01em;
            }
            [data-testid="stMetricLabel"],
            [data-testid="stMetricLabel"] p {
                color: var(--vq-muted) !important;
                font-size: .78rem !important;
                text-transform: uppercase;
                letter-spacing: .08em;
            }
            [data-testid="stMetricDelta"] svg { display: none; }
            [data-testid="stMetricDelta"] {
                font-weight: 600 !important;
                font-size: .85rem !important;
            }
            /* Streamlit expone la dirección del delta por el color inline del
               SVG; estos selectores cubren las dos variantes de su DOM. */
            [data-testid="stMetricDelta"][class*="positive"],
            [data-testid="stMetricDelta"] > div:has(svg[fill="#09ab3b"]),
            div[data-testid="stMetricDelta"] > div[style*="rgb(9, 171, 59)"] {
                color: var(--vq-green) !important;
            }
            [data-testid="stMetricDelta"][class*="negative"],
            [data-testid="stMetricDelta"] > div:has(svg[fill="#ff2b2b"]),
            div[data-testid="stMetricDelta"] > div[style*="rgb(255, 43, 43)"] {
                color: var(--vq-red) !important;
            }

            /* 3. TABLAS -------------------------------------------------- */
            [data-testid="stDataFrame"],
            [data-testid="stTable"] {
                background: var(--vq-panel) !important;
                border: 1px solid var(--vq-border) !important;
                border-radius: var(--vq-radius-md) !important;
                overflow: hidden;
            }
            [data-testid="stDataFrame"] [role="columnheader"],
            [data-testid="stTable"] thead th {
                background: var(--vq-panel-elevated) !important;
                color: var(--vq-primary) !important;
                font-weight: 700 !important;
                text-transform: uppercase;
                letter-spacing: .06em;
                font-size: .74rem !important;
                border-bottom: 1px solid var(--vq-border) !important;
            }
            [data-testid="stDataFrame"] [role="gridcell"],
            [data-testid="stTable"] tbody td {
                background: var(--vq-panel) !important;
                color: var(--vq-text) !important;
                border-color: var(--vq-border-soft) !important;
            }
            [data-testid="stTable"] tbody tr:hover td,
            [data-testid="stDataFrame"] [role="row"]:hover [role="gridcell"] {
                background: var(--vq-panel-elevated) !important;
            }

            /* 4. EXPANDERS ----------------------------------------------- */
            [data-testid="stExpander"],
            details[data-testid="stExpander"] {
                background: var(--vq-panel) !important;
                border: 1px solid var(--vq-border) !important;
                border-radius: var(--vq-radius-md) !important;
                box-shadow: none !important;
            }
            [data-testid="stExpander"] summary,
            [data-testid="stExpander"] details > summary {
                color: var(--vq-text) !important;
                font-weight: 600 !important;
            }
            [data-testid="stExpander"] summary:hover {
                color: var(--vq-primary) !important;
            }

            /* 5. BOTONES ------------------------------------------------- */
            .stButton > button[kind="primary"],
            .stDownloadButton > button[kind="primary"],
            [data-testid="baseButton-primary"] {
                background: var(--vq-primary) !important;
                border: 1px solid var(--vq-primary) !important;
                color: #070a0f !important;
                font-weight: 700 !important;
                border-radius: var(--vq-radius-sm) !important;
                box-shadow: none !important;
                transition: background .15s ease, border-color .15s ease;
            }
            .stButton > button[kind="primary"]:hover,
            .stDownloadButton > button[kind="primary"]:hover,
            [data-testid="baseButton-primary"]:hover {
                background: var(--vq-primary-hover) !important;
                border-color: var(--vq-primary-hover) !important;
                color: #070a0f !important;
            }
            .stButton > button[kind="secondary"],
            [data-testid="baseButton-secondary"] {
                background: transparent !important;
                border: 1px solid var(--vq-border) !important;
                color: var(--vq-text-soft) !important;
                border-radius: var(--vq-radius-sm) !important;
                box-shadow: none !important;
            }
            .stButton > button[kind="secondary"]:hover,
            [data-testid="baseButton-secondary"]:hover {
                border-color: var(--vq-primary) !important;
                color: var(--vq-primary) !important;
            }

            /* 6. CONTENEDORES Y CONTROLES -------------------------------- */
            [data-testid="stVerticalBlockBorderWrapper"] {
                background: var(--vq-panel);
                border: 1px solid var(--vq-border);
                border-radius: var(--vq-radius-md);
            }
            [data-testid="stTabs"] [role="tab"] {
                color: var(--vq-muted) !important;
                font-weight: 600;
            }
            [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
                color: var(--vq-primary) !important;
                border-bottom-color: var(--vq-primary) !important;
            }
            .stTextInput input,
            .stNumberInput input,
            .stTextArea textarea,
            .stSelectbox [data-baseweb="select"] > div,
            .stMultiSelect [data-baseweb="select"] > div {
                background: var(--vq-bg-soft) !important;
                border-color: var(--vq-border) !important;
                color: var(--vq-text) !important;
                border-radius: var(--vq-radius-sm) !important;
            }
            .stTextInput input:focus,
            .stNumberInput input:focus,
            .stTextArea textarea:focus {
                border-color: var(--vq-primary) !important;
                box-shadow: 0 0 0 1px var(--vq-primary) !important;
            }
            /* Alertas nativas: mismo lenguaje de card con filo de color. */
            [data-testid="stAlert"] {
                background: var(--vq-panel) !important;
                border: 1px solid var(--vq-border) !important;
                border-radius: var(--vq-radius-md) !important;
                color: var(--vq-text) !important;
            }
        </style>
        
        """,
        unsafe_allow_html=True,
    )
