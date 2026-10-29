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

print(f"🔄 Avvio motore quantitativo avanzato a due liste per il: {oggi}...")

# ==========================================
# 📐 1. CALCOLO POISSON E PROBABILITÀ AVANZATE
# ==========================================
def poisson_probability(lmbda, k):
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def calculate_advanced_match_probabilities(home_xg, away_xg, home_corners_exp, away_corners_exp, home_cards_exp, away_cards_exp, home_shots_exp, away_shots_exp):
    home_win, draw, away_win = 0, 0, 0
    over_15, over_25, over_35 = 0, 0, 0
    btts = 0
    
    # Matrice esatta dei risultati 0-5 per calcoli complessi
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

    # Statistiche di contorno
    total_corners_exp = home_corners_exp + away_corners_exp
    p_over_tot_corners = sum(poisson_probability(total_corners_exp, c) for c in range(10)) 
    
    total_cards_exp = home_cards_exp + away_cards_exp
    p_over_cards = sum(poisson_probability(total_cards_exp, c) for c in range(5)) 

    total_shots_exp = home_shots_exp + away_shots_exp
    p_over_shots = sum(poisson_probability(total_shots_exp, s) for s in range(24)) 

    # --- CALCOLI AVANZATI PER LA SECONDA LISTA ---
    # 1. Combo: 1X + Over 1.5 (Approssimazione probabilistica indipendente intersecata)
    p_1x = home_win + draw
    p_combo_1x_over15 = p_1x * over_15

    # 2. Gol di scarto (Vittoria con esattamente 1 gol di scarto)
    p_scarto_1 = sum(matrix[h][a] for h in range(6) for a in range(6) if abs(h - a) == 1 and h != a)

    # 3. Parziale / Finale approssimato (1/1: Casa in vantaggio a fine 1° tempo e a fine partita)
    # Stima del primo tempo dimezzando i lambda
    h_xg_ht = home_xg * 0.45
    a_xg_ht = away_xg * 0.45
    p_home_ht = sum(poisson_probability(h_xg_ht, h) * poisson_probability(a_xg_ht, a) for h in range(4) for a in range(4) if h > a)
    p_ht_ft_11 = p_home_ht * (home_win * 1.1 if home_win < 0.9 else 0.9) # Correzione ponderata

    return {
        "p_1": home_win, "p_x": draw, "p_2": away_win,
        "p_1x": p_1x, "p_x2": away_win + draw,
        "p_over15": over_15, "p_under15": 1 - over_15,
        "p_over25": over_25, "p_under25": 1 - over_25,
        "p_over35": over_35, "p_under35": 1 - over_35,
        "p_goal": btts, "p_nogoal": 1 - btts,
        "p_over_corners": p_over_tot_corners,
        "p_over_cards": p_over_cards,
        "p_over_shots": p_over_shots,
        # Metriche Avanzate Seconda Lista
        "p_combo_1x_over15": p_combo_1x_over15,
        "p_scarto_1": p_scarto_1,
        "p_ht_ft_11": p_ht_ft_11
    }

# ==========================================
# 📈 2. GESTIONE QUOTE & SELEZIONE DOPPIA LISTA
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
        "goal": 1.80, "corners": 1.85, "cards": 1.90, "shots": 1.85,
        "combo_1x_over15": 1.65, "scarto_1": 2.40, "ht_ft_11": 3.20
    }

def evaluate_primary_bet(probs, match_odds_dict, bankroll=1000.0):
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
    max_edge = 0.03  # Filtro Alta Qualità (Edge > 3%)
    
    for m in markets:
        odds = m["odds"]
        if not odds or odds < 1.50:  # Quota minima 1.50
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
                "is_value": True
            }
            
    if not best_market:
        return {"bet_type": "Nessuna", "model_prob": 0, "odds": 0, "edge": 0, "is_value": False, "stake": 0}

    # Kelly al 30%
    stake = 0.0
    b = best_market["odds"] - 1
    p = best_market["model_prob"] / 100
    q = 1 - p
    kelly_fraction = (b * p - q) / b
    if kelly_fraction > 0:
        stake = round(bankroll * kelly_fraction * 0.30, 2)
            
    best_market["stake"] = stake
    return best_market

def evaluate_advanced_bet(probs, match_odds_dict):
    advanced_markets = [
        {"name": "Combo: 1X + Over 1.5", "prob": probs["p_combo_1x_over15"], "odds": match_odds_dict.get("combo_1x_over15", 1.65)},
        {"name": "Scarto 1 Gol (Vittoria di Misura)", "prob": probs["p_scarto_1"], "odds": match_odds_dict.get("scarto_1", 2.40)},
        {"name": "Parziale/Finale: 1/1", "prob": probs["p_ht_ft_11"], "odds": match_odds_dict.get("ht_ft_11", 3.20)}
    ]
    
    best_adv = None
    max_edge = 0.025 # Soglia di vantaggio per le combo
    
    for m in advanced_markets:
        odds = m["odds"]
        if not odds or odds < 1.50:
            continue
        implied_prob = 1 / odds
        edge = m["prob"] - implied_prob
        
        if edge > max_edge:
            max_edge = edge
            best_adv = {
                "bet_type": m["name"],
                "model_prob": round(m["prob"] * 100, 1),
                "odds": odds,
                "edge": round(edge * 100, 2),
                "is_value": True
            }
            
    if not best_adv:
        return {"bet_type": "Nessuna Combo Valida", "model_prob": 0, "odds": 0, "edge": 0, "is_value": False}
    return best_adv

try:
    # ==========================================
    # 📊 3. VERIFICA ESITI DI IERI
    # ==========================================
    print(f"🔄 Verifica esiti delle partite di ieri ({ieri})...")
    report_ieri_lines = []
    
    if os.path.exists(STORICO_FILE):
        with open(STORICO_FILE, "r") as f:
            storico_data = json.load(f)
            
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
                    hg, ag = score.get('home', 0), score.get('away', 0)
                    risultati_reali_ieri[f"{c_it}_vs_{o_it}"] = {"hg": hg, "ag": ag}

        if ieri in storico_data:
            for match_key, pronostico_salvato in storico_data[ieri].items():
                if match_key in risultati_reali_ieri:
                    res = risultati_reali_ieri[match_key]
                    hg, ag = res["hg"], res["ag"]
                    tot_g = hg + ag
                    bet = pronostico_salvato["bet_type"]
                    vinta = False
                    
                    if bet == "Segno 1": vinta = hg > ag
                    elif bet == "Segno X": vinta = hg == ag
                    elif bet == "Segno 2": vinta = hg < ag
                    elif bet == "Doppia 1X": vinta = hg >= ag
                    elif bet == "Doppia X2": vinta = hg <= ag
                    elif "Over 1.5" in bet: vinta = tot_g > 1.5
                    elif "Under 1.5" in bet: vinta = tot_g < 1.5
                    elif "Over 2.5" in bet: vinta = tot_g > 2.5
                    elif "Under 2.5" in bet: vinta = tot_g < 2.5
                    elif "Over 3.5" in bet: vinta = tot_g > 3.5
                    elif "Goal (BTTS)" in bet: vinta = hg > 0 and ag > 0
                    elif "Combo: 1X + Over 1.5" in bet: vinta = (hg >= ag) and (tot_g > 1.5)
                    elif "Scarto 1 Gol" in bet: vinta = abs(hg - ag) == 1
                    else: vinta = hg > ag
                    
                    icona = "✅" if vinta else "❌"
                    report_ieri_lines.append(f"• {match_key.replace('_vs_', ' vs ').title()} ({hg}-{ag}) ➔ {bet} {icona}")

    # ==========================================
    # 📥 4. RECUPERO QUOTE & DATI ODIERNI (CASA/TRASFERTA + FORMA)
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
            key_match = f"{home_name}_vs_{away_name}"
            
            odds_cache[key_match] = {
                "1": ev.get('odds_1', 2.0), "x": ev.get('odds_x', 3.2), "2": ev.get('odds_2', 3.0),
                "1x": ev.get('odds_1x', 1.55), "x2": ev.get('odds_x2', 1.60),
                "over15": ev.get('over_15', 1.50), "under15": ev.get('under_15', 3.0),
                "over25": ev.get('over_25', 1.9), "under25": ev.get('under_25', 1.8),
                "over35": ev.get('over_35', 3.5), "goal": ev.get('btts_yes', 1.85),
                "corners": ev.get('over_corners', 1.85), "cards": ev.get('over_cards', 1.90),
                "shots": ev.get('over_shots', 1.85),
                "combo_1x_over15": ev.get('combo_1x_over15', 1.68),
                "scarto_1": ev.get('scarto_1', 2.45),
                "ht_ft_11": ev.get('ht_ft_11', 3.30)
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
            # Estraiamo le tabelle separate casa e trasferta se disponibili, altrimenti totali
            table_total = []
            table_home = []
            table_away = []
            for s in standings_list:
                if s.get('type') == 'TOTAL': table_total = s.get('table', [])
                if s.get('type') == 'HOME': table_home = s.get('table', [])
                if s.get('type') == 'AWAY': table_away = s.get('table', [])
            
            classifiche_cache[comp_id] = {
                "total": {item['team']['name']: item for item in table_total if 'team' in item},
                "home": {item['team']['name']: item for item in table_home if 'team' in item},
                "away": {item['team']['name']: item for item in table_away if 'team' in item}
            }
        else:
            classifiche_cache[comp_id] = {"total": {}, "home": {}, "away": {}}

    partite_analizzate_primarie = []
    partite_analizzate_avanzate = []
    nuovo_storico_oggi = {}

    for m in raw_matches:
        comp_id = m.get('competition', {}).get('id')
        status_match = m.get('status', 'TIMED')
        home_team = m.get('homeTeam', {})
        away_team = m.get('awayTeam', {})
        
        casa = home_team.get('shortName') or home_team.get('name', 'Casa')
        ospite = away_team.get('shortName') or away_team.get('name', 'Ospite')
        
        comp_data = classifiche_cache.get(comp_id, {"total": {}, "home": {}, "away": {}})
        dati_casa_home = comp_data["home"].get(home_team.get('name'), comp_data["total"].get(home_team.get('name'), {"goalsFor": 12, "goalsAgainst": 8}))
        dati_ospite_away = comp_data["away"].get(away_team.get('name'), comp_data["total"].get(away_team.get('name'), {"goalsFor": 10, "goalsAgainst": 12}))
        
        # Calcolo xG mirato separando Casa e Trasferta
        gf_casa = dati_casa_home.get('goalsFor', 12) / max(1, dati_casa_home.get('playedGames', 5))
        gs_ospite = dati_ospite_away.get('goalsAgainst', 12) / max(1, dati_ospite_away.get('playedGames', 5))
        home_xg = max(0.8, (gf_casa + gs_ospite) / 2)

        gf_ospite = dati_ospite_away.get('goalsFor', 10) / max(1, dati_ospite_away.get('playedGames', 5))
        gs_casa = dati_casa_home.get('goalsAgainst', 8) / max(1, dati_casa_home.get('playedGames', 5))
        away_xg = max(0.6, (gf_ospite + gs_casa) / 2)
        
        home_corners, away_corners = 5.2, 4.3
        home_cards, away_cards = 2.1, 2.4
        home_shots, away_shots = 13.5, 11.0

        probs = calculate_advanced_match_probabilities(home_xg, away_xg, home_corners, away_corners, home_cards, away_cards, home_shots, away_shots)
        match_odds = find_odds_for_match(casa, ospite, odds_cache)
        
        best_bet = evaluate_primary_bet(probs, match_odds)
        best_adv = evaluate_advanced_bet(probs, match_odds)
        
        is_rinviata = status_match in ['POSTPONED', 'SUSPENDED', 'CANCELLED']
        match_key = f"{casa.lower()}_vs_{ospite.lower()}"
        
        if best_bet['is_value']:
            nuovo_storico_oggi[match_key] = {"bet_type": best_bet['bet_type']}

        partite_analizzate_primarie.append({
            "casa": casa, "ospite": ospite, "status": status_match, "is_rinviata": is_rinviata, "best_bet": best_bet
        })
        
        if best_adv['is_value']:
            partite_analizzate_avanzate.append({
                "casa": casa, "ospite": ospite, "status": status_match, "is_rinviata": is_rinviata, "best_adv": best_adv
            })

    storico_completo = {}
    if os.path.exists(STORICO_FILE):
        with open(STORICO_FILE, "r") as f:
            try: storico_completo = json.load(f)
            except: storico_completo = {}
            
    storico_completo[oggi] = nuovo_storico_oggi
    with open(STORICO_FILE, "w") as f:
        json.dump(storico_completo, f, indent=4)

    partite_analizzate_primarie.sort(key=lambda x: -x['best_bet']['edge'])
    partite_analizzate_avanzate.sort(key=lambda x: -x['best_adv']['edge'])

    # ==========================================
    # 📄 5. GENERAZIONE REPORT PDF A DUE LISTE
    # ==========================================
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=14, textColor=colors.HexColor('#1A365D'), spaceAfter=2, alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor('#4A5568'), spaceAfter=8, alignment=1)
    section_style = ParagraphStyle('SectionStyle', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#2B6CB0'), spaceBefore=10, spaceAfter=4)
    cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=7.5, textColor=colors.HexColor('#2D3748'))
    header_cell_style = ParagraphStyle('HeaderCellStyle', parent=styles['Normal'], fontSize=7.5, textColor=colors.white, fontName='Helvetica-Bold')

    # Intestazione Generale
    elements.append(Paragraph(f"<b>REPORT QUANTITATIVO AVANZATO - A DUE LISTE</b>", title_style))
    elements.append(Paragraph(f"Data: {oggi} | Quota Min: 1.50 | Edge Min: 3% (Lista 1) / 2.5% (Lista 2) | Kelly: 30%", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2B6CB0'), spaceAfter=8))

    # --- LISTA 1: TOP 15 PARTITE SINGOLE CONSIGLIATE ---
    elements.append(Paragraph("<b>Lista 1: Top Selezioni Singole (Mercati Principali)</b>", section_style))
    
    table_data_1 = [[
        Paragraph("<b>Match</b>", header_cell_style),
        Paragraph("<b>Modello %</b>", header_cell_style),
        Paragraph("<b>Quota</b>", header_cell_style),
        Paragraph("<b>Edge %</b>", header_cell_style),
        Paragraph("<b>Value</b>", header_cell_style),
        Paragraph("<b>Pronostico Consigliato</b>", header_cell_style)
    ]]

    for m in partite_analizzate_primarie[:15]:
        bb = m['best_bet']
        if m['is_rinviata']:
            match_str = f"{m['casa']} - {m['ospite']} (Rinviata)"
            p_str, q_str, edge_str, val_str, pron_str = "-", "-", "-", "-", "⏳ Rinviata"
        else:
            match_str = f"{m['casa']} vs {m['ospite']}"
            p_str = f"{bb['model_prob']}%"
            q_str = str(bb['odds']) if bb['odds'] > 0 else "-"
            edge_str = f"+{bb['edge']}%" if bb['edge'] > 0 else "-"
            val_str = "🟢 SI" if bb['is_value'] else "🔴 NO"
            pron_str = f"<b>{bb['bet_type']}</b>"

        table_data_1.append([
            Paragraph(match_str, cell_style),
            Paragraph(p_str, cell_style),
            Paragraph(q_str, cell_style),
            Paragraph(edge_str, cell_style),
            Paragraph(val_str, cell_style),
            Paragraph(pron_str, cell_style)
        ])

    t1 = Table(table_data_1, colWidths=[145, 55, 55, 50, 45, 212])
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0'))
    ]))
    elements.append(t1)
    
    elements.append(Spacer(1, 10))

    # --- LISTA 2: COMBO, PARZIALI/FINALI E GOL DI SCARTO ---
    elements.append(Paragraph("<b>Lista 2: Selezioni Avanzate (Combo, Parziali/Finali & Scarti)</b>", section_style))
    
    table_data_2 = [[
        Paragraph("<b>Match</b>", header_cell_style),
        Paragraph("<b>Modello %</b>", header_cell_style),
        Paragraph("<b>Quota</b>", header_cell_style),
        Paragraph("<b>Edge %</b>", header_cell_style),
        Paragraph("<b>Pronostico Avanzato Consigliato</b>", header_cell_style)
    ]]

    for m in partite_analizzate_avanzate[:12]:
        ba = m['best_adv']
        if m['is_rinviata']:
            match_str = f"{m['casa']} - {m['ospite']} (Rinviata)"
            p_str, q_str, edge_str, pron_str = "-", "-", "-", "⏳ Rinviata"
        else:
            match_str = f"{m['casa']} vs {m['ospite']}"
            p_str = f"{ba['model_prob']}%"
            q_str = str(ba['odds']) if ba['odds'] > 0 else "-"
            edge_str = f"+{ba['edge']}%" if ba['edge'] > 0 else "-"
            pron_str = f"<b>{ba['bet_type']}</b>"

        table_data_2_row = [
            Paragraph(match_str, cell_style),
            Paragraph(p_str, cell_style),
            Paragraph(q_str, cell_style),
            Paragraph(edge_str, cell_style),
            Paragraph(pron_str, cell_style)
        ]
        table_data_2.append(table_data_2_row)

    t2 = Table(table_data_2, colWidths=[160, 60, 60, 55, 227], repeatRows=1)
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2B6CB0')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#EDF2F7')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0'))
    ]))
    elements.append(t2)

    doc.build(elements)
    print(f"✅ PDF avanzato a due liste generato con successo: {pdf_filename}")

    # ==========================================
    # 📤 6. INVIO TELEGRAM
    # ==========================================
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    caption_text = f"🧠 *Report Quantitativo Avanzato a 2 Liste ({oggi})* 🚀\n\n"
    if report_ieri_lines:
        caption_text += f"📊 *Bilancio Ieri ({ieri}):*\n" + "\n".join(report_ieri_lines[:6])
    else:
        caption_text += f"📊 *Bilancio Ieri ({ieri}):* Nessun pronostico registrato."

    with open(pdf_filename, 'rb') as pdf_file:
        files = {'document': pdf_file}
        payload = {"chat_id": CHAT_ID, "caption": caption_text}
        res_tg = requests.post(telegram_url, data=payload, files=files)
        
    if res_tg.status_code == 200:
        print("✅ Report a due liste inviato correttamente su Telegram!")
    else:
        print(f"⚠️ Errore Telegram: {res_tg.text}")

except Exception as e:
    print(f"❌ Errore generale nell'esecuzione: {e}")
