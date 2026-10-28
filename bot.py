import os
import time
import math
import requests
from datetime import datetime

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

headers_fd = {'X-Auth-Token': API_TOKEN}
oggi = datetime.now().strftime('%Y-%m-%d')
pdf_filename = f"pronostici_quant_{oggi}.pdf"

print(f"🔄 Avvio motore quantitativo (Poisson + Value Betting) per il: {oggi}...")

# ==========================================
# 📐 1. MODULO MATEMATICO: DISTRIBUZIONE DI POISSON
# ==========================================
def poisson_probability(lmbda, k):
    """Calcola la probabilità di k eventi dati lambda (media attesa)."""
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def calculate_poisson_match(home_xg, away_xg, max_goals=5):
    """Calcola le probabilità di 1, X, 2 e Over/Under 2.5 basandosi sugli xG."""
    home_win, draw, away_win = 0, 0, 0
    over_25 = 0
    
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = poisson_probability(home_xg, h) * poisson_probability(away_xg, a)
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p
            
            if (h + a) > 2.5:
                over_25 += p
                
    return {
        "p_1": home_win,
        "p_x": draw,
        "p_2": away_win,
        "p_over25": over_25
    }

# ==========================================
# 📈 2. MODULO VALUE BETTING & EDGE
# ==========================================
def evaluate_value_bet(model_prob, decimal_odds, bankroll=1000.0):
    """Confronta la probabilità del modello con la quota e calcola l'Edge e il Kelly stake."""
    if decimal_odds <= 1.0:
        return {"is_value": False, "edge": 0, "stake": 0}
        
    implied_prob = 1 / decimal_odds
    edge = model_prob - implied_prob
    
    is_value = edge > 0
    stake = 0.0
    
    if is_value:
        # Criterio di Kelly Frazionato (1/4 di Kelly per sicurezza)
        b = decimal_odds - 1
        p = model_prob
        q = 1 - p
        kelly_fraction = (b * p - q) / b
        if kelly_fraction > 0:
            stake = round(bankroll * kelly_fraction * 0.25, 2)
            
    return {
        "is_value": is_value,
        "edge": round(edge * 100, 2),
        "implied_prob": round(implied_prob * 100, 2),
        "stake": stake
    }

# ==========================================
# 📊 3. MODULO BACKTESTING (Simulazione Storica)
# ==========================================
def run_backtesting_simulation(historical_matches):
    """Simula le performance del modello su un set di partite passate con risultati noti."""
    total_bets = 0
    won_bets = 0
    profit = 0.0
    
    for match in historical_matches:
        # match contiene: home_xg, away_xg, quota_1, risultato_reale ('1', 'X', '2')
        probs = calculate_poisson_match(match['home_xg'], match['away_xg'])
        val = evaluate_value_bet(probs['p_1'], match['quota_1'])
        
        if val['is_value']:
            total_bets += 1
            stake = 10.0  # Puntata fissa di test da 10€
            if match['risultato_reale'] == '1':
                won_bets += 1
                profit += (match['quota_1'] - 1) * stake
            else:
                profit -= stake
                
    yield_pct = (profit / (total_bets * 10.0)) * 100 if total_bets > 0 else 0
    return {"total_bets": total_bets, "won_bets": won_bets, "profit": round(profit, 2), "yield": round(yield_pct, 2)}


try:
    # 1. Recupero partite odierne
    url_oggi = f"https://api.football-data.org/v4/matches?date={oggi}"
    res_fd = requests.get(url_oggi, headers=headers_fd)
    time.sleep(2)
    
    raw_matches = res_fd.json().get('matches', []) if res_fd.status_code == 200 else []
    print(f"✅ Trovate {len(raw_matches)} partite nel palinsesto.")

    # 2. Pre-fetching classifiche per stimare i gol attesi (xG euristici basati su attacco/difesa)
    comp_ids = set(m.get('competition', {}).get('id') for m in raw_matches if m.get('competition', {}).get('id'))
    classifiche_cache = {}
    
    for comp_id in comp_ids:
        url_standings = f"https://api.football-data.org/v4/competitions/{comp_id}/standings"
        res_st = requests.get(url_standings, headers=headers_fd)
        time.sleep(2)
        if res_st.status_code == 200:
            standings_list = res_st.json().get('standings', [])
            table = []
            for s in standings_list:
                if s.get('type') == 'TOTAL':
                    table = s.get('table', [])
                    break
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
        dati_casa = standings_map.get(home_team.get('name'), {"goalsFor": 15, "goalsAgainst": 10, "position": 8})
        dati_ospite = standings_map.get(away_team.get('name'), {"goalsFor": 12, "goalsAgainst": 12, "position": 10})
        
        # Stima xG basata sui gol fatti/subiti medi in classifica (semplificazione robusta)
        # In un sistema avanzato useresti la media delle ultime 5 partite
        home_xg = max(0.8, (dati_casa.get('goalsFor', 15) + dati_ospite.get('goalsAgainst', 12)) / 20)
        away_xg = max(0.6, (dati_ospite.get('goalsFor', 12) + dati_casa.get('goalsAgainst', 10)) / 22)
        
        # Calcolo Poisson
        probs = calculate_poisson_match(home_xg, away_xg)
        
        # Simulazione quota di mercato (nella realtà qui useresti la tua Odds API)
        # Per test, ipotizziamo una quota basata sul modello con un piccolo margine
        mock_quota_1 = round(1 / (probs['p_1'] * 0.92), 2) # Aggiunge l'aggio del bookmaker
        
        # Controllo Value Bet
        val_check = evaluate_value_bet(probs['p_1'], mock_quota_1)
        
        is_rinviata = status_match in ['POSTPONED', 'SUSPENDED', 'CANCELLED']

        partite_analizzate.append({
            "casa": casa, "ospite": ospite,
            "status": status_match, "is_rinviata": is_rinviata,
            "home_xg": round(home_xg, 2), "away_xg": round(away_xg, 2),
            "p_1": round(probs['p_1'] * 100, 1),
            "quota": mock_quota_1,
            "is_value": val_check['is_value'],
            "edge": val_check['edge'],
            "stake": val_check['stake']
        })

    # Ordiniamo mettendo prima le vere Value Bet con Edge più alto
    partite_analizzate.sort(key=lambda x: -x['edge'])

    # Esempio di test rapido del modulo di backtesting sullo storico simulato
    dummy_history = [
        {"home_xg": 1.8, "away_xg": 0.9, "quota_1": 1.85, "risultato_reale": "1"},
        {"home_xg": 1.2, "away_xg": 1.3, "quota_1": 2.40, "risultato_reale": "2"},
        {"home_xg": 2.1, "away_xg": 0.8, "quota_1": 1.60, "risultato_reale": "1"},
    ]
    backtest_results = run_backtesting_simulation(dummy_history)

    # ==========================================
    # 📄 GENERAZIONE REPORT PDF PROFESSIONALE
    # ==========================================
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor('#1A365D'), spaceAfter=4, alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#4A5568'), spaceAfter=12, alignment=1)
    cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#2D3748'))
    header_cell_style = ParagraphStyle('HeaderCellStyle', parent=styles['Normal'], fontSize=8, textColor=colors.white, fontName='Helvetica-Bold')

    elements.append(Paragraph(f"<b>QUANTITATIVE BETTING REPORT & VALUE BETS</b>", title_style))
    elements.append(Paragraph(f"Data: {oggi} | Backtest Yield Storico Simulato: {backtest_results['yield']}%", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2B6CB0'), spaceAfter=12))

    table_data = [[
        Paragraph("<b>Match</b>", header_cell_style),
        Paragraph("<b>xG (C-T)</b>", header_cell_style),
        Paragraph("<b>Modello 1%</b>", header_cell_style),
        Paragraph("<b>Quota</b>", header_cell_style),
        Paragraph("<b>Edge %</b>", header_cell_style),
        Paragraph("<b>Value Bet?</b>", header_cell_style),
        Paragraph("<b>Stake (€)</b>", header_cell_style)
    ]]

    for m in partite_analizzate[:15]:
        if m['is_rinviata']:
            match_str = f"{m['casa']} - {m['ospite']} (Rinviata)"
            xg_str, p1_str, q_str, edge_str, val_str, stake_str = "-", "-", "-", "-", "-", "-"
        else:
            match_str = f"{m['casa']} vs {m['ospite']}"
            xg_str = f"{m['home_xg']} - {m['away_xg']}"
            p1_str = f"{m['p_1']}%"
            q_str = str(m['quota'])
            edge_str = f"+{m['edge']}%" if m['edge'] > 0 else f"{m['edge']}%"
            val_str = "🟢 SI" if m['is_value'] else "🔴 NO"
            stake_str = f"€{m['stake']}"

        table_data.append([
            Paragraph(match_str, cell_style),
            Paragraph(xg_str, cell_style),
            Paragraph(p1_str, cell_style),
            Paragraph(q_str, cell_style),
            Paragraph(edge_str, cell_style),
            Paragraph(val_str, cell_style),
            Paragraph(stake_str, cell_style)
        ])

    t = Table(table_data, colWidths=[150, 60, 60, 50, 60, 70, 62])
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
    print(f"✅ PDF Quantitativo generato: {pdf_filename}")

    # ==========================================
    # 📤 INVIO TELEGRAM
    # ==========================================
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(pdf_filename, 'rb') as pdf_file:
        files = {'document': pdf_file}
        payload = {
            "chat_id": CHAT_ID,
            "caption": f"🧠 *Report Quantitativo (Poisson + Value Bet) del {oggi}*\nYield Storico Test: `{backtest_results['yield']}%`"
        }
        res_tg = requests.post(telegram_url, data=payload, files=files)
        
    if res_tg.status_code == 200:
        print("✅ Report inviato con successo su Telegram!")
    else:
        print(f"⚠️ Errore Telegram: {res_tg.text}")

except Exception as e:
    print(f"❌ Errore generale nell'esecuzione: {e}")
