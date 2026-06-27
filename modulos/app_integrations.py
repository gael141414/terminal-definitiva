from __future__ import annotations

import requests
import streamlit as st
import streamlit.components.v1 as components

from modulos.config import CONFIG

try:
    import google.generativeai as genai
except Exception:
    genai = None


def inyectar_atajo_teclado():
    """Inyecta un listener global de JavaScript para el atajo Ctrl+K / Cmd+K"""
    js_code = """
    <script>
    const doc = window.parent.document;
    
    // Evitamos duplicar listeners si Streamlit recarga la página
    if (!doc.getElementById('vq-keyboard-listener')) {
        const scriptTag = doc.createElement('div');
        scriptTag.id = 'vq-keyboard-listener';
        scriptTag.style.display = 'none';
        doc.body.appendChild(scriptTag);

        doc.addEventListener('keydown', function(e) {
            // Detecta Ctrl+K en Windows/Linux o Cmd+K en Mac
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault(); // Evita que el navegador abra su propio buscador
                
                // Busca el input dentro del primer selectbox de Streamlit (El buscador de Empresa)
                const inputs = doc.querySelectorAll('.stSelectbox input');
                if (inputs.length > 0) {
                    inputs[0].focus();
                    
                    // Efecto visual: Resalta la barra momentáneamente
                    const container = inputs[0].closest('div[data-baseweb="select"]');
                    if (container) {
                        const originalBoxShadow = container.style.boxShadow;
                        container.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.6)';
                        setTimeout(() => {
                            container.style.boxShadow = originalBoxShadow;
                        }, 400);
                    }
                }
            }
        });
    }
    </script>
    """
    # Inyectamos el HTML sin que ocupe espacio visual en la web
    components.html(js_code, height=0, width=0)


def load_lottieurl(url: str):
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def obtener_secreto_streamlit(nombre: str):
    """Lee un secreto sin bloquear la app cuando no existe secrets.toml."""
    try:
        return st.secrets.get(nombre)
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def obtener_modelo_gemini():
    """Inicializa Gemini una sola vez y evita repetir list_models en cada prompt."""
    api_key = CONFIG.gemini_api_key or CONFIG.google_api_key
    if not api_key:
        return None

    if genai is None:
        return None

    try:
        genai.configure(api_key=api_key)
        modelo_disponible = None
        for modelo in genai.list_models():
            if 'generateContent' in modelo.supported_generation_methods:
                modelo_disponible = modelo.name
                if "flash" in modelo.name.lower():
                    break
        return genai.GenerativeModel(modelo_disponible) if modelo_disponible else None
    except Exception:
        return None

