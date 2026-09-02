from __future__ import annotations

import streamlit as st


def inject_terminal_theme() -> None:
    """Sistema visual único para ValueQuant Terminal: dark institutional, sobrio y escalable."""
    st.markdown(
        """
        <style>
            @import url('https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css');
            /* Tres familias, tres papeles. JetBrains Mono se venía usando en
               todas las cifras del terminal SIN importarse nunca, así que cada
               número caía al monoespaciado por defecto del navegador. */
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@500;600;700;800&display=swap');

            /* ---------------------------------------------------------------
               SISTEMA DE DISEÑO ValueQuant — capa de tokens.
               Los nombres de token (--vq-*) se mantienen a propósito: unos 40
               módulos y todas las clases .vq-* ya los consumen, así que la
               identidad visual se cambia aquí, en un único punto, sin tocar el
               resto del terminal. Los valores son los del sistema definitivo
               (mismos hex que modulos/config.py, que alimenta los gráficos).
               --------------------------------------------------------------- */
            :root {
                --vq-bg: #05070d;
                --vq-bg-soft: #0d1117;
                --vq-panel: #101827;
                --vq-panel-elevated: #162032;
                --vq-panel-muted: #0d1117;
                --vq-sidebar: #0d1117;

                --vq-border: rgba(147, 164, 187, .35);
                --vq-border-soft: rgba(147, 164, 187, .20);

                --vq-text: #e8edf5;
                --vq-text-soft: #c3cede;
                --vq-muted: #93a4bb;

                --vq-primary: #3b82f6;
                --vq-primary-hover: #60a5fa;
                --vq-primary-soft: rgba(59, 130, 246, .16);
                --vq-cyan: #22d3ee;

                --vq-green: #10e39a;
                --vq-red: #fb5e6d;
                --vq-amber: #fbbf24;

                --vq-radius-sm: 8px;
                --vq-radius-md: 10px;
                --vq-radius-lg: 14px;

                /* Tipografía por papel, no por elemento. */
                --vq-font-titulo: "Space Grotesk", Inter, ui-sans-serif, system-ui, sans-serif;
                --vq-font-texto: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
                --vq-font-dato: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;

                /* Escala de espaciado de 4px: el "texto pegado al margen" venía
                   de que cada componente inventaba su propio padding. */
                --vq-esp-1: 4px;
                --vq-esp-2: 8px;
                --vq-esp-3: 12px;
                --vq-esp-4: 16px;
                --vq-esp-5: 24px;
                --vq-esp-6: 32px;

                /* Profundidad: sombra que asienta la tarjeta sobre el fondo, más
                   un halo azul tenue que es lo que da el aire "de luz" de la
                   referencia. Antes ambas estaban a none y todo se veía plano. */
                --vq-shadow-soft:
                    0 1px 2px rgba(0, 0, 0, .35),
                    0 8px 24px rgba(0, 0, 0, .28);
                --vq-shadow-card:
                    0 1px 2px rgba(0, 0, 0, .40),
                    0 12px 32px rgba(0, 0, 0, .34),
                    0 0 40px rgba(59, 130, 246, .06);
                --vq-shadow-glow: 0 0 0 1px rgba(59, 130, 246, .30), 0 8px 30px rgba(59, 130, 246, .18);
            }

            html, body, .stApp, [class*="css"] {
                font-family: var(--vq-font-texto) !important;
                letter-spacing: 0 !important;
            }

            /* El tracking depende del tamaño: los titulares grandes se leen
               separados si no se aprietan, y las microetiquetas al revés. Un
               único letter-spacing global está mal en algún tamaño siempre. */
            h1, h2, h3, .vq-panel-titulo, .vq-section-title {
                font-family: var(--vq-font-titulo) !important;
                letter-spacing: -0.022em !important;
                line-height: 1.15 !important;
            }

            h4, h5, h6 {
                font-family: var(--vq-font-titulo) !important;
                letter-spacing: -0.01em !important;
            }

            /* Toda cifra, ticker o dato en monoespaciado tabular: las columnas
               de números dejan de bailar al cambiar de dígito. */
            .vq-dato,
            [data-testid="stMetricValue"],
            .vq-market-value,
            .vq-ruta-actual {
                font-family: var(--vq-font-dato) !important;
                font-variant-numeric: tabular-nums;
                letter-spacing: -0.01em;
            }

            .stApp {
                /* Rejilla de puntos + dos focos de luz: la textura técnica de la
                   referencia, resuelta en CSS y sin coste de descarga. */
                background:
                    radial-gradient(circle at 12% 0%, rgba(59, 130, 246, .10), transparent 34rem),
                    radial-gradient(circle at 88% 10%, rgba(34, 211, 238, .07), transparent 30rem),
                    radial-gradient(rgba(147, 164, 187, .09) 1px, transparent 1px),
                    var(--vq-bg) !important;
                background-size: auto, auto, 26px 26px, auto !important;
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

            /* ===============================================================
               TARJETA: el contenedor nativo de Streamlit es la primitiva.

               Antes la tarjeta se dibujaba abriendo un <div> en un st.markdown
               y cerrándolo en otro, con los widgets en medio. Eso no envuelve
               nada: Streamlit pinta cada elemento en su propio contenedor
               hermano y el navegador autocierra el <div>. La tarjeta salía
               VACÍA y el contenido quedaba fuera, pegado al margen y sin el
               padding que le tocaba. st.container(border=True) sí contiene.

               Al estilar el contenedor nativo, toda tarjeta de la aplicación
               hereda el sistema sin repetir CSS por componente.
               =============================================================== */
            div[data-testid="stVerticalBlockBorderWrapper"] {
                background: var(--vq-panel);
                border: 1px solid var(--vq-border) !important;
                border-radius: var(--vq-radius-lg) !important;
                padding: 1.35rem 1.6rem;
                box-shadow: var(--vq-shadow-soft);
            }

            /* Hero de Research Core: la misma tarjeta con el filo iluminado. */
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.vq-hero-marca) {
                position: relative;
                overflow: hidden;
                margin: 1.4rem 0 1.7rem;
                padding: 1.7rem 2rem;
                background: linear-gradient(160deg, rgba(20, 29, 43, .98), rgba(11, 17, 26, .98));
            }

            div[data-testid="stVerticalBlockBorderWrapper"]:has(.vq-hero-marca)::before {
                content: "";
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 1px;
                background: linear-gradient(90deg, transparent, var(--vq-primary) 30%, var(--vq-cyan) 70%, transparent);
            }

            .vq-hero-marca {
                display: none;
            }

            /* --- Cabecera de la aplicación ------------------------------- */
            .vq-nav-marca { display: none; }

            div[data-testid="stVerticalBlockBorderWrapper"]:has(.vq-nav-marca),
            div[data-testid="stVerticalBlock"]:has(> div > .vq-nav-marca) {
                padding-bottom: .2rem;
            }

            /* --- Miga de pan ------------------------------------------------
               Sustituye al botón suelto "Volver a Home": dice a la vez dónde
               estás y cómo salir, que es lo que la navegación debe resolver. */
            .vq-ruta {
                display: flex;
                align-items: center;
                gap: .5rem;
                font-size: .82rem;
                padding: .45rem 0;
            }

            .vq-ruta-paso { color: var(--vq-muted); }

            .vq-ruta-sep {
                color: var(--vq-border);
                font-size: .7rem;
            }

            .vq-ruta-actual {
                color: var(--vq-text);
                font-weight: 700;
                font-family: "JetBrains Mono", ui-monospace, monospace;
            }

            /* --- Cabecera del panel de trabajo --------------------------- */
            .vq-panel-cabecera {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 1rem;
                flex-wrap: wrap;
                margin-bottom: .75rem;
            }

            .vq-panel-titulo {
                color: var(--vq-text);
                font-weight: 800;
                font-size: 1.05rem;
                letter-spacing: -0.01em;
            }

            /* --- Barras de desplazamiento internas -------------------------
               Las tiras horizontales (menú principal, menú de herramientas,
               pestañas) desbordan cuando hay muchos elementos y Streamlit les
               pinta su propia barra. Se sigue pudiendo desplazar con rueda y
               gesto; solo desaparece la barra, que no aporta nada y ensucia.
               La barra de la página se conserva intacta. */
            [data-testid="stTabs"] [data-baseweb="tab-list"],
            .vq-nav-strip,
            nav.navbar,
            iframe[title="streamlit_option_menu.option_menu"] {
                scrollbar-width: none;
                -ms-overflow-style: none;
            }

            [data-testid="stTabs"] [data-baseweb="tab-list"]::-webkit-scrollbar,
            .vq-nav-strip::-webkit-scrollbar,
            nav.navbar::-webkit-scrollbar {
                display: none;
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

                div[data-testid="stVerticalBlockBorderWrapper"] {
                    padding: 1.1rem 1.15rem;
                }

                div[data-testid="stVerticalBlockBorderWrapper"]:has(.vq-hero-marca) {
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
            /* La primitiva de tarjeta se define una sola vez, más arriba. Aquí
               había una segunda regla que la pisaba con otro radio y sin
               padding: dos definiciones del mismo componente. */
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

            /* ===============================================================
               MOVIMIENTO

               Streamlit elimina las etiquetas <script> de st.markdown, así que
               todo esto es CSS puro: es lo único fiable aquí. Nada de esto
               depende de JavaScript ni de librerías externas.

               Regla de fondo: la respuesta se da al PULSAR, no al soltar. En
               cuanto aparece latencia entre el gesto y la reacción, la
               sensación de manipulación directa se cae.
               =============================================================== */

            /* --- Pulsación: reacción inmediata al bajar el dedo ---------- */
            .stButton > button,
            .stDownloadButton > button,
            [data-testid="stFormSubmitButton"] > button,
            [data-testid="stPopover"] button {
                transition:
                    transform .1s cubic-bezier(.2, 0, .2, 1),
                    background .15s ease,
                    border-color .15s ease,
                    box-shadow .15s ease !important;
            }

            .stButton > button:active,
            .stDownloadButton > button:active,
            [data-testid="stFormSubmitButton"] > button:active {
                transform: scale(.97);
            }

            .stButton > button[kind="primary"]:hover,
            [data-testid="stFormSubmitButton"] > button:hover {
                box-shadow: var(--vq-shadow-glow) !important;
            }

            /* --- Tarjetas: elevación al pasar por encima ------------------
               Solo las que son navegables. Una tarjeta puramente informativa
               que se mueve al pasar el cursor promete una interacción que no
               existe. */
            .vq-market-card,
            .vq-news-card,
            .vq-group-card {
                transition:
                    transform .14s cubic-bezier(.2, 0, .2, 1),
                    border-color .14s ease,
                    box-shadow .14s ease;
                will-change: transform;
            }

            .vq-market-card:hover,
            .vq-news-card:hover,
            .vq-group-card:hover {
                transform: translateY(-2px);
                border-color: rgba(59, 130, 246, .45);
                box-shadow: var(--vq-shadow-card);
            }

            /* --- Entrada: la rejilla se construye, no aparece de golpe ---- */
            @keyframes vq-entrada {
                from { opacity: 0; transform: translateY(8px); }
                to   { opacity: 1; transform: none; }
            }

            div[data-testid="stVerticalBlockBorderWrapper"],
            .vq-market-grid > *,
            .vq-news-grid > * {
                animation: vq-entrada .32s cubic-bezier(.2, 0, .2, 1) both;
            }

            /* Escalonado: 40ms por tarjeta. Lo justo para leerse como cascada
               y no como espera. */
            .vq-market-grid > *:nth-child(1),  .vq-news-grid > *:nth-child(1)  { animation-delay: 0ms; }
            .vq-market-grid > *:nth-child(2),  .vq-news-grid > *:nth-child(2)  { animation-delay: 40ms; }
            .vq-market-grid > *:nth-child(3),  .vq-news-grid > *:nth-child(3)  { animation-delay: 80ms; }
            .vq-market-grid > *:nth-child(4),  .vq-news-grid > *:nth-child(4)  { animation-delay: 120ms; }
            .vq-market-grid > *:nth-child(5),  .vq-news-grid > *:nth-child(5)  { animation-delay: 160ms; }
            .vq-market-grid > *:nth-child(n+6), .vq-news-grid > *:nth-child(n+6) { animation-delay: 200ms; }

            /* --- Carga: esqueleto con barrido, en vez del spinner por defecto */
            @keyframes vq-barrido {
                from { background-position: -160% 0; }
                to   { background-position: 260% 0; }
            }

            .vq-esqueleto {
                border-radius: var(--vq-radius-sm);
                background: linear-gradient(
                    90deg,
                    var(--vq-panel) 25%,
                    var(--vq-panel-elevated) 50%,
                    var(--vq-panel) 75%);
                background-size: 220% 100%;
                animation: vq-barrido 1.4s ease-in-out infinite;
            }

            [data-testid="stSpinner"] > div {
                border-top-color: var(--vq-primary) !important;
            }

            /* --- Azulejo de icono: el nodo de la referencia --------------- */
            .vq-azulejo {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                flex: 0 0 36px;
                border-radius: 10px;
                background: linear-gradient(160deg, rgba(59, 130, 246, .18), rgba(34, 211, 238, .08));
                border: 1px solid rgba(59, 130, 246, .28);
                color: var(--vq-primary);
                font-size: 16px;
                box-shadow: inset 0 1px 0 rgba(255, 255, 255, .06);
            }

            /* --- Accesibilidad ------------------------------------------
               Reducir movimiento no es quitar la respuesta: es cambiarla por
               una que no active el sistema vestibular. Se conservan color y
               opacidad, que ayudan a entender; se eliminan desplazamientos,
               escalas y bucles. Hay gente a quien esto le provoca mareo. */
            @media (prefers-reduced-motion: reduce) {
                *,
                *::before,
                *::after {
                    animation-duration: .01ms !important;
                    animation-iteration-count: 1 !important;
                    transition-duration: .01ms !important;
                    scroll-behavior: auto !important;
                }

                .vq-market-card:hover,
                .vq-news-card:hover,
                .vq-group-card:hover,
                .stButton > button:active {
                    transform: none;
                }

                .vq-esqueleto {
                    animation: none;
                    background: var(--vq-panel-elevated);
                }
            }

        </style>
        
        """,
        unsafe_allow_html=True,
    )
