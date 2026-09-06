from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_digest() -> str:
    from telegram_valuequant_bot import (
        morning_briefing,
        run_scan,
    )

    sections: list[str] = ["📌 ValueQuant Daily Close Briefing"]
    try:
        sections.append(morning_briefing())
    except Exception as exc:
        sections.append(f"⚠️ Error briefing: {exc}")

    try:
        scan_items = run_scan()
        if scan_items:
            if isinstance(scan_items, str):
                sections.append(scan_items)
            else:
                sections.extend(scan_items)
    except Exception as exc:
        sections.append(f"⚠️ Error scan: {exc}")

    try:
        resumen = resumen_cartera_vs_indice()
        if resumen:
            sections.append(resumen)
    except Exception as exc:
        sections.append(f"⚠️ Error cartera: {exc}")

    return "\n\n".join(sections)


def resumen_cartera_vs_indice() -> str | None:
    """Una línea con la cartera frente al benchmark de flujos igualados.

    Devuelve None si no hay cartera guardada: el digest no debe llevar una
    sección vacía diciendo que no hay nada.
    """
    from modulos.rendimiento_cartera import calcular_rendimiento
    from modulos.rendimiento_cartera_ui import cargar_cartera

    df = cargar_cartera()
    if df is None or df.empty:
        return None

    transacciones = [
        (str(fila["Ticker"]).strip().upper(), float(fila["Importe (€)"]), fila["Fecha"])
        for _, fila in df.dropna(subset=["Ticker"]).iterrows()
    ]
    if not transacciones:
        return None

    resultado = calcular_rendimiento(transacciones)
    if not resultado.valido:
        return None

    r = resultado.resumen
    signo = "🟢" if (r.get("diferencia_eur") or 0) > 0 else "🔴"
    lineas = [
        f"{signo} Cartera vs índice (mismo dinero, mismas fechas)",
        f"Invertido {r['total_invertido_eur']:,.0f} € · "
        f"cartera {r['valor_cartera_eur']:,.0f} € · "
        f"índice {r['valor_benchmark_eur']:,.0f} €",
        f"Diferencia {r['diferencia_eur']:+,.0f} € ({r['diferencia_pct']:+.1f}%)",
    ]
    mejor = max(resultado.atribucion, key=lambda a: a.alfa_eur, default=None)
    peor = min(resultado.atribucion, key=lambda a: a.alfa_eur, default=None)
    if mejor and peor and mejor.ticker != peor.ticker:
        lineas.append(f"Mejor {mejor.ticker} {mejor.alfa_eur:+,.0f} € · "
                      f"peor {peor.ticker} {peor.alfa_eur:+,.0f} €")
    return "\n".join(lineas)


def send_digest(message: str) -> None:
    from telegram_valuequant_bot import TelegramAPI, dispatch_to_subscribers

    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if chat_id:
        TelegramAPI().send_message(chat_id, message)
    else:
        dispatch_to_subscribers(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily headless Telegram digest for ValueQuant Terminal")
    parser.add_argument("--send", action="store_true", help="Envia el briefing por Telegram")
    parser.add_argument("--dry-run", action="store_true", help="Imprime el briefing sin enviarlo")
    args = parser.parse_args()

    message = build_digest()
    if args.send:
        send_digest(message)
    else:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
