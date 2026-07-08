#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _score(**kwargs):
    defaults = {
        "final_score": 81.0,
        "raw_score": 84.0,
        "verdict": "Alta calidad",
        "confidence": 0.77,
        "confidence_label": "Alta",
        "data_coverage": 0.91,
        "predictive_confidence": 0.69,
        "model_version": "VQ_SCORE_EXPORT_TEST",
        "decision_action": "Candidato prioritario",
        "decision_notes": ["Validar valoración", "Revisar riesgos"],
        "quality_adjusted": False,
        "quality_gate_reason": "",
        "red_flags": [],
        "positives": ["Buen retorno sobre capital"],
        "negatives": [],
        "components": [],
        "top_components": [],
        "weakest_components": [],
    }
    defaults.update(kwargs)

    obj = SimpleNamespace(**defaults)

    def to_summary_payload(ticker):
        return {
            "ticker": ticker,
            "model_version": obj.model_version,
            "final_score": obj.final_score,
            "raw_score": obj.raw_score,
            "verdict": obj.verdict,
            "confidence": obj.confidence,
            "confidence_label": obj.confidence_label,
            "data_coverage": obj.data_coverage,
            "predictive_confidence": obj.predictive_confidence,
            "decision_action": obj.decision_action,
            "decision_notes": obj.decision_notes,
            "quality_adjusted": obj.quality_adjusted,
            "quality_gate_reason": obj.quality_gate_reason,
            "red_flags": obj.red_flags,
            "positives": obj.positives,
            "negatives": obj.negatives,
            "top_components": obj.top_components,
            "weakest_components": obj.weakest_components,
        }

    obj.to_summary_payload = to_summary_payload
    return obj


def run_contract_checks() -> list[str]:
    from modulos.research_report import (
        build_institutional_export_files,
        build_institutional_export_metadata,
        build_institutional_export_pack,
        build_institutional_export_zip,
        build_institutional_memo_markdown,
    )

    checks: list[str] = []
    ticker = "AAPL"
    score = _score()

    memo = build_institutional_memo_markdown(
        ticker=ticker,
        ticker_competidor="MSFT",
        valuequant_score=score,
        res_val={},
        nota_buffett=75.0,
    )
    assert_true("Memo ejecutivo" in memo, "El memo debe tener título ejecutivo")
    assert_true("Decisión propuesta" in memo, "El memo debe incluir decisión propuesta")
    assert_true("ValueQuant Score" in memo, "El memo debe incluir score")
    checks.append("committee memo markdown is generated")

    metadata = build_institutional_export_metadata(
        ticker=ticker,
        ticker_competidor="MSFT",
        valuequant_score=score,
        res_val={},
        nota_buffett=75.0,
    )
    assert_true(metadata["schema_version"] == "institutional_export_v1", "Schema version incorrecta")
    assert_true(metadata["ticker"] == "AAPL", "Ticker metadata incorrecto")
    assert_true(metadata["competitor"] == "MSFT", "Competidor metadata incorrecto")
    assert_true(metadata["score"]["final_score"] == 81.0, "Score metadata incorrecto")
    assert_true(metadata["exports"]["zip_bundle"] is True, "Metadata debe declarar ZIP")
    json.dumps(metadata, ensure_ascii=False)
    checks.append("institutional metadata is JSON serializable")

    files = build_institutional_export_files(
        ticker=ticker,
        ticker_competidor="MSFT",
        valuequant_score=score,
        res_val={},
        nota_buffett=75.0,
        res_is={},
        res_bs={},
        res_cf={},
    )
    assert_true(len(files) == 4, "El pack debe generar 4 archivos")
    assert_true(any(name.endswith("_research_report.md") for name in files), "Falta informe markdown")
    assert_true(any(name.endswith("_research_report_print.html") for name in files), "Falta HTML imprimible")
    assert_true(any(name.endswith("_committee_memo.md") for name in files), "Falta memo comité")
    assert_true(any(name.endswith("_metadata.json") for name in files), "Falta metadata JSON")
    assert_true(all(isinstance(payload, bytes) and payload for payload in files.values()), "Todos los archivos deben tener bytes")
    checks.append("institutional export files are built")

    zip_bytes = build_institutional_export_zip(files)
    assert_true(isinstance(zip_bytes, bytes) and len(zip_bytes) > 100, "ZIP debe contener bytes")
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert_true(len(names) == 4, "ZIP debe contener los 4 archivos")
        assert_true(any(name.endswith("_metadata.json") for name in names), "ZIP debe incluir metadata")
    checks.append("institutional ZIP bundle contains all files")

    pack = build_institutional_export_pack(
        ticker=ticker,
        ticker_competidor="MSFT",
        valuequant_score=score,
        res_val={},
        nota_buffett=75.0,
        res_is={},
        res_bs={},
        res_cf={},
    )
    assert_true(pack["ticker"] == "AAPL", "Pack debe normalizar ticker")
    assert_true(pack["file_count"] == 4, "Pack debe contar archivos")
    assert_true(pack["zip_size_bytes"] == len(pack["zip"]), "Tamaño ZIP debe cuadrar")
    assert_true(pack["metadata_filename"].endswith("_metadata.json"), "Pack debe exponer metadata filename")
    checks.append("institutional export pack returns files, zip and metadata")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Institutional Export Pack Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Institutional Export Pack Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
