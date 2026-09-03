from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - python-dotenv puede no estar instalado en algunos entornos
    load_dotenv = None

try:
    import streamlit as st
except Exception:  # pragma: no cover - permite importar fuera de Streamlit
    st = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOTENV_PATH = PROJECT_ROOT / ".env"

if load_dotenv is not None:
    # override=False mantiene prioridad para variables ya exportadas por el sistema/hosting.
    load_dotenv(DOTENV_PATH, override=False)


PLACEHOLDER_VALUES = {
    "",
    "your_fmp_api_key_here",
    "your_gemini_api_key_here",
    "your_google_api_key_here",
    "your_telegram_bot_token_here",
    "your_telegram_chat_id_here",
    "changeme",
    "change_me",
    "none",
    "null",
}


def _is_missing_secret(value: Any) -> bool:
    """Detecta valores vacíos o placeholders de archivos example/secrets."""
    if value is None:
        return True
    normalized = str(value).strip()
    if normalized.lower() in PLACEHOLDER_VALUES:
        return True
    if normalized.lower().startswith("your_"):
        return True
    return False


def get_secret(name: str, default: Any = None) -> Any:
    """Lee configuración desde Streamlit secrets, variables de entorno o .env local.

    Orden de prioridad efectivo:
    1. st.secrets[name], cuando Streamlit está disponible y no contiene un placeholder.
    2. os.environ[name]. Aquí también entran variables cargadas desde .env.
    3. default.
    """
    if st is not None:
        try:
            value = st.secrets.get(name)  # type: ignore[union-attr]
            if not _is_missing_secret(value):
                return value
        except Exception:
            pass

    value = os.getenv(name)
    if not _is_missing_secret(value):
        return value
    return default


def get_bool_secret(name: str, default: bool = False) -> bool:
    value = str(get_secret(name, str(default))).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    fmp_api_key: str
    gemini_api_key: str
    google_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    sec_edgar_identity: str
    debug: bool = False
    fmp_news_enabled: bool = False


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig(
        app_env=str(get_secret("APP_ENV", "local")),
        fmp_api_key=str(get_secret("FMP_API_KEY", "")),
        gemini_api_key=str(get_secret("GEMINI_API_KEY", "")),
        google_api_key=str(get_secret("GOOGLE_API_KEY", "")),
        telegram_bot_token=str(get_secret("TELEGRAM_BOT_TOKEN", "")),
        telegram_chat_id=str(get_secret("TELEGRAM_CHAT_ID", "")),
        sec_edgar_identity=str(get_secret("SEC_EDGAR_IDENTITY", "Buffett Terminal gaelestgon@gmail.com")),
        debug=get_bool_secret("VALUEQUANT_DEBUG", get_bool_secret("DEBUG", False)),
        fmp_news_enabled=get_bool_secret("FMP_NEWS_ENABLED", False),
    )


CONFIG = get_config()


# --- Umbrales de negocio compartidos -----------------------------------
# Antes coexistían 1.2 y 1.5 como el mismo tipo de umbral duplicado en varios
# archivos (algunos como aviso temprano, otros como red flag más grave) sin
# una única fuente de verdad. Warning = merece atención; Red flag = nivel de
# apalancamiento que el modelo considera peligroso.
DEBT_EQUITY_WARNING = 1.2
DEBT_EQUITY_RED_FLAG = 1.5


# =============================================================================
# SISTEMA DE DISEÑO — fuente única de verdad del color
# =============================================================================
# Extraído del mockup docs/design (Exploracion_Navegacion.html). Antes cada
# módulo hardcodeaba su propio hex ("#00ff88", "#00C0F2", "#1e4bd8"...), lo que
# hacía imposible cambiar la identidad visual sin editar 40 archivos. El CSS
# (modulos/app_theme.py) y los gráficos Plotly (modulos.utils.apply_plotly_theme)
# consumen estas mismas constantes.

COLOR_BG = "#05070d"          # Fondo principal de la app
COLOR_SURFACE = "#101827"     # Fondo de cards / paneles
COLOR_SIDEBAR = "#0d1117"     # Fondo del sidebar
COLOR_PRIMARY = "#3b82f6"     # Azul acento (acciones, headers de tabla)
COLOR_ACCENT = "#22d3ee"      # Cian acento (deltas neutros, detalles)
COLOR_POSITIVE = "#10e39a"    # Verde: métrica favorable
COLOR_NEGATIVE = "#fb5e6d"    # Rojo: métrica de riesgo
COLOR_WARNING = "#fbbf24"     # Ámbar: zona de vigilancia (entre aviso y red flag)
COLOR_TEXT = "#e8edf5"        # Texto primario
COLOR_TEXT_MUTED = "#93a4bb"  # Texto secundario / borde base

FONT_STACK = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
# Familias por papel; deben coincidir con las de modulos/app_theme.py.
FONT_TITULO = "Space Grotesk, Inter, sans-serif"
FONT_DATO = "JetBrains Mono, ui-monospace, Menlo, monospace"

# El borde del sistema es el color muted a distinta opacidad, no un hex propio.
COLOR_BORDER = "rgba(147, 164, 187, 0.35)"
COLOR_BORDER_SOFT = "rgba(147, 164, 187, 0.20)"
COLOR_GRID = "rgba(147, 164, 187, 0.15)"

# Paleta cualitativa para series múltiples. El ORDEN no es decorativo: se validó
# con el verificador de contraste/daltonismo del sistema de diseño sobre el fondo
# de card (#121926). Con verde y cian adyacentes la separación caía a ΔE 14.5 en
# visión normal (por debajo del mínimo de 15: dos series indistinguibles). Este
# orden los separa y sube el peor par adyacente a ΔE 25.3 normal / 9.4 en
# deuteranopía, con contraste >= 3:1 en los cinco tonos.
# No reordenar sin volver a validar.
PLOTLY_COLORWAY = (
    COLOR_PRIMARY,    # azul
    COLOR_WARNING,    # ámbar
    COLOR_ACCENT,     # cian
    COLOR_NEGATIVE,   # rojo
    COLOR_POSITIVE,   # verde
    "#a78bfa",        # violeta (6ª serie; fuera del núcleo de marca)
)


# =============================================================================
# UMBRALES DEL BUFFETT SCORE
# =============================================================================
# Antes vivían como números mágicos dentro de calcular_score_buffett() en
# modulos/utils.py. Centralizarlos permite auditarlos y reutilizarlos en el
# screener/treemap sin duplicar la regla.

BUFFETT_MARGEN_BRUTO_EXCELENTE = 40.0
BUFFETT_MARGEN_BRUTO_BUENO = 20.0
BUFFETT_MARGEN_NETO_EXCELENTE = 20.0
BUFFETT_MARGEN_NETO_BUENO = 10.0
BUFFETT_ROE_MINIMO = 15.0
BUFFETT_ROIC_MINIMO = 15.0
BUFFETT_DEUDA_EXCELENTE = 0.8
BUFFETT_CAPEX_EXCELENTE = 25.0
BUFFETT_CAPEX_ACEPTABLE = 50.0

# Cortes de interpretación del score final (0-100), compartidos por la tabla del
# screener, el treemap de mercado y las tarjetas KPI.
BUFFETT_SCORE_BAJO = 40.0
BUFFETT_SCORE_MEDIO = 60.0


def color_por_buffett_score(score: float | int | None) -> str:
    """Devuelve el color del sistema que corresponde a un Buffett Score.

    Escala pedida por producto: rojo 0-40, ámbar 40-60, verde 60-100.
    """
    try:
        valor = float(score)
    except (TypeError, ValueError):
        return COLOR_TEXT_MUTED
    if valor < BUFFETT_SCORE_BAJO:
        return COLOR_NEGATIVE
    if valor < BUFFETT_SCORE_MEDIO:
        return COLOR_WARNING
    return COLOR_POSITIVE


# ==========================================================================
# DECISIÓN DE VENTA (modulos/decision_venta.py)
#
# Ningún número de este bloque debe repetirse dentro del módulo: si un umbral
# se toca, se toca aquí.
#
# ADVERTENCIA sobre la evidencia disponible. modulos/swing_salidas.py contiene
# una validación sobre 2.377 operaciones donde NINGUNA gestión activa de salida
# batió a aguantar hasta el horizonte (0,39R aguantar · 0,39R salir por señal ·
# 0,28R stop dinámico). Aquella prueba cubría el pilar técnico en horizonte
# swing, no valoración ni fundamentales, así que no invalida este módulo — pero
# es el prior con el que hay que leer cualquier resultado de aquí.
# ==========================================================================

PERFIL_LARGO_PLAZO = "largo_plazo"
PERFIL_SWING = "swing"

# Pesos de los tres pilares por perfil. Suman 1,0.
PESOS_VENTA: dict[str, dict[str, float]] = {
    PERFIL_LARGO_PLAZO: {"valoracion": 0.40, "fundamentales": 0.40, "tecnico": 0.20},
    PERFIL_SWING: {"valoracion": 0.20, "fundamentales": 0.30, "tecnico": 0.50},
}

# Bandas del sell score (0-100).
UMBRAL_REDUCIR = 30.0
UMBRAL_VENDER = 60.0

# Fracción a reducir cuando la decisión es REDUCIR, antes de los topes de
# concentración. Un tercio es el estándar de la toma por tercios.
FRACCION_REDUCCION = 1 / 3

# Stop duro desde el precio de entrada. O'Neil usa −7/−8%; se toma el extremo
# conservador porque aquí cubre posiciones de largo plazo, no solo swing.
STOP_DURO_PCT = 8.0

# Margen sobre el valor razonable a partir del cual se vende del todo: por
# debajo solo se recorta.
MARGEN_SOBREVALORACION_VENTA = 0.25

# Umbrales de tesis rota. Altman clásico y Z'' NO comparten escala.
UMBRAL_ALTMAN_TESIS_ROTA = 1.81
UMBRAL_ALTMAN_DP_TESIS_ROTA = 1.10
UMBRAL_BENEISH_TESIS_ROTA = -1.78
UMBRAL_PIOTROSKI_TESIS_ROTA = 3

# Percentil de múltiplos a partir del cual la acción está cara frente a su
# propia historia.
PERCENTIL_MULTIPLOS_CARO = 80.0

# El régimen de mercado endurece o relaja el pilar técnico: la misma señal
# bajista pesa más cuando el mercado ya está en distribución.
FACTOR_REGIMEN_ADVERSO = 1.25
FACTOR_REGIMEN_FAVORABLE = 0.80

# Regla de las 8 semanas de O'Neil: una subida fuerte y rápida merece dejarla
# correr antes de recortar.
SEMANAS_REGLA_OCHO = 8
SUBIDA_REGLA_OCHO_PCT = 20.0

# Fiscalidad española: informativo, nunca decide.
DIAS_RECOMPRA_ES = 60  # regla de los dos meses para valores cotizados
