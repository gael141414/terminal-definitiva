"""Alternative data module: Congress trading and news sentiment."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from modulos.config import CONFIG
from modulos.fmp_api import (
    BASE_URL,
    FMP_API_KEY,
    FMP_STATUS_DISABLED,
    FMP_STATUS_MESSAGES,
    FMP_STATUS_NO_DATA,
    FMP_STATUS_OK,
    REQUEST_TIMEOUT,
    fetch_fmp_json_classified,
)


SENATE_ENDPOINT = "https://financialmodelingprep.com/api/v4/senate-trading"
HOUSE_ENDPOINT = "https://financialmodelingprep.com/api/v4/senate-disclosure"
NEWS_ENDPOINT = f"{BASE_URL}/stock_news"


POSITIVE_WORDS = {
    "beat",
    "beats",
    "growth",
    "record",
    "upgrade",
    "surge",
    "strong",
    "raises",
    "raised",
    "hikes",
    "bull",
    "upside",
    "profit",
    "approval",
    "partnership",
    "buyback",
}

NEGATIVE_WORDS = {
    "miss",
    "downgrade",
    "lawsuit",
    "probe",
    "fall",
    "falls",
    "weak",
    "loss",
    "cuts",
    "warning",
    "cautious",
    "stretched",
    "sold",
    "delay",
    "inflation",
    "margin pressure",
}

def _style_congress(row):
    """Sombreado verde para compras y rojo para ventas de políticos."""
    tipo = str(row.get("type", "")).lower()
    if "purchase" in tipo or "buy" in tipo:
        return ["background-color: rgba(54, 196, 134, 0.12)"] * len(row)
    elif "sale" in tipo or "sell" in tipo:
        return ["background-color: rgba(239, 91, 107, 0.12)"] * len(row)
    return [""] * len(row)

def _style_news(row):
    """Sombreado según el sentimiento de la noticia."""
    sentimiento = str(row.get("sentimentLabel", "")).lower()
    if "positive" in sentimiento:
        return ["background-color: rgba(54, 196, 134, 0.12)"] * len(row)
    elif "negative" in sentimiento:
        return ["background-color: rgba(239, 91, 107, 0.12)"] * len(row)
    return [""] * len(row)

def _request_list(url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """GET helper that always returns a list."""
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_congress_trading(ticker: str) -> pd.DataFrame:
    """Fetch Senate trading data from FMP.

    Args:
        ticker: Stock ticker.

    Returns:
        DataFrame with political trading disclosures.
    """
    rows = _request_list(SENATE_ENDPOINT, {"ticker": ticker.upper(), "apikey": FMP_API_KEY})
    if not rows:
        rows = _request_list(HOUSE_ENDPOINT, {"ticker": ticker.upper(), "apikey": FMP_API_KEY})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for column in ("transactionDate", "disclosureDate"):
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    return df.sort_values([col for col in ("transactionDate", "disclosureDate") if col in df.columns], ascending=False)


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_fmp_news(ticker: str, limit: int = 20) -> tuple[pd.DataFrame, str]:
    """Fetch latest stock news from FMP.

    Devuelve ``(DataFrame, status)``. ``status`` distingue por qué no hay
    noticias (desactivado por configuración, plan restringido, rate limit,
    fallo del proveedor, o simplemente sin resultados) para que la UI pueda
    mostrar un mensaje preciso en vez de un genérico "sin datos" — y para que
    un 402 (endpoint fuera de plan) nunca se confunda con una clave inválida
    ni marque toda la integración FMP como caída.

    Las noticias son opcionales: un fallo aquí nunca debe propagar una
    excepción — el resto del análisis (perfil, cotización, financieros) no
    depende de esta función.
    """
    if not CONFIG.fmp_news_enabled:
        return pd.DataFrame(), FMP_STATUS_DISABLED

    payload, status = fetch_fmp_json_classified(
        NEWS_ENDPOINT,
        {"tickers": ticker.upper(), "limit": limit, "apikey": FMP_API_KEY},
        context=f"alt_data:news:{ticker.upper()}",
    )
    if status != FMP_STATUS_OK or not payload:
        return pd.DataFrame(), status

    df = pd.DataFrame(payload)
    if "publishedDate" in df.columns:
        df["publishedDate"] = pd.to_datetime(df["publishedDate"], errors="coerce")
    return df, FMP_STATUS_OK


def score_headline_sentiment(title: str) -> float:
    """Deterministic financial headline sentiment score in [-1, 1]."""
    text = str(title or "").lower()
    positive = sum(1 for word in POSITIVE_WORDS if word in text)
    negative = sum(1 for word in NEGATIVE_WORDS if word in text)
    if positive == 0 and negative == 0:
        return 0.0
    return float(np.clip((positive - negative) / max(positive + negative, 1), -1, 1))


def aggregate_media_sentiment(news: pd.DataFrame) -> tuple[float | None, pd.DataFrame]:
    """Compute 0-100 media sentiment gauge value.

    Devuelve ``None`` (no disponible) cuando no hay noticias que analizar —
    en vez de un valor "neutral" (50.0) inventado, que ocultaría que en
    realidad no hay datos y podría leerse como una señal real.
    """
    if news.empty or "title" not in news.columns:
        return None, news
    result = news.copy()
    result["sentimentScore"] = result["title"].map(score_headline_sentiment)
    result["sentimentLabel"] = pd.cut(
        result["sentimentScore"],
        bins=[-1.01, -0.2, 0.2, 1.01],
        labels=["Negativo", "Neutral", "Positivo"],
    )
    gauge = float(np.clip(50 + result["sentimentScore"].mean() * 50, 0, 100))
    return gauge, result


def build_sentiment_gauge(score: float) -> go.Figure:
    """Build a 0-100 media sentiment gauge."""
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": "/100"},
            title={"text": "Sentimiento Mediático"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#38bdf8"},
                "steps": [
                    {"range": [0, 35], "color": "rgba(239,68,68,0.35)"},
                    {"range": [35, 65], "color": "rgba(250,204,21,0.35)"},
                    {"range": [65, 100], "color": "rgba(34,197,94,0.35)"},
                ],
            },
        )
    )
    fig.update_layout(height=330, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
    return fig


def _style_congress(row: pd.Series) -> list[str]:
    """Conditional style for political trades."""
    text = " ".join(str(value).lower() for value in row.values)
    if "purchase" in text or "buy" in text or "compra" in text:
        return ["background-color: rgba(34,197,94,0.18)"] * len(row)
    if "sale" in text or "sell" in text or "venta" in text:
        return ["background-color: rgba(239,68,68,0.15)"] * len(row)
    return [""] * len(row)


def render_alt_data(ticker: str) -> None:
    """Render alternative data dashboard."""
    st.markdown(f"### 🕵️ Alt Data & Insider Congress — {ticker}")
    st.caption("Flujo político y sentimiento mediático para detectar señales de alpha no tradicionales.")

    with st.spinner("Descargando operaciones políticas y noticias FMP..."):
        congress = fetch_congress_trading(ticker)
        news, news_status = fetch_fmp_news(ticker, 20)
        gauge, scored_news = aggregate_media_sentiment(news)

    c1, c2, c3 = st.columns(3)
    c1.metric("Trades políticos", len(congress))
    c2.metric("Noticias analizadas", len(scored_news))
    c3.metric("Score mediático", f"{gauge:.0f}/100" if gauge is not None else "N/D")

    if gauge is not None:
        st.plotly_chart(build_sentiment_gauge(gauge), use_container_width=True)
    else:
        st.info(f"Sentimiento mediático: N/D — {FMP_STATUS_MESSAGES.get(news_status, 'no hay noticias disponibles para calcularlo.')}")

    st.markdown("#### Operaciones políticas recientes")
    if congress.empty:
        st.info("No se encontraron operaciones políticas recientes para este ticker en FMP.")
    else:
        visible_cols = [col for col in ["transactionDate", "disclosureDate", "senator", "representative", "assetDescription", "type", "amount", "owner", "link"] if col in congress.columns]
        st.dataframe(
            congress[visible_cols].head(25).style.apply(_style_congress, axis=1), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "link": st.column_config.LinkColumn(
                    "Documento SEC",
                    help="Abrir el registro oficial",
                    display_text="Ver reporte 📄"
                )
            }
        )

    st.markdown("#### News Sentiment")
    if scored_news.empty:
        if news_status == FMP_STATUS_NO_DATA:
            st.info("FMP no devolvió titulares recientes para este ticker.")
        else:
            st.info(FMP_STATUS_MESSAGES.get(news_status, "Noticias no disponibles."))
    else:
        visible = [col for col in ["publishedDate", "title", "site", "sentimentLabel", "sentimentScore", "url"] if col in scored_news.columns]
        st.dataframe(
            scored_news[visible].style.apply(_style_news, axis=1), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "url": st.column_config.LinkColumn(
                    "Fuente",
                    help="Leer artículo completo",
                    display_text="Leer noticia 🔗"
                )
            }
        )