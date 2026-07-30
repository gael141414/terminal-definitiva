"""Mapeo curado de supervivencia (Sub-fase 2, calibración del score).

Cubre lo que se puede probar de forma determinista (estructura del mapeo
curado, y que resolver_empresa_historica() resuelve por CIK -- nunca por
ticker -- mockeando edgar.Company). La verificación contra SEC EDGAR real
(que Company(CIK) resuelve a la entidad histórica correcta, y que
Company(ticker_historico) resuelve a la entidad EQUIVOCADA o falla, para
BBBY/SHLD/TOYS) se hizo en vivo aparte y se describe en el informe de la
tarea -- aquí solo la lógica determinista, sin red (mismo criterio que el
resto de la suite desde la Fase 7: test_sec_edgar_downloader.py mockea
Company/get_filings en vez de tocar EDGAR real en pytest).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import survivorship_universe as su


# ---------------------------------------------------------------------------
# Estructura del mapeo curado
# ---------------------------------------------------------------------------


def test_los_3_casos_curados_estan_presentes():
    assert set(su.SURVIVORSHIP_CASES) == {"BBBY", "SHLD", "TOYS"}


def test_cada_caso_tiene_ticker_historico_consistente_con_su_clave():
    for clave, caso in su.SURVIVORSHIP_CASES.items():
        assert caso.ticker_historico == clave


def test_cada_caso_tiene_cik_positivo_y_distinto():
    ciks = [caso.cik for caso in su.SURVIVORSHIP_CASES.values()]
    assert all(isinstance(cik, int) and cik > 0 for cik in ciks)
    assert len(set(ciks)) == len(ciks), "los CIK deben ser todos distintos"


def test_cada_caso_documenta_motivo_y_nombre_esperado_no_vacios():
    for caso in su.SURVIVORSHIP_CASES.values():
        assert caso.motivo.strip()
        assert caso.nombre_esperado.strip()
        assert caso.ultimo_filing_10k.strip()


# ---------------------------------------------------------------------------
# resolver_empresa_historica: resuelve por CIK, nunca por ticker
# ---------------------------------------------------------------------------


def test_resolver_empresa_historica_llama_a_company_con_el_cik_no_el_ticker(monkeypatch):
    llamadas = []

    def fake_company(identificador):
        llamadas.append(identificador)
        return f"Company({identificador!r})"

    monkeypatch.setattr(su, "Company", fake_company)

    resultado = su.resolver_empresa_historica("BBBY")

    assert llamadas == [886158]  # el CIK curado, nunca la cadena "BBBY"
    assert resultado == "Company(886158)"


def test_resolver_empresa_historica_es_insensible_a_mayusculas(monkeypatch):
    llamadas = []
    monkeypatch.setattr(su, "Company", lambda identificador: llamadas.append(identificador))

    su.resolver_empresa_historica("shld")

    assert llamadas == [1310067]


def test_resolver_empresa_historica_toys_usa_su_cik_curado(monkeypatch):
    """TOYS es el caso donde Company(ticker) falla por completo -- confirma
    que la resolución curada ni siquiera pasa por esa ruta, sino directo al CIK."""
    llamadas = []
    monkeypatch.setattr(su, "Company", lambda identificador: llamadas.append(identificador))

    su.resolver_empresa_historica("TOYS")

    assert llamadas == [1005414]


def test_resolver_empresa_historica_caso_desconocido_lanza_keyerror_sin_llamar_a_company(monkeypatch):
    llamadas = []
    monkeypatch.setattr(su, "Company", lambda identificador: llamadas.append(identificador))

    with pytest.raises(KeyError):
        su.resolver_empresa_historica("NOEXISTE")

    assert not llamadas, "no debe intentar resolver nada si el caso no está curado"
