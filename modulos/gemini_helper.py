from __future__ import annotations

import os

import google.generativeai as genai
import streamlit as st


def _leer_secreto(nombre: str) -> str | None:
    try:
        valor = st.secrets.get(nombre)
        return str(valor).strip() if valor else None
    except Exception:
        return None


def obtener_api_key_gemini() -> str | None:
    """Lee la clave de Gemini desde Streamlit secrets o variables de entorno."""
    return (
        _leer_secreto("GEMINI_API_KEY")
        or _leer_secreto("GOOGLE_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )


@st.cache_resource(show_spinner=False)
def obtener_modelo_gemini():
    """Inicializa Gemini solo si existe una API key configurada."""
    api_key = obtener_api_key_gemini()
    if not api_key:
        return None

    try:
        genai.configure(api_key=api_key)
        modelo_disponible = None
        for modelo in genai.list_models():
            if "generateContent" in modelo.supported_generation_methods:
                modelo_disponible = modelo.name
                if "flash" in modelo.name.lower():
                    break
        return genai.GenerativeModel(modelo_disponible) if modelo_disponible else None
    except Exception:
        return None


def aviso_gemini_no_configurado():
    st.info(
        "Gemini no está configurado. La sección seguirá funcionando con análisis cuantitativo local. "
        "Para activar textos IA, añade `GEMINI_API_KEY` o `GOOGLE_API_KEY` en `.streamlit/secrets.toml`."
    )
