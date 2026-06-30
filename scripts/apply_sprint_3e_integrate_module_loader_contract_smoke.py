from __future__ import annotations

from pathlib import Path

SMOKE_PATH = Path("modulos/smoke_tests.py")

CRITICAL_FILE_ANCHOR = '    "scripts/print_product_surface_audit.py",\n'
CRITICAL_FILE_LINE = '    "scripts/test_module_loader_contract.py",\n'

SCORING_FUNCTION_ANCHOR = "\ndef _check_scoring_model() -> list[SmokeCheck]:\n"
MODULE_LOADER_CONTRACT_FUNCTION = '''

def _check_module_loader_contract() -> list[SmokeCheck]:
    """Ejecuta los checks contractuales de module_loader/safe_call."""

    checks: list[SmokeCheck] = []
    try:
        contract = importlib.import_module("scripts.test_module_loader_contract")
        contract_checks = contract.run_contract_checks()
        checks.append(_ok("module_loader_contract:loaded", f"{len(contract_checks)} checks"))
        checks.append(_ok("module_loader_contract:behavior", "safe_call contract OK"))
    except Exception as exc:
        checks.append(_fail("module_loader_contract:behavior", f"{type(exc).__name__}: {exc}"))
    return checks
'''

PRODUCT_AUDIT_CALL_ANCHOR = "    checks.extend(_check_product_surface_audit())\n"
MODULE_LOADER_CALL_LINE = "    checks.extend(_check_module_loader_contract())\n"


def main() -> int:
    if not SMOKE_PATH.exists():
        raise FileNotFoundError("No se encuentra modulos/smoke_tests.py. Ejecuta desde la raíz del proyecto.")

    source = SMOKE_PATH.read_text(encoding="utf-8")

    if MODULE_LOADER_CALL_LINE in source:
        print("Sin cambios: Sprint 3E ya parece aplicado.")
        return 0

    new_source = source

    if CRITICAL_FILE_LINE not in new_source:
        if CRITICAL_FILE_ANCHOR not in new_source:
            raise RuntimeError("No se encontró el punto de inserción en CRITICAL_FILES.")
        new_source = new_source.replace(CRITICAL_FILE_ANCHOR, CRITICAL_FILE_ANCHOR + CRITICAL_FILE_LINE, 1)

    if "def _check_module_loader_contract()" not in new_source:
        if SCORING_FUNCTION_ANCHOR not in new_source:
            raise RuntimeError("No se encontró el punto de inserción antes de _check_scoring_model.")
        new_source = new_source.replace(SCORING_FUNCTION_ANCHOR, MODULE_LOADER_CONTRACT_FUNCTION + SCORING_FUNCTION_ANCHOR, 1)

    if MODULE_LOADER_CALL_LINE not in new_source:
        if PRODUCT_AUDIT_CALL_ANCHOR not in new_source:
            raise RuntimeError("No se encontró la llamada a _check_product_surface_audit en run_smoke_tests.")
        new_source = new_source.replace(PRODUCT_AUDIT_CALL_ANCHOR, PRODUCT_AUDIT_CALL_ANCHOR + MODULE_LOADER_CALL_LINE, 1)

    required_tokens = [
        '"scripts/test_module_loader_contract.py"',
        "def _check_module_loader_contract()",
        'importlib.import_module("scripts.test_module_loader_contract")',
        "contract.run_contract_checks()",
        "checks.extend(_check_module_loader_contract())",
    ]
    missing = [token for token in required_tokens if token not in new_source]
    if missing:
        raise RuntimeError(f"La integración de Sprint 3E quedó incompleta. Faltan: {missing}")

    backup = SMOKE_PATH.with_suffix(".py.bak_sprint_3e")
    backup.write_text(source, encoding="utf-8")
    SMOKE_PATH.write_text(new_source, encoding="utf-8")

    print("OK: Sprint 3E aplicado.")
    print("run_smoke_tests.py ahora ejecuta el contrato de module_loader/safe_call.")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile modulos/smoke_tests.py scripts/apply_sprint_3e_integrate_module_loader_contract_smoke.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
