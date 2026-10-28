import os
import requests
import random
import time
from datetime import datetime, timedelta

from reportlab.lib.pagesizes import A4
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

print(f"🔄 Recupero le partite ESCLUSIVAMENTE per la giornata di oggi: {oggi}...")

try:
    raw_matches = []
    # Interroghiamo specificando la data odierna per ogni campionato dei Top 5
    for league in TOP_LEAGUES:
        url_league = f"https://api.football-data.org/v4/competitions/{league}/matches?date={oggi}"
        res_l = requests.get(url_league, headers=headers)
        if res_l.status_code == 200:
            raw_matches.extend(res_l.json().get('matches', []))

    print(f"✅ Trovate {len(raw_matches)} partite in programma oggi nei Top 5 campionati.")

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
        
        confidence = random.randint(20, 95)
        
        # Classificazione in base alla confidence richiesta
        if confidence >= 70:
            fascia = "🥇 ORO"
            priority = 1
        elif confidence >= 40:
            fascia = "🥈 ARGENTO"
            priority = 2
        else:
            fascia = "🥉 BRONZO"
            priority = 3
            
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
            "confidence": confidence, "fascia": fascia, "priority": priority
        })

    # Ordinamento per priorità fascia (Oro -> Argento -> Bronzo) e poi per confidence decrescente
    partite_oggi.sort(key=lambda x: (x['priority'], -x['confidence']))

    # ==========================================
    # 📄 GENERAZIONE PDF GIORNALIERO ORDINATO
    # ==========================================
    pdf_filename = f"Report_Schedine_Giornaliere_{oggi}.pdf"
    doc = SimpleDocTemplate(pdf_filename, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor('#1A237E'), alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.gray, alignment=1)
    section_style = ParagraphStyle('SectionStyle', parent=styles['Heading2'], fontSize=12, leading=15, textColor=colors.HexColor('#0D47A1'), spaceBefore=10, spaceAfter=4)
    cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=8, leading=10)
    cell_header = ParagraphStyle('CellHeader', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.white, fontName="Helvetica-Bold")

    story.append(Paragraph("<b>REPORT GIORNALIERO SCHEDINE - TOP 5 CAMPIONATI</b>", title_style))
    story.append(Paragraph(f"Data Odierna: {oggi} | Ordinato per Classificazione Oro, Argento e Bronzo", subtitle_style))
    story.append(Spacer(1, 10))

    def crea_tabella_categoria(titolo, chiave_prono, prefisso=""):
        story.append(Paragraph(f"<b>{titolo}</b>", section_style))
        table_data = [
            [Paragraph("<b>Fascia / Conf.</b>", cell_header),
             Paragraph("<b>Lega</b>", cell_header),
             Paragraph("<b>Incontro</b>", cell_header),
             Paragraph("<b>Pronostico Giornaliero</b>", cell_header)]
        ]
        
        for p in partite_oggi:
            if chiave_prono == "combo":
                prono_txt = f"{p['combo']} (Q: {p['q_combo']})"
            elif chiave_prono == "dc":
                prono_txt = f"Doppia Chance {p['dc']} (Q: {p['q_dc']})"
            else:
                val = p[chiave_prono]
                q = round(1.55 + (val * 0.02), 2)
                prono_txt = f"Over {val} {prefisso} (Q: {q})"
                
            table_data.append([
                Paragraph(f"<b>{p['fascia']}</b> ({p['confidence']}%)", cell_style),
                Paragraph(p["comp"], cell_style),
                Paragraph(f"{p['casa']} vs {p['ospite']}", cell_style),
                Paragraph(prono_txt, cell_style)
            ])
            
        t = Table(table_data, colWidths=[90, 95, 145, 145])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A237E')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E0E0E0')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F5F5F5')]),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    crea_tabella_categoria("🟨 1. OVER CARTELLINI", "lin_cartellini", "Cartellini")
    crea_tabella_categoria("🎯 2. COMBO MATCH", "combo")
    crea_tabella_categoria("⚽ 3. TIRI IN PORTA", "lin_tp", "Tiri in Porta")
    crea_tabella_categoria("🚀 4. TIRI TOTALI", "lin_tt", "Tiri Totali")
    crea_tabella_categoria("🛡️ 5. DOPPIE CHANCES", "dc")
    crea_tabella_categoria("🚩 6. CALCI D'ANGOLO (CORNER)", "lin_corner", "Corner")

    doc.build(story)
    print(f"✅ PDF giornaliero '{pdf_filename}' generato correttamente.")

    # ==========================================
    # 🚀 INVIO DEL PDF SU TELEGRAM
    # ==========================================
    url_document = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    caption_txt = f"📅 *REPORT GIORNALIERO SCHEDINE* ({oggi})\nPartite odierne ordinate per Oro 🥇, Argento 🥈 e Bronzo 🥉."
    
    with open(pdf_filename, 'rb') as doc_file:
        files = {'document': doc_file}
        data
