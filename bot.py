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

print(f"🔄 Avvio motore quantitativo a mercati diversificati per il: {oggi}...")

def clean_team_name(name):
    if not name: return ""
    nfkd_form = unicodedata.normalize('NFKD', name)
    only_ascii = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    cleaned = only_ascii.lower()
    for word in [' fc', ' cf', ' united', ' city', ' sad']:
        cleaned = cleaned.replace(word, '')
    return "".join(c for c in cleaned if c.isalnum())

def poisson_probability(lmbda, k):
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

# ==========================================
# 📐 MODELLO POISSON & PROBABILITÀ SPECIFICHE
# ==========================================
def calculate_match_profile(home_xg, away_xg, home_corners, away_corners, home_cards, away_cards):
    matrix = [[0.0 for _ in range(6)] for _ in range(6)]
    home_win, draw, away_win = 0, 0, 0
    over_15, over_25, over_35 = 0, 0, 0
    btts = 0
    
    for h in range(6):
        for a in range(6):
            p = poisson_probability(home_xg, h) * poisson_probability(away_xg, a)
            matrix[h][a] = p
            if h > a: home_win += p
            elif h == a: draw += p
            else: away_win += p
            
            tot_g = h + a
            if tot_g > 1.5: over_15 += p
            if tot_g > 2.5: over_25 += p
            if tot_g > 3.5: over_35 += p
            if h > 0 and a > 0: btts += p

    tot_c = home_corners + away_corners
    p_c_tot = sum(poisson_probability(tot_c, c) for c in range(10, 15)) + (1 - sum(poisson_probability(tot_c, c) for c in range(15)))
    p_c_home = sum(poisson_probability(home_corners, c) for c in range(5, 12))
    p_c_away = sum(poisson_probability(away_corners, c) for c in range(4, 12))

    tot_cards = home_cards + away_cards
    p_card_35 = sum(poisson_probability(tot_cards, c) for c in range(4, 12))
    p_card_45 = sum(poisson_probability(tot_cards, c) for c in range(5, 12))

    p_1x = home_win + draw
    p_x2 = away_win + draw
    p_combo = p_1x * over_15
    p_scarto = sum(matrix[h][a] for h in range(6) for a in range(6) if abs(h - a) == 1)
    
    h_ht = home_xg * 0.45
    a_ht = away_xg * 0.45
    p_h_ht = sum(poisson_probability(h_ht, h) * poisson_probability(a_ht, a) for h in range(4) for a in range(4) if h > a)
    p_ht_ft = p_h_ht * home_win

    return {
        "Segno 1": home_win, "Segno X": draw, "Segno 2": away_win,
        "Doppia 1X": p_1x, "Doppia X2": p_x2,
        "Over 1.5": over_15, "Under 1.5": 1 - over_15,
        "Over 2.5": over_25, "Under 2.5": 1 - over_25,
        "Over 3.5": over_35, "Goal (BTTS)": btts,
        "Combo: 1X + Over 1.5": p_combo, "Scarto 1 Gol": p_scarto, "Parziale/Finale: 1/1": p_ht_ft,
        "Over 9.5 Corner Totali": p_c_tot, "Casa Over 4.5 Corner": p_c_home, "Ospite Over 3.5 Corner": p_c_away,
        "Over 3.5 Cartellini": p_card_35, "Over 4.5 Cartellini": p_card_45
    }

def find_real_odds(casa, ospite, odds_cache):
    c_clean = clean_team_name(casa)
    o_clean = clean_team_name(ospite)
    key = f"{c_clean}_vs_{o_clean}"
    if key in odds_cache: return odds_cache[key]
    matches = get_close_matches(key, list(odds_cache.keys()), n=1, cutoff=0.3)
    if matches: return odds_cache[matches[0]]
    return {}

# ==========================================
# 🔍 SELEZIONE UNICA E DIVERSIFICATA PER MATCH
# ==========================================
def pick_best_market_for_category(probs, odds, category_markets):
    best = None
    max_score = -999
    for m_name in category_markets:
        prob = probs.get(m_name, 0.5)
        od = odds.get(m_name.lower().replace(" ", "_"), 1.80)
        # Fallback quota se non presente nell'API
        if not od or od < 1.30:
            od = 1.75 if "Over" in m_name or "Goal" in m_name else 2.10
        
        implied = 1 / od
        edge = prob - implied
        # Punteggio combinato per evitare di dare sempre lo stesso mercato
        score = edge + (prob * 0.2)
        
        if score > max_score:
            max_score = score
            best = {
                "bet_type": m_name,
                "model_prob": round(prob * 100, 1),
                "odds": od,
                "edge": round(edge * 100, 2),
                "is_value": True
            }
    return best if best else {"bet_type": category_markets[0], "model_prob": 55.0, "odds": 1.80, "edge": 1.0, "is_value": True}

try:
    # 📥 DOWNLOAD DATI API
    res_odss = requests.get(ODSS_URL, headers=headers_odss)
    odds_cache = {}
    if res_odss.status_code == 200:
        for ev in res_odss.json().get('data', res_odss.json().get('matches', [])):
            h = clean_team_name(ev.get('home_team', ev.get('home', '')))
            a = clean_team_name(ev.get('away_team', ev.get('away', '')))
            odds_cache[f"{h}_vs_{a}"] = {
                "segno_1": ev.get('odds_1'), "segno_x": ev.get('odds_x'), "segno_2": ev.get('odds_2'),
                "doppia_1x": ev.get('odds_1x'), "doppia_x2": ev.get('odds_x2'),
                "over_1.5": ev.get('over_15'), "over_2.5": ev.get('over_25'), "over_3.5": ev.get('over_35'),
                "goal_(btts)": ev.get('btts_yes'), "over_9.5_corner_totali": ev.get('over_corners'),
                "casa_over_4.5_corner": ev.get('home_corners'), "ospite_over_3.5_corner": ev.get('away_corners'),
                "over_3.5_cartellini": ev.get('odds_cards_35'), "over_4.5_cartellini": ev.get('over_cards'),
                "combo:_1x_+_over_1.5": ev.get('combo_1x_over15'), "scarto_1_gol": ev.get('scarto_1'),
                "parziale/finale:_1/1": ev.get('ht_ft_11')
            }

    url_oggi = f"https://api.football-data.org/v4/matches?date={oggi}"
    res_fd = requests.get(url_oggi, headers=headers_fd)
    time.sleep(2)
    raw_matches = res_fd.json().get('matches', []) if res_fd.status_code == 200 else []

    comp_ids = set(m.get('competition', {}).get('id') for m in raw_matches if m.get('competition', {}).get('id'))
    classifiche_cache = {}
    for cid in comp_ids:
        r_st = requests.get(f"https://api.football-data.org/v4/competitions/{cid}/standings", headers=headers_fd)
        time.sleep(2)
        if r_st.status_code == 200:
            st_list = r_st.json().get('standings', [])
            t_tot = next((s.get('table', []) for s in st_list if s.get('type') == 'TOTAL'), [])
            t_home = next((s.get('table', []) for s in st_list if s.get('type') == 'HOME'), [])
            t_away = next((s.get('table', []) for s in st_list if s.get('type') == 'AWAY'), [])
            classifiche_cache[cid] = {
                "total": {item['team']['name']: item for item in t_tot if 'team' in item},
                "home": {item['team']['name']: item for item in t_home if 'team' in item},
                "away": {item['team']['name']: item for item in t_away if 'team' in item}
            }
        else:
            classifiche_cache[cid] = {"total": {}, "home": {}, "away": {}}

    p_primarie, p_avanzate, p_corner, p_cartellini = [], [], [], []
    nuovo_storico = {}

    for m in raw_matches:
        cid = m.get('competition', {}).get('id')
        status = m.get('status', 'TIMED')
        h_team = m.get('homeTeam', {})
        a_team = m.get('awayTeam', {})
        casa = h_team.get('shortName') or h_team.get('name', 'Casa')
        ospite = a_team.get('shortName') or a_team.get('name', 'Ospite')
        
        c_data = classifiche_cache.get(cid, {"total": {}, "home": {}, "away": {}})
        d_h = c_data["home"].get(h_team.get('name'), c_data["total"].get(h_team.get('name'), {"goalsFor": 1, "goalsAgainst": 1, "playedGames": 1}))
        d_a = c_data["away"].get(a_team.get('name'), c_data["total"].get(a_team.get('name'), {"goalsFor": 1, "goalsAgainst": 1, "playedGames": 1}))
        
        pg_h = max(1, d_h.get('playedGames', 1))
        pg_a = max(1, d_a.get('playedGames', 1))
        
        h_xg = max(0.6, (d_h.get('goalsFor', 1) / pg_h + d_a.get('goalsAgainst', 1) / pg_a) / 2)
        a_xg = max(0.5, (d_a.get('goalsFor', 1) / pg_a + d_h.get('goalsAgainst', 1) / pg_h) / 2)
        
        h_c = 4.0 + (h_xg * 1.1)
        a_c = 3.5 + (a_xg * 1.0)
        h_card = 2.0 + (h_xg * 0.15)
        a_card = 2.0 + (a_xg * 0.15)

        probs = calculate_match_profile(h_xg, a_xg, h_c, a_c, h_card, a_card)
        odds = find_real_odds(casa, ospite, odds_cache)
        
        # Scelta diversificata dei mercati per categoria
        b1 = pick_best_market_for_category(probs, odds, ["Segno 1", "Segno X", "Segno 2", "Doppia 1X", "Over 1.5", "Over 2.5", "Goal (BTTS)"])
        b2 = pick_best_market_for_category(probs, odds, ["Combo: 1X + Over 1.5", "Scarto 1 Gol", "Parziale/Finale: 1/1"])
        b3 = pick_best_market_for_category(probs, odds, ["Over 9.5 Corner Totali", "Casa Over 4.5 Corner", "Ospite Over 3.5 Corner"])
        b4 = pick_best_market_for_category(probs, odds, ["Over 3.5 Cartellini", "Over 4.5 Cartellini"])
        
        is_rinv = status in ['POSTPONED', 'SUSPENDED', 'CANCELLED']
        
        p_primarie.append({"casa": casa, "ospite": ospite, "status": status, "is_rinv": is_rinv, "bet": b1})
        p_avanzate.append({"casa": casa, "ospite": ospite, "status": status, "is_rinv": is_rinv, "bet": b2})
        p_corner.append({"casa": casa, "ospite": ospite, "status": status, "is_rinv": is_rinv, "bet": b3})
        p_cartellini.append({"casa": casa, "ospite": ospite, "status": status, "is_rinv": is_rinv, "bet": b4})

    p_primarie.sort(key=lambda x: -x['bet']['edge'])
    p_avanzate.sort(key=lambda x: -x['bet']['edge'])
    p_corner.sort(key=lambda x: -x['bet']['edge'])
    p_cartellini.sort(key=lambda x: -x['bet']['edge'])

    # 📄 GENERAZIONE PDF
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    elements = []
    styles = getSampleStyleSheet()

    t_style = ParagraphStyle('TStyle', parent=styles['Heading1'], fontSize=13, textColor=colors.HexColor('#1A365D'), spaceAfter=2, alignment=1)
    s_style = ParagraphStyle('SStyle', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#4A5568'), spaceAfter=6, alignment=1)
    sec_style = ParagraphStyle('SecStyle', parent=styles['Heading2'], fontSize=10, textColor=colors.HexColor('#2B6CB0'), spaceBefore=8, spaceAfter=3)
    c_style = ParagraphStyle('CStyle', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#2D3748'))
    h_style = ParagraphStyle('HStyle', parent=styles['Normal'], fontSize=7, textColor=colors.white, fontName='Helvetica-Bold')

    elements.append(Paragraph(f"<b>REPORT QUANTITATIVO - 4 LISTE DIVERSIFICATE</b>", t_style))
    elements.append(Paragraph(f"Data: {oggi} | Modello Poisson con Selezione Unica per Match", s_style))
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
                    Paragraph(f"{b['model_prob']}%", c_style),
                    Paragraph(str(b['odds']), c_style),
                    Paragraph(f"+{b['edge']}%" if b['edge'] > 0 else f"{b['edge']}%", c_style),
                    Paragraph(f"<b>{b['bet_type']}</b>", c_style)
                ])
        
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

    # 📤 TELEGRAM
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(pdf_filename, 'rb') as pdf_file:
        files = {'document': pdf_file}
        payload = {"chat_id": CHAT_ID, "caption": f"🧠 *Report Quantitativo Diversificato ({oggi})* 🚀"}
        requests.post(telegram_url, data=payload, files=files)

except Exception as e:
    print(f"❌ Errore generale nell'esecuzione: {e}")
