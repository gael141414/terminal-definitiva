from __future__ import annotations

try:
    from modulos.yfinance_global_guard import install_yfinance_guard

    install_yfinance_guard()
except Exception:
    # sitecustomize no debe impedir el arranque de la app ni de scripts locales.
    pass
