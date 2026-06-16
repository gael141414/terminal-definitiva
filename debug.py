from downloader import obtener_estados_financieros
import pandas as pd

print("\n" + "="*50)
print("🛠️ INICIANDO TEST DE DEBUG: DESCARGA SEC")
print("="*50)

# Forzamos usar_cache=False para obligar a conectar con la SEC
try:
    is_df, bs_df, cf_df = obtener_estados_financieros("AAPL", 3, usar_cache=False)

    if is_df is not None:
        print("\n✅ ¡ÉXITO! Los datos se descargaron y procesaron.")
        print("\n🔍 Comprobando columnas resultantes (Deben ser años y metadatos):")
        print(is_df.columns.tolist())
    else:
        print("\n❌ FRACASO: La función devolvió None, None, None.")
except Exception as e:
    print(f"\n💥 ERROR FATAL EN LA EJECUCIÓN DEL SCRIPT: {e}")
    import traceback
    traceback.print_exc()