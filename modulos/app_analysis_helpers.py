from __future__ import annotations

from modulos.utils import analizar_sentimiento_noticias as analizar_sentimiento_noticias_utils


def escanear_vulnerabilidades(res_is, res_bs, res_cf):
    """Escanea los estados financieros en busca de Red Flags críticas."""
    alertas = []
    
    # Función auxiliar rápida
    def get_last(df, col):
        if df is not None and col in df.columns:
            s = df[col].dropna()
            return s.iloc[-1] if not s.empty else None
        return None

    # 1. Riesgo de Quiebra (Deuda)
    deuda_cap = get_last(res_bs["ratios"], "Deuda / Capital")
    if deuda_cap and deuda_cap > 1.2:
        alertas.append(f"🚨 **Apalancamiento Peligroso:** Deuda altísima ({deuda_cap:.2f}x el capital). Muy vulnerable a subidas de tipos de interés.")

    # 2. Hemorragia de Efectivo
    fcf = get_last(res_cf["ratios"], "Free Cash Flow (B USD)")
    if fcf and fcf < 0:
        alertas.append(f"🔥 **Quema de Caja:** El Free Cash Flow es negativo (${fcf:.2f}B). La empresa está perdiendo dinero real y podría necesitar emitir acciones o más deuda.")

    # 3. Rentabilidad Basura (Márgenes)
    margen_neto = get_last(res_is["ratios"], "Margen Neto %")
    if margen_neto and margen_neto < 5:
        alertas.append(f"⚠️ **Márgenes Críticos:** El margen neto es solo del {margen_neto:.1f}%. La empresa no tiene poder de fijación de precios (Moat débil).")

    # 4. Destrucción de Valor (ROIC)
    roic = get_last(res_bs["ratios"], "ROIC %")
    if roic and roic < 7:
        alertas.append(f"📉 **Destrucción de Capital:** El ROIC ({roic:.1f}%) es menor que el coste de capital promedio. Crecer destruye valor para el accionista.")

    return alertas


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

