from __future__ import annotations

from pathlib import Path

SMOKE_PATH = Path("modulos/smoke_tests.py")

CRITICAL_FILE_ANCHOR = '    "modulos/tool_router.py",\n'
CRITICAL_FILE_LINE = '    "scripts/print_product_surface_audit.py",\n'

SCORING_FUNCTION_ANCHOR = "\ndef _check_scoring_model() -> list[SmokeCheck]:\n"
PRODUCT_AUDIT_FUNCTION = '''

def _check_product_surface_audit() -> list[SmokeCheck]:
    """Comprueba que catálogo, router, módulos y callables estén alineados."""

    checks: list[SmokeCheck] = []
    try:
        audit = importlib.import_module("scripts.print_product_surface_audit")
        issues, routes, mode_counts = audit.audit_catalog()
        failures = [issue for issue in issues if issue.severity == "FAIL"]
        warnings = [issue for issue in issues if issue.severity == "WARN"]

        checks.append(_ok("product_surface:loaded", f"{len(routes)} routes audited"))

        if failures:
            sample = "; ".join(f"{issue.code}:{issue.label}" for issue in failures[:5])
            checks.append(_fail("product_surface:routes", f"{len(failures)} failures; sample={sample}"))
        else:
            checks.append(_ok("product_surface:routes", f"{len(routes)} routes OK; warnings={len(warnings)}"))

        for mode in ("mvp", "consolidated", "complete"):
            count = int(mode_counts.get(mode, 0))
            checks.append(
                _ok(f"product_surface_mode:{mode}", f"{count} tools")
                if count > 0
                else _fail(f"product_surface_mode:{mode}", "no visible tools")
            )
    except Exception as exc:
        checks.append(_fail("product_surface:loaded", f"{type(exc).__name__}: {exc}"))
    return checks
'''

ROUTER_CALL_ANCHOR = "    checks.extend(_check_router())\n"
PRODUCT_AUDIT_CALL_LINE = "    checks.extend(_check_product_surface_audit())\n"


def main() -> int:
    if not SMOKE_PATH.exists():
        raise FileNotFoundError("No se encuentra modulos/smoke_tests.py. Ejecuta desde la raíz del proyecto.")

    source = SMOKE_PATH.read_text(encoding="utf-8")

    if PRODUCT_AUDIT_CALL_LINE in source:
        print("Sin cambios: Sprint 3B ya parece aplicado.")
        return 0

    new_source = source

    if CRITICAL_FILE_LINE not in new_source:
        if CRITICAL_FILE_ANCHOR not in new_source:
            raise RuntimeError("No se encontró el punto de inserción en CRITICAL_FILES.")
        new_source = new_source.replace(CRITICAL_FILE_ANCHOR, CRITICAL_FILE_ANCHOR + CRITICAL_FILE_LINE, 1)

    if "def _check_product_surface_audit()" not in new_source:
        if SCORING_FUNCTION_ANCHOR not in new_source:
            raise RuntimeError("No se encontró el punto de inserción antes de _check_scoring_model.")
        new_source = new_source.replace(SCORING_FUNCTION_ANCHOR, PRODUCT_AUDIT_FUNCTION + SCORING_FUNCTION_ANCHOR, 1)

    if PRODUCT_AUDIT_CALL_LINE not in new_source:
        if ROUTER_CALL_ANCHOR not in new_source:
            raise RuntimeError("No se encontró la llamada a _check_router en run_smoke_tests.")
        new_source = new_source.replace(ROUTER_CALL_ANCHOR, ROUTER_CALL_ANCHOR + PRODUCT_AUDIT_CALL_LINE, 1)

    required_tokens = [
        '"scripts/print_product_surface_audit.py"',
        "def _check_product_surface_audit()",
        'importlib.import_module("scripts.print_product_surface_audit")',
        "audit.audit_catalog()",
        "checks.extend(_check_product_surface_audit())",
    ]
    missing = [token for token in required_tokens if token not in new_source]
    if missing:
        raise RuntimeError(f"La integración de Sprint 3B quedó incompleta. Faltan: {missing}")

    backup = SMOKE_PATH.with_suffix(".py.bak_sprint_3b")
    backup.write_text(source, encoding="utf-8")
    SMOKE_PATH.write_text(new_source, encoding="utf-8")

    print("OK: Sprint 3B aplicado.")
    print("La auditoría de superficie de producto se ejecutará dentro de run_smoke_tests.py.")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile modulos/smoke_tests.py scripts/apply_sprint_3b_integrate_product_audit_smoke.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
