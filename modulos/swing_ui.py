"""Interfaz del apartado de Swing Trading.

Estructura en cuatro pestañas que siguen el orden real de trabajo:

1. **Escáner**: qué oportunidades hay hoy y con qué plan operarlas.
2. **Estrategias**: qué hace cada regla y en qué contexto funciona.
3. **Validación**: cómo se ha comportado cada estrategia históricamente.
4. **Calculadora**: dimensionar cualquier operación, venga de donde venga.

Sobre el banner de régimen: va arriba y siempre visible a propósito. Es el dato
que condiciona todo lo demás, y esconderlo en una pestaña llevaría a operar
rupturas en un mercado lateral sin enterarse.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modulos.config import (
    COLOR_ACCENT,
    COLOR_NEGATIVE,
    COLOR_POSITIVE,
    COLOR_PRIMARY,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
)
from modulos.swing_backtest import (
    backtest_estrategia,
    tabla_out_of_sample,
    tabla_resumen,
    validar_out_of_sample,
)
from modulos.swing_estrategias import ESTRATEGIAS, ESTRATEGIAS_POR_ID
from modulos.swing_regimen import (
    CORRECCION,
    DISTRIBUCION,
    PANICO,
    RANGO_ALCISTA,
    TENDENCIA_ALCISTA,
    Regimen,
    clasificar_regimen,
)
from modulos.swing_riesgo import construir_plan
from modulos.swing_scanner import descargar_universo, escanear, señales_a_dataframe
from modulos.utils import apply_plotly_theme
from modulos.html_markdown import escribir_html

_ESTADO_ESCANEO = "vq_swing_resultado"
_ESTADO_BACKTEST = "vq_swing_backtest"
_ESTADO_OOS = "vq_swing_oos"

_COLOR_REGIMEN = {
    TENDENCIA_ALCISTA: COLOR_POSITIVE,
    RANGO_ALCISTA: COLOR_ACCENT,
    DISTRIBUCION: COLOR_WARNING,
    CORRECCION: COLOR_NEGATIVE,
    PANICO: COLOR_NEGATIVE,
}


# --------------------------------------------------------------------------
# Universo
# --------------------------------------------------------------------------


def _universo_watchlist() -> list[str]:
    try:
        from modulos.watchlist import cargar_watchlist

        return sorted(cargar_watchlist().keys())
    except Exception:
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def _universo_mercado(limite: int) -> list[str]:
    try:
        from modulos.company_data_helpers import obtener_tickers_filtrados

        return [t.split(" - ")[0].strip() for t in obtener_tickers_filtrados()][:limite]
    except Exception:
        return []


# --------------------------------------------------------------------------
# Banner de régimen
# --------------------------------------------------------------------------


def _posiciones_abiertas() -> dict[str, dict]:
    """Posiciones con acciones y stop, leídas de la watchlist local."""
    try:
        from modulos.watchlist import cargar_watchlist

        abiertas = {}
        for ticker, item in cargar_watchlist().items():
            posicion = item.get("posicion") if isinstance(item, dict) else None
            if isinstance(posicion, dict) and posicion.get("acciones"):
                abiertas[ticker] = posicion
        return abiertas
    except Exception:
        return {}


def _render_banner_regimen(regimen: Regimen) -> None:
    color = _COLOR_REGIMEN.get(regimen.codigo, COLOR_TEXT_MUTED)

    escribir_html(f"""
        <div style="background:#121926; border:1px solid rgba(147,164,187,0.35);
                    border-left:4px solid {color}; border-radius:10px;
                    padding:16px 20px; margin-bottom:14px;">
            <div style="display:flex; align-items:baseline; gap:12px; flex-wrap:wrap;">
                <span style="font-size:11px; letter-spacing:.12em; text-transform:uppercase;
                             color:{COLOR_TEXT_MUTED};">Régimen de mercado</span>
                <span style="font-size:19px; font-weight:800; color:{color};">{regimen.etiqueta}</span>
            </div>
            <div style="color:#93a4bb; font-size:13.5px; margin-top:6px; line-height:1.5;">
                {regimen.descripcion}
            </div>
        </div>
        """)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SPY vs media 200", f"{regimen.distancia_media_pct:+.1f}%" if regimen.distancia_media_pct is not None else "n/d")
    c2.metric("Amplitud del mercado", f"{regimen.amplitud_pct:.0f}%" if regimen.amplitud_pct is not None else "n/d",
              help="Porcentaje de valores del universo por encima de su media de 200 sesiones.")
    c3.metric("VIX", f"{regimen.vix:.1f}" if regimen.vix is not None else "n/d")
    c4.metric("Tamaño sugerido", f"{regimen.factor_tamano:.0%}",
              help="Multiplicador sobre el riesgo normal por operación, según lo hostil que sea el contexto.")

    for aviso in regimen.avisos:
        st.caption(f"⚠️ {aviso}")


# --------------------------------------------------------------------------
# Pestaña 1: escáner
# --------------------------------------------------------------------------


def _render_ficha_senal(fila: pd.Series, motivos: list[str], *, capital: float = 10_000.0,
                        regimen_actual: str = "") -> None:
    es_largo = fila["Dirección"] == "Largo"
    color = COLOR_POSITIVE if es_largo else COLOR_NEGATIVE
    marca = "" if fila["En régimen"] else " · fuera de régimen"

    with st.expander(
        f"{'🟢' if es_largo else '🔴'} {fila['Ticker']} · {fila['Estrategia']} · fuerza {fila['Fuerza']:.0f}{marca}",
        expanded=False,
    ):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Entrada", f"${fila['Precio']:,.2f}")
        c2.metric("Stop", f"${fila['Stop']:,.2f}", f"-{fila['Riesgo/acción %']:.1f}%", delta_color="inverse")
        c3.metric("Objetivo 2R", f"${fila['Objetivo 2R']:,.2f}" if pd.notna(fila["Objetivo 2R"]) else "n/d")
        c4.metric("Acciones", f"{int(fila['Acciones']):,}", f"riesgo {fila['Riesgo €']:,.0f}€")

        st.markdown(f"<span style='color:{color}; font-weight:600;'>Por qué aparece esta señal</span>", unsafe_allow_html=True)
        for motivo in motivos:
            st.markdown(f"- {motivo}")

        if int(fila["Acciones"]) == 0:
            st.warning(
                "Con el capital y el riesgo configurados no sale ni una acción: el stop está "
                "demasiado lejos para el tamaño de la cuenta."
            )

        # --- Concentración: el riesgo que no se ve mirando la operación sola ---
        posiciones = _posiciones_abiertas()
        if posiciones:
            from modulos.swing_concentracion import analizar_concentracion

            informe = analizar_concentracion(
                fila["Ticker"], posiciones, capital=capital,
                riesgo_nuevo_euros=float(fila["Riesgo €"] or 0),
            )
            st.markdown("**Encaje en tu cartera**")
            cc1, cc2 = st.columns(2)
            cc1.metric("Riesgo abierto actual", f"{informe.calor_actual_pct:.1f}%")
            cc2.metric("Con esta posición", f"{informe.calor_con_nueva_pct:.1f}%",
                       f"{informe.calor_con_nueva_pct - informe.calor_actual_pct:+.1f} pp")
            if informe.despejado:
                st.success("Sin problemas de concentración: encaja bien con lo que ya tienes abierto.")
            for aviso in informe.avisos:
                (st.error if aviso.gravedad == "bloqueo" else st.warning)(aviso.mensaje)

        # --- Registro en el diario ---
        from modulos.diario import DESCARTADA, EJECUTADA, MOTIVOS_DESCARTE, registrar_decision

        st.markdown("**Anotar la decisión**")
        d1, d2 = st.columns([2, 1])
        with d1:
            motivo = st.selectbox(
                "Si la descartas, ¿por qué?", MOTIVOS_DESCARTE,
                key=f"mot_{fila['Ticker']}_{fila['_id_estrategia']}",
            )
        with d2:
            st.markdown("<div style='height:1.72rem;'></div>", unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            if b1.button("✅ Tomada", key=f"ok_{fila['Ticker']}_{fila['_id_estrategia']}", use_container_width=True):
                registrar_decision(
                    fila["Ticker"], EJECUTADA, estrategia=fila["Estrategia"],
                    direccion="largo" if es_largo else "corto", precio=float(fila["Precio"]),
                    stop=float(fila["Stop"]), objetivo=float(fila["Objetivo 2R"] or 0),
                    acciones=int(fila["Acciones"]), regimen=regimen_actual,
                    fuerza=float(fila["Fuerza"]),
                )
                st.success("Anotada en el diario.")
            if b2.button("✖️ Descartada", key=f"no_{fila['Ticker']}_{fila['_id_estrategia']}", use_container_width=True):
                registrar_decision(
                    fila["Ticker"], DESCARTADA, estrategia=fila["Estrategia"],
                    precio=float(fila["Precio"]), regimen=regimen_actual, motivo=motivo,
                )
                st.info("Descarte anotado. Registrar lo que NO haces es lo que permite saber si tu filtro aporta.")


def _render_escaner() -> None:
    st.markdown("#### Escáner de oportunidades")
    st.caption(
        "Descarga el histórico de todo el universo en lotes, calcula los indicadores en local y "
        "evalúa las seis estrategias sobre cada valor. Cada señal sale con su plan completo."
    )

    col_a, col_b, col_c = st.columns([1.4, 1, 1])
    with col_a:
        origen = st.radio(
            "Universo a escanear",
            ["Mi watchlist", "Mercado (muestra)", "Lista personalizada"],
            horizontal=True,
        )
    with col_b:
        capital = st.number_input("Capital de la cuenta (€)", min_value=500.0, value=10_000.0, step=500.0)
    with col_c:
        riesgo_pct = st.number_input(
            "Riesgo por operación (%)", min_value=0.1, max_value=5.0, value=1.0, step=0.1,
            help="Porcentaje del capital que se pierde si salta el stop. Entre el 0,5% y el 2% es lo habitual.",
        )

    tickers: list[str] = []
    if origen == "Mi watchlist":
        tickers = _universo_watchlist()
        if not tickers:
            st.info("Tu watchlist está vacía. Añade valores desde «📋 Mi Watchlist» o escanea una muestra del mercado.")
    elif origen == "Mercado (muestra)":
        limite = st.select_slider("Tamaño de la muestra", options=[100, 250, 500, 750], value=250)
        tickers = _universo_mercado(limite)
        st.caption(f"Se escanearán {len(tickers)} valores. Aproximadamente {len(tickers) * 0.09:.0f} segundos de descarga.")
    else:
        texto = st.text_area("Tickers separados por comas", "AAPL, MSFT, NVDA, META, AMD, GOOGL, AMZN, NFLX")
        tickers = [t.strip().upper() for t in texto.split(",") if t.strip()]

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        # Por defecto sólo largos: las dos estrategias cortas tienen expectativa
        # negativa medida, así que activarlas debe ser una decisión consciente.
        direcciones = st.multiselect("Dirección", ["Largo", "Corto"], default=["Largo"])
        if "Corto" in direcciones:
            st.warning(
                "⚠️ Las estrategias cortas de este catálogo tienen expectativa **negativa** en la "
                "validación histórica (−0,14R y −0,20R). Se muestran para investigación, no como "
                "recomendación."
            )
    with col_f2:
        nombres = {e.nombre: e.id for e in ESTRATEGIAS}
        elegidas = st.multiselect("Estrategias", list(nombres), default=list(nombres))

    if st.button("⚡ Escanear mercado", type="primary", use_container_width=True, disabled=not tickers):
        barra = st.progress(0.0, text="Iniciando...")
        ids = tuple(nombres[n] for n in elegidas) or None
        resultado = escanear(tickers, estrategias=ids, progreso=barra)
        barra.empty()
        st.session_state[_ESTADO_ESCANEO] = {
            "resultado": resultado,
            "capital": capital,
            "riesgo": riesgo_pct,
            "direcciones": direcciones,
        }

    estado = st.session_state.get(_ESTADO_ESCANEO)
    if not estado:
        st.info("Configura el universo y pulsa «Escanear mercado».")
        return

    resultado = estado["resultado"]
    _render_banner_regimen(resultado.regimen) if resultado.regimen else None

    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valores analizados", f"{resultado.universo_analizado}/{resultado.universo_solicitado}")
    c2.metric("Señales", len(resultado.senales))
    c3.metric("Largos", len(resultado.largos))
    c4.metric("Cortos", len(resultado.cortos))

    for aviso in getattr(resultado, "avisos", []):
        st.info(aviso)

    if resultado.sin_datos:
        st.caption(
            f"{len(resultado.sin_datos)} valores sin histórico suficiente (menos de 210 sesiones) "
            "quedaron fuera: salidas a bolsa recientes o símbolos deslistados."
        )

    df = señales_a_dataframe(resultado, capital=estado["capital"], riesgo_pct=estado["riesgo"])
    if df.empty:
        st.warning(
            "Ninguna estrategia ha encontrado señal hoy. En un escáner honesto esto es normal y "
            "frecuente: forzar operaciones cuando no hay setup es la vía rápida a perder dinero."
        )
        return

    filtradas = estado["direcciones"] or ["Largo", "Corto"]
    df = df[df["Dirección"].isin(filtradas)]
    solo_regimen = st.checkbox("Mostrar sólo señales alineadas con el régimen actual", value=False)
    if solo_regimen:
        df = df[df["En régimen"]]

    if df.empty:
        st.info("No hay señales que cumplan los filtros seleccionados.")
        return

    st.markdown(f"##### {len(df)} señal(es) ordenadas por fuerza")
    for _, fila in df.head(25).iterrows():
        _render_ficha_senal(
            fila, fila["_motivos"], capital=estado["capital"],
            regimen_actual=resultado.regimen.etiqueta if resultado.regimen else "",
        )

    with st.expander("📄 Ver tabla completa"):
        st.dataframe(df.drop(columns=["_motivos", "_id_estrategia"]), use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------
# Pestaña 2: catálogo de estrategias
# --------------------------------------------------------------------------


def _render_catalogo(regimen: Regimen | None) -> None:
    st.markdown("#### Las seis estrategias")
    st.caption(
        "Ninguna es una invención: cada una recoge un comportamiento del mercado documentado. "
        "La ventaja no está en la regla, sino en aplicarla sobre cientos de valores, sólo en su "
        "régimen y cruzada con los fundamentales que el terminal ya calcula."
    )

    codigo = regimen.codigo if regimen else None
    for estrategia in ESTRATEGIAS:
        activa = codigo in estrategia.regimenes if codigo else None
        if activa is True:
            distintivo, color = "✅ Activa en el régimen actual", COLOR_POSITIVE
        elif activa is False:
            distintivo, color = "⏸️ Fuera de su régimen", COLOR_TEXT_MUTED
        else:
            distintivo, color = "Régimen sin determinar", COLOR_TEXT_MUTED

        with st.expander(f"{'🟢' if estrategia.direccion == 'largo' else '🔴'} {estrategia.nombre}"):
            st.markdown(f"<span style='color:{color}; font-weight:600;'>{distintivo}</span>", unsafe_allow_html=True)
            st.markdown(f"**Qué busca.** {estrategia.resumen}")
            st.markdown(f"**Por qué funciona.** {estrategia.evidencia}")
            st.markdown(
                f"**Horizonte típico.** Entre {estrategia.horizonte_dias[0]} y "
                f"{estrategia.horizonte_dias[1]} sesiones."
            )
            etiquetas = ", ".join(r.replace("_", " ") for r in estrategia.regimenes)
            st.caption(f"Regímenes en los que se activa: {etiquetas}.")

            if estrategia.expectativa_medida is not None:
                validada = estrategia.validada
                color_v = COLOR_POSITIVE if validada else COLOR_NEGATIVE
                titulo = "Conserva ventaja fuera de muestra" if validada else "Sin ventaja fuera de muestra"

                oos = estrategia.expectativa_fuera_muestra
                texto_oos = f"{oos:+.3f}R" if oos is not None else "n/d"
                st.markdown(
                    f"<div style='background:#0d1117; border-left:3px solid {color_v};"
                    f" border-radius:6px; padding:10px 14px; margin-top:8px;'>"
                    f"<b style='color:{color_v};'>{titulo}</b><br>"
                    f"<span style='color:#93a4bb;'>En el periodo de diseño: "
                    f"<b>{estrategia.expectativa_medida:+.3f}R</b> · "
                    f"En el periodo reservado: <b style='color:{color_v};'>{texto_oos}</b></span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if not validada and estrategia.direccion == "corto":
                    st.warning(
                        "Esta estrategia **perdió dinero** en ambos periodos. Se probaron además cinco "
                        "mecánicas de salida distintas y ninguna la volvió rentable. Se mantiene "
                        "disponible para investigar, no para operar."
                    )
                elif not validada:
                    st.warning(
                        "Funcionaba en el periodo con el que se diseñó y **se queda en cero en el "
                        "reservado**. Es el patrón típico de una regla ajustada al pasado."
                    )


# --------------------------------------------------------------------------
# Pestaña 3: validación histórica
# --------------------------------------------------------------------------


def _grafico_expectativa(df: pd.DataFrame):
    if df.empty:
        return None
    colores = [COLOR_POSITIVE if v and v > 0 else COLOR_NEGATIVE for v in df["Expectativa (R)"]]
    fig = go.Figure(
        go.Bar(
            x=df["Expectativa (R)"],
            y=df["Estrategia"],
            orientation="h",
            marker=dict(color=colores),
            text=[f"{v:+.3f}R" if v is not None else "n/d" for v in df["Expectativa (R)"]],
            textposition="outside",
            hovertemplate="%{y}<br>Expectativa: %{x:+.3f}R<extra></extra>",
        )
    )
    fig.update_layout(height=320, xaxis_title="Expectativa por operación (R)", yaxis_title=None, showlegend=False)
    return apply_plotly_theme(fig)


def _render_validacion() -> None:
    st.markdown("#### Validación histórica")
    st.caption(
        "Recorre el histórico buscando cada señal y simula la operación completa: entrada en la "
        "apertura del día siguiente, stop a 2 ATR, objetivo a 2R y cierre por horizonte. Si el stop "
        "y el objetivo caen el mismo día se asume el stop, porque sin datos intradía no se sabe cuál "
        "se tocó primero y suponer lo contrario inflaría el resultado."
    )

    col_a, col_b = st.columns([2, 1])
    with col_a:
        texto = st.text_area(
            "Universo de validación",
            "AAPL, MSFT, NVDA, META, AMD, GOOGL, AMZN, NFLX, JPM, XOM, JNJ, PG, KO, WMT, CAT, BA",
            help="Cuantos más valores, más fiable la muestra y más tarda.",
        )
    with col_b:
        periodo = st.selectbox("Periodo", ["2y", "5y", "10y"], index=1)

    tickers = tuple(t.strip().upper() for t in texto.split(",") if t.strip())

    if st.button("🧪 Ejecutar validación", type="primary", use_container_width=True, disabled=not tickers):
        with st.spinner(f"Descargando {len(tickers)} valores y simulando operaciones..."):
            precios = descargar_universo(tickers, periodo=periodo)
            resultados = {e.id: backtest_estrategia(e.id, precios) for e in ESTRATEGIAS}
        st.session_state[_ESTADO_BACKTEST] = {"resultados": resultados, "n": len(precios), "periodo": periodo}

    estado = st.session_state.get(_ESTADO_BACKTEST)
    if not estado:
        st.info("Elige el universo y pulsa «Ejecutar validación».")
        return

    resumen = tabla_resumen(estado["resultados"])
    if resumen.empty:
        st.warning("No se han generado operaciones suficientes para validar.")
        return

    st.caption(f"Muestra: {estado['n']} valores, periodo {estado['periodo']}.")
    fig = _grafico_expectativa(resumen)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(resumen.drop(columns=["_id"]), use_container_width=True, hide_index=True)

    st.markdown(
        """
**Cómo leer esta tabla.** La cifra que decide es la **expectativa en R**: cuánto se gana o se
pierde de media por operación, medido en unidades de riesgo. Positiva significa que el sistema
tiene ventaja; negativa, que la pierde por mucho que acierte a menudo. El *factor de beneficio*
(ganancias entre pérdidas) debe superar 1. Un porcentaje de acierto alto con expectativa negativa
es la trampa clásica: se gana pequeño muchas veces y se pierde grande unas pocas.
        """
    )
    st.caption(
        "Limitación honesta: no se descuentan comisiones, deslizamiento ni el coste de mantener un "
        "corto, y el resultado depende del periodo elegido. Sirve para comparar estrategias entre sí, "
        "no como promesa de rentabilidad futura."
    )

    st.markdown("---")
    st.markdown("##### Fuera de muestra")
    st.caption(
        "Las cifras de arriba se miden sobre los mismos años con los que se escribieron las reglas, "
        "así que incluyen algo de ajuste al pasado. Aquí el histórico se parte en dos: el primer 60% "
        "se considera periodo de diseño y el 40% restante, terreno no visto. Si la ventaja desaparece "
        "en el segundo tramo, la regla describía el pasado en lugar de capturar un comportamiento estable."
    )

    if st.button("🔬 Ejecutar validación fuera de muestra", use_container_width=True):
        with st.spinner("Partiendo el histórico y midiendo ambos tramos..."):
            precios = descargar_universo(tickers, periodo=estado["periodo"])
            resultados_oos = [validar_out_of_sample(e.id, precios) for e in ESTRATEGIAS]
        st.session_state[_ESTADO_OOS] = resultados_oos

    resultados_oos = st.session_state.get(_ESTADO_OOS)
    if resultados_oos:
        tabla = tabla_out_of_sample(resultados_oos)
        if not tabla.empty:
            corte = next((r.fecha_corte for r in resultados_oos if r.fecha_corte is not None), None)
            if corte is not None:
                st.caption(f"Fecha de corte entre diseño y prueba: **{pd.Timestamp(corte).date()}**.")
            st.dataframe(tabla.drop(columns=["_codigo"]), use_container_width=True, hide_index=True)
            st.caption(
                "«Ventaja retenida» por encima del 100% significa que la estrategia rindió MEJOR en el "
                "tramo reservado que en el de diseño, lo que refuerza que no está sobreajustada."
            )


# --------------------------------------------------------------------------
# Pestaña 4: calculadora
# --------------------------------------------------------------------------


def _render_calculadora(regimen: Regimen | None) -> None:
    st.markdown("#### Calculadora de posición")
    st.caption(
        "Convierte una idea en una operación concreta. La regla es siempre la misma: se decide "
        "cuánto se está dispuesto a perder antes de entrar, y de ahí sale el número de acciones."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        capital = st.number_input("Capital (€)", min_value=500.0, value=10_000.0, step=500.0, key="calc_capital")
        direccion = st.radio("Dirección", ["largo", "corto"], horizontal=True, key="calc_dir")
    with c2:
        entrada = st.number_input("Precio de entrada ($)", min_value=0.01, value=100.0, step=1.0, key="calc_entrada")
        atr = st.number_input("ATR (14) del valor", min_value=0.01, value=3.0, step=0.1,
                              help="Lo devuelve el escáner. Es la volatilidad media diaria en unidades de precio.")
    with c3:
        riesgo = st.number_input("Riesgo por operación (%)", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="calc_riesgo")
        multiplo = st.slider("Stop en ATR", 1.0, 4.0, 2.0, 0.5,
                             help="Más ajustado protege capital pero salta con el ruido normal del valor.")

    usar_regimen = st.checkbox(
        "Ajustar el tamaño al régimen de mercado actual",
        value=True,
        help="Reduce el tamaño automáticamente cuando el contexto es hostil.",
    )
    factor = regimen.factor_tamano if (usar_regimen and regimen) else 1.0

    plan = construir_plan(
        entrada, atr, direccion=direccion, capital=capital,
        riesgo_por_operacion_pct=riesgo, multiplo_atr=multiplo, factor_regimen=factor,
    )

    st.markdown("---")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Acciones", f"{plan.acciones:,}")
    m2.metric("Stop", f"${plan.stop:,.2f}", f"-{plan.distancia_stop_pct:.1f}%", delta_color="inverse")
    m3.metric("Riesgo real", f"{plan.riesgo_euros:,.2f}€", f"{plan.riesgo_pct_real:.2f}% del capital")
    m4.metric("Peso en cartera", f"{plan.peso_cartera_pct:.1f}%")

    if plan.objetivos:
        objetivos = pd.DataFrame(
            [{"Objetivo": k, "Precio": f"${v:,.2f}",
              "Beneficio": f"{(v - plan.entrada) * plan.acciones:+,.0f}€" if plan.direccion == "largo"
              else f"{(plan.entrada - v) * plan.acciones:+,.0f}€"}
             for k, v in plan.objetivos.items()]
        )
        st.dataframe(objetivos, use_container_width=True, hide_index=True)

    for aviso in plan.avisos:
        (st.error if aviso.startswith("BLOQUEO") else st.warning)(aviso)


# --------------------------------------------------------------------------
# Entrada principal
# --------------------------------------------------------------------------


def render_swing_trading() -> None:
    st.markdown("### Swing Trading")
    st.markdown(
        "Operaciones de días a semanas, al alza y a la baja. A diferencia del núcleo de valoración "
        "del terminal, aquí no se busca la mejor empresa a diez años sino el mejor **momento** en un "
        "horizonte corto — con el tamaño de posición y el stop definidos antes de entrar."
    )

    with st.spinner("Leyendo el contexto de mercado..."):
        try:
            regimen = clasificar_regimen()
        except Exception:
            regimen = None

    if regimen is not None:
        _render_banner_regimen(regimen)

    tab_escaner, tab_canslim, tab_estrategias, tab_validacion, tab_calc = st.tabs(
        ["Escáner", "CAN SLIM", "Estrategias", "Validación", "Calculadora"]
    )
    with tab_escaner:
        _render_escaner()
    with tab_canslim:
        from modulos.canslim_ui import render_canslim

        render_canslim()
    with tab_estrategias:
        _render_catalogo(regimen)
    with tab_validacion:
        _render_validacion()
    with tab_calc:
        _render_calculadora(regimen)
