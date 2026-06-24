"""Runner local para briefing de oportunidades.

Permite generar briefing desde terminal sin abrir Streamlit. No envia nada por
Telegram salvo que el caller pida explicitamente `send_telegram=True` y confirme
la accion. Respeta el control local de frecuencia antes de enviar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from modulos.automation_logs import log_briefing_generated
from modulos.automation_schedule import evaluate_delivery_frequency, load_automation_settings
from modulos.briefing_payloads import build_briefing_payloads
from modulos.manual_delivery import send_telegram_text, telegram_status
from modulos.opportunity_briefing import (
    build_opportunity_briefing,
    build_opportunity_briefing_html,
    build_opportunity_briefing_markdown,
)

BriefingFormat = Literal["all", "markdown", "html", "compact"]


@dataclass(frozen=True)
class RunnerOutput:
    kind: str
    path: str


@dataclass(frozen=True)
class RunnerResult:
    ok: bool
    detail: str
    generated_at: str
    outputs: list[RunnerOutput] = field(default_factory=list)
    telegram_attempted: bool = False
    telegram_ok: bool = False
    telegram_detail: str = ""


def _safe_suffix(ts: datetime) -> str:
    return ts.strftime("%Y%m%d_%H%M%S")


def _write_text(path: Path, content: str) -> RunnerOutput:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return RunnerOutput(kind=path.suffix.lstrip(".") or "text", path=str(path))


def _should_write(kind: str, output_format: BriefingFormat) -> bool:
    return output_format == "all" or output_format == kind


def generate_briefing_files(
    *,
    output_dir: str | Path = "exports/briefings",
    output_format: BriefingFormat = "all",
    generated_at: datetime | None = None,
) -> tuple[list[RunnerOutput], str]:
    """Genera archivos locales del briefing y devuelve outputs + texto compacto."""

    generated_at = generated_at or datetime.now()
    output_dir = Path(output_dir)
    suffix = _safe_suffix(generated_at)

    df_watch, df_alerts, df_briefing = build_opportunity_briefing()
    log_briefing_generated(df_watch, df_alerts, df_briefing)
    payloads = build_briefing_payloads(df_watch, df_alerts, df_briefing, generated_at=generated_at)

    outputs: list[RunnerOutput] = []

    if _should_write("markdown", output_format):
        markdown = build_opportunity_briefing_markdown(
            df_watch,
            df_alerts,
            df_briefing,
            generated_at=generated_at,
        )
        outputs.append(
            _write_text(output_dir / f"valuequant_briefing_{suffix}.md", markdown)
        )

    if _should_write("html", output_format):
        html = build_opportunity_briefing_html(
            df_watch,
            df_alerts,
            df_briefing,
            generated_at=generated_at,
        )
        outputs.append(
            _write_text(output_dir / f"valuequant_briefing_{suffix}.html", html)
        )

    if _should_write("compact", output_format):
        outputs.append(
            _write_text(output_dir / f"valuequant_briefing_compact_{suffix}.txt", payloads.compact_text)
        )

    return outputs, payloads.compact_text


def run_local_briefing(
    *,
    output_dir: str | Path = "exports/briefings",
    output_format: BriefingFormat = "all",
    send_telegram: bool = False,
    confirmed: bool = False,
    force_frequency: bool = False,
) -> RunnerResult:
    """Ejecuta el briefing local con salida a disco y envio opcional a Telegram."""

    generated_at_dt = datetime.now()
    generated_at = generated_at_dt.replace(microsecond=0).isoformat()

    outputs, compact_text = generate_briefing_files(
        output_dir=output_dir,
        output_format=output_format,
        generated_at=generated_at_dt,
    )

    if not send_telegram:
        return RunnerResult(
            ok=True,
            detail="Briefing generado localmente. Telegram no solicitado.",
            generated_at=generated_at,
            outputs=outputs,
        )

    if not confirmed:
        return RunnerResult(
            ok=False,
            detail="Envio a Telegram bloqueado: falta confirmacion explicita (--yes).",
            generated_at=generated_at,
            outputs=outputs,
            telegram_attempted=False,
        )

    status = telegram_status()
    if not status.configured:
        return RunnerResult(
            ok=False,
            detail=status.detail,
            generated_at=generated_at,
            outputs=outputs,
            telegram_attempted=True,
            telegram_ok=False,
            telegram_detail=status.detail,
        )

    schedule_settings = load_automation_settings()
    decision = evaluate_delivery_frequency(
        channel="telegram",
        frequency=schedule_settings.frequency,
        max_deliveries_per_period=schedule_settings.max_deliveries_per_period,
    )
    if not decision.allowed and not force_frequency:
        return RunnerResult(
            ok=False,
            detail=f"Envio bloqueado por frecuencia: {decision.reason}",
            generated_at=generated_at,
            outputs=outputs,
            telegram_attempted=False,
            telegram_ok=False,
            telegram_detail=decision.reason,
        )

    delivery = send_telegram_text(compact_text)
    return RunnerResult(
        ok=delivery.ok,
        detail=delivery.detail,
        generated_at=generated_at,
        outputs=outputs,
        telegram_attempted=True,
        telegram_ok=delivery.ok,
        telegram_detail=delivery.detail,
    )
