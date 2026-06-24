"""Entrega manual y confirmada de briefings.

Este módulo no programa envíos ni ejecuta automatizaciones. Solo permite enviar
un payload revisado cuando el usuario confirma explícitamente desde la UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib import parse, request, error
import json

import streamlit as st

from modulos.config import CONFIG
from modulos.briefing_payloads import BriefingPayloads
from modulos.automation_logs import log_delivery_attempt


MAX_TELEGRAM_MESSAGE_CHARS = 3900


@dataclass(frozen=True)
class DeliveryStatus:
    configured: bool
    detail: str


@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    sent_parts: int
    detail: str


def telegram_status() -> DeliveryStatus:
    """Comprueba si existe configuración suficiente para envío manual."""

    has_token = bool(str(CONFIG.telegram_bot_token or "").strip())
    has_chat = bool(str(CONFIG.telegram_chat_id or "").strip())

    if has_token and has_chat:
        return DeliveryStatus(True, "Telegram configurado para envío manual.")
    missing = []
    if not has_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not has_chat:
        missing.append("TELEGRAM_CHAT_ID")
    return DeliveryStatus(False, "Falta configurar: " + ", ".join(missing))


def _split_message(text: str, limit: int = MAX_TELEGRAM_MESSAGE_CHARS) -> list[str]:
    """Divide texto largo respetando un límite prudente para Telegram."""

    clean = str(text or "").strip()
    if not clean:
        return []
    if len(clean) <= limit:
        return [clean]

    parts: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in clean.splitlines():
        extra = len(line) + 1
        if current and current_len + extra > limit:
            parts.append("\n".join(current).strip())
            current = [line]
            current_len = extra
        else:
            current.append(line)
            current_len += extra

    if current:
        parts.append("\n".join(current).strip())

    final_parts: list[str] = []
    for part in parts:
        if len(part) <= limit:
            final_parts.append(part)
        else:
            for start in range(0, len(part), limit):
                final_parts.append(part[start : start + limit])
    return [p for p in final_parts if p]


def send_telegram_text(text: str) -> DeliveryResult:
    """Envía texto a Telegram usando la configuración central.

    No debe llamarse desde flujos automáticos. La UI debe exigir confirmación
    explícita antes de invocar esta función.
    """

    status = telegram_status()
    if not status.configured:
        log_delivery_attempt(
            channel="telegram",
            status="error",
            detail=status.detail,
            sent_parts=0,
            message=text,
        )
        return DeliveryResult(False, 0, status.detail)

    parts = _split_message(text)
    if not parts:
        detail = "No hay contenido para enviar."
        log_delivery_attempt(
            channel="telegram",
            status="error",
            detail=detail,
            sent_parts=0,
            message=text,
        )
        return DeliveryResult(False, 0, detail)

    token = str(CONFIG.telegram_bot_token).strip()
    chat_id = str(CONFIG.telegram_chat_id).strip()
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"

    sent = 0
    try:
        for idx, part in enumerate(parts, start=1):
            prefix = f"Parte {idx}/{len(parts)}\n\n" if len(parts) > 1 else ""
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": prefix + part,
                "disable_web_page_preview": True,
            }
            body = parse.urlencode(payload).encode("utf-8")
            req = request.Request(endpoint, data=body, method="POST")
            with request.urlopen(req, timeout=15) as resp:  # noqa: S310 - endpoint oficial con token configurado por usuario
                response_body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(response_body) if response_body else {}
                if not data.get("ok", False):
                    detail = f"Telegram rechazó el envío: {data}"
                    log_delivery_attempt(
                        channel="telegram",
                        status="error",
                        detail=detail,
                        sent_parts=sent,
                        message=text,
                    )
                    return DeliveryResult(False, sent, detail)
            sent += 1
    except error.HTTPError as exc:
        detail_body = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        detail = f"Error HTTP de Telegram: {exc.code} — {detail_body}"
        log_delivery_attempt(
            channel="telegram",
            status="error",
            detail=detail,
            sent_parts=sent,
            message=text,
        )
        return DeliveryResult(False, sent, detail)
    except Exception as exc:
        detail = f"Error enviando a Telegram: {exc}"
        log_delivery_attempt(
            channel="telegram",
            status="error",
            detail=detail,
            sent_parts=sent,
            message=text,
        )
        return DeliveryResult(False, sent, detail)

    detail = f"Enviado correctamente en {sent} parte(s)."
    log_delivery_attempt(
        channel="telegram",
        status="ok",
        detail=detail,
        sent_parts=sent,
        message=text,
    )
    return DeliveryResult(True, sent, detail)


def render_manual_telegram_panel(payloads: BriefingPayloads) -> None:
    """Panel Streamlit para revisar y enviar manualmente el briefing a Telegram."""

    status = telegram_status()

    with st.expander("📲 Envío manual a Telegram", expanded=False):
        st.caption(
            "Envía el briefing compacto solo después de revisarlo y confirmar manualmente. "
            "No hay programación automática ni ejecución en segundo plano."
        )

        if status.configured:
            st.success(status.detail)
        else:
            st.warning(status.detail)
            st.code(
                "TELEGRAM_BOT_TOKEN=...\nTELEGRAM_CHAT_ID=...",
                language="bash",
            )

        message = st.text_area(
            "Mensaje que se enviará",
            value=payloads.compact_text,
            height=340,
            key="manual_telegram_message_preview",
        )
        parts = _split_message(message)
        st.caption(f"Longitud: {len(message)} caracteres · Partes Telegram estimadas: {len(parts)}")

        confirm = st.checkbox(
            "Confirmo que he revisado el contenido y quiero enviarlo manualmente a Telegram.",
            key="manual_telegram_confirm",
        )

        disabled = not status.configured or not confirm or not message.strip()
        if st.button("📲 Enviar briefing a Telegram", disabled=disabled, use_container_width=True):
            with st.spinner("Enviando briefing a Telegram..."):
                result = send_telegram_text(message)
            if result.ok:
                st.success(result.detail)
            else:
                st.error(result.detail)
