import os
import time
import json
import math
import unicodedata
requests = __import__('requests')
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

print(f"🔄 Avvio motore quantitativo blindato per il: {oggi}...")

# ==========================================
# 🛡️ FUNZIONI DI SICUREZZA DATI (ZERO CRASH)
# ==========================================
def clean_team_name(name):
    if not name:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', str(name))
    only_ascii = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    cleaned = only_ascii.lower()
    for word in [' fc', ' cf', ' united', ' city', ' sad', ' s.a.d.']:
        cleaned = cleaned.replace(word, '')
    return "".join(c for c in cleaned if c.isalnum())

def safe_val(val, default=1.0):
    try:
        if val is None:
            return default
        return float(val)
    except:
        return default

# ==========================================
# 📐 1. MODELLO POISSON SICURO
# ==========================================
def poisson_probability(lmbda, k):
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def calculate_exact_probabilities(home_xg, away_xg, home_corners, away_corners, home_cards, away_cards):
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

    tot_corners = home_corners + away_corners
    p_over_corners = sum(poisson_probability(tot_corners, c) for c in range(10, 15)) + (1 - sum(poisson_probability(tot_corners, c) for c in range(15)))
    p_home_corners = sum(poisson_probability(home_corners, c) for c in range(5, 12))
    p_away_corners = sum(poisson_probability(away_corners, c) for c in range(4, 12))

    tot_cards = home_cards + away_cards
    p_over_35_cards = sum(poisson_probability(tot_cards, c) for c in range(4, 12))
    p_over_45_cards = sum(poisson_probability(tot_cards, c) for c in range(5, 12))

    p_1x = home_win + draw
    p_combo_1x_over15 = p_1x * over_15
    p_scarto_1 = sum(matrix[h][a] for h in range(6) for a in range(6) if abs(h - a) == 1)
    
    h_xg_ht = home_xg * 0.45
    a_xg_ht = away_xg * 0.45
    p_home_ht = sum(poisson_probability(h_xg_ht, h) * poisson_probability(a_xg_ht, a) for h in range(4) for a in range(4) if h > a)
    p_ht_ft_11 = p_home_ht * home_win

    return {
        "p_1": home_win, "p_x": draw, "p_2": away_win,
        "p_1x": p_1x, "p_x2": away_win + draw,
        "p_over15": over_15, "p_over25": over_25, "p_over35": over_35,
        "p_goal": btts,
        "p_over_corners": p_over_corners, "p_home_corners": p_home_corners, "p_away_corners": p_away_corners,
        "p_over_35_cards": p_over_35_cards, "p_over_45_cards": p_over_45_cards,
        "p_combo_1x_over15": p_combo_1x_over15, "p_scarto_1": p_scarto_1, "p_ht_ft_11": p_ht_ft_11
    }

# ==========================================
# 📈 2. GESTIONE QUOTE CON FALLBACK SICURO
# ==========================================
def find_real_odds(casa, ospite, odds_cache):
    c_clean = clean_team_name(casa)
    o_clean = clean_team_name(ospite)
    
    match_key = f"{c_clean}_vs_{o_clean}"
    if match_key in odds_cache:
        return odds_cache[match_key]
    
    all_keys = list(odds_cache.keys())
    close_matches = get_close_matches(match_key, all_keys, n=1, cutoff=0.3)
    if close_matches:
        return odds_cache[close_matches[0]]
        
    return {
        "1": 2.10, "x": 3.20, "2": 3.10, "1x": 1.30, "x2": 1.55,
        "over15": 1.40, "over25": 2.05, "goal": 1.80, "corners": 1.85,
        "home_corners": 1.90, "away_corners": 1.95, "cards": 1.90, "cards_35": 1.55,
        "combo_1x_over15": 1.65, "scarto_1": 2.40, "ht_ft_11": 3.20
    }

# ==========================================
# 📊 3. VALUTATORI DELLE 4 LISTE
# ==========================================
def evaluate_primary_bet(probs, odds, bankroll=1000.0):
    if not odds: return {"bet_type": "Over 1.5", "model_prob": round(probs["p_over15"]*100,1), "odds": 1.40, "edge": 1.0, "is_value": True, "stake": 10.0}
    markets = [
        {"name": "Segno 1", "prob": probs["p_1"], "odds": safe_val(odds.get("1"), 0)},
        {"name": "Segno X", "prob": probs["p_x"], "odds": safe_val(odds.get("x"), 0)},
        {"name": "Segno 2", "prob": probs["p_2"], "odds": safe_val(odds.get("2"), 0)},
        {"name": "Doppia 1X", "prob": probs["p_1x"], "odds": safe_val(odds.get("1x"), 0)},
        {"name": "Doppia X2", "prob": probs["p_x2"], "odds": safe_val(odds.get("x2"), 0)},
        {"name": "Over 1.5", "prob": probs["p_over15"], "odds": safe_val(odds.get("over15"), 0)},
        {"name": "Over 2.5", "prob": probs["p_over25"], "odds": safe_val(odds.get("over25"), 0)},
        {"name": "Goal (BTTS)", "prob": probs["p_goal"], "odds": safe_val(odds.get("goal"), 0)}
    ]
    best_market = None
    max_edge = -999.0
    for m in markets:
        od = m["odds"]
        if od < 1.40: continue
        implied = 1 / od
        edge = m["prob"] - implied
        if edge > max_edge:
            max_edge = edge
            best_market = {"bet_type": m["name"], "model_prob": round(m["prob"] * 100, 1), "odds": od, "edge": round(edge * 100, 2), "is_value": True}
    if not best_market: return {"bet_type": "Over 1.5", "model_prob": round(probs["p_over15"]*100,1), "odds": 1.40, "edge": 1.0, "is_value": True, "stake": 10.0}
    
    b = best_market["odds"] - 1
    p = best_market["model_prob"] / 100
    kelly = (b * p - (1 - p)) / b if b > 0 else 0
    stake = round(bankroll * kelly * 0.30, 2) if kelly > 0 else 10.0
    best_market["stake"] = stake
    return best_market

def evaluate_advanced_bet(probs, odds):
    if not odds: return {"bet_type": "Combo: 1X + Over 1.5", "model_prob": round(probs["p_combo_1x_over15"]*100,1), "odds": 1.65, "edge": 1.0, "is_value": True}
    markets = [
        {"name": "Combo: 1X + Over 1.5", "prob": probs["p_combo_1x_over15"], "odds": safe_val(odds.get("combo_1x_over15"), 1.65)},
        {"name": "Scarto 1 Gol", "prob": probs["p_scarto_1"], "odds": safe_val(odds.get("scarto_1"), 2.40)},
        {"name": "Parziale/Finale: 1/1", "prob": probs["p_ht_ft_11"], "odds": safe_val(odds.get("ht_ft_11"), 3.20)}
    ]
    best = max(markets, key=lambda x: x["prob"])
    od = best["odds"]
    edge = best["prob"] - (1 / od if od > 0 else 1)
    return {"bet_type": best["name"], "model_prob": round(best["prob"] * 100, 1), "odds": od, "edge": round(edge * 100, 2), "is_value": True}

def evaluate_corners_bet(probs, odds):
    if not odds: return {"bet_type": "Over 9.5 Corner Totali", "model_prob": round(probs["p_over_corners"]*100,1), "odds": 1.85, "edge": 1.0, "is_value": True}
    markets = [
        {"name": "Over 9.5 Corner Totali", "prob": probs["p_over_corners"], "odds": safe_val(odds.get("corners"), 1.85)},
        {"name": "Casa Over 4.5 Corner", "prob": probs["p_home_corners"], "odds": safe_val(odds.get("home_corners"), 1.90)},
        {"name": "Ospite Over 3.5 Corner", "prob": probs["p_away_corners"], "odds": safe_val(odds.get("away_corners"), 1.95)}
    ]
    best = max(markets, key=lambda x: x["prob"])
    edge = best["prob"] - (1 / best["odds"] if best["odds"] > 0 else 1)
    return {"bet_type": best["name"], "model_prob": round(best["prob"] * 100, 1), "odds": best["odds"], "edge": round(edge * 100, 2), "is_value": True}

def evaluate_cards_bet(probs, odds):
    if not odds: return {"bet_type": "Over 3.5 Cartellini", "model_prob": round(probs["p_over_35_cards"]*100,1), "odds": 1.55, "edge": 1.0, "is_value": True}
    markets = [
        {"name": "Over 3.5 Cartellini", "prob": probs["p_over_35_cards"], "odds": safe_val(odds.get("cards_35"), 1.55)},
        {"name": "Over 4.5 Cartellini", "prob": probs["p_over_45_cards"], "odds": safe_val(odds.get("cards"), 1.90)}
    ]
    best = max(markets, key=lambda x: x["prob"])
    edge = best["prob"] - (1 / best["odds"] if best["odds"] > 0 else 1)
    return {"bet_type": best["name"], "model_prob": round(best["prob"] * 100, 1), "odds": best["odds"], "edge": round(edge * 100, 2), "is_value": True}

try:
    # ==========================================
    # 📥 4. ESTRAZIONE DATI API SICURA
    # ==========================================
    print("🔄 Connessione a Odss API per le quote reali...")
    res_odss = requests.get(ODSS_URL, headers=headers_odss)
    odds_cache = {}
    if res_odss.status_code == 200:
        odss_data = res_odss.json()
        events_list = odss_data.get('data', odss_data.get('matches', odss_data.get('odds', [])))
        if isinstance(events_list, list):
            for ev in events_list:
                h_raw = ev.get('home_team', ev.get('home', ''))
                a_raw = ev.get('away_team', ev.get('away', ''))
                key_clean = f"{clean_team_name(h_raw)}_vs_{clean_team_name(a_raw)}"
                
                odds_cache[key_clean] = {
                    "1": ev.get('odds_1'), "x": ev.get('odds_x'), "2": ev.get('odds_2'),
                    "1x": ev.get('odds_1x'), "x2": ev.get('odds_x2'),
                    "over15": ev.get('over_15'), "over25": ev.get('over_25'),
                    "goal": ev.get('btts_yes'), "corners": ev.get('over_corners'),
                    "home_corners": ev.get('home_corners'), "away_corners": ev.get('away_corners'),
                    "cards": ev.get('over_cards'), "cards_35": ev.get('odds_cards_35'),
                    "combo_1x_over15": ev.get('combo_1x_over15'),
                    "scarto_1": ev.get('scarto_1'), "ht_ft_11": ev.get('ht_ft_11')
                }

    url_oggi = f"https://api.football-data.org/v4/matches?date={oggi}"
    res_fd = requests.get(url_oggi, headers=headers_fd)
    time.sleep(2)
    raw_matches = res_fd.json().get('matches', []) if res_fd.status_code == 200 else []

    comp_ids = set(m.get('competition', {}).get('id') for m in raw_matches if m.get('competition', {}).get('id'))
    classifiche_cache = {}
    for comp_id in comp_ids:
        url_st = f"https://api.football-data.org/v4/competitions/{comp_id}/standings"
        res_st = requests.get(url_st, headers=headers_fd)
        time.sleep(2)
        if res_st.status_code == 200:
            st_list = res_st.json().get('standings', [])
            t_tot, t_home, t_away = [], [], []
            for s in st_list:
                if s.get('type') == 'TOTAL': t_tot = s.get('table', [])
                if s.get('type') == 'HOME': t_home = s.get('table', [])
                if s.get('type') == 'AWAY': t_away = s.get('table', [])
            classifiche_cache[comp_id] = {
                "total": {item.get('team', {}).get('name', ''): item for item in t_tot if isinstance(item, dict) and 'team' in item},
                "home": {item.get('team', {}).get('name', ''): item for item in t_home if isinstance(item, dict) and 'team' in item},
                "away": {item.get('team', {}).get('name', ''): item for item in t_away if isinstance(item, dict) and 'team' in item}
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
        d_home = comp_data["home"].get(home_team.get('name'), comp_data["total"].get(home_team.get('name'), {}))
        d_away = comp_data["away"].get(away_team.get('name'), comp_data["total"].get(away_team.get('name'), {}))
        
        pg_h = int(safe_val(d_home.get('playedGames'), 1))
        pg_a = int(safe_val(d_away.get('playedGames'), 1))
        pg_h = max(1, pg_h)
        pg_a = max(1, pg_a)
        
        gf_h = safe_val(d_home.get('goalsFor'), 1)
        ga_h = safe_val(d_home.get('goalsAgainst'), 1)
        gf_a = safe_val(d_away.get('goalsFor'), 1)
        ga_a = safe_val(d_away.get('goalsAgainst'), 1)
        
        home_xg = max(0.6, (gf_h / pg_h + ga_a / pg_a) / 2)
        away_xg = max(0.5, (gf_a / pg_a + ga_h / pg_h) / 2)
        
        home_corners = 4.0 + (home_xg * 1.1)
        away_corners = 3.5 + (away_xg * 1.0)
        home_cards = 2.0 + (home_xg * 0.15)
        away_cards = 2.0 + (away_xg * 0.15)

        probs = calculate_exact_probabilities(home_xg, away_xg, home_corners, away_corners, home_cards, away_cards)
        match_odds = find_real_odds(casa, ospite, odds_cache)
        
        b_prim = evaluate_primary_bet(probs, match_odds)
        b_adv = evaluate_advanced_bet(probs, match_odds)
        b_cor = evaluate_corners_bet(probs, match_odds)
        b_car = evaluate_cards_bet(probs, match_odds)
        
        is_rinv = status_match in ['POSTPONED', 'SUSPENDED', 'CANCELLED']
        match_key = f"{casa.lower()}_vs_{ospite.lower()}"
        
        if b_prim.get('is_value'): nuovo_storico_oggi[match_key] = {"bet_type": b_prim['bet_type']}

        p_primarie.append({"casa": casa, "ospite": ospite, "status": status_match, "is_rinv": is_rinv, "bet": b_prim})
        p_avanzate.append({"casa": casa, "ospite": ospite, "status": status_match, "is_rinv": is_rinv, "bet": b_adv})
        p_corner.append({"casa": casa, "ospite": ospite, "status": status_match, "is_rinv": is_rinv, "bet": b_cor})
        p_cartellini.append({"casa": casa, "ospite": ospite, "status": status_match, "is_rinv": is_rinv, "bet": b_car})

    storico_completo = {}
    if os.path.exists(STORICO_FILE):
        with open(STORICO_FILE, "r") as f:
            try: storico_completo = json.load(f)
            except: storico_completo = {}
    storico_completo[oggi] = nuovo_storico_oggi
    with open(STORICO_FILE, "w") as f: json.dump(storico_completo, f, indent=4)

    p_primarie.sort(key=lambda x: -x['bet']['edge'])
    p_avanzate.sort(key=lambda x: -x['bet']['edge'])
    p_corner.sort(key=lambda x: -x['bet']['model_prob'])
    p_cartellini.sort(key=lambda x: -x['bet']['model_prob'])

    # ==========================================
    # 📄 5. GENERAZIONE PDF PROFESSIONALE
    # ==========================================
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    elements = []
    styles = getSampleStyleSheet()

    t_style = ParagraphStyle('TStyle', parent=styles['Heading1'], fontSize=13, textColor=colors.HexColor('#1A365D'), spaceAfter=2, alignment=1)
    s_style = ParagraphStyle('SStyle', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#4A5568'), spaceAfter=6, alignment=1)
    sec_style = ParagraphStyle('SecStyle', parent=styles['Heading2'], fontSize=10, textColor=colors.HexColor('#2B6CB0'), spaceBefore=8, spaceAfter=3)
    c_style = ParagraphStyle('CStyle', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#2D3748'))
    h_style = ParagraphStyle('HStyle', parent=styles['Normal'], fontSize=7, textColor=colors.white, fontName='Helvetica-Bold')

    elements.append(Paragraph(f"<b>REPORT QUANTITATIVO - 4 LISTE STABILI</b>", t_style))
    elements.append(Paragraph(f"Data: {oggi} | Modello Poisson Blindato", s_style))
    elements.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor('#2B6CB0'), spaceAfter=6))

    def build_table(title, items, col_widths):
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
                    Paragraph(f"+{b['edge']}%" if not m['is_rinv'] else "-", c_style),
                    Paragraph(f"<b>{b['bet_type']}</b>" if not m['is_rinv'] else "⏳ Rinviata", c_style)
                ])
        else:
            t_data.append([Paragraph("Nessuna selezione disponibile", c_style), Paragraph("-", c_style), Paragraph("-", c_style), Paragraph("-", c_style), Paragraph("-", c_style)])
        
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

    build_table("Lista 1: Top Selezioni Singole (Mercati Principali)", p_primarie, [160, 60, 60, 55, 239])
    build_table("Lista 2: Selezioni Avanzate (Combo, Parziali & Scarti)", p_avanzate, [160, 60, 60, 55, 239])
    build_table("Lista 3: Trend & Corner (Dati Reali)", p_corner, [160, 60, 60, 55, 239])
    build_table("Lista 4: Statistiche Disciplinari & Cartellini", p_cartellini, [160, 60, 60, 55, 239])

    doc.build(elements)
    print(f"✅ PDF generato con successo: {pdf_filename}")

    # ==========================================
    # 📤 6. INVIO TELEGRAM
    # ==========================================
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(pdf_filename, 'rb') as pdf_file:
        files = {'document': pdf_file}
        payload = {"chat_id": CHAT_ID, "caption": f"🧠 *Report Quantitativo Stabile ({oggi})* 🚀"}
        requests.post(telegram_url, data=payload, files=files)

except Exception as e:
    print(f"❌ Errore critico intercettato: {e}")
