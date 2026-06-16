from __future__ import annotations

import os
import subprocess
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOB_PATH = PROJECT_ROOT / "telegram_bot.py"
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "daily_scan.yml"


def ejecutar_panel_automatizacion():
    st.markdown("### 🤖 Automatización Telegram y Cron Job")
    st.caption("Ejecución headless para enviar un resumen diario al cierre de Wall Street.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Script headless", "OK" if JOB_PATH.exists() else "Falta")
    c2.metric("GitHub Actions", "OK" if WORKFLOW_PATH.exists() else "Falta")
    c3.metric("Telegram token", "Configurado" if (os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")) else "Usa secrets/env")

    st.markdown("#### Ejecución local")
    st.code("TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=... venv/bin/python telegram_bot.py", language="bash")

    st.markdown("#### Programación recomendada")
    st.code("30 22 * * 1-5 cd /home/gael/Escritorio/terminal-quant-value-main && venv/bin/python telegram_bot.py", language="cron")

    if st.button("Probar briefing en seco", type="primary"):
        try:
            result = subprocess.run(
                ["venv/bin/python", "telegram_bot.py"],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                timeout=60,
            )
            if result.returncode == 0:
                st.success("Briefing generado.")
                st.code(result.stdout)
            else:
                st.error(result.stderr or result.stdout)
        except Exception as exc:
            st.error(str(exc))

    with st.expander("Variables necesarias para GitHub Actions/PythonAnywhere"):
        st.markdown(
            """
            - `TELEGRAM_BOT_TOKEN`
            - `TELEGRAM_TOKEN`
            - `TELEGRAM_CHAT_ID` o suscriptores guardados por el bot
            """
        )
