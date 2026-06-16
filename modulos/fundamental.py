import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ---------------- VALUEQUANT DATAFRAME STYLING ---------------- #
VQ_TABLE_GREEN = 'rgba(54, 196, 134, 0.15)'
VQ_TABLE_RED = 'rgba(239, 91, 107, 0.15)'
VQ_TABLE_BG = 'rgba(18, 25, 38, 0.72)'
VQ_TABLE_HEADER_BG = 'rgba(18, 25, 38, 0.98)'
VQ_TABLE_BORDER = 'rgba(255, 255, 255, 0.06)'
VQ_TABLE_TEXT = '#eef4ff'
VQ_TABLE_MUTED = '#93a4bb'


def _format_ratio_value(value):
    """Formatea ratios a 2 decimales sin modificar el DataFrame original."""
    if pd.isna(value):
        return '—'
    try:
        return f'{float(value):,.2f}'
    except (TypeError, ValueError):
        return value


def _style_vq_dataframe(df: pd.DataFrame, *, color_func=None, hide_index: bool = False):
    """Styler corporativo para tablas financieras ValueQuant."""
    ratio_cols = [col for col in df.columns if col != 'Criterio Buffett']
    formatter = {col: _format_ratio_value for col in ratio_cols}

    styler = df.style
    if color_func is not None:
        styler = styler.apply(color_func, axis=1)

    styler = (
        styler
        .format(formatter, na_rep='—')
        .set_table_styles([
            {'selector': 'thead th', 'props': [
                ('background-color', VQ_TABLE_HEADER_BG),
                ('color', VQ_TABLE_TEXT),
                ('font-family', 'Inter, sans-serif'),
                ('font-weight', '700'),
                ('border-bottom', f'1px solid {VQ_TABLE_BORDER}'),
                ('text-align', 'right'),
            ]},
            {'selector': 'tbody th', 'props': [
                ('background-color', VQ_TABLE_HEADER_BG),
                ('color', VQ_TABLE_TEXT),
                ('font-family', 'Inter, sans-serif'),
                ('font-weight', '650'),
                ('border-bottom', f'1px solid {VQ_TABLE_BORDER}'),
                ('text-align', 'left'),
            ]},
            {'selector': 'tbody td', 'props': [
                ('background-color', VQ_TABLE_BG),
                ('color', VQ_TABLE_TEXT),
                ('font-family', 'Inter, sans-serif'),
                ('border-bottom', f'1px solid {VQ_TABLE_BORDER}'),
                ('text-align', 'right'),
            ]},
        ])
        .set_properties(subset=ratio_cols, **{'text-align': 'right'})
    )

    if 'Criterio Buffett' in df.columns:
        styler = styler.set_properties(
            subset=['Criterio Buffett'],
            **{'text-align': 'left', 'color': VQ_TABLE_MUTED, 'font-weight': '500'}
        )

    if hide_index:
        styler = styler.hide(axis='index')

    return styler

# Importamos tus analizadores matemáticos personalizados (que tienes en archivos separados)
from income_analyzer import analizar_cuenta_resultados
from balance_analyzer import analizar_balance
from cashflow_analyzer import analizar_flujo_efectivo
from valuator import calcular_crecimiento_implicito_dcf, calcular_dcf_fcf_por_accion, valorar_empresa
from modulos.utils import obtener_valoracion_sectorial, cargar_datos, calcular_score_buffett
from modulos.scoring_engine import render_valuequant_score_card
from charts import (
    plot_tsr_vs_sp500, 
    plot_dashboard_interactivo, 
    plot_capital_allocation_waterfall,
    plot_owner_earnings,
    plot_shareholder_yield_historico,
    plot_ev_fcf_historico,
    plot_calidad_beneficios,
    plot_anillo_puntuacion,
    plot_adn_financiero,
    plot_treemap_competidores,
    plot_radar_comparativo,
    plot_comparativa_historica,
    plot_football_field,
    plot_proyeccion_dividendos,
    plot_per_bands,
    plot_income_waterfall,
    plot_score_gauge,
    style_historical_databars
)


def _first_existing_column(df: pd.DataFrame, columns: list[str]) -> str | None:
    """Devuelve la primera columna existente sin alterar el DataFrame financiero."""
    return next((col for col in columns if col in df.columns), None)


def _extraer_ultimo_estado_resultados_visual(is_df: pd.DataFrame) -> dict[str, float] | None:
    """Extrae magnitudes para el waterfall visual usando columnas FMP/Yahoo disponibles."""
    if is_df is None or is_df.empty:
        return None
    revenue_col = _first_existing_column(is_df, ["revenue", "totalRevenue", "Ingresos (B USD)", "Total Revenue"])
    cogs_col = _first_existing_column(is_df, ["costOfRevenue", "costOfGoodsSold", "Coste Ventas", "Cost Of Revenue"])
    opex_col = _first_existing_column(is_df, ["operatingExpenses", "Gastos Operativos", "Operating Expense"])
    tax_col = _first_existing_column(is_df, ["incomeTaxExpense", "Impuestos", "Tax Provision"])
    net_col = _first_existing_column(is_df, ["netIncome", "Beneficio Neto", "Net Income"])
    required = [revenue_col, cogs_col, opex_col, tax_col, net_col]
    if any(col is None for col in required):
        return None
    latest = is_df.dropna(subset=[col for col in required if col]).iloc[-1]
    scale = 1e9 if abs(float(latest[revenue_col])) > 1e6 else 1.0
    return {
        "ingresos": float(latest[revenue_col]) / scale,
        "coste_ventas": abs(float(latest[cogs_col])) / scale,
        "gastos_ope": abs(float(latest[opex_col])) / scale,
        "impuestos": abs(float(latest[tax_col])) / scale,
        "beneficio_neto": float(latest[net_col]) / scale,
        "unidad": "B USD" if scale == 1e9 else "USD",
    }


def _crear_tabla_revenue_visual(is_df: pd.DataFrame) -> pd.DataFrame | None:
    """Prepara una tabla visual de ventas históricas para Pandas Styler."""
    if is_df is None or is_df.empty:
        return None
    revenue_col = _first_existing_column(is_df, ["revenue", "totalRevenue", "Ingresos (B USD)", "Total Revenue"])
    if revenue_col is None:
        return None
    serie = pd.to_numeric(is_df[revenue_col], errors="coerce").dropna()
    if serie.empty:
        return None
    scale = 1e9 if abs(float(serie.iloc[-1])) > 1e6 else 1.0
    df_rev = pd.DataFrame({"Año": [str(idx)[:4] for idx in serie.index], "Revenue": (serie / scale).values})
    return df_rev.tail(10).reset_index(drop=True)

def ejecutar_analisis_fundamental(ticker_input, is_df, bs_df, cf_df, res_is, res_bs, res_cf, res_val, nota_buffett, ticker_competidor, valuequant_score=None):
    """Analiza los estados financieros, márgenes, deuda y valoración intrínseca."""
    st.markdown(f"### 🔎 Análisis Fundamental y Valoración: {ticker_input}")

    if res_val is None:
        res_val = {}

    earnings_yield = res_val.get('earnings_yield', 0) if res_val else 0
    tasa_riesgo = res_val.get('tasa_libre_riesgo', 0) if res_val else 0
    precio_actual = res_val.get('precio_actual', 0) if res_val else 0

    # ======== ANÁLISIS BUFFET ========
    st.markdown("#### ⚖️ Test de Coste de Oportunidad (Buffett)")
    c4, c5, c6 = st.columns(3)
    if earnings_yield and tasa_riesgo:
        spread = (earnings_yield - tasa_riesgo) * 100
        color_spread = "normal" if spread > 0 else "inverse"
        c4.metric("Earnings Yield (Rentabilidad)", f"{earnings_yield*100:.2f}%")
        c5.metric("Tasa Libre de Riesgo (Bono 10Y)", f"{tasa_riesgo*100:.2f}%")
        c6.metric("Prima de Riesgo (Spread)", f"{spread:+.2f} pts", delta_color=color_spread)
        if spread < 0:
            st.error(f"🚨 **Alerta Value:** El Bono del Tesoro ({tasa_riesgo*100:.2f}%) rinde más que los beneficios de esta empresa ({earnings_yield*100:.2f}%). Asumes riesgo para ganar menos que un activo garantizado.")
        else:
            st.success(f"✅ **Favorable:** La empresa ofrece una prima de riesgo positiva frente a la renta fija.")
    st.markdown("---")
    st.markdown("#### Score institucional")
    score_col_1, score_col_2 = st.columns([1, 2])

    with score_col_1:
        st.plotly_chart(
            plot_score_gauge(nota_buffett, "Buffett Quality"),
            use_container_width=True
        )

    with score_col_2:
        if valuequant_score is not None:
            render_valuequant_score_card(valuequant_score)
        else:
            st.caption(
                "Gauge visual 0-100 con bandas de calidad: rojo 0-40, ámbar 40-70 "
                "y verde 70-100. No cambia el cálculo del score; solo cambia su presentación."
            )

    st.markdown("---")

    st.markdown("#### 💵 Retorno de Efectivo Real (Caja vs Precio de Mercado)")
    
    acciones = res_val.get('acciones_actuales')
    if precio_actual and acciones and "Free Cash Flow (B USD)" in res_cf["ratios"].columns:
        market_cap = precio_actual * acciones
        
        ultimo_fcf_b = res_cf["ratios"]["Free Cash Flow (B USD)"].dropna().iloc[-1]
        ultimas_recompras_b = res_cf["ratios"]["Recompras (B USD)"].dropna().iloc[-1]
        
        fcf_real = ultimo_fcf_b * 1e9
        recompras_reales = ultimas_recompras_b * 1e9
        
        fcf_yield = (fcf_real / market_cap) * 100
        buyback_yield = (recompras_reales / market_cap) * 100
        
        c7, c8, c9 = st.columns(3)
        
        if market_cap >= 1e12:
            c7.metric("Market Cap (Capitalización)", f"${market_cap / 1e12:.2f} Trillones")
        else:
            c7.metric("Market Cap (Capitalización)", f"${market_cap / 1e9:.2f} Billones")
        
        color_fcf = "normal" if fcf_yield >= 4.0 else "inverse"
        c8.metric("FCF Yield (Rendimiento Efectivo)", f"{fcf_yield:.2f}%", "Óptimo > 4%" if fcf_yield >= 4.0 else "Pobre/Caro", delta_color=color_fcf)
        
        c9.metric("Buyback Yield (Recompras)", f"{buyback_yield:.2f}%", "Destrucción de acciones" if buyback_yield > 0 else "")

        st.write("")
        total_yield = fcf_yield + buyback_yield
        
        if total_yield >= 8.0:
            st.success(f"✅ **Veredicto (Máquina de Efectivo):** Excepcional. La empresa te está devolviendo un **{total_yield:.2f}%** de tu inversión anual de forma 'invisible' (sumando su FCF Yield y las recompras). Está destruyendo acciones a buen ritmo y generando muchísima caja.")
        elif total_yield >= 4.0:
            st.info(f"⚖️ **Veredicto (Sano):** Razonable. Un rendimiento de efectivo total del **{total_yield:.2f}%**, en línea con empresas sólidas y estables. El dinero fluye correctamente hacia el accionista.")
        else:
            st.warning(f"⚠️ **Veredicto (Caja Pobre):** Un rendimiento del **{total_yield:.2f}%** significa que la empresa está muy cara respecto al dinero real que genera, o bien que su negocio requiere reinvertir todo lo que gana (muy intensivo en capital) dejando poco para ti.")
        
    else:
        st.info("No hay datos suficientes de Flujo de Caja para calcular el FCF Yield.")
        
    st.markdown("---")

    st.markdown("#### 🏭 Valoración Relativa (Múltiplos de Mercado)")
    
    with st.spinner("Determinando múltiplo sectorial óptimo..."):
        sector_empresa, metrica_optima, valor_metrica, explicacion, todos_multiplos, umbral = obtener_valoracion_sectorial(ticker_input)
        
        if sector_empresa and sector_empresa != 'Desconocido':
            st.caption(f"**Sector Detectado:** {sector_empresa} | **Métrica Institucional Asignada:** {metrica_optima}")
            st.info(f"💡 **Racionalidad:** {explicacion}")
            
            c_rel1, c_rel2, c_rel3, c_rel4 = st.columns(4)
            
            # Resaltamos la métrica elegida por el algoritmo
            for i, (nombre, valor) in enumerate(todos_multiplos.items()):
                if nombre == metrica_optima:
                    estado = "Barata" if valor > 0 and valor < umbral else "Cara"
                    color_rel = "normal" if estado == "Barata" else "inverse"
                    # Usamos st.metric pero con un fondo destacado o emoji
                    if i == 0: c_rel1.metric(f"🎯 {nombre}", f"{valor:.2f}x", estado, delta_color=color_rel)
                    elif i == 1: c_rel2.metric(f"🎯 {nombre}", f"{valor:.2f}x", estado, delta_color=color_rel)
                    elif i == 2: c_rel3.metric(f"🎯 {nombre}", f"{valor:.2f}x", estado, delta_color=color_rel)
                    elif i == 3: c_rel4.metric(f"🎯 {nombre}", f"{valor:.2f}x", estado, delta_color=color_rel)
                else:
                    # Múltiplos secundarios sin destacar
                    if i == 0: c_rel1.metric(nombre, f"{valor:.2f}x" if valor > 0 else "N/A")
                    elif i == 1: c_rel2.metric(nombre, f"{valor:.2f}x" if valor > 0 else "N/A")
                    elif i == 2: c_rel3.metric(nombre, f"{valor:.2f}x" if valor > 0 else "N/A")
                    elif i == 3: c_rel4.metric(nombre, f"{valor:.2f}x" if valor > 0 else "N/A")
        else:
            st.warning("No se pudo detectar el sector de la empresa para asignar un múltiplo relativo.")
    
    st.markdown("---")

    # --- Fila 4: Análisis DuPont (Calidad del ROE) ---
    st.markdown("#### 🔬 Análisis DuPont: Desmontando el ROE")
    st.caption("Charlie Munger dice: 'Un ROE alto es inútil si se logra a base de deudas'. Aquí vemos de dónde viene realmente el ROE del último año.")
    
    # Función escudo para evitar el IndexError si la columna entera son NaNs
    def get_safe_last_val(df, col):
        if col in df.columns:
            s = df[col].dropna()
            if not s.empty:
                return s.iloc[-1]
        return 0.0

    # Extraemos el último año usando nuestra función escudo
    dupont_margen = get_safe_last_val(res_bs["ratios"], "DuPont: Margen Neto %")
    dupont_rotacion = get_safe_last_val(res_bs["ratios"], "DuPont: Rotación Activos")
    dupont_apalan = get_safe_last_val(res_bs["ratios"], "DuPont: Apalancamiento")
    roe_ultimo = get_safe_last_val(res_bs["ratios"], "ROE %")
    
    c_dp1, c_dp2, c_dp3, c_dp4 = st.columns(4)
    c_dp1.metric("1. Margen Neto (Eficiencia)", f"{dupont_margen:.1f}%")
    c_dp2.metric("2. Rotación Activos (Volumen)", f"{dupont_rotacion:.2f}x")
    
    estado_apalan = "Riesgo si > 3.0x" if dupont_apalan > 3.0 else "Sano"
    color_apalan = "inverse" if dupont_apalan > 3.0 else "normal"
    c_dp3.metric("3. Apalancamiento (Deuda)", f"{dupont_apalan:.2f}x", estado_apalan, delta_color=color_apalan)
    
    c_dp4.metric("= ROE Total", f"{roe_ultimo:.1f}%")

    st.write("")
    if dupont_apalan > 3.0:
        st.error(f"🚨 **Veredicto (Riesgo Oculto):** ¡Cuidado! El ROE parece alto, pero es una ilusión creada por el endeudamiento. La empresa asume un apalancamiento peligroso (**{dupont_apalan:.2f}x**). Si los tipos de interés suben, sus beneficios se hundirán.")
    elif dupont_margen > 15.0:
        st.success(f"✅ **Veredicto (Foso Económico):** El ROE es de máxima calidad. Está impulsado por unos excelentes márgenes de beneficio neto (**{dupont_margen:.1f}%**). La empresa tiene poder de fijación de precios y no depende de deudas masivas.")
    else:
        st.info(f"⚖️ **Veredicto (Modelo de Rotación):** La rentabilidad de la empresa no viene de tener grandes márgenes de beneficio, sino de vender mucho volumen y rotar sus activos rápidamente (**{dupont_rotacion:.2f}x**). Es el clásico modelo de un supermercado como Walmart.")
    
    st.markdown("---")

    # --- Fila 5: Test Piotroski Modificado (Salud Value) ---
    st.markdown("#### 🛡️ Test de Resistencia: Piotroski F-Score (Adaptación Value)")
    st.caption("Sistema de 9 puntos que evalúa la solidez financiera y la tendencia operativa. Un 7-9 indica una empresa blindada. Menos de 4 indica peligro estructural.")

    # Unimos todos los datos para evaluarlos cómodamente
    df_all = pd.concat([res_is["ratios"], res_bs["ratios"], res_cf["ratios"]], axis=1)
    
    # Motor de evaluación de reglas
    def check_cond(col, condition):
        if col not in df_all.columns: return False
        s = df_all[col].dropna()
        if len(s) < 2: return False
        val_act = s.iloc[-1]
        val_prev = s.iloc[-2]
        
        if condition == "pos": return val_act > 0
        if condition == "up": return val_act > val_prev
        if condition == "down": return val_act < val_prev
        if condition == "roic": return val_act >= 15
        return False

    # Las 9 pruebas de fuego de Buffett/Munger
    criterios = [
        (check_cond("Margen Neto %", "pos"), "Beneficios Positivos"),
        (check_cond("Free Cash Flow (B USD)", "pos"), "Genera Caja Real"),
        (check_cond("ROE %", "up"), "ROE Creciente"),
        (check_cond("Margen Bruto %", "up"), "Márgenes Crecientes"),
        (check_cond("DuPont: Rotación Activos", "up"), "Eficiencia al Alza"),
        (check_cond("Deuda / Capital", "down"), "Desapalancamiento"),
        (check_cond("Caja Neta (B USD)", "up"), "Liquidez Creciente"),
        (check_cond("Recompras (B USD)", "pos"), "No Diluye Acciones"),
        (check_cond("ROIC %", "roic"), "ROIC Premium (>15%)")
    ]

    # Calculamos la nota final
    score = sum([1 for p, txt in criterios if p])
    
    # Renderizado visual espectacular
    c_f1, c_f2 = st.columns([1, 3])
    
    with c_f1:
        color_str = "#2ca02c" if score >= 7 else "#ff7f0e" if score >= 4 else "#d62728"
        st.markdown(f"<h1 style='text-align: center; color: {color_str}; font-size: 5rem; margin-bottom: 0;'>{score}/9</h1>", unsafe_allow_html=True)
        if score >= 7: st.success("🟢 Blindaje Total")
        elif score >= 4: st.warning("🟡 Calidad Media")
        else: st.error("🔴 Riesgo Financiero")
        
    with c_f2:
        cols_grid = st.columns(3)
        for i, (passed, text) in enumerate(criterios):
            icono = "✅" if passed else "❌"
            cols_grid[i % 3].markdown(f"**{icono}** {text}")
            
    st.markdown("---")
    
    st.markdown("#### 🏆 Retorno Histórico vs Mercado (S&P 500)")
    fig_tsr = plot_tsr_vs_sp500(ticker_input)
    if fig_tsr:
        st.plotly_chart(fig_tsr, use_container_width=True)
        
        st.caption("💡 *Warren Buffett dice: 'Si no puedes batir al índice, invierte en el índice'. Este gráfico asume una inversión de $10,000 hace 10 años, midiendo si el riesgo de elegir esta acción individual ha sido recompensado frente a comprar el S&P 500.*")
    else:
        st.info("No hay suficientes datos de mercado para generar la comparativa con el S&P 500.")

    # ======== TAB 1 ========
    fig = plot_dashboard_interactivo(
        res_is["ratios"],
        res_bs["ratios"],
        res_cf["ratios"],
        ticker_input
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("#### Cuenta de resultados institucional")
    waterfall_data = _extraer_ultimo_estado_resultados_visual(is_df)
    col_wf, col_rev = st.columns([1.45, 1])
    with col_wf:
        if waterfall_data:
            st.caption(f"Cascada del último ejercicio en {waterfall_data['unidad']}.")
            st.plotly_chart(
                plot_income_waterfall(
                    waterfall_data["ingresos"],
                    waterfall_data["coste_ventas"],
                    waterfall_data["gastos_ope"],
                    waterfall_data["impuestos"],
                    waterfall_data["beneficio_neto"],
                ),
                use_container_width=True,
            )
        else:
            st.info("No hay columnas suficientes para renderizar la cascada de cuenta de resultados.")
    with col_rev:
        df_revenue_visual = _crear_tabla_revenue_visual(is_df)
        if df_revenue_visual is not None and not df_revenue_visual.empty:
            st.caption("Histórico de ventas con data bars. La barra azul compara cada año contra el máximo de la columna.")
            st.dataframe(style_historical_databars(df_revenue_visual, column="Revenue"), use_container_width=True, hide_index=True)
        else:
            st.info("No hay histórico de Revenue suficiente para data bars.")

    # --- FILA DEL EFECTIVO Y CAPITAL ALLOCATION ---
    st.markdown("---")
    col_caja1, col_caja2 = st.columns(2)
    
    with col_caja1:
        st.markdown("#### 💸 Asignación de Capital (10 Años)")
        st.caption("Suma de todos los flujos de caja de la década.")
        fig_waterfall = plot_capital_allocation_waterfall(res_cf["ratios"], ticker_input)
        if fig_waterfall:
            st.plotly_chart(fig_waterfall, use_container_width=True)
            
    with col_caja2:
        st.markdown("#### 👑 Beneficios del Dueño (Owner Earnings)")
        st.caption("Ajuste de Buffett: Separa el CAPEX de mantenimiento del de crecimiento.")
        fig_oe = plot_owner_earnings(res_cf["ratios"], ticker_input)
        if fig_oe:
            st.plotly_chart(fig_oe, use_container_width=True)

    # --- FILA DE GRÁFICOS AVANZADOS ---
    st.markdown("---")
    col_graf1, col_graf2 = st.columns(2)
    
    with col_graf1:
        st.markdown("#### 🎁 Retribución al Accionista")
        fig_sy = plot_shareholder_yield_historico(res_cf["ratios"], ticker_input)
        if fig_sy:
            st.plotly_chart(fig_sy, use_container_width=True)
            
    with col_graf2:
        st.markdown("#### 📊 Valoración Real (EV / FCF)")
        st.caption("Compara el precio actual (limpio de deuda y caja) contra su media histórica.")
        if res_val and res_val.get('acciones_actuales'):
            fig_ev = plot_ev_fcf_historico(ticker_input, res_bs["ratios"], res_cf["ratios"], res_val['acciones_actuales'])
            if fig_ev:
                st.plotly_chart(fig_ev, use_container_width=True)
                
                # Extraer el último múltiplo y la mediana para el veredicto
                try:
                    ultimos_fcf = res_cf["ratios"]['Free Cash Flow (B USD)'].dropna()
                    ultimos_caja = res_bs["ratios"]['Caja Neta (B USD)'].dropna()
                    if not ultimos_fcf.empty and not ultimos_caja.empty and ultimos_fcf.iloc[-1] > 0:
                        market_cap_b = (res_val['precio_actual'] * res_val['acciones_actuales']) / 1e9
                        ev_actual = market_cap_b - ultimos_caja.iloc[-1]
                        multiplo_actual = ev_actual / ultimos_fcf.iloc[-1]
                        
                        st.info(f"💡 **Interpretación:** Hoy pagas **{multiplo_actual:.1f}x** su caja libre. Si este número está muy por debajo de la línea punteada naranja (su media histórica), históricamente estás comprando con descuento. Si está muy por encima, Wall Street está pagando una prima exigente.")
                except: pass
        else:
            st.info("No se pudo calcular el EV/FCF por falta de datos de acciones en circulación.")

        st.markdown("---")
        st.markdown("#### ⏳ Fair Value Timeline (Bandas de PER Históricas)")
        st.caption("La reversión a la media en estado puro. Comprar cuando la línea del precio toca la banda inferior (pesimismo) e ignorar la acción cuando toca la banda superior (euforia).")
    
        with st.spinner("Construyendo el túnel de valoración histórica..."):
            try:
                eps_col = "epsdiluted" if "epsdiluted" in is_df.columns else "eps"
                eps_dict = {
                    str(idx.year): float(value)
                    for idx, value in is_df[eps_col].dropna().items()
                } if eps_col in is_df.columns else None
                fig_per = plot_per_bands(ticker_input, eps_dict)
                if fig_per:
                    st.plotly_chart(fig_per, use_container_width=True)
                else:
                    st.info("No hay suficientes datos históricos ininterrumpidos de beneficios para dibujar las bandas de valoración.")
            except Exception as e:
                st.error(f"Error al generar el gráfico de bandas PER: {e}")

    st.markdown("#### 🔎 Calidad del Beneficio (Filtro Anti-Fraude)")
    st.caption("Si la barra azul (Beneficio) es sistemáticamente mayor que la verde (Caja), la empresa no está cobrando lo que vende o maquilla sus cuentas.")
    fig_calidad = plot_calidad_beneficios(ticker_input)
    if fig_calidad:
        st.plotly_chart(fig_calidad, use_container_width=True)

    # ======== TAB 2 ========
    st.markdown("### 📝 Calidad Fundamental y ADN Financiero")
    
    # --- CÁLCULO RÁPIDO DE PIOTROSPI PARA EL ANILLO ---
    df_all = pd.concat([res_is["ratios"], res_bs["ratios"], res_cf["ratios"]], axis=1)
    def check_cond_rapido(col, condition):
        if col not in df_all.columns: return False
        s = df_all[col].dropna()
        if len(s) < 2: return False
        if condition == "pos": return s.iloc[-1] > 0
        if condition == "up": return s.iloc[-1] > s.iloc[-2]
        if condition == "down": return s.iloc[-1] < s.iloc[-2]
        if condition == "roic": return s.iloc[-1] >= 15
        return False

    piotroski_score = sum([
        check_cond_rapido("Margen Neto %", "pos"), check_cond_rapido("Free Cash Flow (B USD)", "pos"),
        check_cond_rapido("ROE %", "up"), check_cond_rapido("Margen Bruto %", "up"),
        check_cond_rapido("DuPont: Rotación Activos", "up"), check_cond_rapido("Deuda / Capital", "down"),
        check_cond_rapido("Caja Neta (B USD)", "up"), check_cond_rapido("Recompras (B USD)", "pos"),
        check_cond_rapido("ROIC %", "roic")
    ])

    # --- ANILLOS NEÓN Y RADAR ---
    col_adn1, col_adn2, col_adn3 = st.columns([1, 1, 1.5])
    
    with col_adn1:
        # 🛠️ CORRECCIÓN 1: Ahora usamos 'nota_buffett'
        fig_buffett = plot_anillo_puntuacion(nota_buffett, 100, "Buffett Score", "#00C0F2")
        st.plotly_chart(fig_buffett, use_container_width=True)
        
    with col_adn2:
        # 🛠️ CORRECCIÓN 2: Ahora usamos 'piotroski_score'
        fig_piotroski = plot_anillo_puntuacion(piotroski_score, 9, "Piotroski F-Score", "#00ff88")
        st.plotly_chart(fig_piotroski, use_container_width=True)
        
    with col_adn3:
        fig_adn = plot_adn_financiero(ticker_input)
        if fig_adn:
            st.plotly_chart(fig_adn, use_container_width=True)
    
    st.markdown("---")
    st.markdown("#### 📑 Histórico de Ratios y Reglas Inquebrantables")
            
    # 1. Unimos todos los ratios
    df_completo = pd.concat(
        [res_is["ratios"], res_bs["ratios"], res_cf["ratios"]],
        axis=1
    ).T
    
    # 2. Inyectamos los Umbrales de Buffett
    umbrales_buffett = {
        "Margen Bruto %": "> 40% (Ventaja Duradera)", "SG&A % (s/MB)": "< 30% (Fantástico)",
        "I+D % (s/MB)": "< 30% (Foso tecnológico frágil)", "Depreciación % (s/MB)": "< 10% (Poco gasto en maquinaria)",
        "Intereses % (s/OpInc)": "< 15% (Poca deuda)", "Margen Neto %": "> 20% (Monopolio)",
        "ROE %": "> 15% constante", "ROIC %": "> 15% (Verdadera calidad)", 
        "Deuda / Capital": "< 0.80 (Bajo apalancamiento)",
        "CAPEX % sobre Beneficio": "< 50% (Ideal < 25%)", "Crecimiento Gan. Retenidas %": "~ 10% constante"
    }
    df_completo.insert(0, "Criterio Buffett", [umbrales_buffett.get(idx, "-") for idx in df_completo.index])

    # 3. Mostramos la tabla en la web
    # Función para pintar las celdas según reglas Value
    def colorear_matriz(row):
        metric = row.name
        styles = [''] * len(row)
        
        # Reglas: (Operador, Umbral)
        reglas = {
            "Margen Bruto %": ('>', 40), "SG&A % (s/MB)": ('<', 30), "I+D % (s/MB)": ('<', 30),
            "Depreciación % (s/MB)": ('<', 10), "Intereses % (s/OpInc)": ('<', 15),
            "Margen Neto %": ('>', 20), "ROE %": ('>', 15), "ROIC %": ('>', 15),
            "Deuda / Capital": ('<', 0.80), "CAPEX % sobre Beneficio": ('<', 25)
        }
        
        if metric in reglas:
            op, limite = reglas[metric]
            for i, col in enumerate(row.index):
                if col != "Criterio Buffett":
                    try:
                        val = float(row[col])
                        if pd.isna(val): continue
                        if op == '>':
                            styles[i] = f'background-color: {VQ_TABLE_GREEN}; color: #d9fff0; font-weight: 650' if val >= limite else f'background-color: {VQ_TABLE_RED}; color: #ffe0e4; font-weight: 650'
                        else:
                            styles[i] = f'background-color: {VQ_TABLE_GREEN}; color: #d9fff0; font-weight: 650' if val <= limite else f'background-color: {VQ_TABLE_RED}; color: #ffe0e4; font-weight: 650'
                    except: pass
        return styles

    st.dataframe(
        _style_vq_dataframe(df_completo, color_func=colorear_matriz, hide_index=False),
        use_container_width=True,
        height=500
    )
    
    st.markdown("---")
    
    # Convertimos el DataFrame a CSV usando codificación utf-8 para no perder acentos
    csv_data = df_completo.to_csv(index_label="Métrica").encode('utf-8-sig')
    
    st.download_button(
        label="📥 Descargar Reporte (CSV/Excel)",
        data=csv_data,
        file_name=f"{ticker_input}_Reporte_Buffett.csv",
        mime="text/csv",
        type="primary"
    )

    # ======== TAB 3 ========
    if ticker_competidor:
        with st.spinner(f"Descargando informes de la SEC para el competidor {ticker_competidor}..."):
            is_df2, bs_df2, cf_df2, metrics_df2 = cargar_datos(ticker_competidor, 10)
            
            if is_df2 is not None:
                # Analizamos al competidor completo
                res_is2 = analizar_cuenta_resultados(is_df2, cf_df2)
                res_bs2 = analizar_balance(bs_df2, is_df2)
                res_cf2 = analizar_flujo_efectivo(cf_df2, is_df2)
                res_val2 = valorar_empresa(is_df2, bs_df2, cf_df2, metrics_df2, ticker_competidor)
                
                if res_is2 and res_bs2 and res_cf2:
                    # 1. MARCADOR HEAD-TO-HEAD
                    st.markdown(f"### 🥊 {ticker_input} vs {ticker_competidor}")
                    
                    st.markdown("#### 🗺️ Mapa de Mercado Relativo")
                    fig_treemap = plot_treemap_competidores(ticker_input, ticker_competidor)
                    if fig_treemap:
                        st.plotly_chart(fig_treemap, use_container_width=True)
                    st.markdown("---")
                    
                    nota1 = calcular_score_buffett(res_is["ratios"], res_bs["ratios"], res_cf["ratios"])
                    nota2 = calcular_score_buffett(res_is2["ratios"], res_bs2["ratios"], res_cf2["ratios"])
                    
                    c_h1, c_h2, c_h3, c_h4 = st.columns(4)
                    
                    # Empresa 1
                    c_h1.metric(f"Score Value ({ticker_input})", f"{nota1}/100", "Ganador" if nota1 >= nota2 else "Perdedor", delta_color="normal" if nota1 >= nota2 else "inverse")
                    if res_val:
                        c_h2.metric(f"PER Actual ({ticker_input})", f"{res_val['precio_actual'] / res_val['eps_actual']:.1f}x" if res_val['precio_actual'] else "N/A")
                        
                    # Empresa 2
                    c_h3.metric(f"Score Value ({ticker_competidor})", f"{nota2}/100", "Ganador" if nota2 > nota1 else "Perdedor", delta_color="normal" if nota2 > nota1 else "inverse")
                    if res_val2:
                        c_h4.metric(f"PER Actual ({ticker_competidor})", f"{res_val2['precio_actual'] / res_val2['eps_actual']:.1f}x" if res_val2['precio_actual'] else "N/A")

                    st.markdown("---")
                    
                    # 2. GRÁFICOS COMPARATIVOS
                    col_comp1, col_comp2 = st.columns(2)
                    
                    with col_comp1:
                        fig_radar = plot_radar_comparativo(
                            ticker_input, res_is["ratios"], res_bs["ratios"],
                            ticker_competidor, res_is2["ratios"], res_bs2["ratios"]
                        )
                        if fig_radar:
                            st.plotly_chart(fig_radar, use_container_width=True)
                            st.info("💡 **Foso Actual:** El radar muestra quién tiene los fundamentales más fuertes en el último año reportado.")
                            
                    with col_comp2:
                        # Comparativa histórica de ROIC (El foso económico en el tiempo)
                        fig_hist = plot_comparativa_historica(
                            ticker_input, res_bs["ratios"], 
                            ticker_competidor, res_bs2["ratios"], 
                            "ROIC %"
                        )
                        if fig_hist:
                            st.plotly_chart(fig_hist, use_container_width=True)
                        
                        # Comparativa histórica de Márgenes
                        fig_hist2 = plot_comparativa_historica(
                            ticker_input, res_is["ratios"], 
                            ticker_competidor, res_is2["ratios"], 
                            "Margen Neto %"
                        )
                        if fig_hist2:
                            st.plotly_chart(fig_hist2, use_container_width=True)
                            
                        st.caption("📈 **Consistencia:** Buffett prefiere una empresa con un 15% estable durante 10 años, que una con picos del 30% y caídas al 5%.")

            else:
                st.error(f"No se pudieron descargar los datos del competidor {ticker_competidor}. Comprueba el ticker.")
    else:
        st.info("🥊 **El Ring está vacío.** Introduce un ticker rival en el panel lateral (Ej: 'MSFT', 'PEP', 'AMD') para activar la batalla de calidad empresarial.")

    # ======== MODELOS DE VALORACIÓN ========
    st.subheader(f"⚖️ Triangulación de Valor Intrínseco — {ticker_input}")

    if res_val:
        precio_actual = res_val.get('precio_actual')
        eps_actual = res_val.get('eps_actual', 0)
        fcf_por_accion = res_val.get('fcf_per_share') or eps_actual
    
        earnings_yield = res_val.get('earnings_yield', 0)
        tasa_riesgo = res_val.get('tasa_libre_riesgo', 0)
        
        # Extracción de Modelos
        v_graham = res_val.get('graham_value', 0)
        v_lynch = res_val.get('lynch_value', 0)
        v_epv = res_val.get('epv_value', 0)
        
        # --- SECCIÓN 1: MODELOS MATEMÁTICOS ESTÁTICOS ---
        st.markdown("#### 🏛️ Modelos Institucionales (Suelo y Techo)")
        st.caption("Diferentes metodologías de inversión aplicadas a los beneficios actuales de la empresa.")
        
        col_m1, col_m2, col_m3 = st.columns(3)
        
        # Blindaje de seguridad para asegurar que precio_actual es un número
        p_actual_seguro = precio_actual if isinstance(precio_actual, (int, float)) else 0
        
        # 1. Graham
        v_graham = res_val.get('graham_value', 0) if res_val else 0
        if p_actual_seguro > 0 and isinstance(v_graham, (int, float)) and v_graham > 0:
            margen_graham = ((p_actual_seguro - v_graham) / v_graham) * 100
        else:
            margen_graham = 0
            
        color_g = "inverse" if margen_graham > 0 else "normal"
        estado_g = "Cara" if margen_graham > 0 else "Barata"
        col_m1.metric("Benjamin Graham (Value)", f"${v_graham:.2f}", f"{estado_g} ({margen_graham:+.1f}%)", delta_color=color_g)
        col_m1.caption("Graham Number clásico: EPS y valor contable por acción. En negocios asset-light suele ser un suelo muy conservador.")
        
        # 2. Peter Lynch
        v_lynch = res_val.get('lynch_value', 0) if res_val else 0
        if p_actual_seguro > 0 and isinstance(v_lynch, (int, float)) and v_lynch > 0:
            margen_lynch = ((p_actual_seguro - v_lynch) / v_lynch) * 100
        else:
            margen_lynch = 0
            
        color_l = "inverse" if margen_lynch > 0 else "normal"
        estado_l = "Cara" if margen_lynch > 0 else "Barata"
        col_m2.metric("Peter Lynch (Crecimiento)", f"${v_lynch:.2f}", f"{estado_l} ({margen_lynch:+.1f}%)", delta_color=color_l)
        lynch_pe = res_val.get('lynch_pe', 0)
        col_m2.caption(f"PEG=1 sobre crecimiento normalizado. PER justo usado: {lynch_pe:.1f}x.")
        
        # 3. EPV
        v_epv = res_val.get('epv_value', 0) if res_val else 0
        if p_actual_seguro > 0 and isinstance(v_epv, (int, float)) and v_epv > 0:
            margen_epv = ((p_actual_seguro - v_epv) / v_epv) * 100
        else:
            margen_epv = 0
            
        col_m3.metric("EPV (Cero Crecimiento)", f"${v_epv:.2f}")
        col_m3.caption("Valor de capacidad de beneficios sin crecimiento, usando FCF/owner earnings por acción.")

    st.markdown("#### 🎛️ Tu Modelo DCF (Flujos de Caja Descontados)")
    st.caption("Crea tu propio escenario. Los valores por defecto han sido calculados por nuestro algoritmo.")
    
    col_slider1, col_slider2, col_slider3 = st.columns(3)
    
    with col_slider1:
        g_sugerido = res_val.get('crecimiento_sostenible', 0.05) * 100
        cagr_usr = st.slider("Crecimiento Anual FCF/acción %", min_value=-5.0, max_value=20.0, value=float(g_sugerido), step=0.5)
        
    with col_slider2:
        wacc_sugerido = res_val.get('tasa_descuento_capm', 0.10) * 100
        tasa_desc_usr = st.slider("Tasa de Descuento (CAPM) %", min_value=5.0, max_value=20.0, value=float(wacc_sugerido), step=0.5)
        
    with col_slider3:
        margen_seguridad_usr = st.slider("Margen de Seguridad %", min_value=0, max_value=50, value=25, step=5)

    # Cálculo de tu DCF Personalizado con FCF por acción, no con PER terminal.
    terminal_growth = res_val.get('terminal_growth', 0.025)
    v_dcf = calcular_dcf_fcf_por_accion(
        fcf_por_accion,
        cagr_usr / 100,
        tasa_desc_usr / 100,
        terminal_growth,
    )
    precio_compra = v_dcf * (1 - (margen_seguridad_usr / 100))

    c1, c2, c3 = st.columns(3)

    if precio_actual and v_dcf > 0:
        descuento_dcf = ((precio_actual - v_dcf) / v_dcf) * 100
        estado_valor = "Sobrevalorada" if descuento_dcf > 0 else "Infravalorada"
        color_valor = "inverse" if descuento_dcf > 0 else "normal"
        c1.metric("Precio de Mercado Hoy", f"${precio_actual:.2f}", f"{estado_valor} ({descuento_dcf:+.1f}%)", delta_color=color_valor)
    else:
        c1.metric("Precio de Mercado", "No disp.")
        
    c2.metric("Valor Justo (Tu DCF)", f"${v_dcf:.2f}", f"FCF/acc. ${fcf_por_accion:.2f}")
    c3.metric(f"Precio Seguro (-{margen_seguridad_usr}%)", f"${precio_compra:.2f}")

    st.markdown("#### 🧠 Reverse DCF: ¿Qué crecimiento asume el mercado hoy?")
    st.caption("En lugar de adivinar el futuro, calculamos qué crecimiento anual (CAGR) exige el precio actual de la acción para justificar su cotización en bolsa.")

    if precio_actual and fcf_por_accion and fcf_por_accion > 0:
        try:
            implied_g = calcular_crecimiento_implicito_dcf(
                precio_actual,
                fcf_por_accion,
                tasa_desc_usr / 100,
                terminal_growth,
            )
            if implied_g is not None:
                implied_g_pct = implied_g * 100
                c_rev1, c_rev2 = st.columns([1, 2])
                
                color_delta = "inverse" if implied_g_pct > cagr_usr else "normal"
                c_rev1.metric(
                    "Crecimiento Implícito (Priced In)", 
                    f"{implied_g_pct:.2f}%", 
                    f"vs {cagr_usr:.2f}% (Tu estimación)", 
                    delta_color=color_delta
                )
                
                if implied_g_pct > cagr_usr:
                    c_rev2.error(f"⚠️ **Sobrevaloración probable:** El mercado ya está asumiendo que la empresa crecerá al **{implied_g_pct:.2f}%** anual durante 10 años. Si tú crees que solo crecerá al **{cagr_usr:.2f}%**, la acción está cara hoy.")
                else:
                    c_rev2.success(f"✅ **Margen de seguridad:** El mercado es pesimista y solo le exige crecer al **{implied_g_pct:.2f}%**. Como tú estimas un crecimiento del **{cagr_usr:.2f}%**, estás comprando barato.")
            else:
                st.info("Matemáticamente imposible calcular el Reverse DCF (Base negativa).")
        except Exception as e:
            st.error(f"Error en el cálculo del Reverse DCF: {e}")
    else:
        st.info("Se necesita un Precio de Mercado actual y FCF por acción positivo para realizar la ingeniería inversa.")

    # ====== Matriz de Sensibilidad DCF (Heatmap) =======
    st.markdown("#### 🗺️ Matriz de Sensibilidad (Precio Seguro)")
    st.caption("Esta matriz muestra a qué precio deberías comprar la acción dependiendo de si el crecimiento futuro (Eje Y) y la rentabilidad exigida (Eje X) cambian. Las celdas verdes son precios más seguros.")
    
    # Generar variaciones de +/- 2% alrededor de lo que el usuario ha puesto en los sliders
    tasas_desc = [tasa_desc_usr - 2, tasa_desc_usr - 1, tasa_desc_usr, tasa_desc_usr + 1, tasa_desc_usr + 2]
    crecimientos = [cagr_usr - 2, cagr_usr - 1, cagr_usr, cagr_usr + 1, cagr_usr + 2]

    matriz_precios = []
    for g in crecimientos:
        fila = []
        for d in tasas_desc:
            v_i = calcular_dcf_fcf_por_accion(
                fcf_por_accion,
                g / 100,
                d / 100,
                terminal_growth,
            )
            p_c = v_i * (1 - (margen_seguridad_usr / 100))
            fila.append(p_c)
        matriz_precios.append(fila)

    fig_hm = go.Figure(data=go.Heatmap(
        z=matriz_precios,
        x=[f"{d}%" for d in tasas_desc],
        y=[f"{g}%" for g in crecimientos],
        colorscale='RdYlGn', # Rojo (Peligro) a Verde (Seguro)
        text=[[f"${val:.2f}" for val in fila] for fila in matriz_precios],
        texttemplate="%{text}",
        hoverinfo="skip"
    ))
    fig_hm.update_layout(
        xaxis_title="Tasa de Descuento (Retorno Exigido)",
        yaxis_title="Crecimiento Anual Estimado (CAGR)",
        height=350,
        margin=dict(l=40, r=40, t=20, b=40)
    )
    st.plotly_chart(fig_hm, use_container_width=True)
    st.markdown("---")

    st.markdown("#### Football Field Chart")
    fig_ff = plot_football_field(ticker_input, precio_actual, res_val)

    if fig_ff:
        st.plotly_chart(fig_ff, use_container_width=True)
    else:
        st.info("No se pudo generar el gráfico Football Field...")
    st.markdown("---")

    # ======== TAB 8 ========
    st.markdown("### 💸 Estrategia de Dividendos Crecientes (DGI)")
    st.caption("No mires el dividendo actual, mira el futuro. El *Yield on Cost* (Rentabilidad sobre Coste) te dice cuánto dinero te pagará la empresa anualmente respecto a lo que pagaste por ella el día que la compraste.")
    
    if precio_actual:
        with st.spinner("Calculando histórico y proyecciones de dividendos..."):
            fig_dgi, texto_dgi = plot_proyeccion_dividendos(ticker_input, precio_actual)
            
            if fig_dgi:
                st.plotly_chart(fig_dgi, use_container_width=True)
                st.success(texto_dgi)
            else:
                st.info(texto_dgi) # Muestra el mensaje de error si la empresa no paga dividendo
    else:
        st.warning("Se necesita un precio de mercado actual para calcular el Yield on Cost.")    
