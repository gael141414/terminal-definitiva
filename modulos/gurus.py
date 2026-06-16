import streamlit as st

def ejecutar_visor_gurus(ticker_input, res_is, res_bs, res_cf, res_val):
    st.markdown(f"### 🎓 Cónclave de Gurús: Análisis de {ticker_input}")
    st.markdown("Hemos programado los algoritmos de selección de los mejores gestores de la historia. Descubre si esta empresa pasaría sus estrictos filtros de inversión.")
    
    # --- ESCUDOS DE SEGURIDAD (ANTI-CRASH) ---
    def get_last(df, col):
        if df is not None and col in df.columns:
            s = df[col].dropna()
            return s.iloc[-1] if not s.empty else 0
        return 0

    def safe_get(diccionario, clave, multiplicador=1):
        """Extrae el dato de forma segura. Si es None o texto, devuelve 0."""
        if diccionario and clave in diccionario:
            valor = diccionario[clave]
            # Solo multiplicamos si es realmente un número (int o float)
            if isinstance(valor, (int, float)):
                return valor * multiplicador
        return 0

    # --- 1. JOEL GREENBLATT (La Fórmula Mágica) ---
    st.markdown("---")
    st.markdown("#### 🪄 Joel Greenblatt: La Fórmula Mágica")
    st.caption("Busca dos cosas simples: Empresas buenas (Alto ROIC) a precios baratos (Alto Earnings Yield).")
    
    roic = get_last(res_bs["ratios"], "ROIC %")
    ey = safe_get(res_val, 'earnings_yield', 100) # Usamos el escudo aquí
    
    col_g1, col_g2, col_g3 = st.columns(3)
    col_g1.metric("ROIC (> 25% ideal)", f"{roic:.1f}%")
    col_g2.metric("Earnings Yield (> 8% ideal)", f"{ey:.1f}%")
    
    with col_g3:
        if roic > 25 and ey > 8:
            st.success("✅ **¡Acción Mágica!** La empresa es extraordinariamente rentable y cotiza a un precio muy atractivo.")
        elif roic > 15 and ey > 5:
            st.info("⚖️ **Atractiva:** Cumple los mínimos de rentabilidad y precio, pero no es una ganga absoluta.")
        elif roic == 0 and ey == 0:
            st.warning("⚠️ **Datos Incompletos:** No se pudo evaluar la Fórmula Mágica.")
        else:
            st.error("❌ **Descartada:** La empresa o no es un negocio excepcional (ROIC bajo) o Wall Street ya la ha encarecido demasiado (EY bajo).")

    # --- 2. PETER LYNCH (El modelo GARP) ---
    st.markdown("---")
    st.markdown("#### 🏃‍♂️ Peter Lynch: Crecimiento a Precio Razonable (GARP)")
    st.caption("Si el PER de una empresa es menor a su tasa de crecimiento de beneficios (Ratio PEG < 1), es una ganga. Si es el doble, está sobrevalorada.")
    
    per = safe_get(res_val, 'per_asumido', 1) # Usamos el escudo aquí
    crecimiento = safe_get(res_val, 'crecimiento_sostenible', 100) # Usamos el escudo aquí
    
    col_p1, col_p2, col_p3 = st.columns(3)
    col_p1.metric("PER Actual", f"{per:.1f}x")
    col_p2.metric("Crecimiento Esperado", f"{crecimiento:.1f}%")
    
    with col_p3:
        if per > 0 and crecimiento > 0:
            peg = per / crecimiento
            if peg <= 1:
                st.success(f"✅ **Aprobada:** PEG de {peg:.2f}. Peter Lynch compraría esta acción porque su crecimiento justifica con creces su múltiplo.")
            elif peg <= 1.5:
                st.warning(f"⚠️ **Justa:** PEG de {peg:.2f}. Precio razonable, pero no ofrece un gran margen de seguridad.")
            else:
                st.error(f"❌ **Cara:** PEG de {peg:.2f}. El mercado es demasiado optimista y exige un PER muy superior al crecimiento real del negocio.")
        else:
            st.info("Datos insuficientes para calcular el ratio PEG.")

    # --- 3. PHILIP FISHER (Crecimiento en Ventas) ---
    st.markdown("---")
    st.markdown("#### 📈 Philip Fisher: El Motor de Ventas")
    st.caption("Fisher ignoraba los márgenes a corto plazo y se centraba en empresas capaces de crecer sus ventas año tras año de forma agresiva.")
    
    if res_is is not None and "Crecimiento Ventas %" in res_is["ratios"].columns:
        hist_ventas = res_is["ratios"]["Crecimiento Ventas %"].dropna()
        if len(hist_ventas) >= 3:
            media_3y = hist_ventas.iloc[-3:].mean()
            col_f1, col_f2 = st.columns([1, 2])
            col_f1.metric("Crecimiento Ventas (Media 3A)", f"{media_3y:.1f}%")
            
            with col_f2:
                if media_3y > 15:
                    st.success("✅ **Motor Intacto:** Crecimiento superior al 15% anual. Es una auténtica compounder en etapa de expansión.")
                elif media_3y > 5:
                    st.info("⚖️ **Empresa Madura:** Crecimiento estable pero lento. Típico de empresas de gran capitalización consolidadas.")
                else:
                    st.error("❌ **Negocio Estancado:** La empresa no está logrando vender más que hace 3 años. Peligro de pérdida de cuota de mercado.")
        else:
            st.info("No hay suficientes datos históricos para calcular la media de crecimiento a 3 años.")
    else:
         st.info("Métrica de ventas no encontrada.")
