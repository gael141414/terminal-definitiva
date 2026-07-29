#!/usr/bin/env bash
set -Eeuo pipefail

# Plantilla segura para la validación cruzada SEC↔FMP nocturna de ValueQuant.
# No contiene credenciales. No la ejecutes desde cron sin adaptar PROJECT_DIR.
# Necesita data/watchlist.json real (local) — no funciona en un checkout de
# CI/GitHub Actions, por eso este job es cron local, no un workflow.

PROJECT_DIR="/home/gael/Escritorio/terminal-limpia"
VENV_DIR="$PROJECT_DIR/.venv"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

if [[ -d "$VENV_DIR" ]]; then
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
fi

python scripts/run_sec_validation.py

# Para avisar por Telegram cuando aparezcan discrepancias nuevas, después de
# validar varias corridas sin envío, usa esta variante manualmente o en cron:
# python scripts/run_sec_validation.py --send-telegram --yes
