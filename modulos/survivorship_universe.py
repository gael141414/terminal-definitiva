"""Mapeo curado de supervivencia (Sub-fase 2, calibración del score).

SEC EDGAR conserva el historial completo de empresas que ya no cotizan
(quiebra, liquidación, adquisición) siempre que hayan presentado filings en
su día -- los CIK son permanentes y nunca se reasignan. El problema real,
confirmado empíricamente contra 3 casos reales (ver diagnóstico de la
Sub-fase 2), es que el TICKER sí se recicla: ``Company(ticker)`` puede
resolver silenciosamente a una entidad completamente distinta, o fallar,
una vez el ticker original queda libre.

Este módulo NO resuelve el sesgo de supervivencia del universo (qué
empresas estaban en un índice en la fecha X -- eso ya se señaló aparte en
el diagnóstico de la Fase 8/calibración). Resuelve un problema más acotado:
dado que se quiere incluir en el backtest una empresa concreta que ya no
cotiza, ¿cómo se llega a sus datos reales sin que el ticker reciclado lleve
a la empresa equivocada? La respuesta: nunca resolver por ticker histórico,
siempre por CIK. ``edgar.Company()`` acepta un CIK (int o str) exactamente
igual que acepta un ticker -- por eso ``downloader.py`` no necesita ningún
cambio: basta con pasarle el CIK (como string) en el mismo parámetro donde
hoy se le pasa un ticker.

Casos curados y verificados en vivo contra SEC EDGAR:

- BBBY (Bed Bath & Beyond, quiebra Chapter 11 2023): el ticker fue
  reutilizado por Overstock.com tras comprar la marca en la quiebra --
  ``Company('BBBY')`` hoy resuelve a esa empresa NUEVA (CIK 1130713,
  filings 2024-2026), no a la Bed Bath & Beyond original. La entidad
  original (CIK 886158) se renombró a "20230930-DK-Butterfly-1, Inc." tras
  vender la marca -- de ahí que el nombre esperado ya no contenga
  "Bed Bath".
- SHLD (Sears Holdings, quiebra Chapter 11 2018): el ticker fue reasignado
  a un emisor de ETFs -- ``Company('SHLD')`` hoy resuelve a "Global X
  Funds" (CIK 1432353), sin ninguna relación con Sears.
- TOYS (Toys R Us, liquidación completa 2017-2018): el ticker nunca se
  reutilizó -- ``Company('TOYS')`` falla directamente con
  ``CompanyNotFoundError`` en vez de resolver a una entidad equivocada (a
  diferencia de BBBY/SHLD, aquí el fallo es ruidoso, no silencioso -- pero
  sigue bloqueando el acceso si no se conoce el CIK de antemano).
"""

from __future__ import annotations

from dataclasses import dataclass

from edgar import Company


@dataclass(frozen=True, slots=True)
class HistoricalCompanyRecord:
    """Una empresa que ya no cotiza, identificada por su CIK real -- nunca
    por el ticker con el que operaba, que puede haber sido reasignado.

    ``nombre_esperado`` es un fragmento (no una igualdad exacta) del nombre
    real registrado en SEC EDGAR para este CIK: sirve para verificar que la
    resolución sigue siendo correcta, tolerando que el nombre legal cambie
    (p. ej. tras una venta de marca post-quiebra, como en BBBY).

    ``ultimo_filing_10k`` es la fecha del último 10-K conocido en el momento
    en que se curó este registro -- referencia de cobertura, no una garantía
    viva (un trustee de la quiebra podría presentar un filing tardío).
    """

    ticker_historico: str
    cik: int
    nombre_esperado: str
    ultimo_filing_10k: str
    motivo: str
    nota: str = ""


SURVIVORSHIP_CASES: dict[str, HistoricalCompanyRecord] = {
    "BBBY": HistoricalCompanyRecord(
        ticker_historico="BBBY",
        cik=886158,
        nombre_esperado="DK-Butterfly",
        ultimo_filing_10k="2023-06-14",
        motivo="quiebra (Chapter 11, 2023)",
        nota=(
            "El ticker BBBY fue reutilizado por Overstock.com tras comprar la marca "
            "en la quiebra -- Company('BBBY') hoy resuelve a esa empresa NUEVA "
            "(CIK 1130713, filings 2024-2026), no a la Bed Bath & Beyond original."
        ),
    ),
    "SHLD": HistoricalCompanyRecord(
        ticker_historico="SHLD",
        cik=1310067,
        nombre_esperado="SEARS HOLDINGS",
        ultimo_filing_10k="2018-03-23",
        motivo="quiebra (Chapter 11, 2018)",
        nota=(
            "El ticker SHLD fue reasignado a un emisor de ETFs -- Company('SHLD') "
            "hoy resuelve a 'Global X Funds' (CIK 1432353), sin ninguna relación con Sears."
        ),
    ),
    "TOYS": HistoricalCompanyRecord(
        ticker_historico="TOYS",
        cik=1005414,
        nombre_esperado="TOYS R US",
        ultimo_filing_10k="2017-04-12",
        motivo="liquidación completa (Chapter 11, 2017-2018)",
        nota=(
            "El ticker TOYS nunca se reutilizó -- Company('TOYS') falla directamente "
            "con CompanyNotFoundError en vez de resolver a una entidad equivocada "
            "(a diferencia de BBBY/SHLD, el fallo aquí es ruidoso, no silencioso)."
        ),
    ),
}


def resolver_empresa_historica(caso_key: str) -> Company:
    """Resuelve una empresa histórica por su CIK curado -- nunca por el
    ticker con el que operaba, que puede haberse reasignado (ver
    ``SURVIVORSHIP_CASES`` y el diagnóstico de la Sub-fase 2).

    Reutilizable directamente con ``downloader.py``:
    ``downloader.obtener_estados_financieros(str(caso.cik), años=...)``
    funciona igual que con un ticker real, porque ``edgar.Company()`` acepta
    un CIK como string indistintamente -- no hace falta tocar downloader.py.

    Lanza ``KeyError`` si ``caso_key`` no está curado (nunca degrada en
    silencio a una resolución por ticker sin verificar).
    """
    caso = SURVIVORSHIP_CASES.get(caso_key.upper())
    if caso is None:
        raise KeyError(
            f"'{caso_key}' no está en SURVIVORSHIP_CASES -- casos curados: {sorted(SURVIVORSHIP_CASES)}"
        )
    return Company(caso.cik)
