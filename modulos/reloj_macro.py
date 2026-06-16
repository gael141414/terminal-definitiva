import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

@st.cache_data(ttl=86400, show_spinner=False)
def calcular_regimen_mercado():
    """Descarga proxies de mercado para estimar Crecimiento e Inflación."""
    try:
        # Cobre (Crecimiento Industrial), Oro (Refugio)
        # TIP (Bonos vs Inflación), IEF (Bonos Nominales)
        tickers = ['HG=F', 'GC=F', 'TIP', 'IEF']
        data = yf.download(tickers, period="6mo", interval="1d")['Close']
        
        # Limpiamos datos
        data = data.ffill().dropna()
        
        # 1. Ratio de Crecimiento (Cobre / Oro)
        data['Crecimiento_Ratio'] = data['HG=F'] / data['GC=F']
        # 2. Ratio de Inflación (TIP / IEF)
        data['Inflacion_Ratio'] = data['TIP'] / data['IEF']
        
        # Calculamos el Momentum de 3 meses (aprox 60 días laborables)
        # ¿Están acelerando o desacelerando?
        mom_crecimiento = (data['Crecimiento_Ratio'].iloc[-1] / data['Crecimiento_Ratio'].iloc[-60]) - 1
        mom_inflacion = (data['Inflacion_Ratio'].iloc[-1] / data['Inflacion_Ratio'].iloc[-60]) - 1
        
        # Normalizamos para el gráfico (escala arbitraria de -10 a 10 para visualización)
        crecimiento_score = max(min(mom_crecimiento * 100, 10), -10)
        inflacion_score = max(min(mom_inflacion * 100, 10), -10)
        
        # Determinamos el cuadrante
        if crecimiento_score > 0 and inflacion_score < 0:
            regimen = "Recuperación"
        elif crecimiento_score > 0 and inflacion_score > 0:
            regimen = "Sobrecalentamiento"
        elif crecimiento_score < 0 and inflacion_score > 0:
            regimen = "Estanflación"
        else:
            regimen = "Reflación (Recesión)"
            
        return crecimiento_score, inflacion_score, regimen
    except Exception as e:
        # Valores por defecto en caso de fallo de API
        return 0, 0, "Desconocido"

def plot_cuadrante_reloj(crec_score, inf_score, regimen):
    """Dibuja la matriz 2x2 del Reloj Económico."""
    fig = go.Figure()

    # Añadir los 4 cuadrantes como rectángulos de fondo
    # Cuadrante 1: Sobrecalentamiento (Arriba Derecha) - Rojo suave
    fig.add_shape(type="rect", x0=0, y0=0, x1=10, y1=10, fillcolor="rgba(255, 50, 50, 0.1)", line_width=0)
    # Cuadrante 2: Estanflación (Arriba Izquierda) - Naranja suave
    fig.add_shape(type="rect", x0=-10, y0=0, x1=0, y1=10, fillcolor="rgba(255, 150, 0, 0.1)", line_width=0)
    # Cuadrante 3: Reflación (Abajo Izquierda) - Azul suave
    fig.add_shape(type="rect", x0=-10, y0=-10, x1=0, y1=0, fillcolor="rgba(50, 150, 255, 0.1)", line_width=0)
    # Cuadrante 4: Recuperación (Abajo Derecha) - Verde suave
    fig.add_shape(type="rect", x0=0, y0=-10, x1=10, y1=0, fillcolor="rgba(50, 255, 50, 0.1)", line_width=0)

    # Etiquetas de los cuadrantes
    fig.add_annotation(x=5, y=5, text="🔥 SOBRECALENTAMIENTO<br>(Crecimiento ⬆️ | Inflación ⬆️)", showarrow=False, font=dict(color="white", size=14))
    fig.add_annotation(x=-5, y=5, text="⚠️ ESTANFLACIÓN<br>(Crecimiento ⬇️ | Inflación ⬆️)", showarrow=False, font=dict(color="white", size=14))
    fig.add_annotation(x=-5, y=-5, text="🧊 RECESIÓN / REFLACIÓN<br>(Crecimiento ⬇️ | Inflación ⬇️)", showarrow=False, font=dict(color="white", size=14))
    fig.add_annotation(x=5, y=-5, text="🌱 RECUPERACIÓN<br>(Crecimiento ⬆️ | Inflación ⬇️)", showarrow=False, font=dict(color="white", size=14))

    # Ejes Centrales (Cruz)
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")
    fig.add_vline(x=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")

    # El punto "TÚ ESTÁS AQUÍ"
    fig.add_trace(go.Scatter(
        x=[crec_score], y=[inf_score],
        mode='markers+text',
        marker=dict(size=25, color='#00C0F2', line=dict(width=3, color='white'), symbol='star'),
        text=["📍 ESTADO ACTUAL"],
        textposition="top center",
        textfont=dict(color="#00C0F2", size=16, family="Arial Black"),
        name="Mercado Actual"
    ))

    # Diseño del Layout
    fig.update_layout(
        xaxis=dict(title="CRECIMIENTO ECONÓMICO (Ratio Cobre/Oro)", range=[-10, 10], showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(title="EXPECTATIVAS DE INFLACIÓN (Ratio TIP/IEF)", range=[-10, 10], showgrid=False, zeroline=False, showticklabels=False),
        height=600,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=20, b=20),
        showlegend=False
    )
    return fig

def ejecutar_reloj_macro():
    st.markdown("### 🕰️ El Reloj Económico (Macro Regime Tracker)")
    st.markdown("El mercado no premia a las empresas buenas todo el tiempo. Premia a los activos que mejor sobreviven a la fase macroeconómica actual. El algoritmo lee los mercados de bonos y materias primas para posicionar la economía en tiempo real.")

    with st.spinner("Calculando el momentum del Cobre, Oro y Bonos del Tesoro (3 meses)..."):
        crec, inf, regimen = calcular_regimen_mercado()
        
        if regimen != "Desconocido":
            # 1. Gráfico Matriz
            fig = plot_cuadrante_reloj(crec, inf, regimen)
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            
            # 2. Recomendaciones Tácticas según el Régimen
            st.markdown(f"#### 🎯 Diagnóstico Actual: **{regimen}**")
            
            col_rec1, col_rec2, col_rec3 = st.columns(3)
            
            if regimen == "Recuperación":
                col_rec1.success("✅ **SOBREPONDERAR (Comprar)**\n- Acciones Growth / Tecnología\n- Consumo Discrecional\n- Bonos Corporativos High Yield")
                col_rec2.info("⚖️ **NEUTRAL (Mantener)**\n- Sector Financiero\n- Industriales")
                col_rec3.error("❌ **INFRAPONDERAR (Vender)**\n- Efectivo / Cash\n- Oro y Refugios\n- Bonos Gubernamentales Largos")
                st.caption("💡 **Contexto:** La inflación baja permite a los bancos centrales relajar los tipos de interés, mientras la economía crece. Es el escenario 'Ricitos de Oro' ideal para el S&P 500 y las tecnológicas.")
                
            elif regimen == "Sobrecalentamiento":
                col_rec1.success("✅ **SOBREPONDERAR (Comprar)**\n- Materias Primas (Petróleo, Cobre)\n- Acciones Value (Energía, Materiales)\n- Mercados Emergentes")
                col_rec2.info("⚖️ **NEUTRAL (Mantener)**\n- Efectivo / Cash\n- Sector Inmobiliario (REITs)")
                col_rec3.error("❌ **INFRAPONDERAR (Vender)**\n- Bonos a Largo Plazo (Sufren con la inflación)\n- Acciones Tech (Sensibles a tipos de interés)")
                st.caption("💡 **Contexto:** La economía crece mucho, pero la inflación se dispara. Los bancos centrales suben tipos de interés. Los bonos son tóxicos aquí, lo mejor son los activos reales tangibles.")
                
            elif regimen == "Estanflación":
                col_rec1.success("✅ **SOBREPONDERAR (Comprar)**\n- Efectivo / Liquidez (Rey)\n- Oro y Metales Preciosos\n- Acciones Defensivas (Salud, Utilities)")
                col_rec2.info("⚖️ **NEUTRAL (Mantener)**\n- Materias Primas energéticas\n- Bonos a Corto Plazo")
                col_rec3.error("❌ **INFRAPONDERAR (Vender)**\n- Acciones Cíclicas\n- Acciones de Crecimiento (Growth)\n- Bonos a Largo Plazo")
                st.caption("💡 **Contexto:** El peor escenario posible. La economía frena pero los precios suben (Ej: Shock de los 70s o Guerra de Ucrania). Casi nada funciona bien. Es momento de proteger el capital y esperar.")
                
            else: # Reflación / Recesión
                col_rec1.success("✅ **SOBREPONDERAR (Comprar)**\n- Bonos Gubernamentales (TLT)\n- Efectivo / Liquidez\n- Acciones Ultra-Defensivas (Consumo Básico)")
                col_rec2.info("⚖️ **NEUTRAL (Mantener)**\n- Oro\n- Acciones de alta calidad crediticia")
                col_rec3.error("❌ **INFRAPONDERAR (Vender)**\n- Materias Primas (Colapsan sin demanda)\n- Empresas fuertemente endeudadas\n- Sector Inmobiliario")
                st.caption("💡 **Contexto:** El crecimiento se desploma y la inflación desaparece. Los bancos centrales entran en pánico y bajan los tipos a cero. Los Bonos Gubernamentales (Renta Fija) son el activo estrella aquí.")

        else:
            st.error("No se pudo calcular el régimen macro actual por un fallo de red con Yahoo Finance.")
