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

    return "\n\n".join(sections)


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
