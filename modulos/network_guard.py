"""Bloqueo determinista de red para suites que no deben depender de la
disponibilidad real de un proveedor externo en el momento de ejecutarse.

``modulos/smoke_tests.py`` instala este guard por defecto: cualquier intento
de red real (Yahoo, FMP, RSS, Lottie...) durante los smoke tests falla de
inmediato con ``NetworkBlockedError`` en vez de esperar una respuesta real que
puede tardar, dar 429/402, o no estar disponible en el entorno de CI. Eso
obliga a que todo el código bajo prueba pase por el camino de degradación de
la capa de resiliencia (yahoo_resilience.py / fmp_api.py) de forma
determinista, en lugar de "pasar porque hoy el proveedor respondió algo"
(incluido un fallo real, que la resiliencia también absorbe y por tanto
enmascara una eventual regresión real en la propia suite).

Se parchea en dos puntos, no solo ``socket.socket.connect``:

- ``requests.adapters.HTTPAdapter.send``: punto de paso obligatorio de
  *todas* las llamadas hechas con la librería ``requests`` (FMP, RSS, Lottie,
  y las rutas de yfinance que aún usan requests), independientemente de si se
  invocan como ``requests.get`` o a través de una ``Session``.
- ``curl_cffi.requests.session.Session.request``: yfinance usa ``curl_cffi``
  (bindings de libcurl en C) para el histórico de precios y otros endpoints,
  para evitar la detección de bots de Yahoo. curl_cffi abre sus conexiones a
  través de sus propios bindings compilados, sin pasar por
  ``socket.socket.connect`` de Python — bloquear solo el socket estándar deja
  esas llamadas sin cubrir (se detectó exactamente así: con el guard limitado
  a socket, las llamadas a ``yf.Ticker(...).history()`` seguían golpeando la
  red real y devolviendo 429 genuinos).

Se mantiene además el bloqueo de ``socket.socket.connect`` como red de
seguridad adicional para cualquier otro uso de red no cubierto explícitamente
por los dos puntos anteriores.
"""

from __future__ import annotations

import contextlib
import socket
from typing import Iterator

import requests.adapters

try:
    import curl_cffi.requests.session as _curl_cffi_session
except Exception:  # pragma: no cover - curl_cffi es opcional/puede faltar
    _curl_cffi_session = None


class NetworkBlockedError(OSError):
    """Se lanza cuando el guard de red bloquea un intento de conexión real."""


_NETWORK_BLOCKED_MESSAGE = (
    "Red externa deshabilitada durante los smoke tests (modo determinista). "
    "Pasa --allow-network para el modo de integración real contra proveedores reales."
)

_original_socket_connect = socket.socket.connect
_original_requests_send = requests.adapters.HTTPAdapter.send
_original_curl_cffi_request = _curl_cffi_session.Session.request if _curl_cffi_session else None

_installed = False


def _blocked_socket_connect(self: socket.socket, *args: object, **kwargs: object) -> None:
    raise NetworkBlockedError(_NETWORK_BLOCKED_MESSAGE)


def _blocked_requests_send(self: requests.adapters.HTTPAdapter, *args: object, **kwargs: object) -> None:
    raise NetworkBlockedError(_NETWORK_BLOCKED_MESSAGE)


def _blocked_curl_cffi_request(self, *args: object, **kwargs: object) -> None:
    raise NetworkBlockedError(_NETWORK_BLOCKED_MESSAGE)


def install_network_guard() -> None:
    """Bloquea requests, curl_cffi (yfinance) y sockets crudos. Idempotente."""
    global _installed
    socket.socket.connect = _blocked_socket_connect  # type: ignore[method-assign]
    requests.adapters.HTTPAdapter.send = _blocked_requests_send  # type: ignore[method-assign]
    if _curl_cffi_session is not None:
        _curl_cffi_session.Session.request = _blocked_curl_cffi_request  # type: ignore[method-assign]
    _installed = True


def uninstall_network_guard() -> None:
    global _installed
    socket.socket.connect = _original_socket_connect  # type: ignore[method-assign]
    requests.adapters.HTTPAdapter.send = _original_requests_send  # type: ignore[method-assign]
    if _curl_cffi_session is not None:
        _curl_cffi_session.Session.request = _original_curl_cffi_request  # type: ignore[method-assign]
    _installed = False


def is_installed() -> bool:
    return _installed


@contextlib.contextmanager
def blocked_network() -> Iterator[None]:
    """Context manager: bloquea la red real solo durante el bloque ``with``.

    Restaura el estado previo al salir (no desinstala un guard que ya estuviera
    activo por otra razón, para poder anidarse sin sorpresas).
    """
    was_installed = is_installed()
    if not was_installed:
        install_network_guard()
    try:
        yield
    finally:
        if not was_installed:
            uninstall_network_guard()
