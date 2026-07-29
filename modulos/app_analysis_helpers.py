from __future__ import annotations

from modulos.utils import analizar_sentimiento_noticias as analizar_sentimiento_noticias_utils
from modulos.utils import escanear_vulnerabilidades


def analizar_sentimiento_noticias(ticker):
    """Compatibilidad: delega en el motor NLP robusto de modulos.utils."""
    return analizar_sentimiento_noticias_utils(ticker)


def ultimo_ratio(resultado, columna):
    """Extrae el último dato no nulo de un dataframe o diccionario de ratios."""
    try:
        df = resultado.get("ratios") if isinstance(resultado, dict) else resultado
        if df is not None and columna in df.columns:
            serie = df[columna].dropna()
            return serie.iloc[-1] if not serie.empty else None
    except Exception:
        return None
    return None

