import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

def generar_graficos_buffett(df_is, df_bs, df_cf, ticker):
    """
    Genera un panel visual avanzado de 6 gráficos basado en las métricas
    de ventaja competitiva duradera de Warren Buffett.
    """
    if df_is is None or df_bs is None or df_cf is None:
        print("[!] Datos insuficientes para graficar.")
        return

    # Limpiar los años para el eje X (ej: "2023-09-30" -> "2023")
    # Usamos el índice de is_df y lo alineamos
    años = [str(a)[:4] for a in df_is.index]

    # Crear panel de gráficos (3 filas x 2 columnas)
    fig, axs = plt.subplots(3, 2, figsize=(18, 16))
    plt.subplots_adjust(hspace=0.4, wspace=0.25)
    fig.suptitle(f"Análisis Value (Equity Bond): {ticker}", fontsize=24, fontweight="bold")

    # Colores corporativos y limpios
    color_main = "#1f77b4"
    color_sec = "#ff7f0e"

    # =====================================================
    # [0,0] MÁRGENES - Poder de fijación de precios
    # =====================================================
    if "Margen Bruto %" in df_is.columns and "Margen Neto %" in df_is.columns:
        axs[0, 0].plot(años, df_is["Margen Bruto %"], marker="o", linewidth=2.5, label="Margen Bruto %", color=color_main)
        axs[0, 0].plot(años, df_is["Margen Neto %"], marker="s", linestyle="--", linewidth=2, label="Margen Neto %", color=color_sec)
        axs[0, 0].axhline(y=40, linestyle=":", color="green", alpha=0.7, label="Umbral Excelente MB (>40%)")
        axs[0, 0].axhline(y=20, linestyle=":", color="red", alpha=0.7, label="Umbral Excelente MN (>20%)")
        axs[0, 0].set_title("1. Poder de Precios (Márgenes)", fontsize=14, fontweight='bold')
        axs[0, 0].set_ylabel("Porcentaje (%)")
        axs[0, 0].legend()
        axs[0, 0].grid(True, alpha=0.3)

    # =====================================================
    # [0,1] RENTABILIDAD - ROE
    # =====================================================
    if "ROE %" in df_bs.columns:
        axs[0, 1].bar(años, df_bs["ROE %"], alpha=0.8, color="#2ca02c", edgecolor="black")
        axs[0, 1].axhline(y=15, linestyle="-", color="red", label="Mínimo Buffett (15%)")
        axs[0, 1].set_title("2. Eficiencia Directiva (ROE)", fontsize=14, fontweight='bold')
        axs[0, 1].set_ylabel("Porcentaje (%)")
        axs[0, 1].legend()
        axs[0, 1].grid(axis="y", alpha=0.3)

    # =====================================================
    # [1,0] EL DINERO REAL - Free Cash Flow vs Beneficio
    # =====================================================
    if "Free Cash Flow (B USD)" in df_cf.columns:
        # Extraemos el beneficio neto asumiendo que el margen neto y ventas están, lo simplificamos graficando el FCF directo
        axs[1, 0].fill_between(años, df_cf["Free Cash Flow (B USD)"], color="#9467bd", alpha=0.3)
        axs[1, 0].plot(años, df_cf["Free Cash Flow (B USD)"], marker="D", color="#9467bd", linewidth=2, label="Free Cash Flow (Owner Earnings)")
        axs[1, 0].set_title("3. Generación de Efectivo Real (FCF)", fontsize=14, fontweight='bold')
        axs[1, 0].set_ylabel("Billones (B USD)")
        axs[1, 0].legend()
        axs[1, 0].grid(True, alpha=0.3)

    # =====================================================
    # [1,1] RETORNO AL ACCIONISTA - Recompras
    # =====================================================
    if "Recompras (B USD)" in df_cf.columns:
        axs[1, 1].bar(años, df_cf["Recompras (B USD)"], color="#d62728", alpha=0.8, edgecolor="black")
        axs[1, 1].set_title("4. Retorno al Accionista (Recompras)", fontsize=14, fontweight='bold')
        axs[1, 1].set_ylabel("Billones (B USD) quemados")
        axs[1, 1].grid(axis="y", alpha=0.3)

    # =====================================================
    # [2,0] SOLIDEZ FINANCIERA - Caja Neta vs Deuda
    # =====================================================
    if "Caja Neta (B USD)" in df_bs.columns:
        colores_caja = ['green' if x >= 0 else 'red' for x in df_bs["Caja Neta (B USD)"]]
        axs[2, 0].bar(años, df_bs["Caja Neta (B USD)"], color=colores_caja, alpha=0.7, edgecolor="black")
        axs[2, 0].axhline(y=0, color="black", linewidth=1.5)
        axs[2, 0].set_title("5. Solidez (Caja Neta)", fontsize=14, fontweight='bold')
        axs[2, 0].set_ylabel("Billones (B USD)")
        axs[2, 0].grid(axis="y", alpha=0.3)

    # =====================================================
    # [2,1] INTENSIDAD DE CAPITAL - CAPEX
    # =====================================================
    if "CAPEX % sobre Beneficio" in df_cf.columns:
        axs[2, 1].plot(años, df_cf["CAPEX % sobre Beneficio"], marker="v", color="#8c564b", linewidth=2, label="CAPEX / Beneficio Neto")
        axs[2, 1].axhline(y=25, linestyle="--", color="green", alpha=0.7, label="Excelente (<25%)")
        axs[2, 1].axhline(y=50, linestyle="--", color="red", alpha=0.7, label="Límite Peligro (>50%)")
        axs[2, 1].set_title("6. Coste de Mantenimiento (CAPEX)", fontsize=14, fontweight='bold')
        axs[2, 1].set_ylabel("Porcentaje (%)")
        axs[2, 1].legend()
        axs[2, 1].grid(True, alpha=0.3)

    # Guardar y mostrar
    nombre_archivo = f"{ticker}_buffett_dashboard.png"
    plt.savefig(nombre_archivo, dpi=300, bbox_inches="tight")
    print(f"\n[+] Dashboard visual HD guardado con éxito: {nombre_archivo}")
    plt.show()

# Bloque de ejecución independiente para pruebas
if __name__ == "__main__":
    from downloader import obtener_estados_financieros
    from income_analyzer import analizar_cuenta_resultados
    from balance_analyzer import analizar_balance
    from cashflow_analyzer import analizar_flujo_efectivo

    is_df, bs_df, cf_df = obtener_estados_financieros("AAPL", 10)
    if is_df is not None:
        res_is = analizar_cuenta_resultados(is_df)
        res_bs = analizar_balance(bs_df, is_df)
        res_cf = analizar_flujo_efectivo(cf_df, is_df)
        generar_graficos_buffett(res_is["ratios"], res_bs["ratios"], res_cf["ratios"], "AAPL")