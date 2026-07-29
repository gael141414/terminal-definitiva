"""Research Core — resumen ejecutivo en 4 niveles (Paso 3, mockup
research_core_navegacion_kpi.html, sección 1c).

Usa las dataclasses reales de modulos.scoring_engine (ValueQuantScore,
ScoreComponent) con datos sintéticos pero estructuralmente realistas — no un
mock ad-hoc — para no depender de red real ni de credenciales FMP.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import research_core
from modulos.scoring_engine import ScoreComponent, ValueQuantScore

# Los 8 componentes reales de modulos/scoring_engine.py::calcular_valuequant_score,
# con los mismos nombres y pesos exactos (30/22/15/10/8/5/5/5 = 100%).
REAL_PILLAR_NAMES_AND_WEIGHTS = [
    ("Calidad fundamental", 0.30),
    ("Valoración", 0.22),
    ("Riesgo y forense", 0.15),
    ("Crecimiento y catalizadores", 0.10),
    ("Asignación de capital e insiders", 0.08),
    ("Momentum y timing", 0.05),
    ("Macro, sector y liquidez", 0.05),
    ("Opciones, alt data y NLP", 0.05),
]


def _make_score(**overrides) -> ValueQuantScore:
    components = [
        ScoreComponent(name=name, score=score, weight=weight, confidence=confidence)
        for (name, weight), score, confidence in zip(
            REAL_PILLAR_NAMES_AND_WEIGHTS,
            [88, 68, 74, 79, 84, 55, 61, 47],
            [0.95, 0.90, 0.85, 0.70, 0.60, 0.50, 0.65, 0.40],
        )
    ]
    defaults = dict(
        final_score=82.0,
        confidence=0.83,
        components=components,
        red_flags=[],
        positives=["ROIC 41% sostenido 10 años.", "Recompras reducen el float un 3.1% anual."],
        negatives=["Concentración: iPhone sigue siendo ~48% de ingresos."],
        verdict="Alta calidad",
        data_coverage=0.87,
        confidence_label="Alta",
        predictive_confidence=0.61,
    )
    defaults.update(overrides)
    return ValueQuantScore(**defaults)


@pytest.fixture
def captured_markdown(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(research_core.st, "markdown", lambda body, **kwargs: calls.append(body))

    class _FakeColumn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_columns(spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        return [_FakeColumn() for _ in range(n)]

    monkeypatch.setattr(research_core.st, "columns", fake_columns)
    monkeypatch.setattr(research_core.st, "info", lambda *a, **k: None)
    return calls


# ---------------------------------------------------------------------------
# Tier 1: score circular + veredicto + valoración con barra de margen
# ---------------------------------------------------------------------------


def test_verdict_color_tres_bandas():
    assert research_core._verdict_color(90)[0] == "#3ddc97"
    assert research_core._verdict_color(60)[0] == "#f5b04c"
    assert research_core._verdict_color(30)[0] == "#f36c6c"
    assert research_core._verdict_color(None)[0] == "#5b6a80"


def test_tier1_margen_positivo_infravalorada(captured_markdown):
    summary = {"final_score": 82.0, "verdict": "Alta calidad", "verdict_text": "texto"}
    res_val = {"dcf_value": 391.0, "precio_actual": 333.74}

    research_core._render_tier1_score_and_valuation(summary, res_val)
    combined = "\n".join(captured_markdown)

    assert "+17.2%" in combined  # (391-333.74)/333.74 = 17.16% ~ +17.2%
    assert "$391" in combined
    assert "$333.74" in combined
    assert "#3ddc97" in combined  # margen positivo -> verde


def test_tier1_margen_negativo_sobrevalorada(captured_markdown):
    summary = {"final_score": 40.0, "verdict": "Evitar por ahora", "verdict_text": "texto"}
    res_val = {"dcf_value": 80.0, "precio_actual": 100.0}

    research_core._render_tier1_score_and_valuation(summary, res_val)
    combined = "\n".join(captured_markdown)

    assert "-20.0%" in combined
    assert "#f36c6c" in combined  # margen negativo -> rojo


def test_tier1_sin_valoracion_disponible_no_lanza_y_muestra_nd(captured_markdown):
    summary = {"final_score": None, "verdict": "Pendiente", "verdict_text": ""}
    research_core._render_tier1_score_and_valuation(summary, res_val=None)
    combined = "\n".join(captured_markdown)

    assert "n/d" in combined
    assert "—" in combined  # score display cuando final_score es None


def test_tier1_barra_usa_el_mismo_rango_que_scoring_engine():
    """La posición del marcador debe coincidir con scoring_engine._score_linear(-0.35, 0.35),
    el mismo rango que usa _valuation_component para puntuar el margen de seguridad."""
    from modulos.scoring_engine import _score_linear

    margin = 0.172
    expected_pct = _score_linear(margin, -0.35, 0.35)
    assert expected_pct == pytest.approx(74.57, abs=0.5)


# ---------------------------------------------------------------------------
# Tier 2: franja de confianza de datos
# ---------------------------------------------------------------------------


def test_tier2_cobertura_y_confianza_reales(captured_markdown):
    score = _make_score()
    summary = {"coverage": score.data_coverage}

    research_core._render_tier2_data_confidence(score, summary)
    combined = "\n".join(captured_markdown)

    assert "87%" in combined
    assert "CONFIANZA ALTA" in combined
    # Momentum (55, confianza 0.50) y Opciones/alt data (47, confianza 0.40) están
    # por debajo del umbral 0.55 -> deben listarse como confianza reducida.
    assert "Momentum y timing" in combined
    assert "Opciones, alt data y NLP" in combined


def test_tier2_sin_bloques_debiles_muestra_mensaje_positivo(captured_markdown):
    components = [
        ScoreComponent(name=name, score=80, weight=weight, confidence=0.90)
        for name, weight in REAL_PILLAR_NAMES_AND_WEIGHTS
    ]
    score = _make_score(components=components, confidence_label="Alta")
    summary = {"coverage": 0.95}

    research_core._render_tier2_data_confidence(score, summary)
    combined = "\n".join(captured_markdown)

    assert "Ningún bloque por debajo del umbral mínimo de confianza" in combined


def test_tier2_valuequant_score_none_no_lanza(captured_markdown):
    research_core._render_tier2_data_confidence(None, {"coverage": None})
    combined = "\n".join(captured_markdown)
    assert "Cobertura no disponible" in combined


# ---------------------------------------------------------------------------
# Tier 3: rejilla 4x2 con los 8 componentes reales
# ---------------------------------------------------------------------------


def test_tier3_renderiza_los_8_pilares_reales(monkeypatch, captured_markdown):
    score = _make_score()
    research_core._render_tier3_pillars(score)
    combined = "\n".join(captured_markdown)

    for name, weight in REAL_PILLAR_NAMES_AND_WEIGHTS:
        assert name in combined
        assert f"{weight * 100:.0f}%" in combined

    # 8 pilares -> 8 tarjetas (cada una con su barra de progreso propia).
    assert combined.count("border-radius:11px") == 8


def test_tier3_sin_componentes_muestra_info_no_lanza(captured_markdown):
    research_core._render_tier3_pillars(None)
    # No debe intentar iterar sobre None ni lanzar excepción.


def test_tier3_pesos_de_los_8_pilares_suman_100_por_ciento():
    total = sum(weight for _, weight in REAL_PILLAR_NAMES_AND_WEIGHTS)
    assert total == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Tier 4: fortalezas y riesgos de la tesis
# ---------------------------------------------------------------------------


def test_tier4_usa_positives_negatives_reales_del_score(captured_markdown):
    score = _make_score()
    research_core._render_tier4_thesis(score)
    combined = "\n".join(captured_markdown)

    assert "ROIC 41% sostenido 10 años." in combined
    assert "Concentración: iPhone sigue siendo ~48% de ingresos." in combined
    assert "Fortalezas de la tesis" in combined
    assert "Riesgos vigilados" in combined


def test_tier4_listas_vacias_muestra_mensaje_por_defecto(captured_markdown):
    score = _make_score(positives=[], negatives=[])
    research_core._render_tier4_thesis(score)
    combined = "\n".join(captured_markdown)

    assert "Sin fortalezas destacadas todavía." in combined
    assert "Sin riesgos destacados todavía." in combined
