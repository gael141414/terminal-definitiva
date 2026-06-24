#!/usr/bin/env bash
set -Eeuo pipefail

# Plantilla segura para generar el briefing semanal de ValueQuant.
# No contiene credenciales. No la ejecutes desde cron sin adaptar PROJECT_DIR.

PROJECT_DIR="/home/gael/Escritorio/terminal-limpia"
VENV_DIR="$PROJECT_DIR/.venv"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

if [[ -d "$VENV_DIR" ]]; then
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
fi

python scripts/run_opportunity_briefing.py \
  --format all

# Variante de envio semanal a Telegram, solo cuando este validado:
# python scripts/run_opportunity_briefing.py --format compact --send-telegram --yes
