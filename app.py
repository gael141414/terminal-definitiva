import streamlit as st

st.set_page_config(
    page_title="ValueQuant Terminal",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="collapsed",
)

import html

from financials.income_analyzer import analizar_cuenta_resultados
from financials.balance_analyzer import analizar_balance
from financials.cashflow_analyzer import analizar_flujo_efectivo
from financials.valuator import valorar_empresa
from modulos.config import CONFIG
from modulos.app_assets import asset_to_data_uri, strip_visual_prefix
from modulos.app_theme import inject_terminal_theme
from modulos.app_navigation import (
    BLOQUE_UI,
    TOOL_UI_ICONS,
    render_context_header,
    render_option_menu_safe,
)
from modulos.app_home import render_home_page
from modulos.market_widgets import (
    analizar_rotacion_sectores,
    buscar_etf_yahoo,
    render_ticker_tape,
)
from modulos.tradingview_widgets import render_tradingview_widget, renderizar_grafico_tradingview
from modulos.company_data_helpers import obtener_datos_directiva, obtener_tickers_filtrados, obtener_transacciones_insiders, obtener_valoracion_sectorial
from modulos.app_company_ui import render_company_empty_state
from modulos.app_integrations import inyectar_atajo_teclado, load_lottieurl, obtener_modelo_gemini, obtener_secreto_streamlit
from modulos.app_analysis_helpers import analizar_sentimiento_noticias, escanear_vulnerabilidades, ultimo_ratio
from modulos.app_runtime import build_runtime_paths
from modulos.module_loader import safe_call
from modulos.utils import cargar_datos, calcular_score_buffett
from modulos.scoring_engine import calcular_valuequant_score
from modulos.fmp_api import diagnosticar_conexion_fmp
from modulos.ui_components import render_kpi_card
from modulos.tool_catalog import (
    TOOL_CATALOG,
    BLOQUES_HERRAMIENTAS,
    HERRAMIENTAS_POR_LABEL,
    obtener_bloques_por_modo,
    obtener_herramientas_por_bloque_y_modo,
    obtener_modos_navegacion,
)
from modulos.tool_router import CompanyToolContext, render_company_tool, render_independent_tool
from modulos.html_markdown import escribir_html

# ---------------- CONFIGURACIÓN ---------------- #
# 1. CONFIGURACIÓN DE PÁGINA movida al inicio del archivo para cumplir Streamlit.

# ==========================================
# MARKET TICKER TAPE FIJO
# ==========================================

# ---------------- DATA LOADER ---------------- #

# ==========================================
# WIDGET RADICAL 2: MOTOR TRADINGVIEW EN VIVO
# ==========================================

# ---------------- TERMINAL UI 2026: ASSETS, CSS, HOME Y NAVEGACIÓN ---------------- #
RUNTIME_PATHS = build_runtime_paths(__file__)
APP_DIR = RUNTIME_PATHS.app_dir
LOGO_PATH = RUNTIME_PATHS.logo_path
HOME_BG_PATH = RUNTIME_PATHS.home_bg_path
FMP_API_KEY = CONFIG.fmp_api_key

inject_terminal_theme()

inyectar_atajo_teclado()

# ---------------- UI PREMIUM & CONTROL CENTRAL ---------------- #        

# ---------------------------------------------------------
# 1. NAVEGACIÓN SUPERIOR Y CONTROL CENTRAL
# ---------------------------------------------------------
render_ticker_tape()

logo_uri_nav = asset_to_data_uri(LOGO_PATH)
logo_tag_nav = f"<img src='{logo_uri_nav}' alt='ValueQuant Terminal'>" if logo_uri_nav else ""
modos_navegacion = obtener_modos_navegacion()
modo_labels = [modo["label"] for modo in modos_navegacion]
modo_keys = [modo["key"] for modo in modos_navegacion]
modo_default_idx = modo_keys.index("mvp") if "mvp" in modo_keys else 0

# La cabecera es un contenedor REAL. Antes se abría <div class="vq-nav-shell">
# en un st.markdown y se cerraba en otro, con el menú en medio: eso no envuelve
# nada, porque Streamlit pinta cada elemento en un contenedor hermano y el
# navegador autocierra el <div>.
#
# El selector de modo vivía en una barra lateral que existía solo para él, y su
# valor se repetía además en un panel del cuerpo. Ahora es un desplegable en la
# propia cabecera: un control de producto, no una sección de la aplicación.
contenedor_cabecera = st.container()
with contenedor_cabecera:
    st.markdown('<span class="vq-nav-marca"></span>', unsafe_allow_html=True)
    col_marca, col_modo = st.columns([5, 1], gap="small")

    with col_marca:
        escribir_html(f"""
            <div class="vq-brand-row">
                <div class="vq-brand">{logo_tag_nav}<span>ValueQuant Terminal</span></div>
                <div class="vq-session-pill"><i class="bi bi-broadcast-pin"></i> Research desk active</div>
            </div>
        """)

    with col_modo:
        with st.popover("Modo", use_container_width=True):
            modo_label = st.radio(
                "Modo de navegación",
                modo_labels,
                index=modo_default_idx,
                key="vq_navigation_mode",
                help="MVP muestra solo el producto principal. Consolidado agrupa herramientas por arquitectura objetivo. Completo muestra todo.",
            )

modo_navegacion = modo_keys[modo_labels.index(modo_label)] if modo_label in modo_labels else "mvp"

bloques_internos = list(obtener_bloques_por_modo(modo_navegacion))
if not bloques_internos:
    bloques_internos = list(BLOQUES_HERRAMIENTAS)

# Research Core no es una pestaña más (mockup docs/design/research_core_navegacion_kpi.html,
# sección 1a): es la puerta de entrada dominante, fusionada en "Home" — ver más abajo,
# donde una búsqueda desde la tarjeta hero de Home activa este mismo bloque sin pasar
# por una pestaña independiente.
bloques_internos = [b for b in bloques_internos if b != "🧩 Research Core"]

menu_interno = ["__home__"] + bloques_internos
menu_labels = ["Home"] + [BLOQUE_UI.get(b, (strip_visual_prefix(b), "grid"))[0] for b in bloques_internos]
menu_icons = ["house"] + [BLOQUE_UI.get(b, (strip_visual_prefix(b), "grid"))[1] for b in bloques_internos]
# El menú principal va dentro del contenedor de cabecera abierto arriba.
with contenedor_cabecera:
    seleccion_menu = render_option_menu_safe(menu_labels, menu_icons, key=f"vq_main_nav_{modo_navegacion}")

# Aquí se pintaba un panel que solo repetía el modo ya elegido en el selector de
# la cabecera. Dos controles para el mismo dato es ruido, no redundancia útil.

seleccion_idx = menu_labels.index(seleccion_menu) if seleccion_menu in menu_labels else 0
en_home = menu_interno[seleccion_idx] == "__home__"
# Activado por la tarjeta hero de Research Core en Home (modulos/app_home.py) —
# mientras esté activo, "Home" deja de mostrar la landing y muestra directamente
# el Research Core ya resuelto, sin que este exista como pestaña independiente.
research_core_activo = en_home and bool(st.session_state.get("vq_research_core_activo", False))

if en_home and not research_core_activo:
    render_home_page(LOGO_PATH, HOME_BG_PATH)
    st.stop()

if research_core_activo:
    # Un botón suelto flotando sobre el contenido no dice dónde estás. La miga
    # de pan responde a la vez a "dónde estoy" y "cómo salgo", que es lo que
    # tiene que resolver la navegación.
    col_ruta, col_salir = st.columns([6, 1], gap="small")
    with col_ruta:
        escribir_html(f"""
            <nav class="vq-ruta" aria-label="Ruta de navegación">
                <span class="vq-ruta-paso">Home</span>
                <i class="bi bi-chevron-right vq-ruta-sep"></i>
                <span class="vq-ruta-paso">Research Core</span>
                <i class="bi bi-chevron-right vq-ruta-sep"></i>
                <span class="vq-ruta-actual">{html.escape(str(st.session_state.get("ticker_analizado", "")))}</span>
            </nav>
        """)
    with col_salir:
        if st.button("Salir", key="vq_volver_home", use_container_width=True):
            st.session_state["vq_research_core_activo"] = False
            st.rerun()

bloque_actual = "🧩 Research Core" if research_core_activo else menu_interno[seleccion_idx]
herramientas_bloque = obtener_herramientas_por_bloque_y_modo(bloque_actual, modo_navegacion)
etiquetas_bloque = [h["label"] for h in herramientas_bloque]
tool_labels = [strip_visual_prefix(label) for label in etiquetas_bloque]
tool_icons = [TOOL_UI_ICONS.get(label, "circle") for label in etiquetas_bloque]

# El panel de trabajo es un contenedor real: antes se abría el <div> aquí y se
# cerraba 90 líneas más abajo, con los widgets en medio. Nunca los envolvió.
contenedor_trabajo = st.container(border=True)
with contenedor_trabajo:
    escribir_html(f"""
        <div class="vq-panel-cabecera">
            <div>
                <div class="vq-context-eyebrow">Área de trabajo</div>
                <div class="vq-panel-titulo">{html.escape(strip_visual_prefix(bloque_actual))}</div>
            </div>
            <span class="vq-badge vq-badge-primary">
                <i class="bi bi-command"></i> Command Center
            </span>
        </div>
    """)

    seleccion_herramienta = render_option_menu_safe(
        tool_labels,
        tool_icons,
        key=f"vq_tool_nav_{seleccion_idx}"
    )

    seleccion_tool_idx = tool_labels.index(seleccion_herramienta) if seleccion_herramienta in tool_labels else 0
    seccion_actual = etiquetas_bloque[seleccion_tool_idx]
    herramienta_actual = HERRAMIENTAS_POR_LABEL[seccion_actual]

    st.markdown(
        f"<div class='vq-tool-caption'>{html.escape(herramienta_actual['descripcion'])}</div>",
        unsafe_allow_html=True,
    )

    # Variables contextuales compartidas por el router
    ticker_input = "AAPL"
    etf_input = "SPY"
    ticker_competidor = ""
    años_hist = 10
    analizar_btn = False

    if herramienta_actual["input_mode"] == "etf":
        col_a, col_b = st.columns([1.3, 2.7])
        with col_a:
            st.caption("Análisis de fondos")
            busqueda_etf = st.text_input("Buscar ETF", value="", placeholder="Vanguard, SPY, QQQ...", label_visibility="collapsed")
        with col_b:
            if busqueda_etf:
                try:
                    resultados_busqueda = buscar_etf_yahoo(busqueda_etf)
                    if resultados_busqueda:
                        seleccion = st.selectbox("Selecciona fondo", resultados_busqueda, label_visibility="collapsed")
                        etf_input = seleccion.split(" ➔ ")[0].strip()
                    else:
                        etf_input = busqueda_etf.upper().strip()
                        st.info(f"Usando ticker exacto: {etf_input}")
                except Exception:
                    etf_input = busqueda_etf.upper().strip()
            else:
                st.info("Introduce un ETF para iniciar la radiografía.")
    elif herramienta_actual["input_mode"] == "standalone":
        st.caption("Herramienta independiente. Los controles específicos aparecen en el panel central.")
    else:
        try:
            lista_tickers_sec = obtener_tickers_filtrados()
        except Exception:
            lista_tickers_sec = ["AAPL - Apple Inc.", "MSFT - Microsoft Corp."]

        indice_aapl = next((i for i, item in enumerate(lista_tickers_sec) if item.startswith("AAPL -")), 0)
        indice_default = indice_aapl
        if research_core_activo:
            # Llegamos aquí desde la tarjeta hero de Home con un ticker ya resuelto
            # (modulos.app_home._activar_research_core) — el selectbox debe arrancar
            # en ese ticker, no en AAPL por defecto.
            ticker_buscado_hero = st.session_state.get("ticker_analizado")
            if ticker_buscado_hero:
                indice_default = next(
                    (
                        i
                        for i, item in enumerate(lista_tickers_sec)
                        if item.split(" - ")[0].strip().upper() == str(ticker_buscado_hero).upper()
                    ),
                    indice_aapl,
                )
        col_1, col_2, col_3, col_4 = st.columns([2.2, 2.2, 1, 1])
        with col_1:
            seleccion_principal = st.selectbox("Empresa", options=lista_tickers_sec, index=indice_default)
            ticker_input = seleccion_principal.split(" - ")[0]
        with col_2:
            lista_competidores = [""] + lista_tickers_sec
            seleccion_competidor = st.selectbox("Comparador", options=lista_competidores, index=0)
            ticker_competidor = seleccion_competidor.split(" - ")[0] if seleccion_competidor else ""
        with col_3:
            años_hist = st.slider("Años FMP", 1, 5, 5)
        with col_4:
            st.markdown("<div style='height:1.72rem;'></div>", unsafe_allow_html=True)
            analizar_btn = st.button("Analizar", use_container_width=True, type="primary")


render_context_header(
    bloque=bloque_actual,
    herramienta=herramienta_actual,
    ticker=ticker_input if herramienta_actual["input_mode"] == "company" else None,
    competidor=ticker_competidor if ticker_competidor else None,
    años=años_hist if herramienta_actual["input_mode"] == "company" else None,
)

# ---------------------------------------------------------
# 2. ENRUTADOR PRINCIPAL (Gestión de la pantalla central)
# ---------------------------------------------------------

herramientas_independientes = [
    h["label"] for h in TOOL_CATALOG if h["input_mode"] in {"standalone", "etf"}
]

# CASOS INDEPENDIENTES (No necesitan darle al botón del sidebar)
if seccion_actual in herramientas_independientes:
    st.markdown("<br>", unsafe_allow_html=True)
    render_independent_tool(seccion_actual, etf_input=etf_input)

# CASOS DE EMPRESA (Requieren pulsar el botón del sidebar la primera vez)
else:
    # ---------------------------------------------------------
    # RUTA B: HERRAMIENTAS DE EMPRESA (Requieren pulsar el botón)
    # ---------------------------------------------------------
    
    # 1. Escuchamos al botón de la barra lateral
    if analizar_btn:
        st.session_state['empresa_analizada'] = True
        st.session_state['ticker_analizado'] = ticker_input
        st.session_state['competidor_analizado'] = ticker_competidor
        st.session_state['años_analizados'] = años_hist

    # 2. Si AÚN NO han pulsado el botón -> Mostramos la Landing Page
    empresa_no_analizada = (
        not st.session_state.get('empresa_analizada', False)
        or st.session_state.get('ticker_analizado') != ticker_input
        or st.session_state.get('competidor_analizado') != ticker_competidor
        or st.session_state.get('años_analizados') != años_hist
    )

    if empresa_no_analizada:
        render_company_empty_state(ticker_input, herramienta_actual)
        st.stop()

    # 3. Si YA han pulsado el botón -> Cargamos los datos y mostramos la herramienta
    with st.spinner(f"Sincronizando con Wall Street... Descargando {años_hist} años de datos para {ticker_input}"):
        is_df, bs_df, cf_df, metrics_df = cargar_datos(ticker_input, años_hist)

    datos_fmp = {
        "income_statement": None if is_df is None else is_df.shape,
        "balance_sheet": None if bs_df is None else bs_df.shape,
        "cash_flow": None if cf_df is None else cf_df.shape,
        "key_metrics": None if metrics_df is None else metrics_df.shape,
    }

    if is_df is None or bs_df is None or cf_df is None:
        st.error(f"🚨 FMP no devolvió estados financieros completos para `{ticker_input}`.")
        st.caption(
            "Puede ser un ticker mal escrito o con formato distinto (algunas clases de acciones "
            "usan guion, p. ej. `BRK-B`) — o que este símbolo no esté disponible con el plan de "
            "FMP contratado, algo que no depende del ticker y que reintentar no soluciona. "
            "El detalle exacto (código HTTP de cada endpoint) está en «Diagnóstico FMP» abajo."
        )
        with st.expander("Diagnóstico FMP"):
            st.json(datos_fmp)
            with st.spinner("Probando endpoints FMP sin caché..."):
                st.json(diagnosticar_conexion_fmp(ticker_input, 2))
            if st.button("Limpiar caché FMP y reintentar"):
                try:
                    st.cache_data.clear()
                except Exception:
                    pass
                st.rerun()
        st.stop()

    # Procesamiento matemático de fondo (Para el Chatbot y otras funciones futuras)
    res_is = analizar_cuenta_resultados(is_df, cf_df)
    res_bs = analizar_balance(bs_df, is_df)
    res_cf = analizar_flujo_efectivo(cf_df, is_df)
    res_val = valorar_empresa(is_df, bs_df, cf_df, metrics_df, ticker_input)

    nota_buffett = calcular_score_buffett(
        res_is["ratios"],
        res_bs["ratios"],
        res_cf["ratios"]
    )

    valuequant_score = calcular_valuequant_score(
        ticker=ticker_input,
        is_df=is_df,
        bs_df=bs_df,
        cf_df=cf_df,
        res_is=res_is,
        res_bs=res_bs,
        res_cf=res_cf,
        res_val=res_val,
    )

    st.session_state["nota_buffett"] = nota_buffett
    st.session_state["valuequant_score"] = valuequant_score

    st.markdown(
        "<div class='vq-section-title'><i class='bi bi-speedometer2'></i>Panel ejecutivo</div>",
        unsafe_allow_html=True,
    )

    col_kpi_1, col_kpi_2, col_kpi_3 = st.columns(3)

    with col_kpi_1:
        render_kpi_card(
            label="Empresa analizada",
            value=ticker_input,
            detail=f"Histórico cargado: {años_hist} años",
            status="neutral"
        )

    with col_kpi_2:
        render_kpi_card(
            label="Módulo activo",
            value=strip_visual_prefix(herramienta_actual["label"]),
            detail=strip_visual_prefix(bloque_actual),
            status="positive"
        )

    with col_kpi_3:
        render_kpi_card(
            label="Comparador",
            value=ticker_competidor if ticker_competidor else "No definido",
            detail="Benchmark relativo",
            status="positive" if ticker_competidor else "warning"
        )
    
    # Invocamos la herramienta correspondiente desde el router central
    tool_context = CompanyToolContext(
        ticker=ticker_input,
        competitor=ticker_competidor,
        years=años_hist,
        is_df=is_df,
        bs_df=bs_df,
        cf_df=cf_df,
        metrics_df=metrics_df,
        res_is=res_is,
        res_bs=res_bs,
        res_cf=res_cf,
        res_val=res_val,
        nota_buffett=nota_buffett,
        valuequant_score=valuequant_score,
        sector_rotation_fn=analizar_rotacion_sectores,
    )
    render_company_tool(seccion_actual, tool_context)

# Chat lateral legacy retirado: la nueva arquitectura usa navegación superior sin sidebar.
