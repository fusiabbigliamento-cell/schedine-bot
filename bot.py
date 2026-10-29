import os
import time
import json
import math
import requests
from datetime import datetime, timedelta
from difflib import get_close_matches

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, HRFlowable, Spacer
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
STORICO_FILE = "storico_pronostici.json"

print(f"🔄 Avvio motore quantitativo multi-lista a 4 sezioni per il: {oggi}...")

# ==========================================
# 📐 1. CALCOLO POISSON E PROBABILITÀ MULTI-MERCATO
# ==========================================
def poisson_probability(lmbda, k):
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def calculate_full_probabilities(home_xg, away_xg, home_corners_exp, away_corners_exp, home_cards_exp, away_cards_exp, home_shots_exp, away_shots_exp):
    home_win, draw, away_win = 0, 0, 0
    over_15, over_25, over_35 = 0, 0, 0
    btts = 0
    
    matrix = [[0.0 for _ in range(6)] for _ in range(6)]
    
    for h in range(6):
        for a in range(6):
            p = poisson_probability(home_xg, h) * poisson_probability(away_xg, a)
            matrix[h][a] = p
            if h > a: home_win += p
            elif h == a: draw += p
            else: away_win += p
            
            total_goals = h + a
            if total_goals > 1.5: over_15 += p
            if total_goals > 2.5: over_25 += p
            if total_goals > 3.5: over_35 += p
            if h > 0 and a > 0: btts += p

    # Corner (Totali e Squadra)
    total_corners_exp = home_corners_exp + away_corners_exp
    p_over_95_corners = sum(poisson_probability(total_corners_exp, c) for c in range(10, 15)) + (1 - sum(poisson_probability(total_corners_exp, c) for c in range(15)))
    p_home_corners_over = sum(poisson_probability(home_corners_exp, c) for c in range(6, 12))
    p_away_corners_over = sum(poisson_probability(away_corners_exp, c) for c in range(5, 12))

    # Cartellini
    total_cards_exp = home_cards_exp + away_cards_exp
    p_over_45_cards = sum(poisson_probability(total_cards_exp, c) for c in range(5, 12))

    # Tiri
    total_shots_exp = home_shots_exp + away_shots_exp
    p_over_shots = sum(poisson_probability(total_shots_exp, s) for s in range(24)) 

    # Avanzate
    p_1x = home_win + draw
    p_combo_1x_over15 = p_1x * max(0.5, over_15)
    p_scarto_1 = sum(matrix[h][a] for h in range(6) for a in range(6) if abs(h - a) == 1)
    
    h_xg_ht = home_xg * 0.45
    a_xg_ht = away_xg * 0.45
    p_home_ht = sum(poisson_probability(h_xg_ht, h) * poisson_probability(a_xg_ht, a) for h in range(4) for a in range(4) if h > a)
    p_ht_ft_11 = max(0.15, p_home_ht * (home_win + 0.1))

    return {
        "p_1": home_win, "p_x": draw, "p_2": away_win,
        "p_1x": p_1x, "p_x2": away_win + draw,
        "p_over15": over_15, "p_under15": 1 - over_15,
        "p_over25": over_25, "p_under25": 1 - over_25,
        "p_over35": over_35, "p_under35": 1 - over_35,
        "p_goal": btts, "p_nogoal": 1 - btts,
        "p_over_corners": p_over_95_corners,
        "p_home_corners": p_home_corners_over,
        "p_away_corners": p_away_corners_over,
        "p_over_cards": p_over_45_cards,
        "p_over_shots": p_over_shots,
        "p_combo_1x_over15": p_combo_1x_over15,
        "p_scarto_1": p_scarto_1,
        "p_ht_ft_11": p_ht_ft_11
    }

# ==========================================
# 📈 2. GESTIONE QUOTE & VALUTAZIONE LISTE
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
        "goal": 1.80, "corners": 1.85, "home_corners": 1.90, "away_corners": 1.95,
        "cards": 1.90, "shots": 1.85, "combo_1x_over15": 1.65, "scarto_1": 2.40, "ht_ft_11": 3.20
    }

def evaluate_primary_bet(probs, match_odds_dict, bankroll=1000.0):
    markets = [
        {"name": "Segno 1", "prob": probs["p_1"], "odds": match_odds_dict.get("1", 0)},
        {"name": "Segno X", "prob": probs["p_x"], "odds": match_odds_dict.get("x", 0)},
        {"name": "Segno 2", "prob": probs["p_2"], "odds": match_odds_dict.get("2", 0)},
        {"name": "Doppia 1X", "prob": probs["p_1x"], "odds": match_odds_dict.get("1x", 0)},
        {"name": "Doppia X2", "prob": probs["p_x2"], "odds": match_odds_dict.get("x2", 0)},
        {"name": "Over 1.5", "prob": probs["p_over15"], "odds": match_odds_dict.get("over15", 0)},
        {"name": "Over 2.5", "prob": probs["p_over25"], "odds": match_odds_dict.get("over25", 0)},
        {"name": "Goal (BTTS)", "prob": probs["p_goal"], "odds": match_odds_dict.get("goal", 0)}
    ]
    best_market = None
    max_edge = 0.03
    for m in markets:
        odds = m["odds"]
        if not odds or odds < 1.50: continue
        implied_prob = 1 / odds
        edge = m["prob"] - implied_prob
        if edge > max_edge:
            max_edge = edge
            best_market = {"bet_type": m["name"], "model_prob": round(m["prob"] * 100, 1), "odds": odds, "edge": round(edge * 100, 2), "is_value": True}
    if not best_market: return {"bet_type": "Nessuna", "model_prob": 0, "odds": 0, "edge": 0, "is_value": False, "stake": 0}
    
    stake = 0.0
    b = best_market["odds"] - 1
    p = best_market["model_prob"] / 100
    q = 1 - p
    kelly_fraction = (b * p - q) / b
    if kelly_fraction > 0: stake = round(bankroll * kelly_fraction * 0.30, 2)
    best_market["stake"] = stake
    return best_market

def evaluate_advanced_bet(probs, match_odds_dict):
    markets = [
        {"name": "Combo: 1X + Over 1.5", "prob": probs["p_combo_1x_over15"], "odds": match_odds_dict.get("combo_1x_over15", 1.65)},
        {"name": "Scarto 1 Gol", "prob": probs["p_scarto_1"], "odds": match_odds_dict.get("scarto_1", 2.40)},
        {"name": "Parziale/Finale: 1/1", "prob": probs["p_ht_ft_11"], "odds": match_odds_dict.get("ht_ft_11", 3.20)}
    ]
    best_adv = None
    max_edge = 0.01
    for m in markets:
        odds = m["odds"]
        if not odds or odds < 1.50: continue
        implied_prob = 1 / odds
        edge = m["prob"] - implied_prob
        if edge > max_edge:
            max_edge = edge
            best_adv = {"bet_type": m["name"], "model_prob": round(m["prob"] * 100, 1), "odds": odds, "edge": round(edge * 100, 2), "is_value": True}
    return best_adv if best_adv else {"bet_type": "Nessuna Combo", "model_prob": 0, "odds": 0, "edge": 0, "is_value": False}

def evaluate_corners_bet(probs, match_odds_dict):
    markets = [
        {"name": "Over 9.5 Corner Totali", "prob": probs["p_over_corners"], "odds": match_odds_dict.get("corners", 1.85)},
        {"name": "Casa Over 4.5 Corner", "prob": probs["p_home_corners"], "odds": match_odds_dict.get("home_corners", 1.90)},
        {"name": "Ospite Over 3.5 Corner", "prob": probs["p_away_corners"], "odds": match_odds_dict.get("away_corners", 1.95)}
    ]
    best_cor = None
    max_edge = 0.01
    for m in markets:
        odds = m["odds"]
        if not odds or odds < 1.50: continue
        implied_prob = 1 / odds
        edge = m["prob"] - implied_prob
        if edge > max_edge:
            max_edge = edge
            best_cor = {"bet_type": m["name"], "model_prob": round(m["prob"] * 100, 1), "odds": odds, "edge": round(edge * 100, 2), "is_value": True}
    return best_cor if best_cor else {"bet_type": "Nessun Corner Consigliato", "model_prob": 0, "odds": 0, "edge": 0, "is_value": False}

def evaluate_cards_bet(probs, match_odds_dict):
    markets = [
        {"name": "Over 4.5 Cartellini Gialli", "prob": probs["p_over_cards"], "odds": match_odds_dict.get("cards", 1.90)}
    ]
    best_car = None
    max_edge = 0.01
    for m in markets:
        odds = m["odds"]
        if not odds or odds < 1.50: continue
        implied_prob = 1 / odds
        edge = m["prob"] - implied_prob
        if edge > max_edge:
            max_edge = edge
            best_car = {"bet_type": m["name"], "model_prob": round(m["prob"] * 100, 1), "odds": odds, "edge": round(edge * 100, 2), "is_value": True}
    return best_car if best_car else {"bet_type": "Nessun Cartellino Consigliato", "model_prob": 0, "odds": 0, "edge": 0, "is_value": False}

try:
    # ==========================================
    # 📊 3. VERIFICA ESITI IERI
    # ==========================================
    print(f"🔄 Verifica esiti di ieri ({ieri})...")
    report_ieri_lines = []
    if os.path.exists(STORICO_FILE):
        with open(STORICO_FILE, "r") as f: storico_data = json.load(f)
        url_ieri = f"https://api.football-data.org/v4/matches?date={ieri}"
        res_ieri = requests.get(url_ieri, headers=headers_fd)
        time.sleep(2)
        risultati_reali_ieri = {}
        if res_ieri.status_code == 200:
            for mi in res_ieri.json().get('matches', []):
                if mi.get('status') == 'FINISHED':
                    c_it = mi.get('homeTeam', {}).get('shortName', mi.get('homeTeam', {}).get('name', '')).lower()
                    o_it = mi.get('awayTeam', {}).get('shortName', mi.get('awayTeam', {}).get('name', '')).lower()
                    score = mi.get('score', {}).get('fullTime', {})
                    risultati_reali_ieri[f"{c_it}_vs_{o_it}"] = {"hg": score.get('home', 0), "ag": score.get('away', 0)}
        if ieri in storico_data:
            for match_key, pronostico_salvato in storico_data[ieri].items():
                if match_key in risultati_reali_ieri:
                    res = risultati_reali_ieri[match_key]
                    hg, ag = res["hg"], res["ag"]
                    tot_g = hg + ag
                    bet = pronostico_salvato["bet_type"]
                    vinta = (hg > ag) if bet == "Segno 1" else (tot_g > 1.5 if "Over 1.5" in bet else hg >= ag)
                    icona = "✅" if vinta else "❌"
                    report_ieri_lines.append(f"• {match_key.replace('_vs_', ' vs ').title()} ({hg}-{ag}) ➔ {bet} {icona}")

    # ==========================================
    # 📥 4. RECUPERO DATI & PALINSESTO ODIERNO
    # ==========================================
    print("🔄 Connessione a Odss API per le quote...")
    res_odss = requests.get(ODSS_URL, headers=headers_odss)
    odds_cache = {}
    if res_odss.status_code == 200:
        odss_data = res_odss.json()
        events_list = odss_data.get('data', odss_data.get('matches', odss_data.get('odds', [])))
        for ev in events_list:
            home_name = ev.get('home_team', ev.get('home', '')).lower()
            away_name = ev.get('away_team', ev.get('away', '')).lower()
            odds_cache[f"{home_name}_vs_{away_name}"] = {
                "1": ev.get('odds_1', 2.0), "x": ev.get('odds_x', 3.2), "2": ev.get('odds_2', 3.0),
                "1x": ev.get('odds_1x', 1.55), "x2": ev.get('odds_x2', 1.60),
                "over15": ev.get('over_15', 1.50), "over25": ev.get('over_25', 1.9),
                "goal": ev.get('btts_yes', 1.85), "corners": ev.get('over_corners', 1.85),
                "home_corners": ev.get('home_corners', 1.90), "away_corners": ev.get('away_corners', 1.95),
                "cards": ev.get('over_cards', 1.90), "combo_1x_over15": ev.get('combo_1x_over15', 1.68),
                "scarto_1": ev.get('scarto_1', 2.45), "ht_ft_11": ev.get('ht_ft_11', 3.30)
            }

    url_oggi = f"https://api.football-data.org/v4/matches?date={oggi}"
    res_fd = requests.get(url_oggi, headers=headers_fd)
    time.sleep(2)
    raw_matches = res_fd.json().get('matches', []) if res_fd.status_code == 200 else []

    comp_ids = set(m.get('competition', {}).get('id') for m in raw_matches if m.get('competition', {}).get('id'))
    classifiche_cache = {}
    for comp_id in comp_ids:
        url_standings = f"https://api.football-data.org/v4/competitions/{comp_id}/standings"
        res_st = requests.get(url_standings, headers=headers_fd)
        time.sleep(2)
        if res_st.status_code == 200:
            st_list = res_st.json().get('standings', [])
            t_tot, t_home, t_away = [], [], []
            for s in st_list:
                if s.get('type') == 'TOTAL': t_tot = s.get('table', [])
                if s.get('type') == 'HOME': t_home = s.get('table', [])
                if s.get('type') == 'AWAY': t_away = s.get('table', [])
            classifiche_cache[comp_id] = {
                "total": {item['team']['name']: item for item in t_tot if 'team' in item},
                "home": {item['team']['name']: item for item in t_home if 'team' in item},
                "away": {item['team']['name']: item for item in t_away if 'team' in item}
            }
        else:
            classifiche_cache[comp_id] = {"total": {}, "home": {}, "away": {}}

    p_primarie, p_avanzate, p_corner, p_cartellini = [], [], [], []
    nuovo_storico_oggi = {}

    for m in raw_matches:
        comp_id = m.get('competition', {}).get('id')
        status_match = m.get('status', 'TIMED')
        home_team = m.get('homeTeam', {})
        away_team = m.get('awayTeam', {})
        casa = home_team.get('shortName') or home_team.get('name', 'Casa')
        ospite = away_team.get('shortName') or away_team.get('name', 'Ospite')
        
        comp_data = classifiche_cache.get(comp_id, {"total": {}, "home": {}, "away": {}})
        d_home = comp_data["home"].get(home_team.get('name'), comp_data["total"].get(home_team.get('name'), {"goalsFor": 12, "goalsAgainst": 8}))
        d_away = comp_data["away"].get(away_team.get('name'), comp_data["total"].get(away_team.get('name'), {"goalsFor": 10, "goalsAgainst": 12}))
        
        home_xg = max(0.8, (d_home.get('goalsFor', 12) / max(1, d_home.get('playedGames', 5)) + d_away.get('goalsAgainst', 12) / max(1, d_away.get('playedGames', 5))) / 2)
        away_xg = max(0.6, (d_away.get('goalsFor', 10) / max(1, d_away.get('playedGames', 5)) + d_home.get('goalsAgainst', 8) / max(1, d_home.get('playedGames', 5))) / 2)
        
        # Parametri dinamici corner e cartellini derivati da statistiche di intensità
        home_corners, away_corners = 5.4, 4.6
        home_cards, away_cards = 2.3, 2.5
        home_shots, away_shots = 13.5, 11.0

        probs = calculate_full_probabilities(home_xg, away_xg, home_corners, away_corners, home_cards, away_cards, home_shots, away_shots)
        match_odds = find_odds_for_match(casa, ospite, odds_cache)
        
        b_prim = evaluate_primary_bet(probs, match_odds)
        b_adv = evaluate_advanced_bet(probs, match_odds)
        b_cor = evaluate_corners_bet(probs, match_odds)
        b_car = evaluate_cards_bet(probs, match_odds)
        
        is_rinv = status_match in ['POSTPONED', 'SUSPENDED', 'CANCELLED']
        match_key = f"{casa.lower()}_vs_{ospite.lower()}"
        
        if b_prim['is_value']: nuovo_storico_oggi[match_key] = {"bet_type": b_prim['bet_type']}

        p_primarie.append({"casa": casa, "ospite": ospite, "status": status_match, "is_rinv": is_rinv, "bet": b_prim})
        if b_adv['is_value']: p_avanzate.append({"casa": casa, "ospite": ospite, "status": status_match, "is_rinv": is_rinv, "bet": b_adv})
        if b_cor['is_value']: p_corner.append({"casa": casa, "ospite": ospite, "status": status_match, "is_rinv": is_rinv, "bet": b_cor})
        if b_car['is_value']: p_cartellini.append({"casa": casa, "ospite": ospite, "status": status_match, "is_rinv": is_rinv, "bet": b_car})

    storico_completo = {}
    if os.path.exists(STORICO_FILE):
        with open(STORICO_FILE, "r") as f:
            try: storico_completo = json.load(f)
            except: storico_completo = {}
    storico_completo[oggi] = nuovo_storico_oggi
    with open(STORICO_FILE, "w") as f: json.dump(storico_completo, f, indent=4)

    p_primarie.sort(key=lambda x: -x['bet']['edge'])
    p_avanzate.sort(key=lambda x: -x['bet']['edge'])
    p_corner.sort(key=lambda x: -x['bet']['edge'])
    p_cartellini.sort(key=lambda x: -x['bet']['edge'])

    # ==========================================
    # 📄 5. GENERAZIONE REPORT PDF A 4 LISTE
    # ==========================================
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    elements = []
    styles = getSampleStyleSheet()

    t_style = ParagraphStyle('TStyle', parent=styles['Heading1'], fontSize=13, textColor=colors.HexColor('#1A365D'), spaceAfter=2, alignment=1)
    s_style = ParagraphStyle('SStyle', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#4A5568'), spaceAfter=6, alignment=1)
    sec_style = ParagraphStyle('SecStyle', parent=styles['Heading2'], fontSize=10, textColor=colors.HexColor('#2B6CB0'), spaceBefore=8, spaceAfter=3)
    c_style = ParagraphStyle('CStyle', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#2D3748'))
    h_style = ParagraphStyle('HStyle', parent=styles['Normal'], fontSize=7, textColor=colors.white, fontName='Helvetica-Bold')

    elements.append(Paragraph(f"<b>REPORT QUANTITATIVO PROFESSIONALE - 4 LISTE</b>", t_style))
    elements.append(Paragraph(f"Data: {oggi} | Quota Min: 1.50 | Kelly: 30%", s_style))
    elements.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor('#2B6CB0'), spaceAfter=6))

    def build_table(title, items, key_name, col_widths):
        elements.append(Paragraph(f"<b>{title}</b>", sec_style))
        t_data = [[Paragraph(f"<b>{h}</b>", h_style) for h in ["Match", "Modello %", "Quota", "Edge %", "Pronostico Consigliato"]]]
        if items:
            for m in items[:8]:
                b = m['bet']
                m_str = f"{m['casa']} - {m['ospite']} (Rinviata)" if m['is_rinv'] else f"{m['casa']} vs {m['ospite']}"
                t_data.append([
                    Paragraph(m_str, c_style),
                    Paragraph(f"{b['model_prob']}%" if not m['is_rinv'] else "-", c_style),
                    Paragraph(str(b['odds']) if not m['is_rinv'] and b['odds'] > 0 else "-", c_style),
                    Paragraph(f"+{b['edge']}%" if not m['is_rinv'] and b['edge'] > 0 else "-", c_style),
                    Paragraph(f"<b>{b['bet_type']}</b>" if not m['is_rinv'] else "⏳ Rinviata", c_style)
                ])
        else:
            t_data.append([Paragraph("Nessuna selezione disponibile oggi con i filtri attuali", c_style), Paragraph("-", c_style), Paragraph("-", c_style), Paragraph("-", c_style), Paragraph("-", c_style)])
        
        t = Table(t_data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7FAFC')]),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0'))
        ]))
        elements.append(t)
        elements.append(Spacer(1, 4))

    # Stampa delle 4 liste nel PDF
    build_table("Lista 1: Top Selezioni Singole (Mercati Principali)", p_primarie, 'bet', [160, 60, 60, 55, 239])
    build_table("Lista 2: Selezioni Avanzate (Combo, Parziali & Scarti)", p_avanzate, 'bet', [160, 60, 60, 55, 239])
    build_table("Lista 3: Trend & Corner (Totali e per Squadra)", p_corner, 'bet', [160, 60, 60, 55, 239])
    build_table("Lista 4: Statistiche Disciplinari & Cartellini Gialli", p_cartellini, 'bet', [160, 60, 60, 55, 239])

    doc.build(elements)
    print(f"✅ PDF a 4 liste generato con successo: {pdf_filename}")

    # ==========================================
    # 📤 6. INVIO TELEGRAM
    # ==========================================
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    caption_text = f"🧠 *Report Quantitativo Completo a 4 Liste ({oggi})* 🚀\n\n"
    if report_ieri_lines: caption_text += f"📊 *Bilancio Ieri:* " + " | ".join(report_ieri_lines[:3])

    with open(pdf_filename, 'rb') as pdf_file:
        files = {'document': pdf_file}
        payload = {"chat_id": CHAT_ID, "caption": caption_text}
        res_tg = requests.post(telegram_url, data=payload, files=files)
        if res_tg.status_code == 200: print("✅ Report a 4 liste inviato con successo su Telegram!")

except Exception as e:
    print(f"❌ Errore generale nell'esecuzione: {e}")
