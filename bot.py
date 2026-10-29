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
pdf_filename = f"schedina_consigliata_{oggi}.pdf"
STORICO_FILE = "storico_pronostici.json"

print(f"🔄 Ripristino configurazione originaria schedina unica per il: {oggi}...")

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

def calculate_match_probabilities(home_xg, away_xg):
    home_win, draw, away_win = 0, 0, 0
    over_15, over_25 = 0, 0
    btts = 0
    
    for h in range(6):
        for a in range(6):
            p = poisson_probability(home_xg, h) * poisson_probability(away_xg, a)
            if h > a: home_win += p
            elif h == a: draw += p
            else: away_win += p
            
            tot_g = h + a
            if tot_g > 1.5: over_15 += p
            if tot_g > 2.5: over_25 += p
            if h > 0 and a > 0: btts += p

    p_1x = home_win + draw
    p_x2 = away_win + draw
    
    return {
        "Segno 1": home_win, "Segno X": draw, "Segno 2": away_win,
        "Doppia 1X": p_1x, "Doppia X2": p_x2,
        "Over 1.5": over_15, "Over 2.5": over_25, "Goal (BTTS)": btts
    }

def find_real_odds(casa, ospite, odds_cache):
    c_clean = clean_team_name(casa)
    o_clean = clean_team_name(ospite)
    key = f"{c_clean}_vs_{o_clean}"
    if key in odds_cache: return odds_cache[key]
    matches = get_close_matches(key, list(odds_cache.keys()), n=1, cutoff=0.3)
    if matches: return odds_cache[matches[0]]
    return {
        "1": 2.20, "x": 3.30, "2": 3.00, "1x": 1.32, "x2": 1.55,
        "over15": 1.35, "over25": 2.05, "goal": 1.80
    }

def select_best_market(probs, odds):
    markets = [
        ("Segno 1", probs["Segno 1"], odds.get("1")),
        ("Segno X", probs["Segno X"], odds.get("x")),
        ("Segno 2", probs["Segno 2"], odds.get("2")),
        ("Doppia 1X", probs["Doppia 1X"], odds.get("1x")),
        ("Doppia X2", probs["Doppia X2"], odds.get("x2")),
        ("Over 1.5", probs["Over 1.5"], odds.get("over15")),
        ("Over 2.5", probs["Over 2.5"], odds.get("over25")),
        ("Goal (BTTS)", probs["Goal (BTTS)"], odds.get("goal"))
    ]
    
    best = None
    max_score = -999
    for name, prob, od in markets:
        if not od or od < 1.30:
            od = 1.80 if "Over" in name or "Goal" in name else 2.10
        
        implied = 1 / od
        edge = prob - implied
        score = edge + (prob * 0.1)
        
        if score > max_score:
            max_score = score
            best = {
                "bet_type": name,
                "model_prob": round(prob * 100, 1),
                "odds": od,
                "edge": round(edge * 100, 2)
            }
    return best if best else {"bet_type": "Segno 2", "model_prob": 45.0, "odds": 3.00, "edge": 5.0}

try:
    res_odss = requests.get(ODSS_URL, headers=headers_odss)
    odds_cache = {}
    if res_odss.status_code == 200:
        for ev in res_odss.json().get('data', res_odss.json().get('matches', [])):
            h = clean_team_name(ev.get('home_team', ev.get('home', '')))
            a = clean_team_name(ev.get('away_team', ev.get('away', '')))
            odds_cache[f"{h}_vs_{a}"] = {
                "1": ev.get('odds_1'), "x": ev.get('odds_x'), "2": ev.get('odds_2'),
                "1x": ev.get('odds_1x'), "x2": ev.get('odds_x2'),
                "over15": ev.get('over_15'), "over25": ev.get('over_25'),
                "goal": ev.get('btts_yes')
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

    schedina_matches = []
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

        probs = calculate_match_probabilities(h_xg, a_xg)
        odds = find_real_odds(casa, ospite, odds_cache)
        best_bet = select_best_market(probs, odds)
        
        is_rinv = status in ['POSTPONED', 'SUSPENDED', 'CANCELLED']
        schedina_matches.append({
            "casa": casa, "ospite": ospite, "status": status, "is_rinv": is_rinv, "bet": best_bet
        })

    schedina_matches.sort(key=lambda x: -x['bet']['edge'])

    # 📄 GENERAZIONE PDF
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    t_style = ParagraphStyle('TStyle', parent=styles['Heading1'], fontSize=14, textColor=colors.HexColor('#1A365D'), spaceAfter=2, alignment=1)
    s_style = ParagraphStyle('SStyle', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor('#4A5568'), spaceAfter=8, alignment=1)
    c_style = ParagraphStyle('CStyle', parent=styles['Normal'], fontSize=7.5, textColor=colors.HexColor('#2D3748'))
    h_style = ParagraphStyle('HStyle', parent=styles['Normal'], fontSize=7.5, textColor=colors.white, fontName='Helvetica-Bold')

    elements.append(Paragraph(f"<b>SCHEDINA CONSIGLIATA - UNICA LISTA</b>", t_style))
    elements.append(Paragraph(f"Data: {oggi} | Modello Poisson Reale", s_style))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2B6CB0'), spaceAfter=10))

    t_data = [[Paragraph(f"<b>{h}</b>", h_style) for h in ["Match", "Modello %", "Quota", "Edge %", "Pronostico Consigliato"]]]
    
    for m in schedina_matches[:15]:
        b = m['bet']
        m_str = f"{m['casa']} - {m['ospite']} (Rinviata)" if m['is_rinv'] else f"{m['casa']} vs {m['ospite']}"
        t_data.append([
            Paragraph(m_str, c_style),
            Paragraph(f"{b['model_prob']}%", c_style),
            Paragraph(str(b['odds']), c_style),
            Paragraph(f"+{b['edge']}%" if b['edge'] > 0 else f"{b['edge']}%", c_style),
            Paragraph(f"<b>{b['bet_type']}</b>", c_style)
        ])

    t = Table(t_data, colWidths=[160, 60, 60, 55, 237])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0'))
    ]))
    elements.append(t)
    doc.build(elements)

    # 📤 TELEGRAM
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(pdf_filename, 'rb') as pdf_file:
        files = {'document': pdf_file}
        payload = {"chat_id": CHAT_ID, "caption": f"🧠 *Schedina Consigliata del {oggi}* 🚀"}
        requests.post(telegram_url, data=payload, files=files)

except Exception as e:
    print(f"❌ Errore generale nell'esecuzione: {e}")
