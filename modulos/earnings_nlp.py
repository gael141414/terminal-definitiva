from __future__ import annotations

import re
from datetime import date

import pandas as pd
import requests
import streamlit as st

from modulos.fmp_api import FMP_API_KEY
from modulos.gemini_helper import obtener_modelo_gemini
from modulos.utils import analizar_sentimiento_noticias


BASE_URL = "https://financialmodelingprep.com/api/v3"
REQUEST_TIMEOUT = 20


@st.cache_data(ttl=86400, show_spinner=False)
def descargar_transcripcion_fmp(ticker: str, year: int, quarter: int) -> dict | None:
    """Descarga una transcripción de earnings call desde FMP si el plan lo permite."""
    symbol = ticker.upper().strip()
    endpoints = [
        (
            f"{BASE_URL}/earning_call_transcript/{symbol}",
            {"year": year, "quarter": quarter, "apikey": FMP_API_KEY},
        ),
        (
            f"https://financialmodelingprep.com/stable/earning-call-transcript",
            {"symbol": symbol, "year": year, "quarter": quarter, "apikey": FMP_API_KEY},
        ),
    ]

    for url, params in endpoints:
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list) and payload:
                item = payload[0]
                if isinstance(item, dict) and (item.get("content") or item.get("transcript")):
                    return item
            if isinstance(payload, dict) and (payload.get("content") or payload.get("transcript")):
                return payload
        except Exception:
            continue
    return None


def _extraer_bullets_local(texto: str) -> dict[str, object]:
    clean = re.sub(r"\s+", " ", texto or "").strip()
    lower = clean.lower()
    positivos = sum(lower.count(word) for word in ["strong", "growth", "record", "improve", "demand", "opportunity"])
    negativos = sum(lower.count(word) for word in ["inflation", "pressure", "weak", "decline", "headwind", "uncertain", "slowdown"])
    guidance_hits = [m.group(0) for m in re.finditer(r"guidance|outlook|next quarter|fiscal year|expect", lower)]

    tono = "Optimista" if positivos > negativos + 2 else "Pesimista" if negativos > positivos + 2 else "Mixto/Prudente"
    problemas = []
    for etiqueta, palabras in {
        "Inflación / costes": ["inflation", "cost pressure", "pricing"],
        "Demanda": ["demand", "consumer", "orders"],
        "Cadena de suministro": ["supply", "inventory", "logistics"],
        "Tipos / macro": ["rates", "macro", "uncertain"],
    }.items():
        if any(p in lower for p in palabras):
            problemas.append(etiqueta)

    return {
        "tono": tono,
        "problemas": problemas or ["No se detectan problemas dominantes por palabras clave."],
        "guidance": "Mencionan guidance/outlook." if guidance_hits else "No se detecta guidance explícito por palabras clave.",
        "resumen": clean[:1200] + ("..." if len(clean) > 1200 else ""),
    }


def _resumir_con_ia(ticker: str, transcript: str) -> str | None:
    model = obtener_modelo_gemini()
    if model is None:
        return None

    prompt = f"""
    Analiza esta transcripción de earnings call de {ticker}. Responde en español con:
    1. Tono de la directiva: Optimista, prudente o pesimista.
    2. Problemas mencionados: inflación, demanda, supply chain, márgenes, deuda, competencia.
    3. Guidance: qué esperan para el próximo trimestre/año.
    4. Señales de alerta: evasivas, lenguaje defensivo o contradicciones.

    Transcripción:
    {transcript[:18000]}
    """
    try:
        response = model.generate_content(prompt)
        return getattr(response, "text", None)
    except Exception:
        return None


def ejecutar_earnings_nlp(ticker_input: str):
    st.markdown(f"### 🧠 Earnings Call NLP: {ticker_input}")
    st.caption("Analiza el lenguaje de la directiva: tono, problemas mencionados y guidance.")

    current_year = date.today().year
    c1, c2 = st.columns(2)
    year = c1.number_input("Año fiscal", min_value=2010, max_value=current_year + 1, value=current_year, step=1)
    quarter = c2.selectbox("Trimestre", [1, 2, 3, 4], index=0)

    with st.spinner("Buscando transcripción y analizando narrativa..."):
        transcript_obj = descargar_transcripcion_fmp(ticker_input, int(year), int(quarter))

        if transcript_obj:
            transcript = transcript_obj.get("content") or transcript_obj.get("transcript") or ""
            st.success("Transcripción encontrada.")
            resumen_ia = _resumir_con_ia(ticker_input, transcript)
            if resumen_ia:
                st.markdown(resumen_ia)
            else:
                local = _extraer_bullets_local(transcript)
                st.info("IA generativa no disponible; usando análisis local por NLP.")
                st.metric("Tono directiva", local["tono"])
                st.write("**Problemas detectados:**", ", ".join(local["problemas"]))
                st.write("**Guidance:**", local["guidance"])
                with st.expander("Fragmento de transcripción"):
                    st.write(local["resumen"])
        else:
            st.warning("No se pudo descargar la transcripción desde FMP para ese trimestre. Muestro sentimiento de noticias como fallback.")
            noticias, sentimiento = analizar_sentimiento_noticias(ticker_input)
            st.metric("Sentimiento noticias", f"{sentimiento:+.2f}")
            if noticias:
                df = pd.DataFrame(noticias)
                st.dataframe(df[["Titular", "Fuente", "Sentimiento", "Polaridad"]], use_container_width=True, hide_index=True)
