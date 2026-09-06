"""¿Predicen algo los pilares de valoración y fundamentales?

La pregunta ha cambiado respecto al encargo original. La validación de salidas
(docs/resultado_validacion_salidas.md) dejó claro dos veces, con diseños
distintos, que ninguna regla de salida bate a aguantar. Así que reconstruir los
pilares A y B para alimentar una regla de venta ya no tiene sentido.

La pregunta útil es la contraria: **¿sirven para SELECCIONAR?** Si el score de
fundamentales de una empresa, calculado con lo que se sabía ese día, ordena el
retorno de los meses siguientes, entonces vale como criterio de compra aunque no
valga como criterio de venta.

Sin look-ahead, de verdad
--------------------------
Cada observación se sitúa el día siguiente a la FECHA DE FILING real, que es
cuando el mercado supo el dato. Nunca en el cierre del ejercicio, que es entre
uno y tres meses antes de que las cuentas existieran públicamente.
``point_in_time_scoring._filtrar_columnas_por_filing_date`` descarta además los
ejercicios cuya fecha de filing se desconoce, en vez de asumir que ya estaban
disponibles.

El precio de referencia y el retorno posterior se toman de la serie de cotización
recortada a esa misma fecha.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("valuequant.validacion_pilares")

__all__ = [
    "ObservacionPilar", "construir_observaciones", "medir_poder_predictivo",
    "tabla_por_decil", "HORIZONTES",
]

# Tres horizontes: si el efecto existe pero tarda, se ve; si solo aparece en uno
# y no en los vecinos, es ruido.
HORIZONTES = (63, 126, 252)

MINIMO_OBSERVACIONES = 40


@dataclass(slots=True)
class ObservacionPilar:
    """Los pilares tal y como se podían calcular ese día, y lo que pasó después."""

    ticker: str
    as_of: str
    filing_date: str
    piotroski: float | None = None
    piotroski_norm: float | None = None     # 0-100, normalizado por evaluados
    altman: float | None = None
    beneish: float | None = None
    percentil_multiplos: float | None = None
    precio: float | None = None
    retornos: dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        base = {
            "ticker": self.ticker, "as_of": self.as_of, "filing_date": self.filing_date,
            "piotroski": self.piotroski, "piotroski_norm": self.piotroski_norm,
            "altman": self.altman, "beneish": self.beneish,
            "percentil_multiplos": self.percentil_multiplos, "precio": self.precio,
        }
        for h, v in self.retornos.items():
            base[f"retorno_{h}d"] = v
        return base


def _retorno_forward(precios: pd.Series, desde: pd.Timestamp, sesiones: int) -> float | None:
    posteriores = precios[precios.index >= desde]
    if len(posteriores) <= sesiones:
        return None
    inicial = float(posteriores.iloc[0])
    if inicial <= 0:
        return None
    return (float(posteriores.iloc[sesiones]) - inicial) / inicial


def construir_observaciones(
    ticker: str,
    precios: pd.Series,
    *,
    puntos: Sequence[dict[str, Any]] | None = None,
    reconstruir: Any = None,
) -> list[ObservacionPilar]:
    """Una observación por filing con retorno posterior ya realizado.

    ``puntos`` y ``reconstruir`` se inyectan en los tests para no tocar la red.
    """
    from modulos.forense_scores import (
        altman_z_score, beneish_m_score, normalizar_estados, piotroski_f_score,
    )
    from modulos.multiplos_historicos import evaluar_multiplos

    # Fuente por defecto: SEC EDGAR. FMP restringe el endpoint as-reported a un
    # puñado de símbolos (403 en el resto), y con 57 valores solo devolvió 15
    # observaciones de 3 empresas. EDGAR responde para todas.
    #
    # Se descarga UNA vez por valor y se filtra por fecha en memoria para cada
    # punto: pedir los estados una vez por punto multiplicaba por seis las
    # llamadas a la SEC sin añadir nada.
    if puntos is None or reconstruir is None:
        import downloader
        from modulos.point_in_time_scoring import _filtrar_columnas_por_filing_date

        try:
            # usar_cache=False a propósito: los filing_dates viajan en .attrs
            # del DataFrame y NO sobreviven al caché en disco. Con caché el
            # filtro por fecha no encuentra ninguna fecha y descarta todos los
            # ejercicios — correctamente, porque es conservador, pero entonces
            # no queda nada que medir. Es lo que hace point_in_time_scoring.
            df_is, df_bs, df_cf, status = downloader.obtener_estados_financieros_con_diagnostico(
                ticker, años=10, usar_cache=False,
            )
        except Exception as exc:
            LOGGER.warning("Sin estados SEC para %s: %s", ticker, exc)
            return []
        if status is not None or df_is is None:
            return []

        fechas: dict[str, str] = {}
        for df in (df_is, df_bs, df_cf):
            if df is not None:
                fechas.update(df.attrs.get("filing_dates", {}))
        if not fechas:
            return []

        if puntos is None:
            puntos = [
                {"ticker": ticker, "fiscal_year": year, "filing_date": fecha,
                 "as_of_date": (pd.Timestamp(fecha) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")}
                for year, fecha in sorted(fechas.items())
            ]

        if reconstruir is None:
            def reconstruir(_ticker: str, as_of: str):
                return tuple(
                    _filtrar_columnas_por_filing_date(df, as_of)
                    for df in (df_is, df_bs, df_cf)
                )

    if precios is None or precios.empty:
        return []
    precios = precios.dropna().sort_index()
    if getattr(precios.index, "tz", None) is not None:
        precios.index = precios.index.tz_localize(None)

    observaciones: list[ObservacionPilar] = []
    for punto in puntos:
        as_of = str(punto.get("as_of_date") or "")
        if not as_of:
            continue
        try:
            fecha = pd.Timestamp(as_of)
        except Exception:
            continue

        try:
            is_df, bs_df, cf_df = reconstruir(ticker, as_of)
        except Exception as exc:
            LOGGER.debug("No se pudo reconstruir %s @ %s: %s", ticker, as_of, exc)
            continue
        if is_df is None or bs_df is None:
            continue

        resultados = normalizar_estados(is_df)
        balance = normalizar_estados(bs_df)
        flujos = normalizar_estados(cf_df)

        anteriores = precios[precios.index <= fecha]
        precio = float(anteriores.iloc[-1]) if not anteriores.empty else None

        observacion = ObservacionPilar(
            ticker=ticker, as_of=as_of,
            filing_date=str(punto.get("filing_date") or ""), precio=precio,
        )

        pf = piotroski_f_score(balance, resultados, flujos)
        if pf.evaluable and pf.evaluados:
            observacion.piotroski = float(pf.valor)
            observacion.piotroski_norm = float(pf.valor / pf.evaluados * 100)

        # El Altman clásico necesita capitalización, que no se reconstruye sin
        # el número de acciones de esa fecha: se usa la doble prima, que emplea
        # patrimonio contable y por tanto sí es point-in-time.
        az = altman_z_score(balance, resultados, modelo="doble_prima")
        if az.evaluable:
            observacion.altman = float(az.valor)

        bm = beneish_m_score(balance, resultados, flujos)
        if bm.evaluable:
            observacion.beneish = float(bm.valor)

        try:
            multiplos = evaluar_multiplos(anteriores, resultados, balance, flujos)
            observacion.percentil_multiplos = multiplos.percentil_medio
        except Exception:
            pass

        for horizonte in HORIZONTES:
            r = _retorno_forward(precios, fecha, horizonte)
            if r is not None:
                observacion.retornos[horizonte] = r

        if observacion.retornos:
            observaciones.append(observacion)

    return observaciones


# ==========================================================================
# MEDICIÓN
# ==========================================================================


# Signo esperado de la correlación con el retorno posterior, según la teoría que
# se está poniendo a prueba. Declararlo evita el truco de celebrar cualquier
# correlación mirando después qué signo salió.
SIGNO_ESPERADO = {
    "piotroski": "positivo",        # más solidez, mejor retorno
    "piotroski_norm": "positivo",
    "altman": "positivo",           # más lejos de la quiebra, mejor retorno
    "beneish": "negativo",          # más indicio de maquillaje, peor retorno
    "percentil_multiplos": "negativo",  # más caro frente a su historia, peor retorno
}


def medir_poder_predictivo(observaciones: Sequence[ObservacionPilar],
                           *, minimo: int = MINIMO_OBSERVACIONES) -> dict[str, Any]:
    """Spearman de cada pilar contra el retorno, por horizonte.

    Spearman y no Pearson: interesa si el ORDEN se respeta, no que la relación
    sea lineal. Con menos de ``minimo`` observaciones no se publica número.
    """
    if not observaciones:
        return {"suficiente": False, "observaciones": 0}

    df = pd.DataFrame([o.to_dict() for o in observaciones])
    salida: dict[str, Any] = {"observaciones": len(df), "suficiente": len(df) >= minimo,
                              "tickers": int(df["ticker"].nunique())}
    if not salida["suficiente"]:
        salida["nota"] = (f"Solo {len(df)} observaciones; hacen falta {minimo} para "
                          "publicar una correlación.")
        return salida

    for pilar, signo in SIGNO_ESPERADO.items():
        if pilar not in df.columns:
            continue
        bloque: dict[str, Any] = {"signo_esperado": signo}
        for horizonte in HORIZONTES:
            columna = f"retorno_{horizonte}d"
            if columna not in df.columns:
                continue
            pareja = df[[pilar, columna]].dropna()
            if len(pareja) < minimo:
                bloque[f"{horizonte}d"] = {"n": len(pareja), "spearman": None}
                continue
            rho = float(pareja[pilar].corr(pareja[columna], method="spearman"))
            bloque[f"{horizonte}d"] = {
                "n": len(pareja),
                "spearman": round(rho, 4),
                "coherente": (rho > 0) if signo == "positivo" else (rho < 0),
            }
        salida[pilar] = bloque

    return salida


def tabla_por_decil(observaciones: Sequence[ObservacionPilar], pilar: str,
                    horizonte: int = 252, *, grupos: int = 5) -> pd.DataFrame:
    """Retorno medio posterior por quintil del pilar.

    Una correlación puede ser pequeña y aun así separar los extremos, que es lo
    que importa para seleccionar. Y al revés: una correlación decente puede venir
    del medio de la distribución y no servir para nada operativo.
    """
    if not observaciones:
        return pd.DataFrame()

    df = pd.DataFrame([o.to_dict() for o in observaciones])
    columna = f"retorno_{horizonte}d"
    if pilar not in df.columns or columna not in df.columns:
        return pd.DataFrame()

    pareja = df[[pilar, columna]].dropna()
    if len(pareja) < grupos * 5:
        return pd.DataFrame()

    try:
        pareja["grupo"] = pd.qcut(pareja[pilar], grupos, labels=False, duplicates="drop")
    except ValueError:
        return pd.DataFrame()

    resumen = pareja.groupby("grupo").agg(
        n=(columna, "size"),
        pilar_medio=(pilar, "mean"),
        retorno_medio=(columna, "mean"),
        retorno_mediano=(columna, "median"),
    )
    resumen["retorno_medio_%"] = (resumen["retorno_medio"] * 100).round(2)
    resumen["retorno_mediano_%"] = (resumen["retorno_mediano"] * 100).round(2)
    return resumen.drop(columns=["retorno_medio", "retorno_mediano"])
