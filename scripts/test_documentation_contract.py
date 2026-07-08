#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def run_contract_checks() -> list[str]:
    checks: list[str] = []

    required_files = [
        "README.md",
        "docs/USER_GUIDE.md",
        "docs/RELEASE_RUNBOOK.md",
    ]
    for file_path in required_files:
        assert_true((PROJECT_ROOT / file_path).exists(), f"Falta {file_path}")
    checks.append("documentation files exist")

    readme = _read("README.md")
    for token in [
        "Research Core",
        "ValueQuant Score",
        "Exportación institucional",
        "QA local recomendado",
        "run_release_readiness.py",
        "Advertencia",
    ]:
        assert_true(token in readme, f"README debe incluir {token}")
    checks.append("README documents current product surface")

    guide = _read("docs/USER_GUIDE.md")
    for token in [
        "Research Core",
        "Interpretación del ValueQuant Score",
        "Quality gates",
        "Watchlist",
        "Backtesting básico",
        "Confianza predictiva",
        "Exportación institucional",
        "QA antes de entregar",
    ]:
        assert_true(token in guide, f"USER_GUIDE debe incluir {token}")
    checks.append("user guide covers operating workflow")

    runbook = _read("docs/RELEASE_RUNBOOK.md")
    for token in [
        "Preparar rama",
        "Validación local mínima",
        "No usar",
        "git add .",
        "Pull Request",
        "Merge",
        "QA final tras merge",
        "Criterios de bloqueo",
    ]:
        assert_true(token in runbook, f"RELEASE_RUNBOOK debe incluir {token}")
    checks.append("release runbook covers sprint workflow")

    combined = "\n".join([readme, guide, runbook]).lower()
    assert_true(".streamlit/secrets.toml` reales" in readme, "README debe advertir sobre secrets reales")
    assert_true("no constituye asesoramiento financiero" in combined, "Debe existir disclaimer financiero")
    checks.append("documentation includes safety disclaimers")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Documentation Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Documentation Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
