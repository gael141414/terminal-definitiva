import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
from modulos.gemini_helper import aviso_gemini_no_configurado, obtener_modelo_gemini


def _veredicto_multibagger_local(score, ticker, sector, revenue_growth, gross_margins, insider_hold, current_ratio):
    if score >= 75:
        base = "perfil cuantitativo fuerte para vigilancia prioritaria"
    elif score >= 50:
        base = "perfil interesante, pero todavía especulativo"
    else:
        base = "perfil débil para una tesis 10x en este momento"

    riesgos = []
    if revenue_growth < 10:
        riesgos.append("crecimiento insuficiente")
    if gross_margins < 30:
        riesgos.append("márgenes poco escalables")
    if insider_hold < 3:
        riesgos.append("baja alineación insider")
    if current_ratio < 1:
        riesgos.append("riesgo de liquidez/dilución")

    detalle_riesgos = ", ".join(riesgos) if riesgos else "el principal riesgo es ejecución y valoración"
    return (
        f"**{ticker} ({sector})** muestra un {base}. "
        f"El TAM debe validarse fuera del score, pero los datos actuales apuntan a estos riesgos: {detalle_riesgos}."
    )

def ejecutar_radar_multibagger(ticker_input):
    """Escáner de ADN matemático para Small/Mid Caps (Crecimiento, Márgenes, Insiders)"""

    st.markdown(f"### 🚀 Radar de Diamantes en Bruto: {ticker_input}")
    st.markdown("Evalúa si esta empresa tiene el ADN matemático y cualitativo de una 'Multibagger' (capacidad de multiplicar su valor por 10x). Basado en los criterios cuantitativos de hipercrecimiento y escalabilidad.")

    with st.spinner("Extrayendo métricas de crecimiento, márgenes y alineación de la directiva..."):
        try:
            import yfinance as yf
            import pandas as pd
            import plotly.express as px

            empresa = yf.Ticker(ticker_input)
            info = empresa.info

            # 1. Extracción de Métricas Críticas (El ADN del pelotazo)
            market_cap = info.get('marketCap', 0)
            revenue_growth = info.get('revenueGrowth', 0) * 100 if info.get('revenueGrowth') else 0
            gross_margins = info.get('grossMargins', 0) * 100 if info.get('grossMargins') else 0
            insider_hold = info.get('heldPercentInsiders', 0) * 100 if info.get('heldPercentInsiders') else 0
            current_ratio = info.get('currentRatio', 0)

            # 2. Sistema de Puntuación Cuantitativa (0 a 100)
            score = 0
            puntos_detalle = {}

            # Criterio 1: Tamaño (Puntúa más si es pequeña/mediana)
            if market_cap > 0 and market_cap < 2e9:
                score += 20; puntos_detalle['Micro/Small Cap (< $2B)'] = 20
            elif market_cap >= 2e9 and market_cap < 10e9:
                score += 15; puntos_detalle['Mid Cap ($2B - $10B)'] = 15
            else:
                score += 5; puntos_detalle['Large/Mega Cap (Difícil hacer x10)'] = 5

            # Criterio 2: Crecimiento en Ventas (> 20% es ideal)
            if revenue_growth > 25:
                score += 20; puntos_detalle['Hipercrecimiento (>25% YoY)'] = 20
            elif revenue_growth > 10:
                score += 10; puntos_detalle['Crecimiento Sólido (>10% YoY)'] = 10
            else:
                puntos_detalle['Crecimiento Estancado / Negativo'] = 0

            # Criterio 3: Márgenes Brutos (Escalabilidad)
            if gross_margins > 60:
                score += 20; puntos_detalle['Altamente Escalable (>60% Margen)'] = 20
            elif gross_margins > 30:
                score += 10; puntos_detalle['Márgenes Industriales/Estándar'] = 10
            else:
                puntos_detalle['Márgenes Bajos (Difícil escalar)'] = 0

            # Criterio 4: Skin in the game (Insiders)
            if insider_hold > 10:
                score += 20; puntos_detalle['Fundadores Involucrados (>10% acciones)'] = 20
            elif insider_hold > 3:
                score += 10; puntos_detalle['Buena Alineación (>3%)'] = 10
            else:
                puntos_detalle['Sin Skin in the Game (<3%)'] = 0

            # Criterio 5: Caja para sobrevivir sin diluir (Liquidez)
            if current_ratio > 2.0:
                score += 20; puntos_detalle['Caja Fuerte (Sin riesgo de dilución)'] = 20
            elif current_ratio > 1.0:
                score += 10; puntos_detalle['Liquidez Aceptable'] = 10
            else:
                puntos_detalle['Riesgo de Ampliación de Capital (Falta liquidez)'] = 0

            st.markdown("---")
            st.markdown(f"### 🧬 Multibagger Score: {score}/100")
            st.progress(score / 100)

            # 3. Gráfico Radar Vectorial (Plotly)
            df_radar = pd.DataFrame(dict(
                r=[
                    20 if market_cap < 10e9 else 5,
                    min(revenue_growth, 30) / 30 * 20 if revenue_growth > 0 else 0,
                    min(gross_margins, 80) / 80 * 20 if gross_margins > 0 else 0,
                    min(insider_hold, 15) / 15 * 20 if insider_hold > 0 else 0,
                    min(current_ratio, 3) / 3 * 20 if current_ratio > 0 else 0
                ],
                theta=['Tamaño', 'Crecimiento', 'Escalabilidad', 'Insiders', 'Liquidez']
            ))
            
            fig_radar = px.line_polar(df_radar, r='r', theta='theta', line_close=True, range_r=[0, 20])
            fig_radar.update_traces(fill='toself', line_color='#00C0F2', fillcolor='rgba(0, 192, 242, 0.4)')
            fig_radar.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', 
                plot_bgcolor='rgba(0,0,0,0)', 
                polar=dict(radialaxis=dict(visible=False)),
                margin=dict(t=20, b=20, l=20, r=20)
            )
            
            col1, col2 = st.columns([1, 1.2])
            with col1:
                st.plotly_chart(fig_radar, use_container_width=True)
            with col2:
                st.markdown("#### Desglose del ADN Matemático")
                for k, v in puntos_detalle.items():
                    if v == 20:
                        st.write(f"🟢 **{v} pts** - {k}")
                    elif v > 0:
                        st.write(f"🟡 **{v} pts** - {k}")
                    else:
                        st.write(f"🔴 **{v} pts** - {k}")
                
                st.markdown("<br>", unsafe_allow_html=True)
                st.caption(f"**Datos Extraídos:** Cap. Mercado: ${market_cap/1e9:.2f}B | Crecimiento: {revenue_growth:.2f}% | Insider Hold: {insider_hold:.2f}%")

            # 4. Auditoría Cualitativa IA (El Foso Defensivo)
            st.markdown("---")
            st.markdown("### 🧠 Veredicto de Disrupción (TAM & Moat)")
            with st.spinner("La IA está evaluando el Total Addressable Market (TAM) y los riesgos existenciales..."):
                
                prompt_startup = f"""
                Actúa como un gestor de Venture Capital y Small Caps de Silicon Valley. 
                Analiza la empresa {ticker_input} (Sector: {info.get('sector', 'Desconocido')}).
                Su Score Cuantitativo Multibagger es {score}/100.
                
                Escribe un informe de 3 párrafos yendo directo al grano:
                1. TAM y Oportunidad: ¿El mercado al que se dirigen es lo suficientemente masivo para que hagan un x10 en capitalización?
                2. Riesgo de Muerte: ¿Qué es lo más probable que los mate o los lleve a la bancarrota? (Competencia gigante, quemar mucha caja, mala gestión).
                3. Veredicto Final: ¿Es una trampa de valor o un diamante en bruto? No uses lenguaje genérico, sé un analista duro.
                """
                
                model = obtener_modelo_gemini()
                if model:
                    response = model.generate_content(prompt_startup)
                    st.write(response.text)
                else:
                    aviso_gemini_no_configurado()
                    st.write(_veredicto_multibagger_local(
                        score,
                        ticker_input,
                        info.get('sector', 'Desconocido'),
                        revenue_growth,
                        gross_margins,
                        insider_hold,
                        current_ratio,
                    ))

        except Exception as e:
            st.error(f"Error procesando los datos de la empresa: {e}. Es posible que falten datos fundamentales en la base de datos para este Ticker.")
        
