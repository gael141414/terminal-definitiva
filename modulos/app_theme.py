from __future__ import annotations

import streamlit as st


def inject_terminal_theme() -> None:
    """Sistema visual único para ValueQuant Terminal: dark institutional, sobrio y escalable."""
    st.markdown(
        """
        <style>
            @import url('https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css');
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

            :root {
                --vq-bg: #080B10;
                --vq-bg-soft: #0B111A;
                --vq-panel: #101722;
                --vq-panel-elevated: #141D2B;
                --vq-panel-muted: #0E1520;
                --vq-border: #243044;
                --vq-border-soft: rgba(148, 163, 184, .16);

                --vq-text: #F4F7FB;
                --vq-text-soft: #CBD5E1;
                --vq-muted: #8C9AAF;

                --vq-primary: #3B82F6;
                --vq-primary-soft: rgba(59, 130, 246, .14);
                --vq-cyan: #22D3EE;

                --vq-green: #22C55E;
                --vq-red: #EF4444;
                --vq-amber: #F59E0B;

                --vq-radius-sm: 8px;
                --vq-radius-md: 12px;
                --vq-radius-lg: 18px;

                --vq-shadow-soft: 0 18px 45px rgba(0, 0, 0, .28);
                --vq-shadow-card: 0 10px 30px rgba(0, 0, 0, .22);
            }

            html, body, .stApp, [class*="css"] {
                font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
                letter-spacing: 0 !important;
            }

            .stApp {
                background:
                    radial-gradient(circle at 12% 0%, rgba(59, 130, 246, .10), transparent 34rem),
                    radial-gradient(circle at 88% 10%, rgba(34, 211, 238, .07), transparent 30rem),
                    linear-gradient(180deg, #080B10 0%, #0A0F16 100%) !important;
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
                background: #05070B;
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
                color: #BFDBFE;
            }

            .vq-badge-success {
                border-color: rgba(34, 197, 94, .32);
                background: rgba(34, 197, 94, .10);
                color: #BBF7D0;
            }

            .vq-badge-warning {
                border-color: rgba(245, 158, 11, .32);
                background: rgba(245, 158, 11, .10);
                color: #FDE68A;
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
                color: #BFDBFE;
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
                color: #BFDBFE;
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
                background: #0B1421;
                filter: saturate(.9) contrast(1.04);
                border-radius: 6px 6px 0 0;
            }

            .vq-news-body {
                padding: .95rem;
            }

            .vq-news-title {
                margin: .35rem 0 0;
                color: #F4F7FB;
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
                background: #172033 !important;
                color: var(--vq-text) !important;
                border: 1px solid rgba(148, 163, 184, .20) !important;
                box-shadow: none !important;
                font-weight: 750 !important;
                letter-spacing: 0 !important;
                transition: transform .14s ease, background .14s ease, border-color .14s ease !important;
            }

            .stButton > button:hover {
                transform: translateY(-1px) !important;
                background: #1D2A40 !important;
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
                background: #0B111A !important;
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
                background: #080B10;
            }

            ::-webkit-scrollbar-thumb {
                background: #243044;
                border-radius: 999px;
                border: 2px solid #080B10;
            }

            ::-webkit-scrollbar-thumb:hover {
                background: #334155;
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

                .vq-tape-item {
                    padding: 0 1rem;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
