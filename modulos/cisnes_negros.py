from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf


def _serie_cierre_ajustada(data: pd.DataFrame | pd.Series) -> pd.Series:
    """Normaliza la salida de yfinance a una Serie de precios."""
    if isinstance(data, pd.Series):
        serie = data
    elif isinstance(data, pd.DataFrame):
        df = data.copy()
        if isinstance(df.columns, pd.MultiIndex):
            if "Close" in df.columns.get_level_values(0):
                df = df["Close"]
            elif "Adj Close" in df.columns.get_level_values(0):
                df = df["Adj Close"]
        elif "Close" in df.columns:
            df = df["Close"]
        elif "Adj Close" in df.columns:
            df = df["Adj Close"]

        if isinstance(df, pd.DataFrame):
            serie = df.iloc[:, 0]
        else:
            serie = df
    else:
        return pd.Series(dtype=float)

    serie = pd.to_numeric(serie, errors="coerce").dropna()
    serie.index = pd.to_datetime(serie.index, errors="coerce")
    return serie[~serie.index.isna()].sort_index()


def _max_drawdown_periodo(precios: pd.Series) -> float:
    if precios.empty or len(precios) < 2:
        return 0.0
    maximos = precios.cummax()
    drawdowns = (precios / maximos - 1.0) * 100
    return float(drawdowns.min())


def ejecutar_simulador_crisis(ticker_input):
    st.markdown(f"### 🦢 Simulador de Cisnes Negros: {ticker_input}")
    st.markdown("¿Tienes estómago para aguantar esta acción? Sometemos a la empresa a las peores crisis de la historia reciente para medir su **Resiliencia Extrema** y su pérdida máxima histórica (Max Drawdown).")

    with st.spinner(f"Simulando colapsos de mercado para {ticker_input}..."):
        try:
            descarga = yf.download(
                ticker_input,
                period="max",
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            precios = _serie_cierre_ajustada(descarga)

            if precios.empty or len(precios) < 252:
                st.warning("No hay suficiente historia para esta empresa. El test requiere al menos un año de precios diarios.")
                return

            crisis = {
                "📉 Gran Crisis Financiera (2007-2009)": ("2007-10-09", "2009-03-09"),
                "🦠 Crash del COVID-19 (2020)": ("2020-02-19", "2020-03-23"),
                "🔥 Shock de Inflación / Tipos (2022)": ("2022-01-03", "2022-10-12"),
                "🏦 Crisis Bancaria Regional (2023)": ("2023-03-08", "2023-05-04"),
            }

            resultados = []
            for nombre, (inicio, fin) in crisis.items():
                precios_crisis = precios.loc[inicio:fin]
                if len(precios_crisis) > 5:
                    drawdown = _max_drawdown_periodo(precios_crisis)
                    estado = "Cotizaba"
                else:
                    drawdown = 0.0
                    estado = "Sin historial"

                resultados.append({
                    "Crisis": nombre,
                    "Caída Máxima (%)": drawdown,
                    "Estado": estado,
                })

            df_res = pd.DataFrame(resultados)

            st.markdown("#### 🩸 Sangrado Máximo por Crisis (Drawdown)")
            df_res_filtrado = df_res[df_res["Caída Máxima (%)"] < 0].copy()

            if not df_res_filtrado.empty:
                fig = px.bar(
                    df_res_filtrado,
                    x="Caída Máxima (%)",
                    y="Crisis",
                    orientation="h",
                    text_auto=".2f",
                    color="Caída Máxima (%)",
                    color_continuous_scale="Reds_r",
                )
                fig.update_layout(
                    height=380,
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    xaxis_title="Pérdida de Capital (%)",
                    yaxis_title="",
                    coloraxis_showscale=False,
                )
                fig.update_traces(textposition="outside", texttemplate="%{x:.2f}%")
                st.plotly_chart(fig, use_container_width=True)

                peor_caida = float(df_res_filtrado["Caída Máxima (%)"].min())
                crisis_peor = df_res_filtrado.loc[df_res_filtrado["Caída Máxima (%)"].idxmin(), "Crisis"]
                st.info(
                    f"💡 **Veredicto de Riesgo:** el peor episodio comparable para **{ticker_input}** fue "
                    f"**{crisis_peor}**, con un drawdown de **{abs(peor_caida):.2f}%**."
                )
            else:
                st.info("La empresa es demasiado joven para haber pasado por estas crisis.")

            with st.expander("Detalle numerico"):
                st.dataframe(df_res, use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Error calculando cisnes negros: {e}")
