from __future__ import annotations

import streamlit.components.v1 as components


def render_tradingview_widget(ticker):
    """Inyecta el terminal avanzado interactivo de TradingView mediante iframe"""
    
    # Algunos tickers de Yahoo Finance (ej. BRK-B) necesitan limpieza para TradingView
    ticker_tv = ticker.replace("-", ".") 
    
    html_code = f"""
    <!-- TradingView Widget BEGIN -->
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div id="tradingview_terminal" style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
      "autosize": true,
      "symbol": "{ticker_tv}",
      "interval": "D",
      "timezone": "exchange",
      "theme": "dark",
      "style": "1",
      "locale": "es",
      "enable_publishing": false,
      "backgroundColor": "#0b1426",
      "gridColor": "#1e3354",
      "hide_top_toolbar": false,
      "hide_legend": false,
      "save_image": false,
      "container_id": "tradingview_terminal",
      "toolbar_bg": "#0b1426"
    }}
      );
      </script>
    </div>
    <!-- TradingView Widget END -->
    """
    # Renderizamos el HTML incrustado con una altura de 600 píxeles
    components.html(html_code, height=600)


def renderizar_grafico_tradingview(ticker):
    """Inyecta el widget avanzado y nativo de TradingView interactivo"""
    codigo_html = f"""
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div id="tv_chart_container" style="height:600px;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
      "autosize": true,
      "symbol": "{ticker}",
      "interval": "D",
      "timezone": "Etc/UTC",
      "theme": "dark",
      "style": "1",
      "locale": "es",
      "enable_publishing": false,
      "backgroundColor": "#0b0e14",
      "gridColor": "#1f293d",
      "hide_top_toolbar": false,
      "hide_legend": false,
      "save_image": false,
      "container_id": "tv_chart_container",
      "toolbar_bg": "#131722",
      "studies": [
        "Volume@tv-basicstudies",
        "MASimple@tv-basicstudies"
      ]
    }}
      );
      </script>
    </div>
    """
    components.html(codigo_html, height=600)

