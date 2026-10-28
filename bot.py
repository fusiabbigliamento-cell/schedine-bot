import os
import time
import requests
from datetime import datetime

# Import per la generazione del PDF con ReportLab
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ==========================================
# 🔑 CONFIGURAZIONE API & CREDENZIALI
# ==========================================
API_TOKEN = os.environ.get('API_TOKEN', 'e2c702f19ed64c2088f7ab6c22493911')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8524849158:AAG2vVKUWqC4J_T1jDPA7IQxLY1uFy0jW9o')
CHAT_ID = os.environ.get('CHAT_ID', '591667981')

headers_fd = {'X-Auth-Token': API_TOKEN}
oggi = datetime.now().strftime('%Y-%m-%d')
pdf_filename = f"pronostici_{oggi}.pdf"

print(f"🔄 Avvio analisi strutturale e generazione report per il: {oggi}...")

try:
    # 1. Recupero delle partite odierne
    url_oggi = f"https://api.football-data.org/v4/matches?date={oggi}"
    res_fd = requests.get(url_oggi, headers=headers_fd)
    time.sleep(2)  # Rispetto del Rate Limit API
    
    raw_matches = []
    if res_fd.status_code == 200:
        raw_matches = res_fd.json().get('matches', [])

    print(f"✅ Trovate {len(raw_matches)} partite nel palinsesto odierno.")

    # 2. PRE-FETCHING DELLE CLASSIFICHE CON GESTIONE COPPE / DATI MANCANTI
    comp_ids = set(m.get('competition', {}).get('id') for m in raw_matches if m.get('competition', {}).get('id'))
    
    classifiche_cache = {}
    for comp_id in comp_ids:
        url_standings = f"https://api.football-data.org/v4/competitions/{comp_id}/standings"
        res_st = requests.get(url_standings, headers=headers_fd)
        time.sleep(2)  # Pausa per rispettare il limite di 30 req/min
        
        if res_st.status_code == 200:
            standings_list = res_st.json().get('standings', [])
            table = []
            for s in standings_list:
                if s.get('type') == 'TOTAL':
                    table = s.get('table', [])
                    break
            if not table and standings_list:
                table = standings_list[0].get('table', [])
                
            # Mappatura sicura dei dati squadra
            classifiche_cache[comp_id] = {item['team']['name']: item for item in table if 'team' in item}
        else:
            classifiche_cache[comp_id] = {} # Fallback vuoto per coppe o tornei senza classifica standard

    partite_analizzate = []

    for m in raw_matches:
        comp = m.get('competition', {})
        comp_id = comp.get('id')
        status_match = m.get('status', 'TIMED')
        home_team = m.get('homeTeam', {})
        away_team = m.get('awayTeam', {})
        
        casa = home_team.get('shortName') or home_team.get('name', 'Casa')
        ospite = away_team.get('shortName') or away_team.get('name', 'Ospite')
        
        standings_map = classifiche_cache.get(comp_id, {})
        
        # Punto 2: Gestione sicura dati mancanti (fallback neutro per coppe/tornei senza classifica)
        dati_casa = standings_map.get(home_team.get('name'), {"position": 10, "points": 0})
        dati_ospite = standings_map.get(away_team.get('name'), {"position": 10, "points": 0})
        
        pos_casa = dati_casa.get('position', 10)
        pos_ospite = dati_ospite.get('position', 10)
        punti_casa = dati_casa.get('points', 0)
        punti_ospite = dati_ospite.get('points', 0)
        
        diff_pos = abs(pos_ospite - pos_casa)
        diff_punti = abs(punti_casa - punti_ospite)
        forza_match = diff_punti + (diff_pos * 0.5)
        
        # Confidenza dinamica
        conf_calc = 40.0 + (diff_punti * 2.2) + (diff_pos * 1.1)
        confidence = int(min(max(conf_calc, 38), 93))

        if confidence >= 75:
            fascia = "🟢 ALTA"
            priority = 1
            dc = "1X" if pos_casa < pos_ospite else "X2"
            combo = "1X + Over 1.5 Gol" if pos_casa < pos_ospite else "X2 + Over 1.5 Gol"
        elif confidence >= 55:
            fascia = "🟡 MEDIA"
            priority = 2
            dc = "1X" if pos_casa <= pos_ospite else "X2"
            combo = "Goal SI + Over 1.5"
        else:
            fascia = "🔴 BASSA"
            priority = 3
            dc = "1X"
            combo = "12 + Over 1.5 Gol"

        # Punto 3: Logica statistica avanzata e basata su metriche reali anziché moduli casuali
        lin_cart = round(2.5 + (diff_pos * 0.15), 1)
        lin_tp = round(4.0 + (forza_match * 0.1), 1)
        lin_tt = round(20.5 + (diff_pos * 0.2), 1)
        lin_co = round(8.5 + (forza_match * 0.12), 1)

        is_rinviata = status_match in ['POSTPONED', 'SUSPENDED', 'CANCELLED']

        partite_analizzate.append({
            "casa": casa, "ospite": ospite,
            "status": status_match, "is_rinviata": is_rinviata,
            "lin_cartellini": lin_cart, "lin_tp": lin_tp,
            "lin_tt": lin_tt, "lin_corner": lin_co,
            "dc": dc, "combo": combo,
            "confidence": 0 if is_rinviata else confidence, 
            "fascia": fascia, "priority": priority
        })

    # Ordiniamo per priorità e prendiamo le migliori
    partite_analizzate.sort(key=lambda x: (x['priority'], -x['confidence']))

    # ==========================================
    # 📄 PUNTO 4: GENERAZIONE DEL REPORT PDF
    # ==========================================
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()

    # Stili personalizzati
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1A365D'), spaceAfter=6, alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#4A5568'), spaceAfter=15, alignment=1)
    section_style = ParagraphStyle('SectionStyle', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#2B6CB0'), spaceBefore=10, spaceAfter=6)
    cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#2D3748'))
    header_cell_style = ParagraphStyle('HeaderCellStyle', parent=styles['Normal'], fontSize=9, textColor=colors.white, fontName='Helvetica-Bold')

    elements.append(Paragraph(f"<b>REPORT PRONOSTICI & ANALISI STRUTTURALE</b>", title_style))
    elements.append(Paragraph(f"Data di generazione: {oggi} | Software Engine v2.0", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2B6CB0'), spaceAfter=15))

    # Creazione Tabella dei Match Analizzati per il PDF
    table_data = [[
        Paragraph("<b>Match</b>", header_cell_style),
        Paragraph("<b>Fascia / Conf.</b>", header_cell_style),
        Paragraph("<b>Combo Consigliata</b>", header_cell_style),
        Paragraph("<b>DC</b>", header_cell_style),
        Paragraph("<b>Linee (Cart/TP/Corner)</b>", header_cell_style)
    ]]

    for m in partite_analizzate[:15]: # Includiamo fino a 15 partite nel PDF pulito
        if m['is_rinviata']:
            match_str = f"{m['casa']} - {m['ospite']} (Rinviata)"
            conf_str = "⏳ Rinviata"
            combo_str = "-"
            dc_str = "-"
            stats_str = "-"
        else:
            match_str = f"{m['casa']} vs {m['ospite']}"
            conf_str = f"{m['fascia']} ({m['confidence']}%)"
            combo_str = m['combo']
            dc_str = m['dc']
            stats_str = f"C: >{m['lin_cartellini']} | T: >{m['lin_tp']} | Co: >{m['lin_corner']}"

        table_data.append([
            Paragraph(match_str, cell_style),
            Paragraph(conf_str, cell_style),
            Paragraph(combo_str, cell_style),
            Paragraph(dc_str, cell_style),
            Paragraph(stats_str, cell_style)
        ])

    t = Table(table_data, colWidths=[130, 85, 120, 45, 120])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2B6CB0')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0'))
    ]))

    elements.append(t)
    doc.build(elements)
    print(f"✅ PDF generato correttamente: {pdf_filename}")

    # ==========================================
    # 📤 INVIO DEL PDF TRAMITE TELEGRAM
    # ==========================================
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    
    with open(pdf_filename, 'rb') as pdf_file:
        files = {'document': pdf_file}
        payload = {
            "chat_id": CHAT_ID,
            "caption": f"📊 *Ecco il report PDF con i pronostici e le analisi statistiche del {oggi}* 🚀"
        }
        res_tg = requests.post(telegram_url, data=payload, files=files)
        
    if res_tg.status_code == 200:
        print("✅ Report PDF inviato con successo su Telegram!")
    else:
        print(f"⚠️ Errore invio Telegram: {res_tg.text}")

except Exception as e:
    print(f"❌ Errore generale nell'esecuzione: {e}")
