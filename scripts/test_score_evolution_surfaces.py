#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _sample_history() -> dict[str, list[dict]]:
    return {
        "AAPL": [
            {
                "ticker": "AAPL",
                "saved_at": "2026-07-04T18:00:00+00:00",
                "valuequant_score": 76.0,
                "score_raw_score": 80.0,
                "buffett_score": 82.0,
                "margin_of_safety": 0.14,
                "confidence": 0.82,
                "score_confidence_label": "Alta",
                "score_decision_action": "Candidato prioritario",
                "score_quality_adjusted": False,
                "score_red_flags_count": 0,
                "valuation_regime": "Razonable",
                "target": 110.0,
            },
            {
                "ticker": "AAPL",
                "saved_at": "2026-06-04T18:00:00+00:00",
                "valuequant_score": 68.0,
                "score_raw_score": 72.0,
                "buffett_score": 78.0,
                "margin_of_safety": 0.04,
                "confidence": 0.75,
                "score_confidence_label": "Media",
                "score_decision_action": "Atractiva con matices",
                "score_quality_adjusted": False,
                "score_red_flags_count": 0,
                "valuation_regime": "Aceptable",
                "target": 100.0,
            },
        ],
        "XYZ": [
            {
                "ticker": "XYZ",
                "saved_at": "2026-07-04T18:00:00+00:00",
                "valuequant_score": 52.0,
                "score_raw_score": 64.0,
                "buffett_score": 60.0,
                "margin_of_safety": -0.08,
                "confidence": 0.50,
                "score_confidence_label": "Baja",
                "score_decision_action": "Esperar más datos",
                "score_quality_adjusted": False,
                "score_red_flags_count": 0,
                "valuation_regime": "Exigente",
                "target": 80.0,
            },
            {
                "ticker": "XYZ",
                "saved_at": "2026-06-04T18:00:00+00:00",
                "valuequant_score": 63.0,
                "score_raw_score": 68.0,
                "buffett_score": 66.0,
                "margin_of_safety": 0.02,
                "confidence": 0.70,
                "score_confidence_label": "Media",
                "score_decision_action": "Atractiva con matices",
                "score_quality_adjusted": False,
                "score_red_flags_count": 0,
                "valuation_regime": "Aceptable",
                "target": 90.0,
            },
        ],
    }


def run_contract_checks() -> list[str]:
    checks: list[str] = []

    with patch("modulos.analysis_store.load_saved_analyses", return_value=_sample_history()):
        from modulos.watchlist import _build_watchlist_row
        from modulos.opportunity_briefing import (
            _classify_opportunity,
            _opportunity_score,
            build_watchlist_dataframe,
        )

        row = _build_watchlist_row(
            ticker="AAPL",
            item={"source": "Research Core", "last_saved_at": "2026-07-04T18:00:00+00:00"},
            analysis={
                "action": "Vigilar / estudiar",
                "score_decision_action": "Candidato prioritario",
                "score_raw_score": 80.0,
                "score_quality_adjusted": False,
                "score_confidence_label": "Alta",
                "score_red_flags_count": 0,
                "valuequant_score": 76.0,
                "buffett_score": 82.0,
                "confidence": 0.82,
                "margin_of_safety": 0.14,
                "valuation_regime": "Razonable",
                "competitor": "MSFT",
            },
            precio_actual=100.0,
            cambio_pct=1.2,
            target=110.0,
            distancia_alerta="✅ EN PRECIO",
        )

        assert_true(row["Tendencia Score"] == "Mejora", "Watchlist debe incorporar tendencia de mejora")
        assert_true(row["Delta Score"] == 8.0, "Watchlist debe incorporar delta histórico")
        assert_true(row["Ajuste Tendencia"] > 0, "Mejora debe añadir ajuste positivo")
        assert_true(row["Prioridad Score"] > 0, "Prioridad score debe seguir calculándose")
        checks.append("watchlist row includes score evolution fields")

        sample_watchlist = {
            "AAPL": {
                "target": 110.0,
                "source": "Research Core",
                "last_saved_at": "2026-07-04T18:00:00+00:00",
                "last_analysis": {
                    "action": "Vigilar / estudiar",
                    "score_decision_action": "Candidato prioritario",
                    "score_raw_score": 80.0,
                    "score_quality_adjusted": False,
                    "score_confidence_label": "Alta",
                    "score_red_flags_count": 0,
                    "valuequant_score": 76.0,
                    "buffett_score": 82.0,
                    "confidence": 0.82,
                    "margin_of_safety": 0.14,
                    "valuation_regime": "Razonable",
                    "competitor": "MSFT",
                },
            },
            "XYZ": {
                "target": 80.0,
                "source": "Research Core",
                "last_saved_at": "2026-07-04T18:00:00+00:00",
                "last_analysis": {
                    "action": "Mantener",
                    "score_decision_action": "Esperar más datos",
                    "score_raw_score": 64.0,
                    "score_quality_adjusted": False,
                    "score_confidence_label": "Baja",
                    "score_red_flags_count": 0,
                    "valuequant_score": 52.0,
                    "buffett_score": 60.0,
                    "confidence": 0.50,
                    "margin_of_safety": -0.08,
                    "valuation_regime": "Exigente",
                    "competitor": "-",
                },
            },
        }

        def fake_price(ticker: str) -> dict[str, float]:
            if ticker == "AAPL":
                return {"price": 100.0, "change_pct": 1.2}
            return {"price": 100.0, "change_pct": -0.4}

        with patch("modulos.opportunity_briefing._read_watchlist", return_value=sample_watchlist):
            with patch("modulos.opportunity_briefing._price_snapshot", side_effect=fake_price):
                df = build_watchlist_dataframe()

        assert_true("Tendencia Score" in df.columns, "Briefing watchlist dataframe debe incluir tendencia")
        assert_true("Delta Score" in df.columns, "Briefing watchlist dataframe debe incluir delta")
        assert_true("Ajuste Tendencia" in df.columns, "Briefing watchlist dataframe debe incluir ajuste por tendencia")

        aapl = df[df["Ticker"] == "AAPL"].iloc[0].to_dict()
        xyz = df[df["Ticker"] == "XYZ"].iloc[0].to_dict()

        aapl_bucket, aapl_reason = _classify_opportunity(aapl, pd.DataFrame())
        xyz_bucket, xyz_reason = _classify_opportunity(xyz, pd.DataFrame())

        assert_true(aapl["Tendencia Score"] == "Mejora", "AAPL debe marcar mejora")
        assert_true(aapl_bucket == "Comprar / revisar hoy", "Mejora clara con margen no negativo debe priorizar")
        assert_true("Mejora" in aapl_reason or "prioritario" in aapl_reason.lower(), "Razón debe recoger score/trend")
        assert_true(xyz["Tendencia Score"] == "Deterioro", "XYZ debe marcar deterioro")
        assert_true(xyz_bucket == "Recalcular análisis", "Deterioro fuerte debe forzar recalcular")
        assert_true(isinstance(_opportunity_score(aapl, pd.DataFrame()), int), "Score oportunidad debe seguir siendo entero")
        checks.append("briefing consumes score evolution for classification and scoring")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Score Evolution Surfaces Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Score Evolution Surfaces Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
