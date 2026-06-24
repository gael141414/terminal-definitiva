"""Aplica el Sprint 1C sobre app.py.

Objetivo:
- Eliminar imports directos de módulos secundarios.
- Usar modulos.module_loader.safe_call para cargar herramientas bajo demanda.
- Evitar que un módulo opcional roto tumbe toda la app al arrancar.

Uso desde la raíz del proyecto:
    python scripts/apply_sprint_1c_lazy_imports.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"

OPTIONAL_IMPORT_LINES = [
    "from modulos.roboadvisor import ejecutar_roboadvisor\n",
    "from modulos.proyeccion import ejecutar_proyeccion\n",
    "from modulos.backtest import ejecutar_maquina_del_tiempo\n",
    "from modulos.radar import ejecutar_radar_multibagger\n",
    "from modulos.forense import ejecutar_auditoria_forense\n",
    "from modulos.insiders import ejecutar_rastreador_insiders\n",
    "from modulos.screener import ejecutar_escaner_global\n",
    "from modulos.etf import ejecutar_radiografia_etf\n",
    "from modulos.resumen import ejecutar_resumen_ejecutivo\n",
    "from modulos.fundamental import ejecutar_analisis_fundamental\n",
    "from modulos.tecnico import ejecutar_tecnico_y_opciones\n",
    "from modulos.macro import ejecutar_radar_macro\n",
    "from modulos.reloj_macro import ejecutar_reloj_macro\n",
    "from modulos.liquidez import ejecutar_monitor_liquidez\n",
    "from modulos.cisnes_negros import ejecutar_simulador_crisis\n",
    "from modulos.coberturas import ejecutar_radar_coberturas\n",
    "from modulos.chatbot import render_chatbot\n",
    "from modulos.consejos import ejecutar_apartado_consejos\n",
    "from modulos.predictor import ejecutar_predictor_techos_suelos\n",
    "from modulos.minero_smallcaps import ejecutar_visor_smallcaps\n",
    "from modulos.nlp_analyzer import render_nlp_dashboard\n",
    "from modulos.portfolio import render_portfolio_manager\n",
    "from modulos.backtester import render_backtesting_engine\n",
    "from modulos.automatizacion import ejecutar_panel_automatizacion\n",
    "from modulos.gurus import ejecutar_visor_gurus\n",
    "from modulos.watchlist import ejecutar_watchlist\n",
    "from modulos.screener_avanzado import render_screener_avanzado\n",
    "from modulos.montecarlo import render_montecarlo\n",
    "from modulos.derivados import render_derivados\n",
    "from modulos.alt_data import render_alt_data\n",
    "from charts import render_market_treemap\n",
]

REPLACEMENTS = {
    # Home / visualizaciones
    "render_market_treemap(treemap_df)": "safe_call(\"charts\", \"render_market_treemap\", treemap_df)",

    # Standalone / ETF
    "ejecutar_reloj_macro()": "safe_call(\"modulos.reloj_macro\", \"ejecutar_reloj_macro\")",
    "ejecutar_watchlist()": "safe_call(\"modulos.watchlist\", \"ejecutar_watchlist\")",
    "render_portfolio_manager()": "safe_call(\"modulos.portfolio\", \"render_portfolio_manager\")",
    "render_montecarlo()": "safe_call(\"modulos.montecarlo\", \"render_montecarlo\")",
    "ejecutar_roboadvisor()": "safe_call(\"modulos.roboadvisor\", \"ejecutar_roboadvisor\")",
    "ejecutar_panel_automatizacion()": "safe_call(\"modulos.automatizacion\", \"ejecutar_panel_automatizacion\")",
    "ejecutar_escaner_global()": "safe_call(\"modulos.screener\", \"ejecutar_escaner_global\")",
    "render_screener_avanzado()": "safe_call(\"modulos.screener_avanzado\", \"render_screener_avanzado\")",
    "ejecutar_radiografia_etf(etf_input)": "safe_call(\"modulos.etf\", \"ejecutar_radiografia_etf\", etf_input)",
    "ejecutar_monitor_liquidez()": "safe_call(\"modulos.liquidez\", \"ejecutar_monitor_liquidez\")",
    "render_chatbot()": "safe_call(\"modulos.chatbot\", \"render_chatbot\")",
    "ejecutar_apartado_consejos()": "safe_call(\"modulos.consejos\", \"ejecutar_apartado_consejos\")",
    "ejecutar_visor_smallcaps()": "safe_call(\"modulos.minero_smallcaps\", \"ejecutar_visor_smallcaps\")",

    # Herramientas de empresa: sustituimos solo el inicio de llamada para mantener los argumentos.
    "ejecutar_resumen_ejecutivo(": "safe_call(\"modulos.resumen\", \"ejecutar_resumen_ejecutivo\",",
    "ejecutar_analisis_fundamental(": "safe_call(\"modulos.fundamental\", \"ejecutar_analisis_fundamental\",",
    "ejecutar_tecnico_y_opciones(": "safe_call(\"modulos.tecnico\", \"ejecutar_tecnico_y_opciones\",",
    "render_derivados(": "safe_call(\"modulos.derivados\", \"render_derivados\",",
    "ejecutar_radar_macro(": "safe_call(\"modulos.macro\", \"ejecutar_radar_macro\",",
    "ejecutar_auditoria_forense(": "safe_call(\"modulos.forense\", \"ejecutar_auditoria_forense\",",
    "ejecutar_predictor_techos_suelos(": "safe_call(\"modulos.predictor\", \"ejecutar_predictor_techos_suelos\",",
    "ejecutar_proyeccion(": "safe_call(\"modulos.proyeccion\", \"ejecutar_proyeccion\",",
    "ejecutar_maquina_del_tiempo(": "safe_call(\"modulos.backtest\", \"ejecutar_maquina_del_tiempo\",",
    "render_backtesting_engine(": "safe_call(\"modulos.backtester\", \"render_backtesting_engine\",",
    "render_nlp_dashboard(": "safe_call(\"modulos.nlp_analyzer\", \"render_nlp_dashboard\",",
    "ejecutar_radar_multibagger(": "safe_call(\"modulos.radar\", \"ejecutar_radar_multibagger\",",
    "ejecutar_rastreador_insiders(": "safe_call(\"modulos.insiders\", \"ejecutar_rastreador_insiders\",",
    "render_alt_data(": "safe_call(\"modulos.alt_data\", \"render_alt_data\",",
    "ejecutar_simulador_crisis(": "safe_call(\"modulos.cisnes_negros\", \"ejecutar_simulador_crisis\",",
    "ejecutar_radar_coberturas(": "safe_call(\"modulos.coberturas\", \"ejecutar_radar_coberturas\",",
    "ejecutar_visor_gurus(": "safe_call(\"modulos.gurus\", \"ejecutar_visor_gurus\",",
}


def main() -> None:
    if not APP_PATH.exists():
        raise FileNotFoundError(f"No se encontró app.py en {APP_PATH}")

    content = APP_PATH.read_text(encoding="utf-8")
    original = content

    if "from modulos.module_loader import safe_call" not in content:
        anchor = "from modulos.config import CONFIG\n"
        if anchor not in content:
            raise RuntimeError("No se encontró el import de CONFIG. Ejecuta primero Sprint 1B.2.")
        content = content.replace(anchor, anchor + "from modulos.module_loader import safe_call\n")

    for line in OPTIONAL_IMPORT_LINES:
        content = content.replace(line, "")

    for old, new in REPLACEMENTS.items():
        content = content.replace(old, new)

    if content == original:
        print("No se aplicaron cambios. Puede que app.py ya estuviera migrado.")
    else:
        APP_PATH.write_text(content, encoding="utf-8")
        print("OK: app.py migrado a lazy imports con safe_call.")

    remaining_imports = [line.strip() for line in OPTIONAL_IMPORT_LINES if line in content]
    if remaining_imports:
        print("AVISO: quedan imports opcionales sin retirar:")
        for item in remaining_imports:
            print(f"- {item}")
        raise SystemExit(1)

    print("Siguiente comprobación recomendada:")
    print("python -m py_compile app.py modulos/module_loader.py modulos/config.py modulos/scoring_engine.py")


if __name__ == "__main__":
    main()
