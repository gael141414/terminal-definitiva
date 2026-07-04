#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _sample_watchlist() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Ticker": "AAPL",
                "Precio Actual": 100.0,
                "Var Diaria (%)": 1.1,
                "Precio Objetivo": 110.0,
                "Distancia Num": -0.0909,
                "Distancia al Target": "✅ En target",
                "Acción Research": "Vigilar / estudiar",
                "Acción Score": "Candidato prioritario",
                "Bucket Score": "🟢 Prioritario",
                "ValueQuant": 78.0,
                "Score bruto": 83.0,
                "Buffett": 82.0,
                "Confianza": 0.82,
                "Nivel confianza": "Alta",
                "Ajuste Calidad": False,
                "Quality Gate": "-",
                "Red Flags": 0,
                "Margen Seguridad": 0.15,
                "Régimen Valoración": "Razonable",
                "Comparador": "MSFT",
                "Fuente": "Research Core",
                "Último análisis": "2026-07-04T18:00:00+00:00",
                "Prioridad Score": 82.5,
            },
            {
                "Ticker": "XYZ",
                "Precio Actual": 200.0,
                "Var Diaria (%)": -0.5,
                "Precio Objetivo": 160.0,
                "Distancia Num": 0.25,
                "Distancia al Target": "+25.0% vs target",
                "Acción Research": "Mantener",
                "Acción Score": "Revisión manual obligatoria",
                "Bucket Score": "🔴 Riesgo crítico",
                "ValueQuant": 64.0,
                "Score bruto": 82.0,
                "Buffett": 70.0,
                "Confianza": 0.48,
                "Nivel confianza": "Baja",
                "Ajuste Calidad": True,
                "Quality Gate": "Confianza operativa limitada en bloques críticos.",
                "Red Flags": 1,
                "Margen Seguridad": -0.12,
                "Régimen Valoración": "Exigente",
                "Comparador": "-",
                "Fuente": "Research Core",
                "Último análisis": "2026-07-04T18:00:00+00:00",
                "Prioridad Score": 41.0,
            },
        ]
    )


def run_contract_checks() -> list[str]:
    from modulos.briefing_payloads import build_briefing_payloads
    from modulos.opportunity_briefing import (
        _alerts_for_ticker,
        _classify_opportunity,
        _opportunity_score,
        build_opportunity_briefing_markdown,
    )
    from modulos.watchlist_alerts import build_watchlist_alerts

    checks: list[str] = []
    df_watch = _sample_watchlist()
    df_alerts = build_watchlist_alerts(df_watch)

    rows = []
    for _, row in df_watch.iterrows():
        row_dict = row.to_dict()
        ticker = row_dict["Ticker"]
        ticker_alerts = _alerts_for_ticker(df_alerts, ticker)
        bucket, reason = _classify_opportunity(row_dict, ticker_alerts)
        score = _opportunity_score(row_dict, ticker_alerts)
        top_alert = ticker_alerts.iloc[0].to_dict() if not ticker_alerts.empty else {}

        rows.append(
            {
                "Prioridad": bucket,
                "Ticker": ticker,
                "Score Oportunidad": score,
                "Prioridad Score": row_dict.get("Prioridad Score"),
                "Bucket Score": row_dict.get("Bucket Score"),
                "Razón": reason,
                "Acción sugerida": top_alert.get("Acción sugerida", "Mantener seguimiento"),
                "Acción Score": row_dict.get("Acción Score"),
                "Alerta principal": top_alert.get("Alerta", "Sin alerta relevante"),
                "Precio Actual": row_dict.get("Precio Actual"),
                "Target": row_dict.get("Precio Objetivo"),
                "Distancia": row_dict.get("Distancia al Target"),
                "ValueQuant": row_dict.get("ValueQuant"),
                "Score bruto": row_dict.get("Score bruto"),
                "Confianza": row_dict.get("Confianza"),
                "Nivel confianza": row_dict.get("Nivel confianza"),
                "Ajuste Calidad": row_dict.get("Ajuste Calidad"),
                "Red Flags": row_dict.get("Red Flags"),
                "Quality Gate": row_dict.get("Quality Gate"),
                "Margen Seguridad": row_dict.get("Margen Seguridad"),
                "Último análisis": row_dict.get("Último análisis"),
            }
        )

    df_briefing = pd.DataFrame(rows)

    aapl = df_briefing[df_briefing["Ticker"] == "AAPL"].iloc[0].to_dict()
    xyz = df_briefing[df_briefing["Ticker"] == "XYZ"].iloc[0].to_dict()

    assert_true(aapl["Prioridad"] == "Comprar / revisar hoy", "Candidato prioritario sin gates debe ir a revisar hoy")
    assert_true(xyz["Prioridad"] == "Recalcular análisis", "Red flags/quality gate debe forzar recalcular")
    assert_true(isinstance(aapl["Score Oportunidad"], int), "Score oportunidad debe ser entero")
    assert_true(aapl["Prioridad Score"] == 82.5, "Briefing debe preservar Prioridad Score")
    assert_true(aapl["Acción Score"] == "Candidato prioritario", "Briefing debe preservar Acción Score")
    checks.append("classification consumes score payload fields")

    markdown = build_opportunity_briefing_markdown(df_watch, df_alerts, df_briefing)
    assert_true("Acción Score" in markdown, "Markdown debe incluir Acción Score")
    assert_true("P.Score" in markdown, "Markdown debe incluir prioridad score")
    assert_true("Activos con quality gate" in markdown, "Markdown debe resumir quality gates")
    checks.append("markdown export includes score payload fields")

    payloads = build_briefing_payloads(df_watch, df_alerts, df_briefing)
    assert_true("Prioridad score:" in payloads.compact_text, "Mensaje compacto debe incluir prioridad score")
    assert_true("Acción score:" in payloads.compact_text, "Mensaje compacto debe incluir acción score")
    assert_true("Acción Score" in payloads.email_html, "Email HTML debe incluir acción score")
    assert_true("P.Score" in payloads.email_html, "Email HTML debe incluir prioridad score")
    checks.append("briefing payloads include score payload fields")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Opportunity Briefing Score Payload Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Opportunity Briefing Score Payload Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
