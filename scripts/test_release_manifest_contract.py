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

    for file_path in ["VERSION", "CHANGELOG.md", "docs/RELEASE_NOTES_0.1.0_INTERNAL.md"]:
        assert_true((PROJECT_ROOT / file_path).exists(), f"Falta {file_path}")
    checks.append("release manifest files exist")

    version = _read("VERSION").strip()
    assert_true(version == "0.3.0-internal", f"Versión inesperada: {version}")
    checks.append("version marker is stable")

    changelog = _read("CHANGELOG.md")
    for token in [
        "0.3.0-internal",
        "Research Core",
        "ValueQuant Score",
        "Backtesting básico",
        "Exportación institucional",
        "Release readiness",
        "Limitations",
    ]:
        assert_true(token in changelog, f"CHANGELOG debe incluir {token}")
    checks.append("changelog documents internal release")

    release_notes = _read("docs/RELEASE_NOTES_0.1.0_INTERNAL.md")
    for token in [
        "release interna",
        "Superficie funcional incluida",
        "Research Core",
        "ValueQuant Score",
        "Watchlist",
        "Backtesting básico",
        "Exportación institucional",
        "QA y release readiness",
        "Limitaciones conocidas",
    ]:
        assert_true(token in release_notes, f"Release notes deben incluir {token}")
    checks.append("release notes document functional surface and limitations")

    combined = "\n".join([changelog, release_notes]).lower()
    assert_true("no constituye asesoramiento financiero" in combined, "Debe existir disclaimer financiero")
    assert_true("no garantiza rentabilidad" in combined, "Debe existir limitación de rentabilidad")
    checks.append("release notes include safety disclaimers")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Release Manifest Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Release Manifest Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
