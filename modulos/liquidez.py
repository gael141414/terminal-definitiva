from __future__ import annotations

import datetime
import io

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots


FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def _descargar_serie_fred(series_id: str, start: datetime.date, end: datetime.date) -> pd.Series:
    response = requests.get(
        FRED_CSV_URL,
        params={"id": series_id},
        headers={"User-Agent": "ValueQuant Terminal/1.0"},
        timeout=20,
    )
    response.raise_for_status()

    df = pd.read_csv(io.StringIO(response.text))
    if df.empty:
        raise ValueError(f"FRED no devolvio datos para {series_id}")

    fecha_col = "observation_date" if "observation_date" in df.columns else df.columns[0]
    valor_col = series_id if series_id in df.columns else df.columns[-1]

    df[fecha_col] = pd.to_datetime(df[fecha_col], errors="coerce")
    df[valor_col] = pd.to_numeric(df[valor_col].replace(".", pd.NA), errors="coerce")
    df = df.dropna(subset=[fecha_col]).set_index(fecha_col).sort_index()
    df = df.loc[pd.Timestamp(start):pd.Timestamp(end)]

    serie = df[valor_col].dropna()
    serie.name = series_id
    if serie.empty:
        raise ValueError(f"FRED no devolvio observaciones recientes para {series_id}")
    return serie


@st.cache_data(ttl=86400, show_spinner=False)
def obtener_datos_liquidez():
    try:
        end = datetime.date.today()
        start = end - datetime.timedelta(days=365 * 5)

        walcl = _descargar_serie_fred("WALCL", start, end)
        tga = _descargar_serie_fred("WTREGEN", start, end)
        rrp = _descargar_serie_fred("RRPONTSYD", start, end)
        sp500 = _descargar_serie_fred("SP500", start, end)

        df = pd.concat([walcl, tga, rrp, sp500], axis=1).sort_index()
        df = df.ffill().bfill().dropna()

        # WALCL y WTREGEN llegan en millones de USD; RRPONTSYD ya llega en billones de USD.
        df["WALCL_B"] = df["WALCL"] / 1000
        df["WTREGEN_B"] = df["WTREGEN"] / 1000
        df["RRP_B"] = df["RRPONTSYD"]
        df["Liquidez Neta (Billones $)"] = df["WALCL_B"] - df["WTREGEN_B"] - df["RRP_B"]
        df = df.rename(columns={"SP500": "S&P 500"})

        return df[["Liquidez Neta (Billones $)", "S&P 500", "WALCL_B", "WTREGEN_B", "RRP_B"]].dropna()
    except Exception as e:
        st.error(f"Error conectando con la Reserva Federal: {e}")
        return None


def ejecutar_monitor_liquidez():
    st.markdown("### 🚰 Monitor de Liquidez Global (The FED Tracker)")
    st.markdown("El verdadero motor del mercado no son los beneficios empresariales, es la **Liquidez Neta**. Si la línea azul (Liquidez) sube, compra acciones. Si baja, el mercado caerá tarde o temprano. *Don't fight the FED.*")

    with st.spinner("Conectando con los servidores oficiales de FRED..."):
        df = obtener_datos_liquidez()

        if df is not None and not df.empty:
            liquidez_actual = float(df["Liquidez Neta (Billones $)"].iloc[-1])
            indice_mes = -21 if len(df) >= 21 else 0
            liquidez_mes_pasado = float(df["Liquidez Neta (Billones $)"].iloc[indice_mes])
            cambio_mensual = liquidez_actual - liquidez_mes_pasado

            c1, c2, c3 = st.columns(3)
            c1.metric("💧 Liquidez Neta Actual", f"${liquidez_actual:,.0f} B")
            c2.metric(
                "📊 Inyección/Drenaje (30 Días)",
                f"${cambio_mensual:+,.0f} B",
                "Inyectando 🟢" if cambio_mensual > 0 else "Drenando 🔴",
                delta_color="normal",
            )

            if cambio_mensual > 50:
                c3.success("🟢 Viento a Favor")
            elif cambio_mensual < -50:
                c3.error("🔴 Viento en Contra")
            else:
                c3.warning("⚖️ Liquidez Neutral")

            st.markdown("#### 📈 Correlación Histórica (Liquidez vs S&P 500)")
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["Liquidez Neta (Billones $)"],
                    name="Liquidez Neta FED",
                    line=dict(color="#00C0F2", width=3),
                ),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["S&P 500"],
                    name="S&P 500",
                    line=dict(color="rgba(255,255,255,0.45)", width=2, dash="dot"),
                ),
                secondary_y=True,
            )

            fig.update_layout(
                height=500,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig.update_yaxes(title_text="Liquidez (Billones $)", color="#00C0F2", secondary_y=False)
            fig.update_yaxes(title_text="S&P 500 (Puntos)", color="white", secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📖 Formula y componentes"):
                st.markdown(
                    """
                    **Liquidez Neta = Balance Total FED - TGA - RRP**

                    1. **WALCL:** activos totales de la Reserva Federal.
                    2. **WTREGEN:** cuenta general del Tesoro. Liquidez retenida fuera del mercado.
                    3. **RRPONTSYD:** reverse repos. Liquidez aparcada en la FED.
                    """
                )
                st.dataframe(df.tail(10), use_container_width=True)
