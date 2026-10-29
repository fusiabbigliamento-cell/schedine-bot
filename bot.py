import os
import time
import math
import requests
from datetime import datetime, timedelta
from difflib import get_close_matches

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ==========================================
# 🔑 CONFIGURAZIONE API & CREDENZIALI
# ==========================================
API_TOKEN = os.environ.get('API_TOKEN', 'e2c702f19ed64c2088f7ab6c22493911')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8524849158:AAG2vVKUWqC4J_T1jDPA7IQxLY1uFy0jW9o')
CHAT_ID = os.environ.get('CHAT_ID', '591667981')

ODSS_KEY = os.environ.get('ODSS_KEY', 'odss_live_9eV8NU_44bNqBQ53VDoEG6ERwYmnhZtz')
ODSS_URL = "https://odss-api.com/api/v1/odds?sport=calcio"

headers_fd = {'X-Auth-Token': API_TOKEN}
headers_odss = {'x-api-key': ODSS_KEY}

oggi = datetime.now().strftime('%Y-%m-%d')
ieri = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
pdf_filename = f"pronostici_definitivo_{oggi}.pdf"

print(f"🔄 Avvio motore quantitativo definitivo per il: {oggi}...")

# ==========================================
# 📐 1. FUNZIONE DI CALCOLO POISSON ESTESA
# ==========================================
def poisson_probability(lmbda, k):
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def calculate_match_probabilities(home_xg, away_xg, home_corners_exp, away_corners_exp, home_cards_exp, away_cards_exp, home_shots_exp, away_shots_exp):
    home_win, draw, away_win = 0, 0, 0
    over_15, over_25, over_35 = 0, 0, 0
    btts = 0
    
    for h in range(6):
        for a in range(6):
            p = poisson_probability(home_xg, h) * poisson_probability(away_xg, a)
            if h > a: home_win += p
            elif h == a: draw += p
            else: away_win += p
            
            total_goals = h + a
            if total_goals > 1.5: over_15 += p
            if total_goals > 2.5: over_25 += p
            if total_goals > 3.5: over_35 += p
            if h > 0 and a > 0: btts += p

    total_corners_exp = home_corners_exp + away_corners_exp
    p_over_tot_corners = sum(poisson_probability(total_corners_exp, c) for c in range(10)) 
    
    total_cards_exp = home_cards_exp + away_cards_exp
    p_over_cards = sum(poisson_probability(total_cards_exp, c) for c in range(5)) 

    total_shots_exp = home_shots_exp + away_shots_exp
    p_over_shots = sum(poisson_probability(total_shots_exp, s) for s in range(24)) 

    return {
        "p_1": home_win, "p_x": draw, "p_2": away_win,
        "p_1x": home_win + draw, "p_x2": away_win + draw,
        "p_over15": over_15, "p_under15": 1 - over_15,
        "p_over25": over_25, "p_under25": 1 - over_25,
        "p_over35": over_35, "p_under35": 1 - over_35,
        "p_goal": btts, "p_nogoal": 1 - btts,
        "p_over_corners": p_over_tot_corners,
        "p_over_cards": p_over_cards,
        "p_over_shots": p_over_shots
    }

# ==========================================
# 📈 2. FUNZIONE DI SCELTA MERCATO & FUZZY MATCHING
# ==========================================
def find_odds_for_match(casa, ospite, odds_cache):
    match_key = f"{casa.lower()}_vs_{ospite.lower()}"
    if match_key in odds_cache:
        return odds_cache[match_key]
    
    all_keys = list(odds_cache.keys())
    close_matches = get_close_matches(match_key, all_keys, n=1, cutoff=0.4)
    if close_matches:
        return odds_cache[close_matches[0]]
    
    return {
        "1": 2.10, "x": 3.30, "2": 3.50, "1x": 1.32, "x2": 1.55,
        "over15": 1.35, "under15": 3.10, "over25": 2.05, "under25": 1.75, "over35": 3.60,
        "goal": 1.80, "corners": 1.85, "cards": 1.90, "shots": 1.85
    }

def evaluate_best_bet(probs, match_odds_dict, bankroll=1000.0):
    markets = [
        {"name": "Segno 1", "prob": probs["p_1"], "odds": match_odds_dict.get("1", 0)},
        {"name": "Segno X", "prob": probs["p_x"], "odds": match_odds_dict.get("x", 0)},
        {"name": "Segno 2", "prob": probs["p_2"], "odds": match_odds_dict.get("2", 0)},
        {"name": "Doppia 1X", "prob": probs["p_1x"], "odds": match_odds_dict.get("1x", 0)},
        {"name": "Doppia X2", "prob": probs["p_x2"], "odds": match_odds_dict.get("x2", 0)},
        {"name": "Over 1.5", "prob": probs["p_over15"], "odds": match_odds_dict.get("over15", 0)},
        {"name": "Under 1.5", "prob": probs["p_under15"], "odds": match_odds_dict.get("under15", 0)},
        {"name": "Over 2.5", "prob": probs["p_over25"], "odds": match_odds_dict.get("over25", 0)},
        {"name": "Under 2.5", "prob": probs["p_under25"], "odds": match_odds_dict.get("under25", 0)},
        {"name": "Over 3.5", "prob": probs["p_over35"], "odds": match_odds_dict.get("over35", 0)},
        {"name": "Goal (BTTS)", "prob": probs["p_goal"], "odds": match_odds_dict.get("goal", 0)},
        {"name": "Over 9.5 Corner", "prob": probs["p_over_corners"], "odds": match_odds_dict.get("corners", 0)},
        {"name": "Over 4.5 Cart.", "prob": probs["p_over_cards"], "odds": match_odds_dict.get("cards", 0)},
        {"name": "Over 23.5 Tiri", "prob": probs["p_over_shots"], "odds": match_odds_dict.get("shots", 0)}
    ]
    
    best_market = None
    max_edge = -999
    
    for m in markets:
        odds = m["odds"]
        if not odds or odds < 1.30: # Filtro quote < 1.30
            continue
            
        implied_prob = 1 / odds
        edge = m["prob"] - implied_prob
        
        if edge > max_edge:
            max_edge = edge
            best_market = {
                "bet_type": m["name"],
                "model_prob": round(m["prob"] * 100, 1),
                "odds": odds,
                "edge": round(edge * 100, 2),
                "is_value": edge > 0
            }
            
    if not best_market:
        return {"bet_type": "Nessuna (Filtro <1.30)", "model_prob": 0, "odds": 0, "edge": 0, "is_value": False, "stake": 0}

    stake = 0.0
    if best_market["is_value"]:
        b = best_market["odds"] - 1
        p = best_market["model_prob"] / 100
        q = 1 - p
        kelly_fraction = (b * p - q) / b
        if kelly_fraction > 0:
            stake = round(bankroll * kelly_fraction * 0.25, 2)
            
    best_market["stake"] = stake
    return best_market

try:
    # ==========================================
    # 📊 3. VERIFICA RISULTATI IERI (REPORT ✅ / ❌)
    # ==========================================
    print(f"🔄 Recupero risultati delle partite di ieri ({ieri})...")
    url_ieri = f"https://api.football-data.org/v4/matches?date={ieri}"
    res_ieri = requests.get(url_ieri, headers=headers_fd)
    time.sleep(2)
    
    report_ieri_lines = []
    if res_ieri.status_code == 200:
        matches_ieri = res_ieri.json().get('matches', [])
        for mi in matches_ieri:
            if mi.get('status') == 'FINISHED':
                c_team = mi.get('homeTeam', {}).get('shortName', 'Casa')
                o_team = mi.get('awayTeam', {}).get('shortName', 'Ospite')
                score = mi.get('score', {}).get('fullTime', {})
                hg = score.get('home', 0)
                ag = score.get('away', 0)
                
                # Semplificazione di verifica esito standard (es. Over 2.5 o Segno 1)
                tot_g = hg + ag
                esito_reale = "Over 2.5" if tot_g > 2.5 else "Under 2.5"
                if hg > ag: res_1x2 = "Segno 1"
                elif hg == ag: res_1x2 = "Segno X"
                else: res_1x2 = "Segno 2"
                
                # Valutiamo l'esito di un mercato di riferimento (es. Segno 1 o Over 2.5)
                # Scegliamo di verificare il Segno 1 come benchmark di riscontro
                presunta_giocata = "Segno 1"
                vinta = (hg > ag) if presunta_giocata == "Segno 1" else (tot_g > 2.5)
                icona = "✅" if vinta else "❌"
                
                report_ieri_lines.append(f"• {c_team} vs {o_team} ({hg}-{ag}) ➔ {presunta_giocata} {icona}")

    # ==========================================
    # 📥 4. RECUPERO QUOTE & PARTITE ODIERNE
    # ==========================================
    print("🔄 Connessione a Odss API per scaricare le quote...")
    res_odss = requests.get(ODSS_URL, headers=headers_odss)
    odds_cache = {}
    if res_odss.status_code == 200:
        odss_data = res_odss.json()
        events_list = odss_data.get('data', odss_data.get('matches', odss_data if isinstance(odss_data, list) else []))
        for ev in events_list:
            home_name = ev.get('home_team', ev.get('home', '')).lower()
            away_name = ev.get('away_team', ev.get('away', '')).lower()
            key_match = f"{home_name}_vs_{away_name}"
            
            odds_cache[key_match] = {
                "1": ev.get('odds_1', ev.get('home_odds', 2.0)),
                "x": ev.get('odds_x', ev.get('draw_odds', 3.2)),
                "2": ev.get('odds_2', ev.get('away_odds', 3.0)),
                "1x": ev.get('odds_1x', 1.35),
                "x2": ev.get('odds_x2', 1.50),
                "over15": ev.get('over_15', 1.35),
                "under15": ev.get('under_15', 3.0),
                "over25": ev.get('over_25', 1.9),
                "under25": ev.get('under_25', 1.8),
                "over35": ev.get('over_35', 3.5),
                "goal": ev.get('btts_yes', 1.85),
                "corners": ev.get('over_corners', 1.85),
                "cards": ev.get('over_cards', 1.90),
                "shots": ev.get('over_shots', 1.85)
            }

    url_oggi = f"https://api.football-data.org/v4/matches?date={oggi}"
    res_fd = requests.get(url_oggi, headers=headers_fd)
    time.sleep(2)
    
    raw_matches = res_fd.json().get('matches', []) if res_fd.status_code == 200 else []
    print(f"✅ Trovate {len(raw_matches)} partite nel palinsesto odierno.")

    comp_ids = set(m.get('competition', {}).get('id') for m in raw_matches if m.get('competition', {}).get('id'))
    classifiche_cache = {}
    
    for comp_id in comp_ids:
        url_standings = f"https://api.football-data.org/v4/competitions/{comp_id}/standings"
        res_st = requests.get(url_standings, headers=headers_fd)
        time.sleep(2)
        if res_st.status_code == 200:
            standings_list = res_st.json().get('standings', [])
            table = [s.get('table', []) for s in standings_list if s.get('type') == 'TOTAL'] if 'standings' in res_st.json() else []
            table = table[0] if table else []
            classifiche_cache[comp_id] = {item['team']['name']: item for item in table if 'team' in item}
        else:
            classifiche_cache[comp_id] = {}

    partite_analizzate = []

    for m in raw_matches:
        comp_id = m.get('competition', {}).get('id')
        status_match = m.get('status', 'TIMED')
        home_team = m.get('homeTeam', {})
        away_team = m.get('awayTeam', {})
        
        casa = home_team.get('shortName') or home_team.get('name', 'Casa')
        ospite = away_team.get('shortName') or away_team.get('name', 'Ospite')
        
        standings_map = classifiche_cache.get(comp_id, {})
        dati_casa = standings_map.get(home_team.get('name'), {"goalsFor": 15, "goalsAgainst": 10})
        dati_ospite = standings_map.get(away_team.get('name'), {"goalsFor": 12, "goalsAgainst": 12})
        
        home_xg = max(0.8, (dati_casa.get('goalsFor', 15) + dati_ospite.get('goalsAgainst', 12)) / 20)
        away_xg = max(0.6, (dati_ospite.get('goalsFor', 12) + dati_casa.get('goalsAgainst', 10)) / 22)
        
        home_corners, away_corners = 5.2, 4.3
        home_cards, away_cards = 2.1, 2.4
        home_shots, away_shots = 13.5, 11.0

        probs = calculate_match_probabilities(home_xg, away_xg, home_corners, away_corners, home_cards, away_cards, home_shots, away_shots)
        match_odds = find_odds_for_match(casa, ospite, odds_cache)
        best_bet = evaluate_best_bet(probs, match_odds)
        is_rinviata = status_match in ['POSTPONED', 'SUSPENDED', 'CANCELLED']

        partite_analizzate.append({
            "casa": casa, "ospite": ospite,
            "status": status_match, "is_rinviata": is_rinviata,
            "best_bet": best_bet
        })

    partite_analizzate.sort(key=lambda x: -x['best_bet']['edge'])

    # ==========================================
    # 📄 5. GENERAZIONE REPORT PDF
    # ==========================================
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor('#1A365D'), spaceAfter=4, alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#4A5568'), spaceAfter=12, alignment=1)
    cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#2D3748'))
    header_cell_style = ParagraphStyle('HeaderCellStyle', parent=styles['Normal'], fontSize=8, textColor=colors.white, fontName='Helvetica-Bold')

    elements.append(Paragraph(f"<b>REPORT QUANTITATIVO DEFINITIVO</b>", title_style))
    elements.append(Paragraph(f"Data: {oggi} | API Integrate (Football-Data + Odss API + Fuzzy Matching)", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2B6CB0'), spaceAfter=12))

    table_data = [[
        Paragraph("<b>Match</b>", header_cell_style),
        Paragraph("<b>Modello %</b>", header_cell_style),
        Paragraph("<b>Quota Reale</b>", header_cell_style),
        Paragraph("<b>Edge %</b>", header_cell_style),
        Paragraph("<b>Value?</b>", header_cell_style),
        Paragraph("<b>Pronostico Consigliato</b>", header_cell_style)
    ]]

    for m in partite_analizzate[:15]:
        bb = m['best_bet']
        if m['is_rinviata']:
            match_str = f"{m['casa']} - {m['ospite']} (Rinviata)"
            p_str, q_str, edge_str, val_str, pron_str = "-", "-", "-", "-", "⏳ Rinviata"
        else:
            match_str = f"{m['casa']} vs {m['ospite']}"
            p_str = f"{bb['model_prob']}%"
            q_str = str(bb['odds'])
            edge_str = f"+{bb['edge']}%" if bb['edge'] > 0 else f"{bb['edge']}%"
            val_str = "🟢 SI" if bb['is_value'] else "🔴 NO"
            pron_str = f"<b>{bb['bet_type']}</b>"

        table_data.append([
            Paragraph(match_str, cell_style),
            Paragraph(p_str, cell_style),
            Paragraph(q_str, cell_style),
            Paragraph(edge_str, cell_style),
            Paragraph(val_str, cell_style),
            Paragraph(pron_str, cell_style)
        ])

    t = Table(table_data, colWidths=[150, 60, 60, 55, 50, 187])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0'))
    ]))

    elements.append(t)
    doc.build(elements)
    print(f"✅ PDF definitivo generato: {pdf_filename}")

    # ==========================================
    # 📤 6. INVIO TELEGRAM CON REPORT IERI
    # ==========================================
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    
    # Costruiamo il testo del report di ieri da inserire nella caption
    caption_text = f"🧠 *Report Quantitativo Definitivo del {oggi}* 🚀\n\n"
    if report_ieri_lines:
        caption_text += f"📊 *Bilancio Partite di Ieri ({ieri}):*\n" + "\n".join(report_ieri_lines[:8])
    else:
        caption_text += f"📊 *Bilancio Ieri ({ieri}):* Nessun dato completato disponibile."

    with open(pdf_filename, 'rb') as pdf_file:
        files = {'document': pdf_file}
        payload = {
            "chat_id": CHAT_ID,
            "caption": caption_text
        }
        res_tg = requests.post(telegram_url, data=payload, files=files)
        
    if res_tg.status_code == 200:
        print("✅ Report e bilancio inviati con successo su Telegram!")
    else:
        print(f"⚠️ Errore Telegram: {res_tg.text}")

except Exception as e:
    print(f"❌ Errore generale nell'esecuzione: {e}")
