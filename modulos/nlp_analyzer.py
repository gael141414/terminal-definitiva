"""NLP analyzer for earnings call transcripts.

This module is intentionally isolated from the rest of the Streamlit app so the
data extraction and LLM analysis can be tested independently.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal, TypedDict

import requests
import streamlit as st

from modulos.fmp_api import FMP_API_KEY


FMP_TRANSCRIPT_URL = "https://financialmodelingprep.com/api/v3/earning_call_transcript/{ticker}"
REQUEST_TIMEOUT = 25
Tone = Literal["Optimista", "Neutral", "Pesimista"]


class TranscriptAnalysis(TypedDict):
    """Structured output returned by the LLM."""

    tono: str
    red_flags: list[str]
    guidance: str


def _read_secret(name: str) -> str | None:
    """Read a secret from Streamlit or environment variables.

    Args:
        name: Secret/environment variable name.

    Returns:
        Secret value or ``None`` if unavailable.
    """
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name)


def get_latest_transcript(ticker: str, api_key: str) -> str | None:
    """Download the latest earnings call transcript from FMP.

    Args:
        ticker: Stock ticker, for example ``"AAPL"``.
        api_key: Financial Modeling Prep API key.

    Returns:
        Transcript text if FMP returns one, otherwise ``None``.
    """
    try:
        symbol = ticker.upper().strip()
        if not symbol or not api_key:
            return None

        response = requests.get(
            FMP_TRANSCRIPT_URL.format(ticker=symbol),
            params={"apikey": api_key},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload: Any = response.json()

        if isinstance(payload, list) and payload:
            for item in payload:
                if isinstance(item, dict):
                    transcript = item.get("content") or item.get("transcript")
                    if transcript:
                        return str(transcript)
        if isinstance(payload, dict):
            transcript = payload.get("content") or payload.get("transcript")
            if transcript:
                return str(transcript)
        return None
    except Exception:
        return None


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from an LLM response."""
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _validate_analysis(raw: dict[str, Any]) -> TranscriptAnalysis:
    """Normalize LLM output to the exact schema required by the UI."""
    tono = str(raw.get("tono", "Neutral")).strip()
    if not any(tono.startswith(valid) for valid in ("Optimista", "Neutral", "Pesimista")):
        tono = "Neutral - No hay señal dominante en la narrativa."

    red_flags_raw = raw.get("red_flags", [])
    if isinstance(red_flags_raw, str):
        red_flags = [red_flags_raw]
    elif isinstance(red_flags_raw, list):
        red_flags = [str(item) for item in red_flags_raw if str(item).strip()]
    else:
        red_flags = []

    guidance = str(raw.get("guidance", "Guidance no identificado.")).strip()
    return {
        "tono": tono,
        "red_flags": red_flags or ["Sin red flags explícitas detectadas."],
        "guidance": guidance,
    }


def _fallback_local_analysis(transcript_text: str) -> TranscriptAnalysis:
    """Rule-based fallback when no LLM key/client is available."""
    lower = transcript_text.lower()
    positive_terms = ("strong demand", "record", "growth", "accelerate", "margin expansion", "confident")
    negative_terms = ("inflation", "delay", "headwind", "margin pressure", "weak demand", "slowdown", "uncertain")
    positive = sum(lower.count(term) for term in positive_terms)
    negative = sum(lower.count(term) for term in negative_terms)

    if positive > negative + 2:
        tono = "Optimista - La directiva repite lenguaje de crecimiento y confianza."
    elif negative > positive + 2:
        tono = "Pesimista - Dominan referencias a presión, incertidumbre o debilidad."
    else:
        tono = "Neutral - La narrativa combina oportunidades y riesgos sin sesgo claro."

    flags = []
    for label, terms in {
        "Inflación/costes": ("inflation", "cost pressure", "pricing pressure"),
        "Retrasos o supply chain": ("delay", "supply chain", "logistics"),
        "Caída de márgenes": ("margin pressure", "gross margin decline", "lower margins"),
        "Demanda débil": ("weak demand", "slowdown", "softness"),
    }.items():
        if any(term in lower for term in terms):
            flags.append(label)

    guidance = "No se detecta guidance explícito." if "guidance" not in lower and "outlook" not in lower else (
        "La transcripción contiene referencias a guidance/outlook; revisa si elevan o recortan expectativas."
    )

    return {"tono": tono, "red_flags": flags or ["Sin red flags explícitas detectadas."], "guidance": guidance}


def analyze_transcript_with_llm(transcript_text: str, openai_api_key: str | None) -> TranscriptAnalysis:
    """Analyze an earnings call transcript with an OpenAI-compatible LLM.

    The function uses the official ``openai`` client. If ``GROQ_API_KEY`` is
    available, it uses Groq's OpenAI-compatible endpoint for speed. Otherwise it
    uses ``OPENAI_API_KEY`` / the provided ``openai_api_key``.

    Args:
        transcript_text: Raw transcript text.
        openai_api_key: OpenAI API key. A Groq key is also accepted when it
            starts with ``gsk_``.

    Returns:
        JSON-like dict with exactly ``tono``, ``red_flags`` and ``guidance``.
    """
    try:
        from openai import OpenAI

        groq_key = _read_secret("GROQ_API_KEY")
        api_key = groq_key or openai_api_key or _read_secret("OPENAI_API_KEY")
        if not api_key:
            return _fallback_local_analysis(transcript_text)

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        model = "gpt-4o-mini"
        if groq_key or str(api_key).startswith("gsk_"):
            client_kwargs["base_url"] = "https://api.groq.com/openai/v1"
            model = "llama-3.3-70b-versatile"

        client = OpenAI(**client_kwargs)
        system_prompt = (
            "Eres un analista financiero senior especializado en earnings calls. "
            "Devuelve SOLO JSON valido con exactamente estas 3 claves: "
            "tono, red_flags, guidance. "
            "tono debe ser un string empezando por Optimista, Neutral o Pesimista "
            "y una justificacion de 1 linea. red_flags debe ser una lista de strings. "
            "guidance debe ser un resumen de 2 lineas de las previsiones futuras."
        )
        user_prompt = f"Transcript:\n{transcript_text[:24000]}"

        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        parsed = _extract_json(content)
        return _validate_analysis(parsed or {})
    except Exception:
        return _fallback_local_analysis(transcript_text)


def render_nlp_dashboard(ticker: str) -> None:
    """Render the Streamlit dashboard for earnings call sentiment analysis.

    Args:
        ticker: Stock ticker selected in the main app.
    """
    st.markdown(f"### 🧠 NLP Earnings Calls: {ticker}")
    st.caption("Descarga la última transcripción de resultados y extrae tono, red flags y guidance.")

    if not st.button("Analizar última earnings call", type="primary", use_container_width=True):
        return

    with st.spinner("Descargando transcripción desde FMP..."):
        transcript = get_latest_transcript(ticker, FMP_API_KEY)

    if not transcript:
        st.error("No se pudo descargar la última transcripción desde FMP para este ticker o plan de API.")
        return

    with st.spinner("Analizando narrativa de la directiva con LLM..."):
        analysis = analyze_transcript_with_llm(transcript, _read_secret("OPENAI_API_KEY"))

    tone = analysis["tono"]
    if tone.startswith("Optimista"):
        st.success(f"**Tono:** {tone}")
    elif tone.startswith("Pesimista"):
        st.error(f"**Tono:** {tone}")
    else:
        st.info(f"**Tono:** {tone}")

    st.markdown("#### Red Flags")
    for red_flag in analysis["red_flags"]:
        st.warning(red_flag)

    st.markdown("#### Guidance")
    st.info(analysis["guidance"])

    with st.expander("Ver fragmento de transcripción"):
        st.write(transcript[:2500] + ("..." if len(transcript) > 2500 else ""))
