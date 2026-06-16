import streamlit as st
import random

def ejecutar_apartado_consejos():
    st.markdown("# 🎓 El Aula del Oráculo: Lecciones de Inversión")
    st.markdown("Cada clic en el botón inferior desbloquea una píldora de sabiduría institucional. Úsalas para construir tu criterio de inversor profesional.")

    # --- BASE DE DATOS DE CONOCIMIENTO ---
    base_conocimiento = [
        {
            "categoria": "🧠 Psicología del Mercado",
            "autor": "Seth Klarman",
            "cita": "La inversión es la intersección de la economía y la psicología.",
            "pildora_tecnica": "El 'Sesgo de Recencia' hace que los inversores crean que lo que ha pasado en los últimos 6 meses seguirá pasando siempre. Los profesionales operan en ciclos de 5-10 años.",
            "dificultad": "Básica"
        },
        {
            "categoria": "📊 Análisis Fundamental",
            "autor": "Joel Greenblatt",
            "cita": "Comprar buenos negocios a precios de ganga es el secreto del éxito.",
            "pildora_tecnica": "El 'Earnings Yield' (EBIT/Enterprise Value) es superior al PER porque ignora la estructura de capital y los impuestos, permitiendo comparar empresas con diferentes niveles de deuda.",
            "dificultad": "Avanzada"
        },
        {
            "categoria": "🛡️ Gestión de Riesgos",
            "autor": "Nassim Taleb",
            "cita": "No confundas suerte con habilidad, ni probabilidad con certidumbre.",
            "pildora_tecnica": "La 'Estrategia Barbell' consiste en tener el 90% en activos ultra-seguros (Cash/Bonos) y el 10% en activos de alto riesgo (Opciones/Small Caps). Así estás protegido ante el colapso pero expuesto a ganancias explosivas.",
            "dificultad": "Experto"
        },
        {
            "categoria": "💹 Especulación y Macro",
            "autor": "George Soros",
            "cita": "No importa si tienes razón o no, lo que importa es cuánto dinero ganas cuando tienes razón y cuánto pierdes cuando te equivocas.",
            "pildora_tecnica": "La 'Reflexividad' de los mercados: Los precios no solo reflejan los fundamentales, sino que los precios PUEDEN CAMBIAR los fundamentales (ej: una acción que sube mucho facilita que la empresa pida crédito barato).",
            "dificultad": "Media"
        },
        {
            "categoria": "⚖️ Valoración",
            "autor": "Bruce Greenwald",
            "cita": "A largo plazo, todo se reduce a la capacidad de generar caja por encima del coste de capital.",
            "pildora_tecnica": "El EPV (Earnings Power Value) valora la empresa asumiendo crecimiento CERO. Si el valor actual es mucho mayor que el EPV, estás pagando solo por el crecimiento futuro, lo cual es arriesgado.",
            "dificultad": "Avanzada"
        }
    ]

    # --- LÓGICA DEL BOTÓN ---
    if "pildora_actual" not in st.session_state:
        st.session_state.pildora_actual = None

    col_btn, _ = st.columns([1, 2])
    with col_btn:
        if st.button("💊 Generar Nueva Píldora de Conocimiento", use_container_width=True):
            st.session_state.pildora_actual = random.choice(base_conocimiento)

    # --- RENDERIZADO DE LA LECCIÓN ---
    if st.session_state.pildora_actual:
        p = st.session_state.pildora_actual
        
        st.markdown(f"### {p['categoria']}")
        
        # Estética de tarjeta de profesor
        with st.container(border=True):
            st.markdown(f"#### 📜 La Sentencia del Maestro")
            st.info(f"*\"{p['cita']}\"* — **{p['autor']}**")
            
            st.markdown("#### 🔬 El Conocimiento Oculto")
            st.write(p['pildora_tecnica'])
            
            st.divider()
            col_inf1, col_inf2 = st.columns(2)
            col_inf1.write(f"**Nivel de la lección:** `{p['dificultad']}`")
            col_inf2.write(f"**Relevancia:** 💎 Alta")
    else:
        st.info("Pulsa el botón superior para comenzar tu lección del día.")
