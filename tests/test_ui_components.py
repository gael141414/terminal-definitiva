"""Tarjeta KPI estandarizada de 5 estados (Paso 2, mockup research_core_navegacion_kpi.html, 1b).

Verifica los 5 estados exactos del mockup, el forzado automático a
"no_disponible" cuando el valor es None/NaN (el resultado típico de un guard
financiero), el helper de clasificación por umbrales, y que los call sites
reales (modulos/resumen.py, modulos/fundamental.py) usan el componente en vez
de un st.metric ad-hoc que confunda "ausente" con "cero".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import ui_components
from modulos.config import DEBT_EQUITY_RED_FLAG, DEBT_EQUITY_WARNING


@pytest.fixture
def captured_markdown(monkeypatch):
    """Captura el HTML pasado a st.markdown en vez de necesitar un run real de Streamlit."""
    calls: list[str] = []
    monkeypatch.setattr(ui_components.st, "markdown", lambda body, **kwargs: calls.append(body))
    return calls


# ---------------------------------------------------------------------------
# Los 5 estados exactos del mockup
# ---------------------------------------------------------------------------


def test_estado_normal_sin_badge_delta_cian(captured_markdown):
    ui_components.render_kpi_card("ROE", "28.4%", delta="▲ +1.8 pp", tag="TTM")
    html_out = captured_markdown[0]

    assert "28.4%" in html_out
    assert "#37c6e6" in html_out  # delta cian
    assert "FAVORABLE" not in html_out
    assert "VIGILAR" not in html_out
    assert "RIESGO" not in html_out
    assert "TTM" in html_out


def test_estado_favorable_verde_con_badge_y_filo_izquierdo(captured_markdown):
    ui_components.render_kpi_card(
        "Margen neto", "25.3%", status="favorable", delta="▲ +2.1 pp",
        detail="supera el umbral de calidad (>20%)",
    )
    html_out = captured_markdown[0]

    assert "FAVORABLE" in html_out
    assert "#3ddc97" in html_out
    assert "inset 3px 0 0 #3ddc97" in html_out
    assert "supera el umbral de calidad" in html_out


def test_estado_advertencia_ambar(captured_markdown):
    ui_components.render_kpi_card(
        "Deuda / Capital", "1.3x", status="advertencia",
        detail=f"Entre el aviso ({DEBT_EQUITY_WARNING}x) y el umbral crítico ({DEBT_EQUITY_RED_FLAG}x).",
    )
    html_out = captured_markdown[0]

    assert "VIGILAR" in html_out
    assert "#f5b04c" in html_out
    assert "inset 3px 0 0 #f5b04c" in html_out


def test_estado_riesgo_rojo(captured_markdown):
    ui_components.render_kpi_card(
        "Deuda / Capital", "2.1x", status="riesgo",
        detail="supera el umbral crítico de 1.5x — red flag",
    )
    html_out = captured_markdown[0]

    assert "RIESGO" in html_out
    assert "#f36c6c" in html_out
    assert "inset 3px 0 0 #f36c6c" in html_out


def test_estado_no_disponible_borde_punteado_y_nd(captured_markdown):
    ui_components.render_kpi_card("FCF Yield", None)
    html_out = captured_markdown[0]

    assert "n/d" in html_out
    assert "1px dashed" in html_out
    assert "SIN DATOS" in html_out
    assert "excluido del score" in html_out
    # Nunca debe mostrarse un "0" o un delta falso para un dato ausente.
    assert "▲" not in html_out


# ---------------------------------------------------------------------------
# None/NaN de los guards financieros -> no_disponible SIEMPRE, sin importar
# qué status se haya pedido explícitamente (nunca un 0/N-A genérico).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_value", [None, float("nan")])
@pytest.mark.parametrize("requested_status", ["normal", "favorable", "advertencia", "riesgo"])
def test_valor_ausente_fuerza_no_disponible_pase_lo_que_pase(captured_markdown, bad_value, requested_status):
    ui_components.render_kpi_card("ROIC", bad_value, status=requested_status)
    html_out = captured_markdown[0]

    assert "n/d" in html_out
    assert "SIN DATOS" in html_out


def test_alias_de_estados_heredados_sigue_funcionando(captured_markdown):
    """app.py sigue llamando con status='neutral'/'positive'/'warning'/'negative'."""
    ui_components.render_kpi_card("Empresa analizada", "AAPL", status="neutral")
    assert "n/d" not in captured_markdown[-1]

    ui_components.render_kpi_card("Módulo activo", "Research Core", status="positive")
    assert "FAVORABLE" in captured_markdown[-1]

    ui_components.render_kpi_card("Comparador", "No definido", status="warning")
    assert "VIGILAR" in captured_markdown[-1]

    ui_components.render_kpi_card("Riesgo", "x", status="negative")
    assert "RIESGO" in captured_markdown[-1]


def test_valor_cero_real_no_se_confunde_con_ausente(captured_markdown):
    """0.0 es un valor real (p. ej. Deuda/Capital de una empresa sin deuda) y
    debe mostrarse tal cual, no como n/d."""
    ui_components.render_kpi_card("Deuda / Capital", "0.00x", status="normal")
    html_out = captured_markdown[0]

    assert "0.00x" in html_out
    assert "n/d" not in html_out


# ---------------------------------------------------------------------------
# kpi_status_from_thresholds
# ---------------------------------------------------------------------------


def test_kpi_status_from_thresholds_con_debt_equity():
    assert ui_components.kpi_status_from_thresholds(0.5, warning=DEBT_EQUITY_WARNING, danger=DEBT_EQUITY_RED_FLAG) == "normal"
    assert ui_components.kpi_status_from_thresholds(1.3, warning=DEBT_EQUITY_WARNING, danger=DEBT_EQUITY_RED_FLAG) == "advertencia"
    assert ui_components.kpi_status_from_thresholds(2.1, warning=DEBT_EQUITY_WARNING, danger=DEBT_EQUITY_RED_FLAG) == "riesgo"
    # Exactamente en el umbral: "no interpretable como aviso" (estrictamente mayor).
    assert ui_components.kpi_status_from_thresholds(DEBT_EQUITY_WARNING, warning=DEBT_EQUITY_WARNING, danger=DEBT_EQUITY_RED_FLAG) == "normal"


def test_kpi_status_from_thresholds_none_y_nan_dan_no_disponible():
    assert ui_components.kpi_status_from_thresholds(None, warning=1.2, danger=1.5) == "no_disponible"
    assert ui_components.kpi_status_from_thresholds(float("nan"), warning=1.2, danger=1.5) == "no_disponible"


def test_kpi_status_from_thresholds_higher_is_worse_false():
    # Ejemplo: un ratio de cobertura donde valores BAJOS son el problema.
    assert ui_components.kpi_status_from_thresholds(5.0, warning=3.0, danger=1.5, higher_is_worse=False) == "normal"
    assert ui_components.kpi_status_from_thresholds(2.0, warning=3.0, danger=1.5, higher_is_worse=False) == "advertencia"
    assert ui_components.kpi_status_from_thresholds(1.0, warning=3.0, danger=1.5, higher_is_worse=False) == "riesgo"


# ---------------------------------------------------------------------------
# Integración: resumen.py / fundamental.py ya no confunden ausente con cero
# ---------------------------------------------------------------------------


def test_resumen_ejecutivo_ya_no_usa_st_metric_ad_hoc_para_el_scorecard():
    source = (PROJECT_ROOT / "modulos" / "resumen.py").read_text(encoding="utf-8")
    assert "render_kpi_card" in source
    assert "sc1.metric(" not in source
    assert "sc2.metric(" not in source
    assert "sc3.metric(" not in source
    assert "sc4.metric(" not in source


def test_fundamental_dupont_ya_no_usa_get_safe_last_val_con_default_cero():
    source = (PROJECT_ROOT / "modulos" / "fundamental.py").read_text(encoding="utf-8")
    assert "render_kpi_card" in source
    assert "c_dp1.metric(" not in source
    assert "c_dp2.metric(" not in source
    assert "c_dp3.metric(" not in source
    assert "c_dp4.metric(" not in source

    # El escudo local del bloque DuPont debe devolver None, no 0.0, ante datos
    # ausentes (antes: "return 0.0", exactamente el 0-sintético que el resto
    # de la tarea ya eliminó de la capa de datos).
    start = source.index("def get_safe_last_val")
    end = source.index("dupont_margen = get_safe_last_val")
    shield_body = source[start:end]
    assert "return None" in shield_body
    assert "return 0.0" not in shield_body
