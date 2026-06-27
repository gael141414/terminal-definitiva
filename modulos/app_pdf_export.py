from __future__ import annotations

try:
    from fpdf import FPDF
except Exception:
    FPDF = None


def generar_reporte_pdf(ticker, precio, res_val, nota, fcf_yield, buyback_yield):
    """Genera un informe institucional en PDF de 1 página (Tear Sheet)"""
    if FPDF is None:
        raise RuntimeError("fpdf2 no está instalado. Instálalo o desactiva la exportación PDF.")

    pdf = FPDF()
    pdf.add_page()
    
    # --- CABECERA ---
    pdf.set_fill_color(31, 119, 180) # Azul corporativo
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 22)
    pdf.cell(0, 18, f" TEAR SHEET VALUE: {ticker} ", ln=True, align='C', fill=True)
    
    pdf.set_text_color(100, 100, 100)
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 8, "Generado por Buffett Terminal Analytics (IA Cuantitativa)", ln=True, align='C')
    pdf.ln(5)
    
    # --- 1. SCORE GENERAL ---
    color_score = (44, 160, 44) if nota >= 80 else (255, 127, 14) if nota >= 50 else (214, 39, 40)
    pdf.set_fill_color(*color_score)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, f" CALIDAD FUNDAMENTAL (BUFFETT SCORE): {nota} / 100 ", ln=True, align='C', fill=True)
    pdf.ln(8)
    
    # --- 2. VALORACIÓN Y MARGEN DE SEGURIDAD ---
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "1. Valoracion Intrinseca (Modelo DCF Automizado)", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y()) # Línea separadora
    pdf.ln(3)
    
    pdf.set_font("Arial", '', 11)
    if res_val and precio:
        g = res_val.get('crecimiento_sostenible', 0.05)
        r = res_val.get('tasa_descuento_capm', 0.10)
        eps = res_val.get('eps_actual', 0)
        per = res_val.get('per_asumido', 15)
        
        v_i = (eps * ((1 + g)**10) * per) / ((1 + r)**10)
        margen = ((precio - v_i) / v_i) * 100
        estado = "SOBREVALORADA" if margen > 0 else "INFRAVALORADA (Ganga)"
        
        pdf.cell(90, 8, f"Precio Mercado Hoy: ${precio:.2f}")
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 8, f"Valor Intrinseco Justo: ${v_i:.2f}", ln=True)
        pdf.set_font("Arial", '', 11)
        
        pdf.cell(90, 8, f"Crecimiento asig. (g): {g*100:.1f}%")
        pdf.cell(0, 8, f"Tasa Descuento (CAPM): {r*100:.1f}%", ln=True)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.set_text_color(*((214,39,40) if margen > 0 else (44,160,44)))
        pdf.cell(0, 10, f">> ESTADO ACTUAL: {estado} ({abs(margen):.1f}%)", ln=True)
    else:
        pdf.cell(0, 8, "Datos insuficientes para valoracion matematica.", ln=True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)
    
    # --- 3. RETORNO AL ACCIONISTA ---
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "2. Retribucion Real al Accionista", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    
    pdf.set_font("Arial", '', 11)
    total_yield = fcf_yield + buyback_yield
    pdf.cell(0, 8, f"- FCF Yield (Caja libre sobre precio): {fcf_yield:.2f}%", ln=True)
    pdf.cell(0, 8, f"- Buyback Yield (Recompra de acciones): {buyback_yield:.2f}%", ln=True)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f">> RENDIMIENTO TOTAL EFECTIVO: {total_yield:.2f}%", ln=True)
    pdf.ln(8)
    
    # --- 4. VEREDICTO ---
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "3. Veredicto del Algoritmo Value", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    
    pdf.set_font("Arial", '', 11)
    if nota >= 80:
        texto = "EXCELENTE. Foso economico inquebrantable, rentabilidad sobresaliente y deuda controlada. Un claro candidato para mantener a largo plazo al estilo Berkshire Hathaway."
    elif nota >= 50:
        texto = "PRECAUCION. Negocio solido pero presenta debilidades en margenes, niveles de deuda, o su cotizacion exige demasiado crecimiento futuro. Mantener en el radar."
    else:
        texto = "ALERTA ROJA. Fundamentales deteriorados. Alta probabilidad de destruccion de valor por mala asignacion de capital o deuda asfixiante."
        
    pdf.multi_cell(0, 6, texto)
    
    # Guardar en memoria y devolver bytes en lugar de fugar almacenamiento en disco
    try:
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
    except TypeError:
        # Para versiones modernas de fpdf2 que retornan bytearray
        pdf_bytes = bytes(pdf.output())
    return pdf_bytes

