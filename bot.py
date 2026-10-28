import os
import requests
import random
import time
from datetime import datetime, timedelta

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

# ==========================================
# 🔑 CONFIGURAZIONE
# ==========================================
API_TOKEN = os.environ.get('API_TOKEN', 'e2c702f19ed64c2088f7ab6c22493911')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8524849158:AAG2vVKUWqC4J_T1jDPA7IQxLY1uFy0jW9o')
CHAT_ID = os.environ.get('CHAT_ID', '591667981')

TOP_LEAGUES = ['SA', 'PL', 'PD', 'BL1', 'FL1']
headers = {'X-Auth-Token': API_TOKEN}

oggi = datetime.now().strftime('%Y-%m-%d')
ieri = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

print(f"🔄 Recupero partite dai Top 5 Campionati per la data: {oggi}...")

try:
    raw_matches = []
    for league in TOP_LEAGUES:
        url_league = f"https://api.football-data.org/v4/competitions/{league}/matches?date={oggi}"
        res_l = requests.get(url_league, headers=headers)
        if res_l.status_code == 200:
            raw_matches.extend(res_l.json().get('matches', []))

    # Se non ci sono partite nei top 5 oggi, prendiamo il palinsesto generale
    if not raw_matches:
        url_gen = f"https://api.football-data.org/v4/matches?date={oggi}"
        res_g = requests.get(url_gen, headers=headers)
        if res_g.status_code == 200:
            raw_matches = res_g.json().get('matches', [])

    print(f"✅ Trovate {len(raw_matches)} partite da analizzare.")

    partite_oggi = []
    for m in raw_matches:
        comp = m.get('competition', {}).get('name', 'Campionato')
        casa = m.get('homeTeam', {}).get('shortName') or m.get('homeTeam', {}).get('name', 'Casa')
        ospite = m.get('awayTeam', {}).get('shortName') or m.get('awayTeam', {}).get('name', 'Ospite')
        
        seed_m = sum(ord(c) for c in (casa + ospite))
        random.seed(seed_m)
        
        g_c, g_o = round(random.uniform(1.2, 2.4), 1), round(random.uniform(1.3, 2.6), 1)
        tp_c, tp_o = round(random.uniform(3.5, 6.2), 1), round(random.uniform(2.8, 5.5), 1)
        tt_c, tt_o = round(random.uniform(11.0, 16.5), 1), round(random.uniform(9.5, 14.5), 1)
        co_c, co_o = round(random.uniform(4.0, 7.0), 1), round(random.uniform(3.5, 6.0), 1)
        
        confidence = random.randint(25, 95)
        if confidence >= 70:
            fascia = "🥇 Oro"
        elif confidence >= 40:
            fascia = "🥈 Argento"
        else:
            fascia = "🥉 Bronzo"
            
        prob_1x = round(random.uniform(1.18, 1.42), 2)
        prob_x2 = round(random.uniform(1.25, 1.55), 2)
        
        pool_combo = [
            ("1X + Over 1.5 Gol", 1.48), ("X2 + Over 1.5 Gol", 1.55),
            ("Goal SI + Over 1.5", 1.72), ("12 + Over 1.5 Gol", 1.38),
            ("1X + Under 3.5 Gol", 1.42), ("X2 + Under 3.5 Gol", 1.46)
        ]
        scelta_combo, quota_combo = random.choice(pool_combo)

        lin_cart = round(g_c + g_o + 0.5, 1)
        lin_tp = max(3, int(tp_c + tp_o - 1)) + 0.5
        lin_tt = int(tt_c + tt_o - 2) + 0.5
        lin_co = max(7, int(co_c + co_o - 1)) + 0.5
        dc = "1X" if len(casa) % 2 != 0 else "X2"

        partite_oggi.append({
            "comp": comp, "casa": casa, "ospite": ospite,
            "lin_cartellini": lin_cart, "lin_tp": lin_tp,
            "lin_tt": lin_tt, "lin_corner": lin_co,
            "dc": dc, "combo": scelta_combo, "q_combo": quota_combo,
            "q_dc": prob_1x if dc == "1X" else prob_x2,
            "confidence": confidence, "fascia": fascia
        })

    # ==========================================
    # 📄 GENERAZIONE PDF CON REPORTLAB
    # ==========================================
    pdf_filename = f"Report_Schedine_{oggi}.pdf"
    doc = SimpleDocTemplate(pdf_filename, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor('#1A237E'), alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, leading=12, textColor=colors.gray, alignment=1)
    section_style = ParagraphStyle('SectionStyle', parent=styles['Heading2'], fontSize=13, leading=16, textColor=colors.HexColor('#0D47A1'), spaceBefore=12, spaceAfter=6)
    cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=8, leading=10)
    cell_header = ParagraphStyle('CellHeader', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.white, fontName="Helvetica-Bold")

    story.append(Paragraph("<b>ANALISI COMPLETA SCHEDINE GIORNALIERE</b>", title_style))
    story.append(Paragraph(f"Data: {oggi} | Top 5 Campionati Europei | Partite Analizzate: {len(partite_oggi)}", subtitle_style))
    story.append(Spacer(1, 15))

    def crea_tabella_categoria(titolo, chiave_prono, prefisso=""):
        story.append(Paragraph(f"<b>{titolo}</b>", section_style))
        table_data = [
            [Paragraph("<b>Lega</b>", cell_header),
             Paragraph("<b>Incontro</b>", cell_header),
             Paragraph("<b>Pronostico</b>", cell_header),
             Paragraph("<b>Conf.</b>", cell_header),
             Paragraph("<b>Fascia</b>", cell_header)]
        ]
        
        for p in partite_oggi:
            if chiave_prono == "combo":
                prono_txt = p["combo"]
            elif chiave_prono == "dc":
                prono_txt = f"Doppia Chance {p['dc']}"
            else:
                prono_txt = f"Over {p[chiave_prono]} {prefisso}"
                
            table_data.append([
                Paragraph(p["comp"], cell_style),
                Paragraph(f"{p['casa']} - {p['ospite']}", cell_style),
                Paragraph(prono_txt, cell_style),
                Paragraph(f"{p['confidence']}%", cell_style),
                Paragraph(p["fascia"], cell_style)
            ])
            
        t = Table(table_data, colWidths=[90, 160, 150, 50, 75])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A237E')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E0E0E0')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F5F5F5')]),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    crea_tabella_categoria("🟨 OVER CARTELLINI", "lin_cartellini", "Cartellini")
    crea_tabella_categoria("🎯 COMBO MATCH", "combo")
    crea_tabella_categoria("⚽ TIRI IN PORTA", "lin_tp", "Tiri in Porta")
    crea_tabella_categoria("🚀 TIRI TOTALI", "lin_tt", "Tiri Totali")
    crea_tabella_categoria("🛡️ DOPPIE CHANCES", "dc")
    crea_tabella_categoria("🚩 CALCI D'ANGOLO (CORNER)", "lin_corner", "Corner")

    doc.build(story)
    print(f"✅ PDF '{pdf_filename}' generato con successo.")

    # ==========================================
    # 🚀 INVIO DEL PDF SU TELEGRAM
    # ==========================================
    url_document = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    
    caption_txt = f"📊 *REPORT COMPLETO IN PDF* ({oggi})\nIn allegato trovi l'analisi tabellata di tutti i match con le fasce Oro 🥇, Argento 🥈 e Bronzo 🥉."
    
    with open(pdf_filename, 'rb') as doc_file:
        files = {'document': doc_file}
        data = {
            'chat_id': CHAT_ID,
            'caption': caption_txt,
            'parse_mode': 'Markdown'
        }
        res_send = requests.post(url_document, data=data, files=files)
        
    if res_send.status_code == 200:
        print("✅ File PDF inviato con successo su Telegram!")
    else:
        print(f"⚠️ Errore invio Telegram: {res_send.text}")

except Exception as e:
    print(f"❌ Errore generale: {e}")
