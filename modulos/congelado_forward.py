"""Congelado hacia delante de las decisiones de venta (validación forward).

Por qué esto y no solo un backfill
-----------------------------------
Reconstruir el pasado siempre admite la sospecha de contaminación: por muy bien
que se filtre por fecha de filing, quien escribe el código ya sabe cómo acabó la
historia. Un registro que se va escribiendo HOY, antes de conocer el retorno
posterior, no admite esa sospecha. Es la única validación de la que nadie puede
decir que está contaminada.

Cuesta poco y compone: cada snapshot es una observación más. En un par de
trimestres hay muestra para medir si los sub-scores predicen algo.

Qué se guarda
-------------
Por cada valor y fecha: la acción decidida, el sell score, los tres sub-scores y
el precio del momento. El precio es lo que después permite calcular el retorno
posterior sin volver a pedir histórico ajustado.

Qué NO se guarda: nada que se pueda recalcular después. El objetivo es un
registro pequeño que se pueda mantener años.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

LOGGER = logging.getLogger("valuequant.congelado")

__all__ = [
    "RegistroCongelado", "FICHERO_CONGELADO", "INICIO_CONGELADO",
    "congelar_universo", "guardar_registros", "cargar_registros",
    "cruzar_con_retorno_posterior", "resumen_poder_predictivo",
]

CARPETA_DATOS = "data"
FICHERO_CONGELADO = os.path.join(CARPETA_DATOS, "decisiones_congeladas.json")

# Fecha en que empieza el registro forward. Cualquier observación anterior sería
# un backfill y debe marcarse como tal, nunca mezclarse en silencio.
INICIO_CONGELADO = "2026-09-03"

VERSION_REGISTRO = 1


@dataclass(slots=True)
class RegistroCongelado:
    """Una decisión tal y como se tomó en su día, sin saber qué pasó después."""

    ticker: str
    fecha: str                       # ISO, día del snapshot
    accion: str
    sell_score: float | None
    sub_valoracion: float | None
    sub_fundamentales: float | None
    sub_tecnico: float | None
    precio: float | None
    perfil: str
    version: int = VERSION_REGISTRO
    origen: str = "forward"          # "forward" | "backfill": nunca se mezclan

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker, "fecha": self.fecha, "accion": self.accion,
            "sell_score": self.sell_score, "sub_valoracion": self.sub_valoracion,
            "sub_fundamentales": self.sub_fundamentales, "sub_tecnico": self.sub_tecnico,
            "precio": self.precio, "perfil": self.perfil,
            "version": self.version, "origen": self.origen,
        }


# ==========================================================================
# PERSISTENCIA
# ==========================================================================


def _leer(path: str | Path) -> list[dict[str, Any]]:
    ruta = Path(path)
    if not ruta.exists():
        return []
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        LOGGER.warning("No se pudo leer %s: %s", ruta, exc)
        return []
    return datos if isinstance(datos, list) else []


def guardar_registros(registros: Sequence[RegistroCongelado],
                      *, path: str | Path = FICHERO_CONGELADO) -> int:
    """Añade al histórico. NUNCA sobrescribe: cada snapshot es una observación.

    Se descartan los duplicados de (ticker, fecha, perfil): ejecutar el job dos
    veces el mismo día no debe inflar la muestra, porque duplicar observaciones
    estrecharía artificialmente cualquier intervalo de confianza posterior.
    """
    os.makedirs(CARPETA_DATOS, exist_ok=True)
    existentes = _leer(path)
    claves = {(r.get("ticker"), r.get("fecha"), r.get("perfil")) for r in existentes}

    nuevos = [r.to_dict() for r in registros
              if (r.ticker, r.fecha, r.perfil) not in claves]
    if not nuevos:
        return 0

    Path(path).write_text(
        json.dumps(existentes + nuevos, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(nuevos)


def cargar_registros(*, path: str | Path = FICHERO_CONGELADO,
                     solo_forward: bool = True) -> list[dict[str, Any]]:
    """Lee el histórico. Por defecto excluye backfills: mezclarlos con el
    registro forward destruiría justo la propiedad que lo hace valioso."""
    datos = _leer(path)
    if solo_forward:
        return [r for r in datos if r.get("origen", "forward") == "forward"]
    return datos


# ==========================================================================
# CONGELADO
# ==========================================================================


def congelar_universo(
    tickers: Iterable[str],
    *,
    perfil: str = "largo_plazo",
    fecha: str | None = None,
    decidir: Any = None,
) -> list[RegistroCongelado]:
    """Toma una decisión por valor y la deja lista para persistir.

    ``decidir`` existe para los tests: por defecto usa decision_venta.
    """
    if decidir is None:
        from modulos.decision_venta import decidir_venta as decidir

    dia = fecha or datetime.now(timezone.utc).date().isoformat()
    registros: list[RegistroCongelado] = []

    for ticker in tickers:
        simbolo = str(ticker or "").strip().upper()
        if not simbolo:
            continue
        try:
            decision = decidir(simbolo, perfil=perfil)
        except Exception as exc:
            # Un valor que falla no puede tumbar el job: el registro se compone
            # de observaciones independientes.
            LOGGER.warning("No se pudo congelar %s: %s", simbolo, exc)
            continue

        sub = getattr(decision, "sub_scores", {}) or {}
        registros.append(RegistroCongelado(
            ticker=simbolo,
            fecha=dia,
            accion=getattr(decision, "accion", "MANTENER"),
            sell_score=getattr(decision, "sell_score", None),
            sub_valoracion=sub.get("valoracion"),
            sub_fundamentales=sub.get("fundamentales"),
            sub_tecnico=sub.get("tecnico"),
            precio=getattr(decision, "precio_actual", None),
            perfil=perfil,
        ))

    return registros


# ==========================================================================
# LECTOR: ¿predijeron algo?
# ==========================================================================


def cruzar_con_retorno_posterior(
    registros: Sequence[dict[str, Any]],
    precios: dict[str, pd.Series],
    *,
    horizonte_dias: int = 63,
) -> pd.DataFrame:
    """Une cada decisión congelada con el retorno REALIZADO después.

    Solo se cruzan las observaciones cuyo horizonte ya ha vencido: incluir las
    que aún no han madurado sesgaría la muestra hacia los movimientos rápidos,
    que son justo los más extremos.
    """
    filas: list[dict[str, Any]] = []

    for registro in registros:
        ticker = registro.get("ticker")
        serie = precios.get(ticker)
        if serie is None or serie.empty:
            continue
        try:
            fecha = pd.Timestamp(registro.get("fecha"))
        except Exception:
            continue

        posteriores = serie[serie.index >= fecha]
        if len(posteriores) <= horizonte_dias:
            continue  # aún no ha vencido

        precio_inicial = registro.get("precio") or float(posteriores.iloc[0])
        if not precio_inicial or precio_inicial <= 0:
            continue
        precio_final = float(posteriores.iloc[horizonte_dias])

        filas.append({
            "ticker": ticker,
            "fecha": registro.get("fecha"),
            "accion": registro.get("accion"),
            "sell_score": registro.get("sell_score"),
            "sub_valoracion": registro.get("sub_valoracion"),
            "sub_fundamentales": registro.get("sub_fundamentales"),
            "sub_tecnico": registro.get("sub_tecnico"),
            "retorno_posterior": (precio_final - precio_inicial) / precio_inicial,
        })

    return pd.DataFrame(filas)


def resumen_poder_predictivo(cruce: pd.DataFrame, *, minimo: int = 30) -> dict[str, Any]:
    """Correlación de Spearman entre cada sub-score y el retorno posterior.

    Spearman y no Pearson: interesa si el orden se respeta (más score, peor
    retorno), no que la relación sea lineal.

    Un sell score alto debería ir con retorno posterior BAJO, así que la
    correlación esperada es NEGATIVA. Con menos de ``minimo`` observaciones
    maduras no se publica ningún número.
    """
    if cruce is None or cruce.empty or len(cruce) < minimo:
        return {
            "suficiente": False,
            "observaciones": 0 if cruce is None or cruce.empty else len(cruce),
            "minimo_requerido": minimo,
            "nota": "Muestra insuficiente: el registro forward todavía no ha madurado.",
        }

    resultado: dict[str, Any] = {"suficiente": True, "observaciones": len(cruce)}
    for columna in ("sell_score", "sub_valoracion", "sub_fundamentales", "sub_tecnico"):
        if columna not in cruce.columns:
            continue
        pareja = cruce[[columna, "retorno_posterior"]].dropna()
        if len(pareja) < minimo:
            resultado[columna] = {"observaciones": len(pareja), "spearman": None}
            continue
        rho = float(pareja[columna].corr(pareja["retorno_posterior"], method="spearman"))
        resultado[columna] = {
            "observaciones": len(pareja),
            "spearman": round(rho, 4),
            "signo_esperado": "negativo",
            "coherente": rho < 0,
        }
    return resultado
