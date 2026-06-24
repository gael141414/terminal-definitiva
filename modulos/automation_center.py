"""Centro de automatización operativa de ValueQuant Terminal.

Este módulo centraliza el estado de configuración, generación de payloads y envío
manual confirmado del briefing. No programa tareas ni ejecuta envíos en segundo
plano.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from modulos.config import CONFIG
from modulos.briefing_payloads import build_briefing_payloads
from modulos.manual_delivery import render_manual_telegram_panel, telegram_status
from modulos.opportunity_briefing import build_opportunity_briefing


def _configured(value: Any) -> bool:
    return bool(str(value or "").strip())


def _status_chip(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        st.success(f"✅ {label}: configurado" + (f" · {detail}" if detail else ""))
    else:
        st.warning(f"⚠️ {label}: pendiente" + (f" · {detail}" if detail else ""))


def _render_configuration_status() -> None:
    st.subheader("Estado de configuración")

    c1, c2, c3 = st.columns(3)
    with c1:
        _status_chip("FMP API", _configured(CONFIG.fmp_api_key), "datos fundamentales")
    with c2:
        _status_chip("Telegram token", _configured(CONFIG.telegram_bot_token), "envío manual")
    with c3:
        _status_chip("Telegram chat", _configured(CONFIG.telegram_chat_id), "destino")

    status = telegram_status()
    if status.configured:
        st.info("Telegram está listo para envío manual confirmado. No hay automatizaciones activas.")
    else:
        st.caption(status.detail)
        with st.expander("Cómo configurar Telegram", expanded=False):
            st.code(
                "TELEGRAM_BOT_TOKEN=tu_token_del_bot\nTELEGRAM_CHAT_ID=tu_chat_id",
                language="bash",
            )
            st.markdown(
                "Guarda esos valores en `.env` o `.streamlit/secrets.toml`. "
                "No subas credenciales reales a GitHub."
            )


def _render_briefing_summary(df_watch: pd.DataFrame, df_alerts: pd.DataFrame, df_briefing: pd.DataFrame) -> None:
    st.subheader("Briefing operativo")

    high_alerts = 0
    if df_alerts is not None and not df_alerts.empty and "Prioridad" in df_alerts.columns:
        high_alerts = int((df_alerts["Prioridad"] == "Alta").sum())

    review_today = 0
    recalc = 0
    if df_briefing is not None and not df_briefing.empty and "Prioridad" in df_briefing.columns:
        review_today = int((df_briefing["Prioridad"] == "Comprar / revisar hoy").sum())
        recalc = int((df_briefing["Prioridad"] == "Recalcular análisis").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Activos watchlist", len(df_watch) if df_watch is not None else 0)
    c2.metric("Alertas altas", high_alerts)
    c3.metric("Revisar hoy", review_today)
    c4.metric("Recalcular", recalc)

    if df_briefing is None or df_briefing.empty:
        st.warning("No hay briefing disponible. Guarda primero análisis desde Research Core o añade activos a la watchlist.")
        return

    top = df_briefing.iloc[0].to_dict()
    st.markdown(
        f"""
        <div style='padding:18px;border:1px solid rgba(55,198,230,.25);border-radius:16px;background:rgba(18,25,38,.75);margin:12px 0;'>
            <div style='font-size:.8rem;color:#9fb3c8;text-transform:uppercase;letter-spacing:.08em;'>Prioridad principal</div>
            <div style='font-size:1.6rem;font-weight:800;color:#e8eef8;'>{top.get('Ticker', '-')} · {top.get('Prioridad', '-')}</div>
            <div style='color:#9fb3c8;margin-top:6px;'>Score oportunidad: <strong>{top.get('Score Oportunidad', '-')}</strong></div>
            <div style='color:#cbd5e1;margin-top:8px;'>{top.get('Razón', '-')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    columns = [
        col
        for col in ["Prioridad", "Ticker", "Score Oportunidad", "Razón", "Precio Actual", "Target", "ValueQuant", "Margen Seguridad"]
        if col in df_briefing.columns
    ]
    st.dataframe(df_briefing[columns].head(10), use_container_width=True, hide_index=True)


def _render_payloads(df_watch: pd.DataFrame, df_alerts: pd.DataFrame, df_briefing: pd.DataFrame) -> None:
    st.subheader("Payloads preparados")

    payloads = build_briefing_payloads(df_watch, df_alerts, df_briefing)
    suffix = payloads.generated_at.strftime("%Y%m%d_%H%M")

    tab_msg, tab_email, tab_html = st.tabs(["Mensaje compacto", "Email texto", "Email HTML"])

    with tab_msg:
        st.text_area("Mensaje compacto", payloads.compact_text, height=320)
        st.download_button(
            "Descargar mensaje compacto",
            data=payloads.compact_text.encode("utf-8"),
            file_name=f"valuequant_briefing_compacto_{suffix}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with tab_email:
        st.text_input("Asunto sugerido", value=payloads.email_subject)
        st.text_area("Email texto", payloads.email_text, height=320)
        st.download_button(
            "Descargar email texto",
            data=payloads.email_text.encode("utf-8"),
            file_name=f"valuequant_briefing_email_{suffix}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with tab_html:
        st.download_button(
            "Descargar email HTML",
            data=payloads.email_html.encode("utf-8"),
            file_name=f"valuequant_briefing_email_{suffix}.html",
            mime="text/html",
            use_container_width=True,
        )
        st.code(payloads.email_html[:5000], language="html")
        if len(payloads.email_html) > 5000:
            st.caption("Vista previa truncada. El archivo descargado contiene el HTML completo.")

    st.divider()
    render_manual_telegram_panel(payloads)


def render_automation_center() -> None:
    """Renderiza el centro de automatización sin activar envíos programados."""

    st.title("⚙️ Centro de Automatización")
    st.caption(
        "Panel de control para validar configuración, preparar payloads y ejecutar envíos manuales. "
        "No hay programación automática ni procesos en segundo plano."
    )

    _render_configuration_status()
    st.divider()

    with st.spinner("Construyendo briefing desde watchlist..."):
        df_watch, df_alerts, df_briefing = build_opportunity_briefing()

    tab_status, tab_payloads, tab_roadmap = st.tabs(["Resumen", "Payloads y envío", "Roadmap"])

    with tab_status:
        _render_briefing_summary(df_watch, df_alerts, df_briefing)

    with tab_payloads:
        _render_payloads(df_watch, df_alerts, df_briefing)

    with tab_roadmap:
        st.subheader("Próximos pasos de automatización")
        st.markdown(
            """
            **Estado actual**
            - Generación de briefing: operativa.
            - Payload compacto/email: operativo.
            - Telegram: envío manual con confirmación explícita.
            - Automatización periódica: no activada.

            **Antes de programar envíos reales**
            1. Validar que el briefing no contiene datos incorrectos.
            2. Confirmar formato de Telegram/email durante varios días.
            3. Añadir control de frecuencia y logs.
            4. Crear una opción de activación explícita por usuario.
            """
        )
        st.info(f"Última generación de panel: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
