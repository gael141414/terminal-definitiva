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

Disponibilidad de precio histórico (Sub-fase 3, verificado en vivo contra
la API de Yahoo Finance directamente -- sin pasar por yfinance, cuyo propio
mecanismo de cookie/crumb estaba bloqueado por rate-limit en el momento de
esta verificación; el bloqueo era de esa librería, no de Yahoo, que sí
respondía con datos reales a una petición HTTP directa al endpoint de
cotizaciones):

- BBBY: SÍ hay precio real (376 puntos diarios, 2021-12-31 a 2023-06-30,
  ``instrumentType=EQUITY``) que cubre por completo el rango de los puntos
  de congelación de la Sub-fase 3 (2020 a 2023-06-15). Usable en la
  Sub-fase 4 para cruzar retorno.
- SHLD: NO hay precio disponible bajo ningún ticker conocido. El símbolo
  actual resuelve a "Global X Defense Tech ETF" (sin relación con Sears,
  datos solo desde 2023-09) y el sucesor OTC "SHLDQ" devuelve 404 ("No data
  found, symbol may be delisted"). No es un bloqueo temporal: el hueco es
  estructural (reasignación permanente del ticker). NO usable en la
  Sub-fase 4 para retorno -- solo fundamentales.
- TOYS: NO hay precio disponible, y no lo habrá nunca para el rango
  relevante: Toys "R" Us fue una empresa PRIVADA desde el LBO de KKR/Bain/
  Vornado en 2005 hasta su quiebra de 2017 -- no tuvo acción cotizada en
  ningún momento de la ventana de congelación de la Sub-fase 3 (2012-2017).
  El símbolo actual "TOYS" en Yahoo resuelve además a un fondo mutuo sin
  relación alguna. NO usable en la Sub-fase 4 para retorno -- solo
  fundamentales.
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

    ``precio_historico_disponible`` -- verificado en la Sub-fase 3 contra la
    API de Yahoo Finance directamente (ver nota del módulo): indica si este
    caso puede cruzarse con retorno en la Sub-fase 4, o si se queda limitado
    a validar que el score se calcula (solo fundamentales, sin retorno).
    """

    ticker_historico: str
    cik: int
    nombre_esperado: str
    ultimo_filing_10k: str
    motivo: str
    precio_historico_disponible: bool
    nota: str = ""


SURVIVORSHIP_CASES: dict[str, HistoricalCompanyRecord] = {
    "BBBY": HistoricalCompanyRecord(
        ticker_historico="BBBY",
        cik=886158,
        nombre_esperado="DK-Butterfly",
        ultimo_filing_10k="2023-06-14",
        motivo="quiebra (Chapter 11, 2023)",
        precio_historico_disponible=True,
        nota=(
            "El ticker BBBY fue reutilizado por Overstock.com tras comprar la marca "
            "en la quiebra -- Company('BBBY') hoy resuelve a esa empresa NUEVA "
            "(CIK 1130713, filings 2024-2026), no a la Bed Bath & Beyond original. "
            "Precio (Sub-fase 3): SÍ disponible en Yahoo Finance -- 376 puntos diarios "
            "2021-12-31/2023-06-30, instrumentType=EQUITY, cubre todo el rango de "
            "congelación. Usable en la Sub-fase 4 para cruzar retorno."
        ),
    ),
    "SHLD": HistoricalCompanyRecord(
        ticker_historico="SHLD",
        cik=1310067,
        nombre_esperado="SEARS HOLDINGS",
        ultimo_filing_10k="2018-03-23",
        motivo="quiebra (Chapter 11, 2018)",
        precio_historico_disponible=False,
        nota=(
            "El ticker SHLD fue reasignado a un emisor de ETFs -- Company('SHLD') "
            "hoy resuelve a 'Global X Funds' (CIK 1432353), sin ninguna relación con Sears. "
            "Precio (Sub-fase 3): NO disponible en Yahoo Finance bajo ningún ticker -- "
            "'SHLD' hoy es Global X Defense Tech ETF (datos solo desde 2023-09) y el "
            "sucesor OTC 'SHLDQ' devuelve 404. Hueco estructural (ticker reasignado), no "
            "un bloqueo temporal. NO usable en la Sub-fase 4 para retorno, solo fundamentales."
        ),
    ),
    "TOYS": HistoricalCompanyRecord(
        ticker_historico="TOYS",
        cik=1005414,
        nombre_esperado="TOYS R US",
        ultimo_filing_10k="2017-04-12",
        motivo="liquidación completa (Chapter 11, 2017-2018)",
        precio_historico_disponible=False,
        nota=(
            "El ticker TOYS nunca se reutilizó -- Company('TOYS') falla directamente "
            "con CompanyNotFoundError en vez de resolver a una entidad equivocada "
            "(a diferencia de BBBY/SHLD, el fallo aquí es ruidoso, no silencioso). "
            "Precio (Sub-fase 3): NO disponible, y no lo habrá nunca para el rango "
            "relevante -- Toys \"R\" Us fue una empresa PRIVADA (LBO KKR/Bain/Vornado "
            "2005) hasta su quiebra de 2017, sin acción cotizada durante toda la "
            "ventana de congelación (2012-2017). NO usable en la Sub-fase 4 para "
            "retorno, solo fundamentales."
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
