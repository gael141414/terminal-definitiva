import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio
from plotly.subplots import make_subplots
import yfinance as yf
from roboadvisor_engine import PortfolioOptimizer

# ---------------- VALUEQUANT GLOBAL PLOTLY THEME ---------------- #
VQ_COLORS = ['#4f8cff', '#37c6e6', '#36c486', '#e2a93b', '#ef5b6b', '#93a4bb']
VQ_BLUE = VQ_COLORS[0]
VQ_CYAN = VQ_COLORS[1]
VQ_GREEN = VQ_COLORS[2]
VQ_AMBER = VQ_COLORS[3]
VQ_RED = VQ_COLORS[4]
VQ_MUTED = VQ_COLORS[5]
VQ_GRID = 'rgba(255,255,255,0.04)'
VQ_TEMPLATE_NAME = 'valuequant_terminal'

VQ_THEME = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='Inter, sans-serif', color='#eef4ff'),
        colorway=VQ_COLORS,
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor='rgba(13,17,26,0.95)',
            bordercolor='#37c6e6',
            font=dict(family='Inter, sans-serif', color='#eef4ff')
        ),
        xaxis=dict(
            zeroline=False,
            showline=False,
            showgrid=True,
            gridcolor=VQ_GRID,
            gridwidth=1,
            tickfont=dict(color='#93a4bb'),
            title_font=dict(color='#eef4ff')
        ),
        yaxis=dict(
            zeroline=False,
            showline=False,
            showgrid=True,
            gridcolor=VQ_GRID,
            gridwidth=1,
            tickfont=dict(color='#93a4bb'),
            title_font=dict(color='#eef4ff')
        ),
        legend=dict(font=dict(color='#eef4ff')),
        title=dict(font=dict(color='#eef4ff')),
    )
)
pio.templates[VQ_TEMPLATE_NAME] = VQ_THEME
pio.templates.default = VQ_TEMPLATE_NAME


def _apply_vq_layout(fig: go.Figure, *, margin: dict | None = None) -> go.Figure:
    """Aplica la capa visual ValueQuant sin alterar trazas, cálculos ni datos de entrada."""
    fig.update_layout(
        template=VQ_TEMPLATE_NAME,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='Inter, sans-serif', color='#eef4ff'),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor='rgba(13,17,26,0.95)',
            bordercolor=VQ_CYAN,
            font=dict(family='Inter, sans-serif', color='#eef4ff')
        ),
        margin=margin or dict(l=0, r=0, t=40, b=0),
    )
    fig.update_xaxes(
        zeroline=False,
        showline=False,
        showgrid=True,
        gridcolor=VQ_GRID,
        gridwidth=1,
        tickfont=dict(color=VQ_MUTED),
        title_font=dict(color='#eef4ff')
    )
    fig.update_yaxes(
        zeroline=False,
        showline=False,
        showgrid=True,
        gridcolor=VQ_GRID,
        gridwidth=1,
        tickfont=dict(color=VQ_MUTED),
        title_font=dict(color='#eef4ff')
    )
    return fig

# ---------------- INSTITUTIONAL VISUALS ---------------- #
def render_market_treemap(df: pd.DataFrame) -> go.Figure:
    """Crea un mapa de calor de mercado por capitalización y rendimiento diario.

    Args:
        df: DataFrame con columnas Ticker, Sector, MarketCap y Rendimiento_Diario.

    Returns:
        Figura Plotly Treemap con tamaño por MarketCap y color por rendimiento diario.
    """
    required = {"Ticker", "Sector", "MarketCap", "Rendimiento_Diario"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas requeridas para el treemap: {sorted(missing)}")

    plot_df = df.loc[:, ["Ticker", "Sector", "MarketCap", "Rendimiento_Diario"]].copy()
    plot_df["Ticker"] = plot_df["Ticker"].astype(str).str.upper()
    plot_df["Sector"] = plot_df["Sector"].fillna("Sin sector").astype(str)
    plot_df["MarketCap"] = pd.to_numeric(plot_df["MarketCap"], errors="coerce")
    plot_df["Rendimiento_Diario"] = pd.to_numeric(plot_df["Rendimiento_Diario"], errors="coerce")
    plot_df = plot_df.dropna(subset=["Ticker", "MarketCap", "Rendimiento_Diario"])
    plot_df = plot_df[plot_df["MarketCap"] > 0]
    if plot_df.empty:
        raise ValueError("No hay datos válidos para renderizar el treemap de mercado.")

    max_abs = float(plot_df["Rendimiento_Diario"].abs().max()) or 1.0
    fig = px.treemap(
        plot_df,
        path=[px.Constant("Mercado"), "Sector", "Ticker"],
        values="MarketCap",
        color="Rendimiento_Diario",
        color_continuous_scale=[(0.0, "#ef5b6b"), (0.5, "#1f2937"), (1.0, "#36c486")],
        range_color=(-max_abs, max_abs),
        hover_data={"MarketCap": ":,.0f", "Rendimiento_Diario": ":+.2f"},
    )
    fig.update_traces(marker=dict(line=dict(color="rgba(203,213,225,0.18)", width=1)), texttemplate="<b>%{label}</b><br>%{color:+.2f}%", hovertemplate="<b>%{label}</b><br>Market Cap: %{value:,.0f}<br>Rendimiento: %{color:+.2f}%<extra></extra>")
    fig.update_layout(height=620, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter, sans-serif", color="#CBD5E1"), margin=dict(l=0, r=0, t=8, b=0), coloraxis_colorbar=dict(title=dict(text="Día %", font=dict(color="#CBD5E1")), tickfont=dict(color="#CBD5E1")))
    return fig


def plot_income_waterfall(ingresos: float, coste_ventas: float, gastos_ope: float, impuestos: float, beneficio_neto: float) -> go.Figure:
    """Crea una cascada institucional de la cuenta de resultados.

    Args:
        ingresos: Ingresos totales.
        coste_ventas: Coste de ventas, introducido positivo o negativo.
        gastos_ope: Gastos operativos, introducidos positivos o negativos.
        impuestos: Impuestos, introducidos positivos o negativos.
        beneficio_neto: Beneficio neto final.

    Returns:
        Figura Plotly Waterfall.
    """
    values = [float(ingresos), -abs(float(coste_ventas)), -abs(float(gastos_ope)), -abs(float(impuestos)), float(beneficio_neto)]
    fig = go.Figure(go.Waterfall(name="Cuenta de resultados", orientation="v", measure=["relative", "relative", "relative", "relative", "total"], x=["Ingresos", "Coste ventas", "Gastos op.", "Impuestos", "Beneficio neto"], y=values, text=[f"{v:,.1f}" for v in values], textposition="outside", connector={"line": {"color": "rgba(203,213,225,0.35)", "width": 1}}, increasing={"marker": {"color": "#36c486"}}, decreasing={"marker": {"color": "#ef5b6b"}}, totals={"marker": {"color": "#00C0F2"}}, hovertemplate="<b>%{x}</b><br>Importe: %{y:,.2f}<extra></extra>"))
    fig.update_layout(height=430, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter, sans-serif", color="#CBD5E1"), margin=dict(l=20, r=20, t=24, b=20), showlegend=False, yaxis=dict(gridcolor="rgba(203,213,225,0.08)", zerolinecolor="rgba(203,213,225,0.22)", tickfont=dict(color="#CBD5E1")), xaxis=dict(tickfont=dict(color="#CBD5E1")))
    return fig


def plot_score_gauge(score_value: float, titulo: str) -> go.Figure:
    """Crea un velocímetro de score 0-100 con bandas de riesgo.

    Args:
        score_value: Valor del score. Se limita visualmente al rango 0-100.
        titulo: Título del indicador.

    Returns:
        Figura Plotly Indicator.
    """
    score = max(0.0, min(100.0, float(score_value)))
    fig = go.Figure(go.Indicator(mode="gauge+number", value=score, number={"font": {"family": "Inter, sans-serif", "size": 42, "color": "#CBD5E1"}, "suffix": "/100"}, title={"text": titulo, "font": {"family": "Inter, sans-serif", "size": 18, "color": "#CBD5E1"}}, gauge={"axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#CBD5E1"}, "bar": {"color": "#00C0F2", "thickness": 0.24}, "bgcolor": "rgba(17,24,39,0.65)", "borderwidth": 1, "bordercolor": "rgba(203,213,225,0.20)", "steps": [{"range": [0, 40], "color": "rgba(239,91,107,0.34)"}, {"range": [40, 70], "color": "rgba(245,184,75,0.34)"}, {"range": [70, 100], "color": "rgba(54,196,134,0.34)"}], "threshold": {"line": {"color": "#00C0F2", "width": 4}, "thickness": 0.82, "value": score}}))
    fig.update_layout(height=310, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter, sans-serif", color="#CBD5E1"), margin=dict(l=20, r=20, t=48, b=12))
    return fig


def style_historical_databars(df: pd.DataFrame, column: str = "Revenue"):
    """Devuelve un Pandas Styler con barras azules y números alineados a la derecha.

    Args:
        df: DataFrame histórico a renderizar con st.dataframe.
        column: Columna numérica sobre la que aplicar la barra de magnitud.

    Returns:
        pandas.io.formats.style.Styler listo para st.dataframe.
    """
    if column not in df.columns:
        raise ValueError(f"La columna '{column}' no existe en el DataFrame.")
    return (df.style.format({column: "{:,.0f}"}).bar(subset=[column], color="rgba(37, 99, 235, 0.20)", align="left").set_properties(subset=[column], **{"text-align": "right", "font-variant-numeric": "tabular-nums"}).set_table_styles([{"selector": "th", "props": [("text-align", "right"), ("color", "#CBD5E1")]}, {"selector": "td", "props": [("color", "#CBD5E1")]}]))

# ---------------- DASHBOARD ---------------- #
def plot_dashboard_interactivo(df_is, df_bs, df_cf, ticker):
    años = pd.Index(df_is.index).astype(str).str[:4]
    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=(
            "Poder de Precios (Márgenes)", "Eficiencia Directiva (ROE vs ROIC)",
            "Generación de Caja (FCF)", "Retorno al Accionista",
            "Solidez Financiera", "Coste de Mantenimiento"
        ),
        vertical_spacing=0.15
    )

    def safe_col(df, col): return col in df.columns

    # Márgenes y Umbrales
    if safe_col(df_is, "Margen Bruto %"):
        fig.add_trace(go.Scatter(x=años, y=df_is["Margen Bruto %"], name="Margen Bruto", line=dict(width=3)), row=1, col=1)
        fig.add_hline(y=40, line_dash="dash", line_color=VQ_GREEN, row=1, col=1, annotation_text="Ventaja MB > 40%")
    if safe_col(df_is, "Margen Neto %"):
        fig.add_trace(go.Scatter(x=años, y=df_is["Margen Neto %"], name="Margen Neto", line=dict(dash="dash")), row=1, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color=VQ_AMBER, row=1, col=1, annotation_text="Monopolio MN > 20%")

    # ROE y ROIC
    if safe_col(df_bs, "ROE %"):
        fig.add_trace(go.Bar(x=años, y=df_bs["ROE %"], name="ROE %", marker_color=VQ_GREEN, opacity=0.6), row=1, col=2)
    if safe_col(df_bs, "ROIC %"):
        fig.add_trace(go.Scatter(x=años, y=df_bs["ROIC %"], name="ROIC %", mode="lines+markers", line=dict(color=VQ_CYAN, width=3)), row=1, col=2)
    fig.add_hline(y=15, line_dash="solid", line_color=VQ_RED, row=1, col=2, annotation_text="Mínimo Munger (>15%)")

    # FCF
    if safe_col(df_cf, "Free Cash Flow (B USD)"):
        fig.add_trace(go.Scatter(x=años, y=df_cf["Free Cash Flow (B USD)"], fill="tozeroy", name="FCF"), row=2, col=1)
        fig.add_hline(y=0, line_dash="solid", line_color=VQ_RED, row=2, col=1)

    # Recompras
    if safe_col(df_cf, "Recompras (B USD)"):
        fig.add_trace(go.Bar(x=años, y=df_cf["Recompras (B USD)"], name="Recompras"), row=2, col=2)
        fig.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.10)", row=2, col=2)

    # Caja Neta
    if safe_col(df_bs, "Caja Neta (B USD)"):
        colores = [VQ_GREEN if v >= 0 else VQ_RED for v in df_bs["Caja Neta (B USD)"]]
        fig.add_trace(go.Bar(x=años, y=df_bs["Caja Neta (B USD)"], marker_color=colores, name="Caja Neta"), row=3, col=1)
        fig.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.10)", row=3, col=1)

    # CAPEX y Umbrales
    if safe_col(df_cf, "CAPEX % sobre Beneficio"):
        fig.add_trace(go.Scatter(x=años, y=df_cf["CAPEX % sobre Beneficio"], name="CAPEX %"), row=3, col=2)
        fig.add_hline(y=25, line_dash="dash", line_color=VQ_GREEN, row=3, col=2, annotation_text="Excelente < 25%")
        fig.add_hline(y=50, line_dash="solid", line_color=VQ_RED, row=3, col=2, annotation_text="Peligro > 50%")

    fig.update_layout(height=900, title=f"Panel de Control Value: {ticker}", hovermode="x unified", showlegend=False, template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff"))
    return _apply_vq_layout(fig)
def plot_per_bands(ticker, eps_dict=None):
    """Genera el gráfico institucional de Bandas PER"""
    try:
        if eps_dict is None:
            from modulos.fmp_api import extraer_datos_fundamentales_fmp

            is_df, _, _, _ = extraer_datos_fundamentales_fmp(ticker, 5)
            eps_dict = {}
            if is_df is not None and not is_df.empty:
                eps_col = "epsdiluted" if "epsdiluted" in is_df.columns else "eps"
                if eps_col in is_df.columns:
                    eps_dict = {
                        str(idx.year): float(value)
                        for idx, value in is_df[eps_col].dropna().items()
                    }

        if not eps_dict:
            return None

        # Descargar 10 años de precio
        df_price = yf.Ticker(ticker).history(period="10y")
        if df_price.empty: return None

        df_price.reset_index(inplace=True)
        # Limpiar zonas horarias para compatibilidad con Plotly
        if df_price['Date'].dt.tz is not None:
            df_price['Date'] = df_price['Date'].dt.tz_localize(None)
            
        df_price['Year'] = df_price['Date'].dt.year.astype(str)

        # Mapear el EPS anual al precio diario y rellenar hacia adelante
        df_price['EPS'] = df_price['Year'].map(eps_dict)
        df_price['EPS'] = df_price['EPS'].ffill()
        df_price = df_price.dropna(subset=['EPS'])
        
        # Evitar bandas negativas si un año hubo pérdidas
        df_price['EPS'] = df_price['EPS'].clip(lower=0)

        if df_price.empty: return None

        fig = go.Figure()

        # Bandas PER (De barato a burbuja)
        multiplos = [10, 15, 20, 25, 30]
        colores = [VQ_GREEN, VQ_CYAN, VQ_AMBER, VQ_AMBER, VQ_RED] # Verde a Rojo

        for mult, color in zip(multiplos, colores):
            fig.add_trace(go.Scatter(
                x=df_price['Date'], y=df_price['EPS'] * mult,
                name=f'PER {mult}x',
                line=dict(color=color, width=1.5, dash='dot')
            ))

        # Precio de la Acción Real
        fig.add_trace(go.Scatter(
            x=df_price['Date'], y=df_price['Close'], 
            name='Precio Real', 
            line=dict(color=VQ_BLUE, width=2.5)
        ))

        fig.update_layout(
            title=f"Bandas de Valoración (PER Histórico) - {ticker}",
            yaxis_title="Precio por Acción (USD)",
            xaxis_title="Año",
            hovermode="x unified",
            height=500,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=60, b=40),
            template=VQ_TEMPLATE_NAME,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter", color="#eef4ff")
        )
        return _apply_vq_layout(fig)
    except Exception as e:
        st.error(f"No se pudieron generar las bandas PER: {e}")
        return None

def plot_tsr_vs_sp500(ticker):
    """Genera un gráfico base $10,000 comparando la acción contra el S&P 500 y su Sector"""
    try:
        hist_ticker = yf.Ticker(ticker).history(period="10y")['Close']
        hist_spy = yf.Ticker("SPY").history(period="10y")['Close']
        
        # Diccionario de Sectores a ETFs
        sector_etfs = {
            'Technology': 'XLK', 'Healthcare': 'XLV', 'Financial Services': 'XLF',
            'Consumer Cyclical': 'XLY', 'Industrials': 'XLI', 'Communication Services': 'XLC',
            'Consumer Defensive': 'XLP', 'Energy': 'XLE', 'Real Estate': 'XLRE',
            'Utilities': 'XLU', 'Basic Materials': 'XLB'
        }
        
        sector_nombre = yf.Ticker(ticker).info.get('sector', '')
        etf_ticker = sector_etfs.get(sector_nombre)
        
        datos = {ticker: hist_ticker, "SPY (Mercado)": hist_spy}
        
        if etf_ticker:
            hist_etf = yf.Ticker(etf_ticker).history(period="10y")['Close']
            datos[f"{etf_ticker} (Sector {sector_nombre})"] = hist_etf

        df = pd.DataFrame(datos).dropna()
        if df.empty: return None

        if df.index.tz is not None: df.index = df.index.tz_localize(None)

        inversion_inicial = 10000
        df_norm = (df / df.iloc[0]) * inversion_inicial
        
        fig = go.Figure()
        colores = [VQ_BLUE, VQ_AMBER, VQ_GREEN]
        trazos = ['solid', 'dash', 'dot']

        for i, col in enumerate(df_norm.columns):
            retorno = ((df_norm[col].iloc[-1] / inversion_inicial) - 1) * 100
            fig.add_trace(go.Scatter(
                x=df_norm.index, y=df_norm[col], 
                name=f'{col} (+{retorno:,.1f}%)', 
                line=dict(color=colores[i%3], width=3 if i==0 else 2, dash=trazos[i%3])
            ))

        fig.update_layout(
            title=f"Retorno Total ($10k): {ticker} vs Mercado vs Sector",
            yaxis_title="Valor de la Inversión (USD)",
            hovermode="x unified",
            height=500,
            legend=dict(orientation="h", yanchor="bottom", y=1.02), template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        return _apply_vq_layout(fig)
    except Exception as e:
        return None

def plot_calidad_beneficios(ticker):
    """Filtro de Trampas de Valor: Compara Beneficio Neto vs Flujo de Caja Operativo"""
    try:
        ticker_yf = yf.Ticker(ticker)
        is_yf = ticker_yf.financials
        cf_yf = ticker_yf.cashflow
        
        if is_yf.empty or cf_yf.empty: return None
        
        # Buscar Net Income y Operating Cash Flow
        net_income = is_yf.loc['Net Income'] if 'Net Income' in is_yf.index else None
        cfo = cf_yf.loc['Operating Cash Flow'] if 'Operating Cash Flow' in cf_yf.index else None
        
        if net_income is None or cfo is None: return None
        
        # Ordenar por fecha ascendente
        net_income = net_income.sort_index()
        cfo = cfo.sort_index()
        años = net_income.index.year.astype(str)
        
        fig = go.Figure()
        # Beneficios contables (pueden ser manipulados)
        fig.add_trace(go.Bar(x=años, y=net_income / 1e9, name='Beneficio Contable (Papel)', marker_color=VQ_BLUE))
        # Dinero real que entra en la caja (muy difícil de manipular)
        fig.add_trace(go.Bar(x=años, y=cfo / 1e9, name='Caja Operativa (Dinero Real)', marker_color=VQ_GREEN))
        
        fig.update_layout(
            barmode='group',
            title=f"🔎 Calidad del Beneficio (Accruals) - {ticker}",
            yaxis_title="Billones (B USD)",
            height=400,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        return _apply_vq_layout(fig)
    except Exception as e:
        return None

def plot_auditoria_forense(ticker, precio_actual, acciones_actuales):
    """Calcula el Altman Z-Score y escanea las Banderas Rojas de liquidez"""
    try:
        ticker_yf = yf.Ticker(ticker)
        bs = ticker_yf.balance_sheet
        is_stmt = ticker_yf.financials
        
        if bs.empty or is_stmt.empty:
            return None, "Datos insuficientes en Yahoo Finance para la auditoría."

        # Extraer los datos más recientes (columna 0)
        def get_safe(df, keys):
            for k in keys:
                if k in df.index:
                    val = df.loc[k].iloc[0]
                    if pd.notna(val) and val != 0: return val
            return 0.001 # Evitar divisiones por cero

        # 1. Recolección de Datos Contables
        total_assets = get_safe(bs, ['Total Assets'])
        total_liabilities = get_safe(bs, ['Total Liabilities Net Minority Interest', 'Total Liabilities'])
        current_assets = get_safe(bs, ['Current Assets'])
        current_liabilities = get_safe(bs, ['Current Liabilities'])
        retained_earnings = get_safe(bs, ['Retained Earnings'])
        
        ebit = get_safe(is_stmt, ['EBIT', 'Operating Income'])
        sales = get_safe(is_stmt, ['Total Revenue', 'Operating Revenue'])
        interest_expense = get_safe(is_stmt, ['Interest Expense'])
        net_income = get_safe(is_stmt, ['Net Income'])
        
        # 2. CÁLCULO DEL ALTMAN Z-SCORE (Modelo para empresas públicas)
        # Z = 1.2(X1) + 1.4(X2) + 3.3(X3) + 0.6(X4) + 1.0(X5)
        working_capital = current_assets - current_liabilities
        market_cap = precio_actual * acciones_actuales if precio_actual and acciones_actuales else 0
        
        x1 = working_capital / total_assets
        x2 = retained_earnings / total_assets
        x3 = ebit / total_assets
        x4 = market_cap / total_liabilities
        x5 = sales / total_assets
        
        z_score = (1.2 * x1) + (1.4 * x2) + (3.3 * x3) + (0.6 * x4) + (1.0 * x5)
        
        # 3. ESCÁNER DE BANDERAS ROJAS (Red Flags del PDF)
        red_flags = []
        
        # Bandera 1: Liquidez Crítica (Current Ratio)
        current_ratio = current_assets / current_liabilities
        if current_ratio < 1.0:
            red_flags.append(f"🔴 **Liquidez Crítica:** Los pasivos a corto plazo superan a los activos líquidos (Ratio: {current_ratio:.2f}x). Riesgo de impagos a proveedores.")
        elif current_ratio > 3.0:
            red_flags.append(f"🟡 **Efectivo Ocioso:** El ratio de circulante es muy alto ({current_ratio:.2f}x). La empresa acumula efectivo que no está invirtiendo productivamente.")

        # Bandera 2: Cobertura de Intereses (¿Puede pagar su deuda?)
        if interest_expense > 0: # En YF los gastos a veces vienen en positivo o negativo
            interest_expense = abs(interest_expense)
            interest_coverage = ebit / interest_expense
            if interest_coverage < 1.5:
                red_flags.append(f"🔴 **Asfixia Financiera:** El beneficio operativo apenas cubre los intereses de la deuda (Cobertura: {interest_coverage:.1f}x). Alerta máxima de impago.")
            elif interest_coverage < 3.0:
                red_flags.append(f"🟡 **Deuda Pesada:** La cobertura de intereses es de {interest_coverage:.1f}x. Aceptable, pero vulnerable si suben los tipos de interés.")

        # Bandera 3: Dividendos Tóxicos (Payout Ratio)
        divs = ticker_yf.dividends
        if not divs.empty and net_income > 0:
            div_anual = divs.groupby(divs.index.year).sum().iloc[-1]
            payout_ratio = (div_anual * acciones_actuales) / net_income
            if payout_ratio > 1.0:
                red_flags.append(f"🔴 **Dividendo Tóxico:** La empresa reparte más dividendos de lo que gana (Payout: {payout_ratio*100:.1f}%). Lo está pagando con deuda o reservas.")

        # 4. RENDERIZADO VISUAL DEL Z-SCORE
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = z_score,
            title = {'text': "Altman Z-Score (Riesgo de Quiebra)"},
            gauge = {
                'axis': {'range': [0, 5], 'tickwidth': 1},
                'bar': {'color': "black", 'thickness': 0.1},
                'steps': [
                    {'range': [0, 1.8], 'color': VQ_RED, 'name': 'Zona Peligro'}, # Rojo
                    {'range': [1.8, 3.0], 'color': VQ_AMBER, 'name': 'Zona Gris'},  # Naranja
                    {'range': [3.0, 5.0], 'color': VQ_GREEN, 'name': 'Zona Segura'} # Verde
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 3},
                    'thickness': 0.75,
                    'value': 1.8
                }
            }
        ))
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20), template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff"))
        
        return _apply_vq_layout(fig), red_flags, z_score
    except Exception as e:
        return None, [f"Error al calcular la auditoría forense: {e}"], 0

def plot_flujo_opciones(ticker):
    """Analiza el mercado de derivados (Open Interest) para calcular el Put/Call Ratio Institucional"""
    try:
        empresa = yf.Ticker(ticker)
        fechas_opciones = empresa.options
        
        # Si la empresa es muy pequeña o no es de EE.UU., puede no tener derivados
        if not fechas_opciones:
            return None, "No hay mercado de opciones disponible para esta empresa (Sin derivados líquidos)."
            
        puts_totales = 0
        calls_totales = 0
        
        # Analizamos los próximos 3 vencimientos (Corto/Medio plazo = Dinero táctico)
        for fecha in fechas_opciones[:3]:
            cadena = empresa.option_chain(fecha)
            # Sumamos el Open Interest (Contratos abiertos REALES, dinero bloqueado en la mesa)
            calls_totales += cadena.calls['openInterest'].sum()
            puts_totales += cadena.puts['openInterest'].sum()
            
        if calls_totales == 0 and puts_totales == 0:
            return None, "No hay suficiente interés abierto (Open Interest) en las opciones a corto plazo."
            
        ratio_pc = puts_totales / calls_totales if calls_totales > 0 else 0
        
        # --- Renderizado Visual (Gráfico Donut) ---
        labels = ['Calls (Apuestas Alcistas 🐂)', 'Puts (Apuestas Bajistas / Coberturas 🐻)']
        values = [calls_totales, puts_totales]
        colores = [VQ_GREEN, VQ_RED] # Verde y Rojo
        
        fig = go.Figure(data=[go.Pie(
            labels=labels, 
            values=values, 
            hole=.5,
            marker=dict(colors=colores, line=dict(color="rgba(255,255,255,0.08)", width=1)),
            hovertemplate="%{label}: <br>Contratos Abiertos: %{value:,.0f}<extra></extra>"
        )])
        
        fig.update_layout(
            title_text="Flujo de Dinero Institucional (Próximos 3 Vencimientos)",
            annotations=[dict(text=f'P/C Ratio<br><b>{ratio_pc:.2f}x</b>', x=0.5, y=0.5, font_size=18, showarrow=False)],
            height=350,
            margin=dict(t=50, b=20, l=20, r=20),
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5), template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        
        # --- Generación del Diagnóstico ---
        if ratio_pc > 1.2:
            diagnostico = f"🐻 **MIEDO INSTITUCIONAL (Risk-Off):** El Put/Call Ratio es altísimo ({ratio_pc:.2f}x). Hay muchos más contratos bajistas abiertos. Los fondos se están cubriendo ante una posible caída inminente."
        elif ratio_pc < 0.7:
            diagnostico = f"🐂 **CODICIA INSTITUCIONAL (Risk-On):** El Put/Call Ratio es muy bajo ({ratio_pc:.2f}x). Wall Street está inundando el mercado con Calls, apostando fuertemente a que la acción se dispara."
        else:
            diagnostico = f"⚖️ **FLUJO NEUTRAL:** El Put/Call Ratio de {ratio_pc:.2f}x indica un equilibrio sano. No hay movimientos especulativos extremos a corto plazo."
            
        return _apply_vq_layout(fig), diagnostico
    except Exception as e:
        return None, f"El servidor de derivados de Yahoo rechazó la conexión temporalmente: {e}"

def plot_proyeccion_dividendos(ticker, precio_compra, anios_proyeccion=20):
    """Proyecta el crecimiento del dividendo y el Yield on Cost a 20 años"""
    try:
        ticker_yf = yf.Ticker(ticker)
        divs = ticker_yf.dividends
        
        if divs.empty or len(divs) < 4:
            return None, "Esta empresa no paga dividendos consistentes o no hay datos."
            
        # Agrupar por año natural
        divs_anuales = divs.groupby(divs.index.year).sum()
        
        # Coger los últimos 5 años (excluyendo el actual si está a medias)
        anios_completos = divs_anuales.iloc[-6:-1] if len(divs_anuales) > 5 else divs_anuales
        if len(anios_completos) < 3:
            return None, "Historial de dividendos demasiado corto para proyectar."
            
        div_inicial = anios_completos.iloc[0]
        div_final = anios_completos.iloc[-1]
        
        if div_inicial <= 0 or div_final <= 0:
            return None, "Datos de dividendos inválidos (valores nulos o negativos)."
            
        # Calcular el CAGR (Tasa de crecimiento anual) del dividendo
        periodos = len(anios_completos) - 1
        cagr_div = (div_final / div_inicial) ** (1 / periodos) - 1
        
        # Blindaje: Limitamos el crecimiento estimado a un máximo del 12% para ser realistas
        cagr_estimado = min(max(cagr_div, 0), 0.12) 
        
        div_actual = div_final
        
        # Proyección futura
        proyeccion_divs = []
        proyeccion_yoc = []
        anios_futuros = list(range(1, anios_proyeccion + 1))
        
        for t in anios_futuros:
            div_futuro = div_actual * ((1 + cagr_estimado) ** t)
            yoc_futuro = (div_futuro / precio_compra) * 100
            proyeccion_divs.append(div_futuro)
            proyeccion_yoc.append(yoc_futuro)
            
        # Crear gráfico con doble eje Y
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # Barras: Dividendo anual cobrado en dólares
        fig.add_trace(go.Bar(
            x=anios_futuros, y=proyeccion_divs, 
            name="Dividendo Anual ($)", marker_color=VQ_GREEN
        ), secondary_y=False)
        
        # Línea: Yield on Cost (Rentabilidad sobre tu compra)
        fig.add_trace(go.Scatter(
            x=anios_futuros, y=proyeccion_yoc, 
            mode="lines+markers", name="Yield on Cost (%)", 
            line=dict(color=VQ_AMBER, width=3)
        ), secondary_y=True)
        
        fig.update_layout(
            title=f"💸 Magia del Interés Compuesto: Proyección DGI a 20 años ({ticker})",
            xaxis_title="Años en el futuro",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        fig.update_yaxes(title_text="Dividendo Cobrado en Efectivo ($)", secondary_y=False)
        fig.update_yaxes(title_text="Yield on Cost (%)", secondary_y=True)
        
        texto_analisis = f"💡 **Proyección:** Históricamente, {ticker} ha crecido su dividendo al **{cagr_div*100:.1f}%** anual. Siendo conservadores y asumiendo un crecimiento futuro del **{cagr_estimado*100:.1f}%**, si compras hoy a **${precio_compra:.2f}**, en el año {anios_proyeccion} cobrarás **${proyeccion_divs[-1]:.2f}** por acción en puro efectivo. ¡Eso es una rentabilidad anual sobre tu coste original (*Yield on Cost*) del **{proyeccion_yoc[-1]:.1f}%** sin tener que vender tus acciones!"
        
        return _apply_vq_layout(fig), texto_analisis
    except Exception as e:
        return None, f"Error calculando la proyección de dividendos: {e}"

def plot_beneish_m_score(ticker):
    """Calcula el Beneish M-Score cruzando datos contables de los últimos 2 años para detectar manipulación"""
    try:
        empresa = yf.Ticker(ticker)
        bs = empresa.balance_sheet
        is_stmt = empresa.financials
        cf = empresa.cashflow
        
        # Si no tenemos al menos 2 años de datos, no podemos calcular la evolución temporal
        if bs.empty or is_stmt.empty or len(bs.columns) < 2 or len(is_stmt.columns) < 2:
            return None, "Datos históricos insuficientes para el análisis de manipulación (M-Score)."

        def get_safe_2y(df, keys):
            """Extrae el valor del año actual (0) y del año anterior (1) de forma segura"""
            for k in keys:
                if k in df.index:
                    val0 = df.loc[k].iloc[0]
                    val1 = df.loc[k].iloc[1]
                    if pd.notna(val0) and pd.notna(val1) and val1 != 0:
                        return val0, val1
            return 0.001, 0.001 # Prevenir división por cero

        # 1. Extracción de variables de Año Actual (0) y Año Anterior (1)
        ventas_0, ventas_1 = get_safe_2y(is_stmt, ['Total Revenue', 'Operating Revenue'])
        cogs_0, cogs_1 = get_safe_2y(is_stmt, ['Cost Of Revenue', 'Cost of Goods Sold'])
        rec_0, rec_1 = get_safe_2y(bs, ['Accounts Receivable', 'Net Receivables'])
        act_tot_0, act_tot_1 = get_safe_2y(bs, ['Total Assets'])
        act_curr_0, act_curr_1 = get_safe_2y(bs, ['Current Assets', 'Total Current Assets'])
        ppe_0, ppe_1 = get_safe_2y(bs, ['Net PPE', 'Property Plant And Equipment'])
        dep_0, dep_1 = get_safe_2y(cf, ['Depreciation', 'Depreciation And Amortization'])
        sga_0, sga_1 = get_safe_2y(is_stmt, ['Selling General And Administration', 'SG&A'])
        pas_curr_0, pas_curr_1 = get_safe_2y(bs, ['Current Liabilities', 'Total Current Liabilities'])
        deuda_lp_0, deuda_lp_1 = get_safe_2y(bs, ['Long Term Debt', 'Total Long Term Debt'])
        
        # Datos especiales para Accruals (Solo año actual)
        net_income = get_safe_2y(is_stmt, ['Net Income', 'Net Income Continuous Operations'])[0]
        cfo = get_safe_2y(cf, ['Operating Cash Flow', 'Total Cash From Operating Activities'])[0]

        # 2. Cálculo de los 8 Índices de Beneish
        # DSRI: Índice de Ventas a Cobrar (Si es > 1, están inflando ventas dando crédito falso)
        dsri = (rec_0 / ventas_0) / (rec_1 / ventas_1) if ventas_0 > 0 and ventas_1 > 0 else 1.0
        
        # GMI: Índice de Margen Bruto (Si es > 1, los márgenes están empeorando)
        gmi = ((ventas_1 - cogs_1) / ventas_1) / ((ventas_0 - cogs_0) / ventas_0) if ventas_0 > 0 and ventas_1 > 0 else 1.0
        
        # AQI: Índice de Calidad de Activos (Si es > 1, están metiendo basura intangible en el balance)
        aqi_0 = 1 - ((act_curr_0 + ppe_0) / act_tot_0) if act_tot_0 > 0 else 1.0
        aqi_1 = 1 - ((act_curr_1 + ppe_1) / act_tot_1) if act_tot_1 > 0 else 1.0
        aqi = aqi_0 / aqi_1 if aqi_1 > 0 else 1.0
        
        # SGI: Índice de Crecimiento de Ventas
        sgi = ventas_0 / ventas_1 if ventas_1 > 0 else 1.0
        
        # DEPI: Índice de Depreciación (Si es > 1, están ralentizando la depreciación para inflar beneficios artificialmente)
        tasa_dep_0 = dep_0 / (ppe_0 + dep_0) if (ppe_0 + dep_0) > 0 else 1.0
        tasa_dep_1 = dep_1 / (ppe_1 + dep_1) if (ppe_1 + dep_1) > 0 else 1.0
        depi = tasa_dep_1 / tasa_dep_0 if tasa_dep_0 > 0 else 1.0
        
        # SGAI: Índice de Gastos Generales
        sgai = (sga_0 / ventas_0) / (sga_1 / ventas_1) if ventas_0 > 0 and ventas_1 > 0 else 1.0
        
        # LVGI: Índice de Apalancamiento (Deuda)
        lvg_0 = (pas_curr_0 + deuda_lp_0) / act_tot_0 if act_tot_0 > 0 else 1.0
        lvg_1 = (pas_curr_1 + deuda_lp_1) / act_tot_1 if act_tot_1 > 0 else 1.0
        lvgi = lvg_0 / lvg_1 if lvg_1 > 0 else 1.0
        
        # TATA: Acumulaciones Totales vs Activos Totales (Dinero de papel vs Activos reales)
        tata = (net_income - cfo) / act_tot_0 if act_tot_0 > 0 else 0.0

        # 3. La Fórmula Maestra del M-Score (8 Variables)
        m_score = -4.84 + (0.920 * dsri) + (0.528 * gmi) + (0.404 * aqi) + (0.892 * sgi) + (0.115 * depi) - (0.172 * sgai) + (4.679 * tata) - (0.327 * lvgi)

        # 4. Renderizado Visual del Gauge (Medidor)
        # Umbral: > -2.22 = Riesgo de manipulación. < -2.22 = Limpio.
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=m_score,
            number={'valueformat': ".2f"},
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Beneish M-Score (Probabilidad de Manipulación)", 'font': {'size': 16}},
            gauge={
                'axis': {'range': [-5, 0], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "black", 'thickness': 0.25},
                'steps': [
                    {'range': [-5, -2.22], 'color': VQ_GREEN},   # Verde: Zona Segura
                    {'range': [-2.22, -1.78], 'color': VQ_AMBER}, # Naranja: Advertencia
                    {'range': [-1.78, 0], 'color': VQ_RED}      # Rojo: Alto Riesgo Fraude
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': -2.22
                }
            }
        ))
        
        fig.update_layout(height=350, margin=dict(t=50, b=20, l=20, r=20), template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff"))

        # 5. Generación del Diagnóstico Analítico
        diagnostico = ""
        detalles = []
        
        if dsri > 1.2: detalles.append("🚩 **Ventas/Cobros:** Las cuentas por cobrar crecen más rápido que las ventas. Posible falso reconocimiento de ingresos.")
        if gmi > 1.1: detalles.append("⚠️ **Márgenes:** Deterioro severo del margen bruto frente al año anterior.")
        if depi > 1.1: detalles.append("🚩 **Depreciación:** Tasa de depreciación alterada. Podrían estar inflando el beneficio neto de forma contable.")
        if tata > 0.05: detalles.append("⚠️ **Accruals (Devengos):** Demasiado beneficio en papel comparado con el dinero real que entra en la caja.")

        if m_score > -1.78:
            diagnostico = f"🚨 **ALERTA ROJA (Riesgo Crítico):** El M-Score es de {m_score:.2f}. Estadísticamente, la empresa tiene una alta probabilidad de estar manipulando sus estados financieros."
        elif m_score > -2.22:
            diagnostico = f"⚠️ **ADVERTENCIA (Zona Gris):** El M-Score es de {m_score:.2f}. Hay anomalías contables recientes. Revisa las banderas levantadas."
        else:
            diagnostico = f"✅ **CONTABILIDAD SANA:** El M-Score de {m_score:.2f} está en la zona segura. No se detectan patrones matemáticos de fraude contable a gran escala."

        return _apply_vq_layout(fig), diagnostico, detalles
    except Exception as e:
        return None, f"Error calculando Beneish M-Score: {e}", []


def plot_treemap_competidores(ticker, competidor):
    """Muestra un mapa de calor por tamaño de mercado y rendimiento"""
    try:
        # En una versión avanzada, aquí descargarías los 5 principales peers.
        # Por ahora lo hacemos con la empresa y el competidor si existe.
        tickers = [ticker]
        if competidor: tickers.append(competidor)
        
        datos = []
        for t in tickers:
            info = yf.Ticker(t).info
            datos.append({
                'Ticker': t,
                'MarketCap': info.get('marketCap', 1),
                'Cambio52W': info.get('52WeekChange', 0) * 100,
                'Sector': info.get('sector', 'General')
            })
            
        df = pd.DataFrame(datos)
        
        fig = px.treemap(
            df, 
            path=['Sector', 'Ticker'], 
            values='MarketCap',
            color='Cambio52W',
            color_continuous_scale='RdYlGn',
            color_continuous_midpoint=0,
            custom_data=['Cambio52W']
        )
        
        fig.update_traces(
            texttemplate="<b>%{label}</b><br>%{customdata[0]:.2f}%",
            hovertemplate="<b>%{label}</b><br>Retorno Anual: %{customdata[0]:.2f}%<br>Capitalización: %{value}<extra></extra>"
        )
        
        fig.update_layout(
            margin=dict(t=30, l=10, r=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        return _apply_vq_layout(fig)
    except Exception as e:
        import streamlit as st
        st.error(f"Fallo al generar Treemap: {e}")
        return None

def plot_adn_financiero(ticker):
    """Genera un gráfico de Radar que muestra la huella dactilar de la empresa"""
    try:
        info = yf.Ticker(ticker).info
        
        # 1. Extraer métricas y normalizarlas de 0 a 100 (Aproximación para el gráfico)
        # Rentabilidad
        roe = min(max(info.get('returnOnEquity', 0) * 100 * 2, 0), 100) 
        # Crecimiento
        crecimiento = min(max(info.get('revenueGrowth', 0) * 100 * 3, 0), 100)
        # Salud (Inverso de la deuda: menos deuda = más puntuación)
        deuda = info.get('debtToEquity', 100)
        salud = max(100 - (deuda / 2), 0) if deuda else 100
        # Valoración (Inverso del PER: PER bajo = más puntuación)
        per = info.get('trailingPE', 30)
        valoracion = max(100 - (per * 1.5), 0) if per else 50
        # Márgenes
        margen = min(max(info.get('profitMargins', 0) * 100 * 3, 0), 100)

        categorias = ['Rentabilidad (ROE)', 'Crecimiento', 'Valoración (Value)', 'Salud Financiera', 'Márgenes Netos']
        valores = [roe, crecimiento, valoracion, salud, margen]

        fig = go.Figure()

        fig.add_trace(go.Scatterpolar(
            r=valores + [valores[0]], # Cerramos el polígono
            theta=categorias + [categorias[0]],
            fill='toself',
            fillcolor='rgba(55, 198, 230, 0.40)', # Relleno translúcido Cian
            line=dict(color=VQ_CYAN, width=3),
            marker=dict(color='#eef4ff', size=8),
            name='Perfil ADN',
            hovertemplate="%{theta}: %{r:.0f}/100<extra></extra>"
        ))

        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], gridcolor='rgba(255,255,255,0.1)', tickfont=dict(color='#8c9bba')),
                angularaxis=dict(gridcolor='rgba(255,255,255,0.2)', tickfont=dict(color='#eef4ff', size=13))
            ),
            showlegend=False,
            height=450,
            margin=dict(t=40, b=40, l=40, r=40),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            title=dict(text="🧬 Perfil de ADN Financiero", font=dict(color=VQ_CYAN, size=18))
        )
        return _apply_vq_layout(fig)
    except Exception as e:
        return None

def plot_anillo_puntuacion(valor, maximo, titulo, color_hex):
    """Genera un anillo circular estilo Apple Watch para las puntuaciones"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=valor,
        number={'font': {'size': 40, 'color': '#eef4ff'}},
        title={'text': titulo, 'font': {'size': 14, 'color': '#8c9bba'}},
        gauge={
            'axis': {'range': [None, maximo], 'visible': False},
            'bar': {'color': color_hex, 'thickness': 0.8},
            'bgcolor': "rgba(255,255,255,0.05)",
            'borderwidth': 0,
        }
    ))
    fig.update_layout(
        height=200, 
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return _apply_vq_layout(fig)
def plot_frontera_eficiente(tickers):
    """Calcula la Frontera Eficiente de Markowitz con optimizacion SciPy."""
    try:
        tickers = [str(ticker).upper().strip() for ticker in tickers if str(ticker).strip()]
        if len(tickers) < 2:
            return None, None

        datos = yf.download(tickers, period="5y", progress=False)["Close"]
        if isinstance(datos, pd.Series):
            datos = datos.to_frame(name=tickers[0])
        datos = datos.dropna(axis=1, how="all").dropna(how="any")
        if datos.empty or datos.shape[1] < 2:
            return None, None

        optimizer = PortfolioOptimizer.from_price_history(datos, risk_free_rate=0.04)
        frontera = optimizer.efficient_frontier(points=45)
        max_sharpe = optimizer.maximize_sharpe()
        min_vol = optimizer.minimize_volatility()

        frontera["pesos"] = frontera["weights"].apply(
            lambda weights: "<br>".join(
                f"{ticker}: {weight:.1%}" for ticker, weight in weights.items()
            )
        )

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=frontera["volatility"],
            y=frontera["expected_return"],
            mode='lines+markers',
            marker=dict(color=frontera["sharpe_ratio"], colorscale='Viridis', showscale=True, size=8,
                        colorbar=dict(title='Sharpe Ratio')),
            line=dict(color=VQ_CYAN, width=2),
            name='Frontera Eficiente',
            text=frontera["pesos"],
            hovertemplate="Vol: %{x:.2%}<br>Ret: %{y:.2%}<br>%{text}<extra></extra>"
        ))
        fig.add_trace(go.Scatter(
            x=[max_sharpe.volatility], y=[max_sharpe.expected_return], mode='markers',
            marker=dict(color='#22c55e', size=16, symbol='star'),
            name='Cartera Óptima (Max Sharpe)'
        ))
        fig.add_trace(go.Scatter(
            x=[min_vol.volatility], y=[min_vol.expected_return], mode='markers',
            marker=dict(color='#f59e0b', size=13, symbol='diamond'),
            name='Mínima Volatilidad'
        ))
        
        fig.update_layout(
            title="🎯 Frontera Eficiente de Markowitz (SciPy / SLSQP)",
            xaxis_title="Riesgo (Volatilidad Anualizada)",
            yaxis_title="Retorno Esperado (CAGR)",
            height=500, hovermode="closest", template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        
        pesos_dict = {ticker: round(float(weight) * 100, 1) for ticker, weight in max_sharpe.weights.items()}
        pesos_dict = dict(sorted(pesos_dict.items(), key=lambda item: item[1], reverse=True))
        
        return _apply_vq_layout(fig), pesos_dict
    except Exception as e:
        st.error(f"Error calculando Markowitz: {e}")
        return None, None

def plot_estacionalidad_quant(ticker):
    """Descarga 20 años de historia y calcula la probabilidad de éxito mensual (Win Rate)"""
    try:
        # 1. Extracción masiva de datos (20 años)
        df = yf.Ticker(ticker).history(period="20y")
        if df.empty:
            return None, "No hay datos históricos suficientes para calcular probabilidades."
            
        # 2. Matemáticas Cuantitativas: Agrupar por mes y calcular % de retorno
        # Usamos 'ME' (Month End) para la nueva versión de Pandas
        df_monthly = df['Close'].resample('ME').last()
        returns = df_monthly.pct_change() * 100
        returns = returns.dropna()
        
        # Crear tabla manejable
        df_ret = pd.DataFrame({
            'Año': returns.index.year,
            'Mes': returns.index.month,
            'Retorno': returns.values
        })
        
        # 3. Pivot Table (Matriz de Años vs Meses)
        pivot = df_ret.pivot(index='Año', columns='Mes', values='Retorno')
        
        # Bautizamos los meses
        meses_nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        pivot.columns = [meses_nombres[i-1] for i in pivot.columns]
        
        # 4. Cálculo de Probabilidades (Win Rate y Promedio)
        win_rate = (pivot > 0).sum() / pivot.notna().sum() * 100
        avg_return = pivot.mean()
        
        # 5. Renderizado del Heatmap (Motor Gráfico)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.08, row_heights=[0.7, 0.3],
                            subplot_titles=("Mapa de Calor Histórico (% Retorno Mensual)", "Tasa de Victoria (Win Rate % / Probabilidad de Subida)"))
        
        # Añadir el Heatmap
        fig.add_trace(go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale='RdYlGn', # Rojo (pérdida) a Verde (ganancia)
            zmid=0, # El cero es el color neutral (amarillo/blanco)
            text=pivot.round(1).astype(str) + '%',
            texttemplate="%{text}",
            showscale=False,
            hovertemplate="Año: %{y}<br>Mes: %{x}<br>Retorno: %{z:.2f}%<extra></extra>"
        ), row=1, col=1)
        
        # Añadir el Gráfico de Barras del Win Rate
        colores_barras = [VQ_GREEN if val >= 60 else VQ_RED if val <= 40 else VQ_BLUE for val in win_rate]
        fig.add_trace(go.Bar(
            x=win_rate.index,
            y=win_rate.values,
            marker_color=colores_barras,
            text=win_rate.round(0).astype(str) + '%',
            textposition='auto',
            hovertemplate="Mes: %{x}<br>Win Rate: %{y:.1f}%<extra></extra>"
        ), row=2, col=1)
        
        fig.update_layout(
            height=700, 
            margin=dict(t=40, b=20, l=20, r=20),
            showlegend=False, template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        fig.update_yaxes(autorange="reversed", row=1, col=1) # Para que el año actual salga arriba
        fig.update_yaxes(range=[0, 100], row=2, col=1) # El Win Rate va de 0 a 100%
        
        # 6. El Veredicto de la IA Analítica
        mejor_mes = avg_return.idxmax()
        peor_mes = avg_return.idxmin()
        
        diagnostico = f"🎲 **Casino Cuantitativo:** A nivel estadístico, el mes más rentable para comprar es **{mejor_mes}** (Sube el {win_rate[mejor_mes]:.0f}% de las veces con un retorno medio del {avg_return[mejor_mes]:.2f}%). El mes más tóxico históricamente es **{peor_mes}** (Gana solo el {win_rate[peor_mes]:.0f}% de las veces, cayendo un promedio del {avg_return[peor_mes]:.2f}%)."
        
        return _apply_vq_layout(fig), diagnostico
    except Exception as e:
        return None, f"Error calculando la estacionalidad estadística: {e}"

def plot_grafico_tecnico_pro(ticker):
    """Genera un gráfico de velas premium con medias móviles y volumen integrado"""
    try:
        df = yf.Ticker(ticker).history(period="1y")
        if df.empty: return None

        # Calcular Medias Móviles Clave
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()

        # Crear figura con 2 paneles (Precios arriba, Volumen abajo)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.03, row_heights=[0.75, 0.25])

        # 1. Velas Japonesas (Arriba)
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            name='Precio',
            increasing_line_color=VQ_GREEN, decreasing_line_color=VQ_RED
        ), row=1, col=1)

        # Medias Móviles (Glow effect)
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], line=dict(color=VQ_CYAN, width=2), name='EMA 20 (Rápida)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color=VQ_AMBER, width=2), name='EMA 50 (Lenta)'), row=1, col=1)

        # 2. Volumen de Transacciones (Abajo)
        colores_volumen = [VQ_GREEN if row['Close'] >= row['Open'] else VQ_RED for index, row in df.iterrows()]
        fig.add_trace(go.Bar(
            x=df.index, y=df['Volume'], name='Volumen', marker_color=colores_volumen, opacity=0.7
        ), row=2, col=1)

        # Estilizar para que parezca un terminal oscuro premium
        fig.update_layout(
            height=700,
            template=VQ_TEMPLATE_NAME,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(11, 20, 38, 0.5)", # Fondo ligeramente translúcido
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # Quitar la cuadrícula molesta
        fig.update_xaxes(showgrid=False, zeroline=False)
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.05)')

        return _apply_vq_layout(fig)
    except Exception as e:
        return None

def plot_termometro_macro():
    """Descarga datos macroeconómicos y calcula el sentimiento del mercado"""
    try:
        # 1. Descarga individual (Mucho más estable que yf.download en paquete)
        vix_data = yf.Ticker('^VIX').history(period="1mo")['Close']
        tnx_data = yf.Ticker('^TNX').history(period="1mo")['Close']
        # Descargamos 2 años de SPY para asegurarnos de tener 200 días hábiles para la Media Móvil
        spy_data = yf.Ticker('SPY').history(period="2y")['Close'] 
        
        if vix_data.empty or tnx_data.empty or spy_data.empty:
            return None, "Los datos macroeconómicos no están disponibles en este momento."
            
        # 2. Extracción segura de los últimos valores
        vix_actual = float(vix_data.iloc[-1])
        vix_previo = float(vix_data.iloc[-2]) if len(vix_data) > 1 else vix_actual
        
        tnx_actual = float(tnx_data.iloc[-1])
        tnx_previo = float(tnx_data.iloc[-2]) if len(tnx_data) > 1 else tnx_actual
        
        spy_actual = float(spy_data.iloc[-1])
        
        # 3. Calcular la Media Móvil de 200 días del SPY
        spy_200d = spy_data.rolling(window=200).mean().dropna().iloc[-1]
        distancia_mm200 = ((spy_actual / spy_200d) - 1) * 100
        
        # --- Construcción del Índice de Sentimiento (0 a 100) ---
        # 0 = Pánico Absoluto (Oportunidad) | 100 = Euforia (Peligro)
        
        # Puntuación VIX (Inversa: VIX alto = Miedo = Puntuación baja)
        score_vix = max(0, min(100, 100 - ((vix_actual - 12) / (35 - 12) * 100)))
        
        # Puntuación Tendencia (Distancia del SPY a su MM200)
        score_trend = 50 + (distancia_mm200 * 5)
        score_trend = max(0, min(100, score_trend))
        
        # Índice Final Ponderado (60% VIX, 40% Tendencia)
        indice_miedo_codicia = (score_vix * 0.6) + (score_trend * 0.4)
        
        # --- RENDERIZADO VISUAL ---
        fig = make_subplots(rows=1, cols=3, specs=[[{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}]])
        
        # 1. Medidor de Miedo y Codicia
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=indice_miedo_codicia,
            number={'valueformat': ".0f"},
            title={'text': "Sentimiento de Mercado", 'font': {'size': 18}},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "black", 'thickness': 0.2},
                'steps': [
                    {'range': [0, 25], 'color': VQ_RED},    # Rojo (Pánico)
                    {'range': [25, 45], 'color': VQ_AMBER},   # Naranja (Miedo)
                    {'range': [45, 55], 'color': "#c7c7c7"},   # Gris (Neutral)
                    {'range': [55, 75], 'color': VQ_CYAN},   # Verde Claro (Codicia)
                    {'range': [75, 100], 'color': VQ_GREEN}   # Verde Oscuro (Euforia)
                ],
            }
        ), row=1, col=1)
        
        # 2. VIX (Volatilidad)
        fig.add_trace(go.Indicator(
            mode="number+delta",
            value=vix_actual,
            delta={'reference': vix_previo, 'position': "top", 'increasing': {'color': "red"}, 'decreasing': {'color': "green"}},
            title={'text': "VIX (Volatilidad)", 'font': {'size': 14}}
        ), row=1, col=2)
        
        # 3. Bono a 10 Años
        fig.add_trace(go.Indicator(
            mode="number+delta",
            value=tnx_actual,
            delta={'reference': tnx_previo, 'position': "top", 'increasing': {'color': "red"}, 'decreasing': {'color': "green"}},
            number={'suffix': "%", 'valueformat': ".2f"},
            title={'text': "Bono USA 10 Años", 'font': {'size': 14}}
        ), row=1, col=3)
        
        fig.update_layout(height=350, margin=dict(t=50, b=20, l=20, r=20), template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff"))
        
        # --- DIAGNÓSTICO ---
        diagnostico = ""
        if indice_miedo_codicia < 25:
            diagnostico = "🚨 **PÁNICO EXTREMO:** Hay sangre en las calles. El VIX está disparado. Históricamente, este es el mejor momento para comprar."
        elif indice_miedo_codicia > 75:
            diagnostico = "⚠️ **EUFORIA EXTREMA:** El mercado está complaciente y sobrecomprado. Es momento de ser exigente con las valoraciones o acumular liquidez."
        elif tnx_actual > 4.5:
            diagnostico = "⚖️ **NEUTRAL (Presión de Bonos):** El sentimiento es normal, pero la alta rentabilidad de los bonos exige que las acciones tengan beneficios espectaculares."
        else:
            diagnostico = "⚖️ **NEUTRAL / SANO:** El mercado se mueve en rangos históricos normales. Céntrate en el Stock Picking."
            
        return _apply_vq_layout(fig), diagnostico
    except Exception as e:
        return None, f"Error calculando la macroeconomía: {e}"

def plot_radar_comparativo(t1, r_is1, r_bs1, t2, r_is2, r_bs2):
    """Genera un Spider Chart para enfrentar el foso económico de dos empresas"""
    try:
        # Métricas donde "MÁS es MEJOR"
        categorias = ['Margen Bruto %', 'Margen Neto %', 'ROE %', 'ROIC %', 'Crecimiento Benef. Neto %']
        
        # Función auxiliar para extraer el último dato válido de cada métrica
        def get_val(df_is, df_bs, col):
            try:
                if df_is is not None and col in df_is.columns: return max(0, df_is[col].dropna().iloc[-1])
                if df_bs is not None and col in df_bs.columns: return max(0, df_bs[col].dropna().iloc[-1])
            except:
                pass
            return 0
            
        valores1 = [get_val(r_is1, r_bs1, c) for c in categorias]
        valores2 = [get_val(r_is2, r_bs2, c) for c in categorias]

        # Para que el radar se cierre, el primer valor debe repetirse al final
        valores1.append(valores1[0])
        valores2.append(valores2[0])
        categorias_loop = categorias + [categorias[0]]

        fig = go.Figure()
        
        # Polígono de la Empresa Principal (Azul)
        fig.add_trace(go.Scatterpolar(
            r=valores1, theta=categorias_loop, fill='toself', name=t1, 
            line=dict(color=VQ_BLUE, width=2.5), marker=dict(size=8)
        ))
        
        # Polígono de la Empresa Competidora (Naranja)
        fig.add_trace(go.Scatterpolar(
            r=valores2, theta=categorias_loop, fill='toself', name=t2, 
            line=dict(color=VQ_AMBER, width=2.5), marker=dict(size=8)
        ))
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, showticklabels=False),
                angularaxis=dict(tickfont=dict(size=14, weight='bold'))
            ),
            showlegend=True,
            title=f"🥊 Batalla de Calidad: {t1} vs {t2}",
            height=600,
            margin=dict(t=80, b=40, l=40, r=40), template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        return _apply_vq_layout(fig)
    except Exception as e:
        st.error(f"Error generando el radar: {e}")
        return None

def plot_football_field(ticker, precio_actual, res_val):
    """Muestra los rangos de valoración para ver dónde estamos parados"""
    if not precio_actual or not res_val: 
        return None
        
    try:
        info = yf.Ticker(ticker).info
        
        # Manejo seguro si Yahoo Finance no devuelve los datos exactos
        low_52 = info.get('fiftyTwoWeekLow')
        high_52 = info.get('fiftyTwoWeekHigh')
        
        if low_52 is None: low_52 = precio_actual * 0.8
        if high_52 is None: high_52 = precio_actual * 1.2
        
        from valuator import calcular_dcf_fcf_por_accion

        fcf_ps = res_val.get('fcf_per_share') or res_val.get('eps_actual', 0)
        terminal_g = res_val.get('terminal_growth', 0.025)

        if not fcf_ps or fcf_ps <= 0:
            return None

        dcf_bajo = calcular_dcf_fcf_por_accion(fcf_ps, 0.02, 0.12, terminal_g)
        dcf_alto = calcular_dcf_fcf_por_accion(fcf_ps, 0.08, 0.085, terminal_g)

        metodos = ['Rango 52 Semanas', 'Valoración DCF', 'Precio Actual']
        minimos = [low_52, dcf_bajo, precio_actual * 0.99]
        
        # En gráficos horizontales con 'base', la 'x' es la longitud de la barra
        longitudes = [high_52 - low_52, dcf_alto - dcf_bajo, precio_actual * 0.02] 

        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=metodos, x=longitudes, base=minimos, orientation='h',
            marker_color=[VQ_BLUE, VQ_GREEN, VQ_RED],
            width=0.4
        ))
        
        fig.add_vline(x=precio_actual, line_dash="dash", line_color=VQ_RED, annotation_text="Mercado Hoy")
        
        fig.update_layout(
            title="🏈 Campo de Fútbol de Valoración (Football Field)", 
            height=300, 
            showlegend=False,
            margin=dict(l=20, r=40, t=40, b=20),
            template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        return _apply_vq_layout(fig)
    except Exception as e:
        # En lugar de fallar en silencio, ahora lo veremos en Streamlit si algo se rompe
        st.error(f"Error interno generando el Football Field: {e}")
        return None

def plot_termometro_deuda(deuda_capital):
    """Genera un medidor visual para el nivel de apalancamiento"""
    if pd.isna(deuda_capital): return None
    
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = deuda_capital,
        title = {'text': "Nivel de Apalancamiento (Deuda / Capital)", 'font': {'size': 14}},
        gauge = {
            'axis': {'range': [None, max(3, deuda_capital + 0.5)]},
            'bar': {'color': "black"},
            'steps': [
                {'range': [0, 0.8], 'color': VQ_GREEN},   # Verde: Aprobado por Buffett
                {'range': [0.8, 1.5], 'color': VQ_AMBER}, # Naranja: Precaución
                {'range': [1.5, max(3, deuda_capital + 0.5)], 'color': VQ_RED} # Rojo: Peligro
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 0.8 # El límite estricto de Buffett
            }
        }
    ))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20), template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff"))
    return _apply_vq_layout(fig)
def plot_capital_allocation_waterfall(df_cf, ticker):
    """Genera un gráfico Waterfall del uso del efectivo histórico"""
    try:
        # Sumamos todo el historial disponible para ver la foto general
        cfo_total = df_cf['CFO (B USD)'].sum()
        capex_total = -df_cf['CAPEX (B USD)'].sum()
        buybacks_total = -df_cf['Recompras (B USD)'].sum()
        
        # Si la empresa no paga dividendos, será 0
        div_total = -df_cf['Dividendos (B USD)'].sum() if 'Dividendos (B USD)' in df_cf.columns else 0
        
        # El remanente es caja que se han guardado, usado para pagar deuda o hacer adquisiciones
        remanente = cfo_total + capex_total + buybacks_total + div_total

        fig = go.Figure(go.Waterfall(
            name = "Capital Allocation", orientation = "v",
            measure = ["relative", "relative", "relative", "relative", "total"],
            x = ["Caja Operativa (CFO)", "Mantenimiento (CAPEX)", "Dividendos Pagados", "Recompras Acciones", "Caja Retenida / Adquisiciones"],
            textposition = "outside",
            text = [f"${cfo_total:.1f}B", f"${capex_total:.1f}B", f"${div_total:.1f}B", f"${buybacks_total:.1f}B", f"${remanente:.1f}B"],
            y = [cfo_total, capex_total, div_total, buybacks_total, remanente],
            connector = {"line":{"color":"rgb(63, 63, 63)", "dash": "solid"}},
            decreasing = {"marker":{"color":VQ_RED}}, # Rojo para salidas de dinero
            increasing = {"marker":{"color":VQ_GREEN}}, # Verde para entradas
            totals = {"marker":{"color":VQ_BLUE}}      # Azul para el saldo final
        ))
        
        fig.update_layout(
            title = f"Rastro del Dinero (Últimos 10 años): ¿En qué gasta {ticker} su efectivo?",
            showlegend = False,
            height=500,
            margin=dict(l=40, r=40, t=60, b=40),
            template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        # Añadir línea base en 0
        fig.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.10)", line_width=1)
        
        return _apply_vq_layout(fig)
    except Exception as e:
        st.error(f"Error generando gráfico de cascada: {e}")
        return None

def plot_comparativa_historica(t1, df1, t2, df2, metrica, color1=VQ_BLUE, color2=VQ_AMBER):
    """Genera un gráfico de líneas comparando la evolución histórica de una métrica clave"""
    try:
        fig = go.Figure()
        
        if metrica in df1.columns:
            s1 = df1[metrica].dropna()
            fig.add_trace(go.Scatter(x=s1.index, y=s1.values, name=t1, line=dict(color=color1, width=3, shape='spline')))
            
        if metrica in df2.columns:
            s2 = df2[metrica].dropna()
            fig.add_trace(go.Scatter(x=s2.index, y=s2.values, name=t2, line=dict(color=color2, width=3, dash='dash', shape='spline')))
            
        fig.update_layout(
            title=f"Evolución a 10 años: {metrica}",
            yaxis_title="Porcentaje (%)",
            xaxis_title="Año",
            hovermode="x unified",
            height=350,
            margin=dict(l=40, r=40, t=40, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        return _apply_vq_layout(fig)
    except Exception as e:
        return None

def plot_owner_earnings(df_cf, ticker):
    """Compara el Beneficio Contable, el FCF Estándar y los verdaderos Owner Earnings de Buffett"""
    try:
        años = pd.Index(df_cf.index).astype(str).str[:4]
        
        fcf = df_cf['Free Cash Flow (B USD)'] if 'Free Cash Flow (B USD)' in df_cf.columns else pd.Series(0, index=df_cf.index)
        owner_earnings = df_cf['Owner Earnings (B USD)'] if 'Owner Earnings (B USD)' in df_cf.columns else pd.Series(0, index=df_cf.index)

        fig = go.Figure()

        # FCF (La métrica pesimista estándar)
        fig.add_trace(go.Bar(
            x=años, y=fcf,
            name='Free Cash Flow (Estándar)',
            marker_color=VQ_MUTED,
            opacity=0.6
        ))
        
        # Owner Earnings (La métrica real de Buffett)
        fig.add_trace(go.Bar(
            x=años, y=owner_earnings,
            name='Owner Earnings (Buffett)',
            marker_color=VQ_GREEN # Verde
        ))

        fig.update_layout(
            barmode='group', # Agrupado uno al lado del otro
            title=f"La Verdadera Caja: FCF vs Owner Earnings - {ticker}",
            yaxis_title="Billones (B USD)",
            xaxis_title="Año",
            hovermode="x unified",
            height=450,
            margin=dict(l=40, r=40, t=60, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        fig.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.10)", line_width=1)
        
        return _apply_vq_layout(fig)
    except Exception as e:
        st.error(f"Error generando gráfico Owner Earnings: {e}")
        return None

def plot_shareholder_yield_historico(df_cf, ticker):
    """Genera un gráfico de barras apiladas con la evolución de la retribución al accionista"""
    try:
        años = pd.Index(df_cf.index).astype(str).str[:4]
        
        # Rescatamos datos (si no existen, creamos una serie de ceros para no romper el gráfico)
        recompras = df_cf['Recompras (B USD)'] if 'Recompras (B USD)' in df_cf.columns else pd.Series(0, index=df_cf.index)
        dividendos = df_cf['Dividendos (B USD)'] if 'Dividendos (B USD)' in df_cf.columns else pd.Series(0, index=df_cf.index)
        
        fig = go.Figure()
        
        # Barra de Dividendos (Verde dinero)
        fig.add_trace(go.Bar(
            x=años, y=dividendos,
            name='Dividendos Pagados',
            marker_color=VQ_GREEN
        ))
        
        # Barra de Recompras (Azul corporativo)
        fig.add_trace(go.Bar(
            x=años, y=recompras,
            name='Recompras de Acciones (Buybacks)',
            marker_color=VQ_BLUE
        ))
        
        # El secreto está en 'barmode="stack"' para que se apilen una sobre otra
        fig.update_layout(
            barmode='stack',
            title=f"Evolución Histórica: Retribución Total al Accionista - {ticker}",
            yaxis_title="Billones (B USD)",
            xaxis_title="Año",
            hovermode="x unified",
            height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=60, b=40),
            template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )
        
        # Añadir línea base en 0
        fig.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.10)", line_width=1)
        
        return _apply_vq_layout(fig)
    except Exception as e:
        st.error(f"Error generando gráfico de retribución: {e}")
        return None

def plot_ev_fcf_historico(ticker, df_bs, df_cf, acciones_actuales):
    """Genera un gráfico del múltiplo de valoración EV/FCF Histórico"""
    try:
        # 1. Traer precios históricos para calcular la capitalización pasada
        df_price = yf.Ticker(ticker).history(period="10y")
        if df_price.empty: return None

        df_price.reset_index(inplace=True)
        if df_price['Date'].dt.tz is not None:
            df_price['Date'] = df_price['Date'].dt.tz_localize(None)

        # Agrupar el precio por año (usamos la media anual para suavizar volatilidades locas)
        df_price['Year'] = df_price['Date'].dt.year.astype(str)
        precio_anual = df_price.groupby('Year')['Close'].mean()

        # Encontrar los años que tenemos tanto en contabilidad como en precio
        años_comunes = [año for año in precio_anual.index if año in df_bs.index and año in df_cf.index]
        if not años_comunes: return None

        ev_fcf_lista = []
        años_validos = []

        for año in años_comunes:
            precio = precio_anual[año]
            # Market Cap en Billones (B USD)
            market_cap_b = (precio * acciones_actuales) / 1e9

            # EV = Market Cap - Caja Neta (Recuerda: Tu métrica 'Caja Neta' ya es Caja - Deuda)
            caja_neta_b = df_bs.loc[año, 'Caja Neta (B USD)']
            ev_b = market_cap_b - caja_neta_b

            fcf_b = df_cf.loc[año, 'Free Cash Flow (B USD)']

            # Solo calculamos el múltiplo si la empresa generó caja positiva ese año
            if fcf_b > 0: 
                multiplo = ev_b / fcf_b
                ev_fcf_lista.append(multiplo)
                años_validos.append(año)

        if not ev_fcf_lista: return None

        # Calcular la mediana histórica para trazar la línea base
        mediana_ev_fcf = np.median(ev_fcf_lista)

        fig = go.Figure()

        # Línea del múltiplo EV/FCF
        fig.add_trace(go.Scatter(
            x=años_validos, y=ev_fcf_lista,
            mode='lines+markers',
            name='EV / FCF',
            line=dict(color=VQ_MUTED, width=3, shape='spline'),
            marker=dict(size=8, color=VQ_MUTED)
        ))

        # Línea de la mediana (Nuestro "Valor Justo" histórico)
        fig.add_hline(
            y=mediana_ev_fcf,
            line_dash="dash",
            line_color=VQ_AMBER,
            annotation_text=f"Mediana Histórica ({mediana_ev_fcf:.1f}x)",
            annotation_position="bottom right"
        )

        fig.update_layout(
            title=f"Valoración Real: Múltiplo EV / FCF Histórico - {ticker}",
            yaxis_title="Múltiplo (x veces el FCF)",
            xaxis_title="Año",
            hovermode="x unified",
            height=450,
            margin=dict(l=40, r=40, t=60, b=40),
            template=VQ_TEMPLATE_NAME, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#eef4ff")
        )

        return _apply_vq_layout(fig)
    except Exception as e:
        st.error(f"Error generando gráfico EV/FCF: {e}")
        return None

def plot_rotacion_sectorial(df_sectores):
    """Crea un gráfico de barras horizontales con el rendimiento de los sectores"""
    import plotly.graph_objects as go
    
    # Ordenamos de peor a mejor para que el mejor salga arriba del todo en el gráfico
    df_sorted = df_sectores.sort_values(by="1 Mes (%)", ascending=True)
    
    # Pintamos de verde los ganadores y de rojo los perdedores
    colores = [VQ_RED if val < 0 else VQ_GREEN for val in df_sorted["1 Mes (%)"]]
    
    fig = go.Figure(go.Bar(
        x=df_sorted["1 Mes (%)"],
        y=df_sorted["Sector"],
        orientation='h',
        marker_color=colores,
        text=[f"{val:.2f}%" for val in df_sorted["1 Mes (%)"]],
        textposition='auto'
    ))
    
    fig.update_layout(
        title="🌡️ Temperatura Sectorial (Últimos 30 Días)",
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#eef4ff'),
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis=dict(showgrid=True, gridcolor='#1e3354', title="Rendimiento Mensual (%)"),
        yaxis=dict(showgrid=False)
    )
    return _apply_vq_layout(fig)
def plot_visor_trend_following(ticker, period="1y"):
    """Visor 1: EMAs (Tendencia) + MACD (Momentum) + RSI (Sobrecompra/Sobreventa)"""
    try:
        # 1. Descarga de datos
        df = yf.download(ticker, period=period)
        if df.empty or len(df) < 200:
            return None, None
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        # 2. MATEMÁTICAS INSTITUCIONALES
        # -- EMAs --
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # -- MACD --
        df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        df['Señal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Histograma'] = df['MACD'] - df['Señal']
        colores_hist = [VQ_GREEN if val >= 0 else VQ_RED for val in df['Histograma']]

        # -- RSI (Fórmula suavizada de Wilder de 14 periodos) --
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # 3. CONSTRUCCIÓN DEL GRÁFICO TRIPLE (Subplots)
        fig = make_subplots(
            rows=3, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.04, 
            row_heights=[0.5, 0.25, 0.25], # Proporciones de las pantallas
            subplot_titles=("Precio y Tendencia (EMAs)", "Momentum (MACD)", "Fuerza Relativa (RSI)")
        )

        # --- PANEL 1: PRECIO Y EMAs ---
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], 
            low=df['Low'], close=df['Close'], name='Precio'
        ), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color=VQ_CYAN, width=2), name='EMA 50'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], line=dict(color=VQ_AMBER, width=2), name='EMA 200'), row=1, col=1)

        # --- PANEL 2: MACD ---
        fig.add_trace(go.Bar(x=df.index, y=df['Histograma'], marker_color=colores_hist, name='Fuerza'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color=VQ_CYAN, width=1.5), name='MACD'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['Señal'], line=dict(color=VQ_AMBER, width=1.5, dash='dot'), name='Señal'), row=2, col=1)

        # --- PANEL 3: RSI ---
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color=VQ_AMBER, width=1.5), name='RSI'), row=3, col=1)
        # Líneas de sobrecompra (70) y sobreventa (30)
        fig.add_hline(y=70, line_dash="dash", line_color=VQ_RED, opacity=0.5, row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color=VQ_GREEN, opacity=0.5, row=3, col=1)
        # Sombreado interno del RSI (Opcional pero muy pro)
        fig.add_hrect(y0=30, y1=70, fillcolor="white", opacity=0.05, layer="below", line_width=0, row=3, col=1)

        # 4. ESTÉTICA FINTECH
        fig.update_layout(
            height=800, template=VQ_TEMPLATE_NAME,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig.update_xaxes(rangeslider_visible=False, gridcolor="rgba(255,255,255,0.05)")
        fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)")
        # Forzar el rango del RSI de 0 a 100
        fig.update_yaxes(range=[0, 100], row=3, col=1)

        return _apply_vq_layout(fig), df
    except Exception as e:
        return None, None

def plot_visor_breakout_volatilidad(ticker, period="1y"):
    """Visor 2: Squeeze de Volatilidad (Bandas de Bollinger + Canales de Keltner + Volumen)"""
    try:
        import numpy as np
        
        # 1. Descarga de datos
        df = yf.download(ticker, period=period)
        if df.empty or len(df) < 50:
            return None, None
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        # 2. MATEMÁTICAS DE VOLATILIDAD
        # -- Average True Range (ATR) de 20 periodos --
        df['H-L'] = df['High'] - df['Low']
        df['H-C'] = np.abs(df['High'] - df['Close'].shift(1))
        df['L-C'] = np.abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['H-L', 'H-C', 'L-C']].max(axis=1)
        df['ATR'] = df['TR'].rolling(window=20).mean()

        # -- Bandas de Bollinger (20, 2.0) --
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['STD_20'] = df['Close'].rolling(window=20).std()
        df['BB_Up'] = df['SMA_20'] + (df['STD_20'] * 2.0)
        df['BB_Low'] = df['SMA_20'] - (df['STD_20'] * 2.0)

        # -- Canales de Keltner (20, 1.5) --
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['KC_Up'] = df['EMA_20'] + (df['ATR'] * 1.5)
        df['KC_Low'] = df['EMA_20'] - (df['ATR'] * 1.5)

        # -- Lógica del Squeeze (Compresión) --
        # Hay "Squeeze" cuando las Bandas de Bollinger están completamente DENTRO de los Keltner
        df['Squeeze_On'] = (df['BB_Low'] > df['KC_Low']) & (df['BB_Up'] < df['KC_Up'])
        df['Squeeze_Off'] = ~df['Squeeze_On']
        
        # Puntos del Squeeze para el gráfico de momentum
        colores_squeeze = [VQ_RED if sqz else VQ_GREEN for sqz in df['Squeeze_On']]

        # -- Momentum proxy (Precio vs Media) --
        df['Momentum'] = df['Close'] - df['SMA_20']
        colores_mom = [VQ_CYAN if val > 0 else '#4a5b7d' for val in df['Momentum']]

        # -- Volumen Inteligente --
        colores_vol = [VQ_GREEN if row['Close'] >= row['Open'] else VQ_RED for _, row in df.iterrows()]
        df['Vol_SMA'] = df['Volume'].rolling(window=20).mean()

        # 3. CONSTRUCCIÓN DEL GRÁFICO (3 Paneles)
        fig = make_subplots(
            rows=3, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.04, 
            row_heights=[0.6, 0.2, 0.2],
            subplot_titles=("Zonas de Compresión (Bollinger vs Keltner)", "Momentum Squeeze", "Volumen Institucional")
        )

        # --- PANEL 1: PRECIO, BOLLINGER Y KELTNER ---
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Precio'), row=1, col=1)
        
        # Keltner Channels (Banda sombreada Naranja)
        fig.add_trace(go.Scatter(x=df.index, y=df['KC_Up'], line=dict(color='rgba(226, 169, 59, 0.50)', width=1), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['KC_Low'], line=dict(color='rgba(226, 169, 59, 0.50)', width=1), fill='tonexty', fillcolor='rgba(226, 169, 59, 0.08)', name='Keltner Channel'), row=1, col=1)
        
        # Bollinger Bands (Líneas Azules Dasheadas)
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Up'], line=dict(color=VQ_CYAN, width=1.5, dash='dot'), name='Bollinger Up'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Low'], line=dict(color=VQ_CYAN, width=1.5, dash='dot'), name='Bollinger Low'), row=1, col=1)

        # --- PANEL 2: MOMENTUM & SQUEEZE DOTS ---
        # Histograma de momentum
        fig.add_trace(go.Bar(x=df.index, y=df['Momentum'], marker_color=colores_mom, name='Momentum'), row=2, col=1)
        # Línea de Squeeze (Puntos Rojos = Compresión, Verdes = Liberación)
        fig.add_trace(go.Scatter(x=df.index, y=[0]*len(df), mode='markers', marker=dict(color=colores_squeeze, size=6), name='Estado Squeeze'), row=2, col=1)

        # --- PANEL 3: VOLUMEN ---
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colores_vol, name='Volumen'), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['Vol_SMA'], line=dict(color="#eef4ff", width=1.5), name='Media Volumen'), row=3, col=1)

        # 4. ESTÉTICA FINTECH
        fig.update_layout(
            height=850, template=VQ_TEMPLATE_NAME,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig.update_xaxes(rangeslider_visible=False, gridcolor="rgba(255,255,255,0.05)")
        fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)")

        return _apply_vq_layout(fig), df
    except Exception as e:
        return None, None

def plot_visor_reversion_media(ticker, period="1y"):
    """Visor 3: Reversión a la Media (Z-Score + StochRSI + Bollinger)"""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        import yfinance as yf
        import pandas as pd
        import numpy as np
        
        # 1. Descarga de datos
        df = yf.download(ticker, period=period)
        if df.empty or len(df) < 50:
            return None, None
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        # 2. MATEMÁTICAS DE REVERSIÓN
        # -- Medias y Bandas (El Imán del Precio) --
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['STD_20'] = df['Close'].rolling(window=20).std()
        df['BB_Up'] = df['SMA_20'] + (df['STD_20'] * 2.0)
        df['BB_Low'] = df['SMA_20'] - (df['STD_20'] * 2.0)

        # -- Z-Score (Tensión de la Goma Elástica) --
        # Cuántas desviaciones estándar se ha alejado el precio de la media
        df['Z_Score'] = (df['Close'] - df['SMA_20']) / df['STD_20']
        
        # Colores del Z-Score (Pánico = Verde, Euforia = Rojo, Normal = Azul)
        colores_z = []
        for z in df['Z_Score']:
            if z <= -2: colores_z.append(VQ_GREEN) # Pánico / Sobrevendido
            elif z >= 2: colores_z.append(VQ_RED) # Euforia / Sobrecomprado
            else: colores_z.append('#4a5b7d') # Zona neutral

        # -- StochRSI (El Gatillo Rápido) --
        # 1. Calculamos RSI clásico
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 2. Calculamos Estocástico del RSI
        rolling_min = df['RSI'].rolling(window=14).min()
        rolling_max = df['RSI'].rolling(window=14).max()
        # Evitamos divisiones por cero
        rango = rolling_max - rolling_min
        rango = rango.replace(0, 1e-10) 
        
        df['StochRSI'] = ((df['RSI'] - rolling_min) / rango) * 100
        df['Stoch_K'] = df['StochRSI'].rolling(window=3).mean() # Línea rápida
        df['Stoch_D'] = df['Stoch_K'].rolling(window=3).mean()  # Línea lenta de señal

        # 3. CONSTRUCCIÓN DEL GRÁFICO (3 Paneles)
        fig = make_subplots(
            rows=3, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.04, 
            row_heights=[0.5, 0.25, 0.25],
            subplot_titles=("Precio e Imán (SMA 20 + Bollinger)", "Tensión Extrema (Z-Score)", "Gatillo de Giro (StochRSI)")
        )

        # --- PANEL 1: PRECIO Y BOLLINGER ---
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Precio'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color=VQ_AMBER, width=2), name='Media (El Imán)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Up'], line=dict(color='rgba(55, 198, 230, 0.40)', width=1, dash='dash'), name='Banda Sup'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Low'], line=dict(color='rgba(55, 198, 230, 0.40)', width=1, dash='dash'), name='Banda Inf'), row=1, col=1)

        # --- PANEL 2: Z-SCORE (DESVIACIÓN) ---
        fig.add_trace(go.Bar(x=df.index, y=df['Z_Score'], marker_color=colores_z, name='Z-Score'), row=2, col=1)
        # Líneas de extremo estadístico (+2 y -2 desviaciones)
        fig.add_hline(y=2, line_dash="dot", line_color=VQ_RED, row=2, col=1)
        fig.add_hline(y=-2, line_dash="dot", line_color=VQ_GREEN, row=2, col=1)

        # --- PANEL 3: STOCHASTIC RSI ---
        fig.add_trace(go.Scatter(x=df.index, y=df['Stoch_K'], line=dict(color=VQ_CYAN, width=1.5), name='%K (Rápida)'), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['Stoch_D'], line=dict(color=VQ_AMBER, width=1.5, dash='dot'), name='%D (Señal)'), row=3, col=1)
        # Zonas de 80 y 20
        fig.add_hline(y=80, line_dash="dash", line_color=VQ_RED, opacity=0.5, row=3, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color=VQ_GREEN, opacity=0.5, row=3, col=1)
        fig.add_hrect(y0=20, y1=80, fillcolor="white", opacity=0.05, layer="below", line_width=0, row=3, col=1)

        # 4. ESTÉTICA
        fig.update_layout(
            height=850, template=VQ_TEMPLATE_NAME,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig.update_xaxes(rangeslider_visible=False, gridcolor="rgba(255,255,255,0.05)")
        fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)")
        # Forzar StochRSI entre 0 y 100
        fig.update_yaxes(range=[0, 100], row=3, col=1)

        return _apply_vq_layout(fig), df
    except Exception as e:
        return None, None

def plot_visor_ichimoku(ticker, period="1y"):
    """Visor 4: Sistema Holístico Ichimoku Cloud + Flujo de Volumen (OBV)"""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        import yfinance as yf
        import pandas as pd
        import numpy as np
        
        # 1. Descarga de datos
        df = yf.download(ticker, period=period)
        if df.empty or len(df) < 100:
            return None, None
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        # 2. PROYECCIÓN TEMPORAL (El secreto del Ichimoku)
        # Añadimos 26 días laborables al futuro en nuestro DataFrame
        ultimo_dia = df.index[-1]
        fechas_futuras = pd.date_range(start=ultimo_dia + pd.Timedelta(days=1), periods=26, freq='B')
        df = df.reindex(df.index.append(fechas_futuras))

        # 3. MATEMÁTICAS ICHIMOKU
        # -- Tenkan-sen (Línea de Conversión, 9 periodos) -- Rápida
        high_9 = df['High'].rolling(window=9).max()
        low_9 = df['Low'].rolling(window=9).min()
        df['Tenkan'] = (high_9 + low_9) / 2

        # -- Kijun-sen (Línea Base, 26 periodos) -- Lenta
        high_26 = df['High'].rolling(window=26).max()
        low_26 = df['Low'].rolling(window=26).min()
        df['Kijun'] = (high_26 + low_26) / 2

        # -- Senkou Span A (Límite de Nube 1) -- Proyectado 26 periodos al futuro
        df['Senkou_A'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)

        # -- Senkou Span B (Límite de Nube 2, 52 periodos) -- Proyectado 26 periodos al futuro
        high_52 = df['High'].rolling(window=52).max()
        low_52 = df['Low'].rolling(window=52).min()
        df['Senkou_B'] = ((high_52 + low_52) / 2).shift(26)

        # -- Chikou Span (Línea Rezagada) -- Precio desplazado 26 periodos al pasado
        df['Chikou'] = df['Close'].shift(-26)

        # 4. MATEMÁTICAS DE VOLUMEN (On-Balance Volume - OBV)
        # Suma volumen si el día es alcista, resta si es bajista.
        diff = df['Close'].diff()
        direction = np.sign(diff).fillna(0)
        df['OBV'] = (df['Volume'] * direction).fillna(0).cumsum()
        df['OBV_EMA'] = df['OBV'].ewm(span=20, adjust=False).mean()

        # 5. CONSTRUCCIÓN DEL GRÁFICO (2 Paneles)
        fig = make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.05, 
            row_heights=[0.7, 0.3],
            subplot_titles=("Ichimoku Kinko Hyo (La Nube de Equilibrio)", "Flujo de Dinero Institucional (OBV)")
        )

        # --- PANEL 1: ICHIMOKU CLOUD ---
        # Velas (Ocultamos en el futuro donde no hay datos)
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Precio'), row=1, col=1)
        
        # Líneas Clave
        fig.add_trace(go.Scatter(x=df.index, y=df['Tenkan'], line=dict(color=VQ_CYAN, width=1.5), name='Tenkan (Rápida)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['Kijun'], line=dict(color=VQ_AMBER, width=1.5), name='Kijun (Base)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['Chikou'], line=dict(color=VQ_AMBER, width=1, dash='dot'), name='Chikou (Pasado)'), row=1, col=1)

        # La Nube (Kumo) - Magia visual
        # Para colorear la nube de verde o rojo según quién esté arriba (Span A o B), trazamos ambos y rellenamos entre ellos.
        fig.add_trace(go.Scatter(x=df.index, y=df['Senkou_A'], line=dict(color='rgba(54, 196, 134, 0)'), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Senkou_B'], 
            line=dict(color='rgba(239, 91, 107, 0)'), 
            fill='tonexty', 
            fillcolor='rgba(128, 128, 128, 0.15)', # Relleno genérico, Plotly no permite rellenado condicional simple
            name='Nube Futura (Kumo)'
        ), row=1, col=1)
        
        # Repintamos las líneas de la nube para que se vean los bordes
        fig.add_trace(go.Scatter(x=df.index, y=df['Senkou_A'], line=dict(color=VQ_GREEN, width=1), name='Span A (Verde)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['Senkou_B'], line=dict(color=VQ_RED, width=1), name='Span B (Roja)'), row=1, col=1)

        # --- PANEL 2: OBV (Rastro del Dinero) ---
        fig.add_trace(go.Scatter(x=df.index, y=df['OBV'], line=dict(color=VQ_GREEN, width=2), name='OBV'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['OBV_EMA'], line=dict(color="#eef4ff", width=1, dash='dash'), name='Media OBV'), row=2, col=1)

        # 6. ESTÉTICA
        fig.update_layout(
            height=850, template=VQ_TEMPLATE_NAME,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig.update_xaxes(rangeslider_visible=False, gridcolor="rgba(255,255,255,0.05)")
        fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)")

        # Devolvemos el df limpio de las fechas futuras para el análisis del Veredicto
        df_limpio = df.dropna(subset=['Close'])
        return _apply_vq_layout(fig), df_limpio
    except Exception as e:
        return None, None
