from __future__ import annotations

from pathlib import Path

APP_PATH = Path("app.py")
HOME_PATH = Path("modulos/app_home.py")

OLD_MARKET_IMPORT = '''from modulos.market_widgets import (
    analizar_rotacion_sectores,
    buscar_etf_yahoo,
    obtener_market_snapshot,
    obtener_market_treemap_data,
    obtener_ultimas_noticias,
    render_ticker_tape,
)
'''

NEW_MARKET_IMPORT = '''from modulos.market_widgets import (
    analizar_rotacion_sectores,
    buscar_etf_yahoo,
    render_ticker_tape,
)
'''

HOME_TREEMAP_HELPER = '''

def render_market_treemap(df: pd.DataFrame) -> go.Figure:
    """Construye el mapa de calor de mercado de la Home con una figura Plotly autocontenida."""
    required_columns = {"Ticker", "Sector", "MarketCap", "Rendimiento_Diario"}
    if df is None or df.empty or not required_columns.issubset(df.columns):
        return go.Figure()

    plot_df = df[["Ticker", "Sector", "MarketCap", "Rendimiento_Diario"]].copy()
    plot_df["MarketCap"] = pd.to_numeric(plot_df["MarketCap"], errors="coerce").fillna(0)
    plot_df["Rendimiento_Diario"] = pd.to_numeric(plot_df["Rendimiento_Diario"], errors="coerce").fillna(0)
    plot_df = plot_df[plot_df["MarketCap"] > 0]

    if plot_df.empty:
        return go.Figure()

    sector_df = (
        plot_df.groupby("Sector", as_index=False)
        .agg(MarketCap=("MarketCap", "sum"), Rendimiento_Diario=("Rendimiento_Diario", "mean"))
        .sort_values("MarketCap", ascending=False)
    )

    labels = ["Mercado"] + sector_df["Sector"].astype(str).tolist() + plot_df["Ticker"].astype(str).tolist()
    parents = [""] + ["Mercado"] * len(sector_df) + plot_df["Sector"].astype(str).tolist()
    values = [float(plot_df["MarketCap"].sum())] + sector_df["MarketCap"].astype(float).tolist() + plot_df["MarketCap"].astype(float).tolist()
    colors = [0.0] + sector_df["Rendimiento_Diario"].astype(float).tolist() + plot_df["Rendimiento_Diario"].astype(float).tolist()

    fig = go.Figure(
        go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            marker=dict(
                colors=colors,
                colorscale=[
                    [0.0, "#ef5b6b"],
                    [0.5, "#202938"],
                    [1.0, "#36c486"],
                ],
                cmin=-5,
                cmax=5,
                line=dict(width=1, color="rgba(15,23,42,0.75)"),
            ),
            textinfo="label+value",
            hovertemplate="<b>%{label}</b><br>Capitalización relativa: %{value:,.0f}<br>Rendimiento: %{color:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#CBD5E1", size=12),
        margin=dict(l=0, r=0, t=0, b=0),
        height=440,
    )
    return fig
'''


def cleanup_app_imports(app_source: str) -> str:
    if OLD_MARKET_IMPORT not in app_source:
        if NEW_MARKET_IMPORT in app_source:
            return app_source
        raise RuntimeError("No se encontró el bloque esperado de import de market_widgets en app.py.")

    remainder = app_source.replace(OLD_MARKET_IMPORT, "", 1)
    obsolete_names = [
        "obtener_market_snapshot",
        "obtener_market_treemap_data",
        "obtener_ultimas_noticias",
    ]
    still_used = [name for name in obsolete_names if name in remainder]
    if still_used:
        raise RuntimeError(f"No se pueden quitar imports todavía; siguen usados en app.py: {still_used}")

    return app_source.replace(OLD_MARKET_IMPORT, NEW_MARKET_IMPORT, 1)


def ensure_home_runtime_helpers(home_source: str) -> str:
    if "def render_home_page(" not in home_source:
        raise RuntimeError("modulos/app_home.py no contiene render_home_page(). Aplica primero Sprint 2H.")

    updated = home_source

    if "import pandas as pd\n" not in updated:
        if "import streamlit as st\n" not in updated:
            raise RuntimeError("No se encontró el anchor de imports en app_home.py.")
        updated = updated.replace("import streamlit as st\n", "import streamlit as st\nimport pandas as pd\n", 1)

    if "import plotly.graph_objects as go\n" not in updated:
        if "import pandas as pd\n" not in updated:
            raise RuntimeError("No se encontró el anchor de pandas en app_home.py.")
        updated = updated.replace("import pandas as pd\n", "import pandas as pd\nimport plotly.graph_objects as go\n", 1)

    if "def render_market_treemap(" not in updated:
        anchor = "\ndef render_home_page(logo_path, home_bg_path) -> None:\n"
        if anchor not in updated:
            raise RuntimeError("No se encontró el anchor de render_home_page en app_home.py.")
        updated = updated.replace(anchor, HOME_TREEMAP_HELPER + anchor, 1)

    required_tokens = [
        "def render_market_treemap(df: pd.DataFrame) -> go.Figure:",
        "render_market_treemap(df_treemap)",
        "obtener_market_treemap_data()",
    ]
    missing = [token for token in required_tokens if token not in updated]
    if missing:
        raise RuntimeError(f"app_home.py no contiene los tokens esperados tras la limpieza: {missing}")

    return updated


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")
    if not HOME_PATH.exists():
        raise FileNotFoundError("No se encuentra modulos/app_home.py. Ejecuta este script desde la raíz del proyecto.")

    app_source = APP_PATH.read_text(encoding="utf-8")
    home_source = HOME_PATH.read_text(encoding="utf-8")

    if "st.set_page_config(" not in app_source[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2I.")

    new_app_source = cleanup_app_imports(app_source)
    new_home_source = ensure_home_runtime_helpers(home_source)

    if new_app_source == app_source and new_home_source == home_source:
        print("Sin cambios: Sprint 2I ya parece aplicado.")
        return 0

    backup_app = APP_PATH.with_suffix(".py.bak_sprint_2i")
    backup_home = HOME_PATH.with_suffix(".py.bak_sprint_2i")
    backup_app.write_text(app_source, encoding="utf-8")
    backup_home.write_text(home_source, encoding="utf-8")

    APP_PATH.write_text(new_app_source, encoding="utf-8")
    HOME_PATH.write_text(new_home_source, encoding="utf-8")

    print("OK: Sprint 2I aplicado.")
    print("app.py: imports de mercado residuales limpiados.")
    print("app_home.py: helper render_market_treemap() añadido si faltaba.")
    print(f"Backups creados: {backup_app}, {backup_home}")
    print("Valida con: python -m py_compile app.py modulos/app_home.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
