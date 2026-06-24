"""Sprint 2K: integra alertas inteligentes en modulos/watchlist.py.

Uso:
    python scripts/apply_sprint_2k_watchlist_alerts.py
"""

from __future__ import annotations

from pathlib import Path

WATCHLIST_PATH = Path("modulos/watchlist.py")
BACKUP_PATH = Path("modulos/watchlist.py.bak_sprint_2k")

IMPORT_LINE = "from modulos.watchlist_alerts import alert_summary, build_watchlist_alerts\n"

HELPER_BLOCK = '''\n\ndef _render_alerts_panel(df_alerts: pd.DataFrame) -> None:\n    """Panel visual de alertas priorizadas."""\n\n    st.markdown("### 🚨 Alertas inteligentes")\n    st.caption(\n        "Prioriza la watchlist según precio vs target, margen de seguridad, ValueQuant Score, régimen de valoración y antigüedad del análisis."\n    )\n\n    if df_alerts.empty:\n        st.info("No hay alertas disponibles todavía.")\n        return\n\n    summary = alert_summary(df_alerts)\n    a1, a2, a3, a4 = st.columns(4)\n    a1.metric("Alta", summary.get("Alta", 0))\n    a2.metric("Media", summary.get("Media", 0))\n    a3.metric("Baja", summary.get("Baja", 0))\n    a4.metric("Info", summary.get("Info", 0))\n\n    priority_filter = st.multiselect(\n        "Filtrar por prioridad",\n        options=["Alta", "Media", "Baja", "Info"],\n        default=["Alta", "Media"],\n        key="watchlist_alert_priority_filter",\n    )\n\n    filtered_alerts = df_alerts[df_alerts["Prioridad"].isin(priority_filter)] if priority_filter else df_alerts\n\n    if filtered_alerts.empty:\n        st.info("No hay alertas con el filtro seleccionado.")\n        return\n\n    st.dataframe(\n        filtered_alerts[["Prioridad", "Ticker", "Categoría", "Alerta", "Detalle", "Acción sugerida", "Score"]],\n        use_container_width=True,\n        hide_index=True,\n    )\n\n    top_alert = filtered_alerts.iloc[0].to_dict()\n    st.info(\n        f"Prioridad principal: {top_alert.get('Ticker')} — {top_alert.get('Alerta')} | Acción sugerida: {top_alert.get('Acción sugerida')}"\n    )\n'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"No se encontró el bloque requerido: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    if not WATCHLIST_PATH.exists():
        raise FileNotFoundError(f"No existe {WATCHLIST_PATH}")

    text = WATCHLIST_PATH.read_text(encoding="utf-8")
    original = text

    if "from modulos.watchlist_alerts import" not in text:
        text = replace_once(
            text,
            "import yfinance as yf\n",
            "import yfinance as yf\n\n" + IMPORT_LINE,
            "import yfinance",
        )

    if "def _render_alerts_panel" not in text:
        text = replace_once(
            text,
            "\n\n# --- INTERFAZ PRINCIPAL ---",
            HELPER_BLOCK + "\n\n# --- INTERFAZ PRINCIPAL ---",
            "ancla antes de interfaz principal",
        )

    text = text.replace(
        'with st.spinner("Sincronizando precios y snapshots de análisis..."):',
        'with st.spinner("Sincronizando precios, snapshots y alertas inteligentes..."): ',
    )
    text = text.replace(
        'with st.spinner("Sincronizando precios, snapshots y alertas inteligentes..."): ',
        'with st.spinner("Sincronizando precios, snapshots y alertas inteligentes..."):',
    )

    if "df_alerts = build_watchlist_alerts(df_watch)" not in text:
        text = replace_once(
            text,
            "        df_watch = pd.DataFrame(resultados)\n",
            "        df_watch = pd.DataFrame(resultados)\n        df_alerts = build_watchlist_alerts(df_watch)\n",
            "creación df_watch",
        )

    if "_render_alerts_panel(df_alerts)" not in text:
        text = replace_once(
            text,
            '        st.markdown("<br>", unsafe_allow_html=True)\n\n        st.dataframe(\n',
            '        st.markdown("<br>", unsafe_allow_html=True)\n        _render_alerts_panel(df_alerts)\n\n        st.markdown("---")\n        st.markdown("### Tabla de seguimiento")\n        st.dataframe(\n',
            "ancla antes de tabla de seguimiento",
        )

    text = text.replace(
        "Los tickers guardados desde Research Core incluyen acción operativa, score, margen de seguridad y target de seguimiento.",
        "Los tickers guardados desde Research Core incluyen acción operativa, score, margen de seguridad, target de seguimiento y alertas inteligentes.",
    )

    if text == original:
        print("No se aplicaron cambios; watchlist.py ya parecía migrado.")
        return

    if not BACKUP_PATH.exists():
        BACKUP_PATH.write_text(original, encoding="utf-8")

    WATCHLIST_PATH.write_text(text, encoding="utf-8")
    print("Sprint 2K aplicado sobre modulos/watchlist.py")
    print(f"Backup: {BACKUP_PATH}")


if __name__ == "__main__":
    main()
