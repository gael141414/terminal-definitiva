#!/usr/bin/env python3
"""Ejecuta el briefing de oportunidades desde terminal.

Ejemplos:
    python scripts/run_opportunity_briefing.py
    python scripts/run_opportunity_briefing.py --format compact
    python scripts/run_opportunity_briefing.py --send-telegram --yes

El envio a Telegram nunca se ejecuta sin `--send-telegram --yes`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modulos.briefing_runner import run_local_briefing  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera el briefing de oportunidades de ValueQuant sin abrir Streamlit.",
    )
    parser.add_argument(
        "--output-dir",
        default="exports/briefings",
        help="Carpeta de salida para los archivos generados. Default: exports/briefings",
    )
    parser.add_argument(
        "--format",
        choices=["all", "markdown", "html", "compact"],
        default="all",
        help="Formato de salida. Default: all",
    )
    parser.add_argument(
        "--send-telegram",
        action="store_true",
        help="Envia el briefing compacto a Telegram. Requiere tambien --yes.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirmacion explicita para envio a Telegram. Sin este flag no se envia nada.",
    )
    parser.add_argument(
        "--force-frequency",
        action="store_true",
        help="Permite saltarse el bloqueo de frecuencia configurado. Usar solo manualmente.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_local_briefing(
        output_dir=args.output_dir,
        output_format=args.format,
        send_telegram=args.send_telegram,
        confirmed=args.yes,
        force_frequency=args.force_frequency,
    )

    print("=== ValueQuant Briefing Runner ===")
    print(f"Generado: {result.generated_at}")
    print(result.detail)
    print("")

    if result.outputs:
        print("Archivos generados:")
        for output in result.outputs:
            print(f"- {output.path}")
    else:
        print("No se generaron archivos.")

    if result.telegram_attempted:
        print("")
        print("Telegram:")
        print(f"- OK: {result.telegram_ok}")
        print(f"- Detalle: {result.telegram_detail}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
