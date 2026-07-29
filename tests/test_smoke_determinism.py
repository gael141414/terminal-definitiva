"""La suite de smoke tests debe pasar sin tocar la red real.

Antes de este fix, run_smoke_tests.py --strict pasaba "porque la resiliencia
degrada bien" ante fallos reales de red (429 de Yahoo, 401/402/429 de FMP) —
pero eso no distingue "el código maneja bien un fallo real" de "el código
nunca se ejerció contra un escenario de fallo controlado y verificable". Este
test fija esa propiedad: con modulos.network_guard activo (el modo por
defecto de run_smoke_tests()), ningún check debe fallar y ninguna llamada de
red real debe completarse.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests.adapters

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import network_guard
from modulos.smoke_tests import run_smoke_tests


def test_network_guard_bloquea_requests_http_adapter_send():
    calls = {"n": 0}
    original = requests.adapters.HTTPAdapter.send
    try:
        with network_guard.blocked_network():
            assert network_guard.is_installed()
            with pytest.raises(network_guard.NetworkBlockedError):
                requests.get("https://financialmodelingprep.com/api/v3/quote-short/AAPL", timeout=5)
        assert not network_guard.is_installed()
    finally:
        requests.adapters.HTTPAdapter.send = original


def test_blocked_network_es_reentrante_y_restaura_estado_previo():
    assert not network_guard.is_installed()
    with network_guard.blocked_network():
        assert network_guard.is_installed()
        with network_guard.blocked_network():
            assert network_guard.is_installed()
        # El bloque interior no debe desinstalar el guard del exterior.
        assert network_guard.is_installed()
    assert not network_guard.is_installed()


def test_run_smoke_tests_no_falla_con_red_bloqueada():
    """La propiedad central que pedía esta tarea: 0 fallos sin red real.

    ``run_smoke_tests()`` sin argumentos ya usa ``allow_network=False`` por
    defecto (el mismo camino que ``scripts/run_smoke_tests.py --strict`` y
    ``modulos/release_readiness.py`` usan en producción/CI).
    """
    checks = run_smoke_tests()

    failed = [c for c in checks if not c.ok]
    assert not failed, f"{len(failed)} checks fallaron con la red bloqueada: {[c.name for c in failed[:10]]}"
    assert len(checks) > 100, "La suite debe seguir ejecutando su volumen normal de checks"


def test_run_smoke_tests_deja_el_guard_desinstalado_al_terminar():
    """No debe haber fugas de estado: tras correr la suite, la red vuelve a estar disponible."""
    assert not network_guard.is_installed()
    run_smoke_tests()
    assert not network_guard.is_installed()
