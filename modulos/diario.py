"""Diario de decisiones: el bucle de aprendizaje del terminal.

Por qué un diario y no más indicadores
--------------------------------------
El resto del terminal responde a "¿qué hago?". Este módulo responde a una
pregunta distinta y a la larga más rentable: "¿qué me funciona a mí?".

La diferencia importa porque la expectativa que publica el backtest es la de la
regla ejecutada mecánicamente, y nadie opera así. Se salta entradas por dudas, se
cierra antes de tiempo, se aguanta de más. El diario mide lo que realmente
ocurrió, y al cruzar el resultado con el motivo de la entrada aparece el patrón
propio: qué setups aguantas bien, en qué régimen te equivocas, y si tus salidas
mejoran o empeoran el resultado de la regla.

Registrar también lo descartado
-------------------------------
Se anotan las operaciones NO tomadas a propósito. Un diario que sólo guarda lo
ejecutado tiene un sesgo de supervivencia evidente: nunca sabrás si las que
descartaste habrían funcionado, y por tanto nunca sabrás si tu filtro añade
valor o sólo te quita oportunidades.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DB_FOLDER = "data"
DB_FILE = os.path.join(DB_FOLDER, "diario.json")

EJECUTADA = "ejecutada"
DESCARTADA = "descartada"
CERRADA = "cerrada"

ESTADOS = (EJECUTADA, DESCARTADA, CERRADA)

# Motivos de descarte y de cierre predefinidos: en texto libre cada entrada se
# escribe distinta y luego no hay forma de agrupar nada. Con una lista cerrada
# el análisis posterior es posible.
MOTIVOS_DESCARTE = (
    "No me convence el fundamental",
    "Ya tengo demasiada exposición al sector",
    "El stop queda demasiado lejos",
    "No entiendo el negocio",
    "Régimen de mercado desfavorable",
    "Falta de liquidez o valor demasiado pequeño",
    "Otro",
)

MOTIVOS_CIERRE = (
    "Saltó el stop",
    "Alcanzó el objetivo",
    "Señal técnica de salida",
    "Cerré por nervios / dudas",
    "Necesitaba el capital",
    "La tesis dejó de ser válida",
    "Otro",
)


def _inicializar() -> None:
    os.makedirs(DB_FOLDER, exist_ok=True)
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as fichero:
            json.dump([], fichero)


def cargar_diario() -> list[dict[str, Any]]:
    """Lee el diario completo. Un JSON corrupto no debe tumbar la pantalla."""
    _inicializar()
    try:
        with open(DB_FILE, "r", encoding="utf-8") as fichero:
            datos = json.load(fichero)
        return datos if isinstance(datos, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Diario ilegible (%s); se parte de vacío.", type(exc).__name__)
        return []


def _guardar(entradas: list[dict[str, Any]]) -> None:
    _inicializar()
    try:
        with open(DB_FILE, "w", encoding="utf-8") as fichero:
            json.dump(entradas, fichero, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.warning("No se pudo escribir el diario: %s", exc)


def _ahora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def registrar_decision(
    ticker: str,
    estado: str,
    *,
    estrategia: str = "",
    direccion: str = "largo",
    precio: float | None = None,
    stop: float | None = None,
    objetivo: float | None = None,
    acciones: int | None = None,
    regimen: str = "",
    motivo: str = "",
    tesis: str = "",
    fuerza: float | None = None,
) -> str:
    """Registra una decisión y devuelve su identificador."""
    simbolo = str(ticker or "").strip().upper()
    if not simbolo or estado not in ESTADOS:
        return ""

    entrada = {
        "id": uuid.uuid4().hex[:12],
        "timestamp": _ahora(),
        "ticker": simbolo,
        "estado": estado,
        "estrategia": estrategia,
        "direccion": direccion,
        "precio": precio,
        "stop": stop,
        "objetivo": objetivo,
        "acciones": acciones,
        "regimen": regimen,
        "motivo": motivo,
        "tesis": tesis,
        "fuerza": fuerza,
    }

    entradas = cargar_diario()
    entradas.append(entrada)
    _guardar(entradas)
    return entrada["id"]


def cerrar_operacion(
    id_entrada: str,
    *,
    precio_salida: float,
    motivo: str = "",
    notas: str = "",
) -> bool:
    """Cierra una operación abierta y calcula su resultado en R.

    El resultado se calcula con el stop registrado en la apertura, no con uno
    reconstruido después: medir el riesgo a posteriori permitiría maquillar el
    resultado eligiendo la referencia que mejor quede.
    """
    entradas = cargar_diario()
    for entrada in entradas:
        if entrada.get("id") != id_entrada:
            continue
        if entrada.get("estado") != EJECUTADA:
            return False

        entrada["estado"] = CERRADA
        entrada["precio_salida"] = precio_salida
        entrada["fecha_cierre"] = _ahora()
        entrada["motivo_cierre"] = motivo
        entrada["notas_cierre"] = notas

        try:
            precio = float(entrada.get("precio") or 0)
            stop = float(entrada.get("stop") or 0)
            largo = entrada.get("direccion", "largo") == "largo"
            riesgo = abs(precio - stop)
            if riesgo > 0 and precio > 0:
                movimiento = (precio_salida - precio) if largo else (precio - precio_salida)
                entrada["resultado_r"] = round(movimiento / riesgo, 3)
                entrada["resultado_pct"] = round(movimiento / precio * 100.0, 2)
        except (TypeError, ValueError):
            entrada["resultado_r"] = None

        _guardar(entradas)
        return True
    return False


def operaciones_abiertas() -> list[dict[str, Any]]:
    return [e for e in cargar_diario() if e.get("estado") == EJECUTADA]


def diario_a_dataframe() -> pd.DataFrame:
    entradas = cargar_diario()
    if not entradas:
        return pd.DataFrame()

    df = pd.DataFrame(entradas)
    df["Fecha"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True, format="ISO8601")
    return df.dropna(subset=["Fecha"]).sort_values("Fecha", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# Análisis: qué te funciona a ti
# --------------------------------------------------------------------------


def rendimiento_por_estrategia(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Resultado real por estrategia, sólo con operaciones ya cerradas."""
    datos = df if df is not None else diario_a_dataframe()
    if datos.empty or "resultado_r" not in datos.columns:
        return pd.DataFrame()

    cerradas = datos[(datos["estado"] == CERRADA) & datos["resultado_r"].notna()].copy()
    if cerradas.empty:
        return pd.DataFrame()

    cerradas["resultado_r"] = pd.to_numeric(cerradas["resultado_r"], errors="coerce")
    resumen = (
        cerradas.groupby("estrategia")
        .agg(
            Operaciones=("resultado_r", "size"),
            Expectativa_R=("resultado_r", "mean"),
            Acierto_pct=("resultado_r", lambda s: (s > 0).mean() * 100.0),
            Mejor=("resultado_r", "max"),
            Peor=("resultado_r", "min"),
        )
        .reset_index()
        .rename(columns={"estrategia": "Estrategia", "Expectativa_R": "Expectativa (R)", "Acierto_pct": "Acierto %"})
    )
    for columna in ("Expectativa (R)", "Acierto %", "Mejor", "Peor"):
        resumen[columna] = resumen[columna].round(3)
    return resumen.sort_values("Expectativa (R)", ascending=False).reset_index(drop=True)


def rendimiento_por_motivo_cierre(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Cuánto cuesta cada forma de salir.

    Es el cruce que más suele sorprender: revela si cerrar "por nervios" está
    saliendo sistemáticamente más caro que dejar que salte el stop.
    """
    datos = df if df is not None else diario_a_dataframe()
    if datos.empty or "motivo_cierre" not in datos.columns:
        return pd.DataFrame()

    cerradas = datos[(datos["estado"] == CERRADA) & datos["resultado_r"].notna()].copy()
    if cerradas.empty:
        return pd.DataFrame()

    cerradas["resultado_r"] = pd.to_numeric(cerradas["resultado_r"], errors="coerce")
    resumen = (
        cerradas.groupby("motivo_cierre")
        .agg(Operaciones=("resultado_r", "size"), Resultado_medio_R=("resultado_r", "mean"))
        .reset_index()
        .rename(columns={"motivo_cierre": "Motivo de cierre", "Resultado_medio_R": "Resultado medio (R)"})
    )
    resumen["Resultado medio (R)"] = resumen["Resultado medio (R)"].round(3)
    return resumen.sort_values("Resultado medio (R)", ascending=False).reset_index(drop=True)


def resumen_global(df: pd.DataFrame | None = None) -> dict[str, Any]:
    """Cifras de cabecera del diario."""
    datos = df if df is not None else diario_a_dataframe()
    if datos.empty:
        return {"total": 0, "ejecutadas": 0, "descartadas": 0, "cerradas": 0,
                "expectativa_r": None, "acierto_pct": None, "ratio_descarte": None}

    cerradas = datos[(datos["estado"] == CERRADA)].copy()
    erres = pd.to_numeric(cerradas.get("resultado_r"), errors="coerce").dropna() if not cerradas.empty else pd.Series(dtype=float)

    ejecutadas = int((datos["estado"] == EJECUTADA).sum()) + len(cerradas)
    descartadas = int((datos["estado"] == DESCARTADA).sum())
    consideradas = ejecutadas + descartadas

    return {
        "total": int(len(datos)),
        "ejecutadas": int((datos["estado"] == EJECUTADA).sum()),
        "descartadas": descartadas,
        "cerradas": int(len(cerradas)),
        "expectativa_r": round(float(erres.mean()), 3) if not erres.empty else None,
        "acierto_pct": round(float((erres > 0).mean() * 100.0), 1) if not erres.empty else None,
        "ratio_descarte": round(descartadas / consideradas * 100.0, 1) if consideradas else None,
    }
