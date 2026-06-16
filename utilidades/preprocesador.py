from youtube_transcript_api import YouTubeTranscriptApi
import os

def generar_base_conocimiento():
    video_ids = [
        "YXwKy9Z7Z0U", "FN8IbZ2DSeI", "a8a_Q8BX514", "dX_Qir-brCQ", "xTuPY3628Xw",
        "gIyzcj5W0vQ", "3nHw5SG0kdI", "n4eKXcMAB5U", "yyRqmy-DZIs", "us-HWq90czI",
        "d_neze5E2vY", "9uxMUYqthzs", "a97M36ySUlE", "AfqTB89QRtY", "PsaO8KOAqLY",
        "h80BfTLZx_A", "2-21iILq-mo"
    ]
    
    contenido_total = ""
    
    print("📥 Extrayendo transcripciones de YouTube...")
    for vid in video_ids:
        try:
            transcript = YouTubeTranscriptApi.get_transcript(vid, languages=['es'])
            texto = " ".join([t['text'] for t in transcript])
            contenido_total += f"\n--- CONTENIDO VÍDEO {vid} ---\n{texto}\n"
        except Exception as e:
            print(f"⚠️ No se pudo obtener {vid}: {e}")

    # Aquí podrías añadir también el texto de "El Inversor Inteligente" si tienes el .txt
    
    with open("data/brain_context.txt", "w", encoding="utf-8") as f:
        f.write(contenido_total)
    print("✅ Base de conocimiento lista en data/brain_context.txt")

if __name__ == "__main__":
    if not os.path.exists("data"): os.makedirs("data")
    generar_base_conocimiento()
