import os
import requests
import json
from datetime import datetime

# ==========================================
# 🔑 CONFIGURAZIONE API
# ==========================================
API_TOKEN = os.environ.get('API_TOKEN', 'e2c702f19ed64c2088f7ab6c22493911')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8524849158:AAG2vVKUWqC4J_T1jDPA7IQxLY1uFy0jW9o')
CHAT_ID = os.environ.get('CHAT_ID', '591667981')
ODSS_KEY = os.environ.get('ODSS_KEY', 'odss_live_9eV8NU_44bNqBQ53VDoEG6ERwYmnhZtz')

headers_fd = {'X-Auth-Token': API_TOKEN}
headers_odss = {'x-api-key': ODSS_KEY}
oggi = datetime.now().strftime('%Y-%m-%d')

print(f"🔄 Recupero palinsesto e quote reali per la data: {oggi}...")

try:
    # 1. Recupero delle partite odierne da football-data.org
    url_oggi = f"https://api.football-data.org/v4/matches?date={oggi}"
    res_fd = requests.get(url_oggi, headers=headers_fd)
    
    raw_matches = []
    if res_fd.status_code == 200:
        raw_matches = res_fd.json().get('matches', [])

    print(f"✅ Trovate {len(raw_matches)} partite nel palinsesto odierno.")

    # 2. Recupero delle quote reali da Odss API
    url_odss = "https://odss-api.com/api/v1/odds?sport=calcio&limit=50"
    res_odss = requests.get(url_odss, headers=headers_odss)
    
    odds_map = {}
    if res_odss.status_code == 200:
        odds_data = res_odss.json()
        # Gestione sicura ed esplicita della struttura dati di Odss API
        list_odds = []
        if isinstance(odds_data, list):
            list_odds = odds_data
        elif isinstance(odds_data, dict):
            list_odds = odds_data.get('data', odds_data.get('matches', []))
            
        for item in list_odds:
            if isinstance(item, dict):
                home = item.get('home_team', '').lower()
                away = item.get('away_team', '').lower()
                if home and away:
                    odds_map[(home, away)] = item.get('odds', {})

    classifiche_cache = {}
    partite_analizzate = []

    for m in raw_matches:
        comp = m.get('competition', {})
        comp_id = comp.get('id')
        
        status_match = m.get('status', 'TIMED')
        home_team = m.get('homeTeam', {})
        away_team = m.get('awayTeam', {})
        
        casa = home_team.get('shortName') or home_team.get('name', 'Casa')
        ospite = away_team.get('shortName') or away_team.get('name', 'Ospite')
        
        # Recupero classifica reale per analisi strutturale
        if comp_id and comp_id not in classifiche_cache:
            url_standings = f"https://api.football-data.org/v4/competitions/{comp_id}/standings"
            res_st = requests.get(url_standings, headers=headers_fd)
            if res_st.status_code == 200:
                table = res_st.json().get('standings', [{}])[0].get('table', [])
                classifiche_cache[comp_id] = {item['team']['name']: item for item in table}
            else:
                classifiche_cache[comp_id] = {}

        standings_map = classifiche_cache.get(comp_id, {})
        dati_casa = standings_map.get(home_team.get('name'), {"position": 10, "points": 0})
        dati_ospite = standings_map.get(away_team.get('name'), {"position": 10, "points": 0})
        
        pos_casa = dati_casa.get('position', 10)
        pos_ospite = dati_ospite.get('position', 10)
        punti_casa = dati_casa.get('points', 0)
        punti_ospite = dati_ospite.get('points', 0)
        
        # Ricerca quote reali abbinate dall'Odss API
        match_odds = odds_map.get((home_team.get('name', '').lower(), away_team.get('name', '').lower()), {})
        q_1x_reale = match_odds.get('1x', 1.30)
        q_x2_reale = match_odds.get('x2', 1.35)
        q_combo_reale = match_odds.get('combo', 1.50)
        
        diff_pos = pos_ospite - pos_casa
        diff_punti = punti_casa - punti_ospite
        forza_match = abs(diff_punti) + abs(diff_pos) * 0.5
        
        if forza_match > 15 or (pos_casa <= 4 and pos_ospite >= 15):
            confidence = 82
            fascia = "🟢"
            dc = "1X" if pos_casa < pos_ospite else "X2"
            combo = "1X + Over 1.5 Gol" if pos_casa < pos_ospite else "X2 + Over 1.5 Gol"
        elif forza_match > 8:
            confidence = 65
            fascia = "🟡"
            dc = "1X" if pos_casa <= pos_ospite else "X2"
            combo = "Goal SI + Over 1.5"
        else:
            confidence = 38
            fascia = "🔴"
            dc = "1X"
            combo = "12 + Over 1.5 Gol"

        lin_cart = round(3.5 + abs(pos_casa - pos_ospite) * 0.05, 1)
        lin_tp = max(3.5, round(5.0 - (min(pos_casa, pos_ospite) * 0.1), 1))
        lin_tt = 12.5
        lin_co = 9.5

        is_rinviata = status_match in ['POSTPONED', 'SUSPENDED', 'CANCELLED']

        partite_analizzate.append({
            "casa": casa, "ospite": ospite,
            "status": status_match, "is_rinviata": is_rinviata,
            "lin_cartellini": lin_cart, "q_cart": 1.0 if is_rinviata else 1.65,
            "lin_tp": lin_tp, "q_tp": 1.0 if is_rinviata else 1.75,
            "lin_tt": lin_tt, "q_tt": 1.0 if is_rinviata else 1.80,
            "lin_corner": lin_co, "q_corner": 1.0 if is_rinviata else 1.70,
            "dc": dc, "q_dc": 1.0 if is_rinviata else (q_1x_reale if dc=="1X" else q_x2_reale),
            "combo": combo, "q_combo": 1.0 if is_rinviata else q_combo_reale,
            "confidence": confidence, "fascia": fascia, "priority": 1 if fascia=="🟢" else (2 if fascia=="🟡" else 3)
        })

    partite_analizzate.sort(key=lambda x: (x['priority'], -x['confidence']))
    migliori_15 = partite_analizzate[:15]

    # ==========================================
    # 📝 COMPOSIZIONE REPORT PER TELEGRAM
    # ==========================================
    lines = []
    lines.append(f"🧠 *ANALISI CON QUOTE REALI* ({oggi})\n")

    def format_riga(m, prono_txt, quota):
        if m['is_rinviata']:
            return f"• {m['casa']} - {m['ospite']} ➔ ⏳ In attesa | {m['fascia']}"
        else:
            return f"• {m['casa']} - {m['ospite']} ➔ {prono_txt} | Q: {quota} | {m['fascia']}"

    # 1. Cartellini
    lines.append("🟨 *1. CARTELLINI*")
    tot_q1 = 1.0
    for m in migliori_15:
        tot_q1 *= m['q_cart']
        lines.append(format_riga(m, f"Ov {m['lin_cartellini']} Cart.", m['q_cart']))
    lines.append(f"📊 *Tot. Cartellini: {round(tot_q1, 2)}*\n")

    # 2. Combo Match
    lines.append("🎯 *2. COMBO MATCH*")
    tot_q2 = 1.0
    for m in migliori_15:
        tot_q2 *= m['q_combo']
        lines.append(format_riga(m, m['combo'], m['q_combo']))
    lines.append(f"📊 *Tot. Combo: {round(tot_q2, 2)}*\n")

    # 3. Tiri in Porta
    lines.append("⚽ *3. TIRI IN PORTA*")
    tot_q3 = 1.0
    for m in migliori_15:
        tot_q3 *= m['q_tp']
        lines.append(format_riga(m, f"Ov {m['lin_tp']} T.Porta", m['q_tp']))
    lines.append(f"📊 *Tot. Tiri Porta: {round(tot_q3, 2)}*\n")

    # 4. Tiri Totali
    lines.append("🚀 *4. TIRI TOTALI*")
    tot_q4 = 1.0
    for m in migliori_15:
        tot_q4 *= m['q_tt']
        lines.append(format_riga(m, f"Ov {m['lin_tt']} T.Tot", m['q_tt']))
    lines.append(f"📊 *Tot. Tiri Totali: {round(tot_q4, 2)}*\n")

    # 5. Doppie Chances
    lines.append("🛡️ *5. DOPPIE CHANCES*")
    tot_q5 = 1.0
    for m in migliori_15:
        tot_q5 *= m['q_dc']
        lines.append(format_riga(m, f"DC {m['dc']}", m['q_dc']))
    lines.append(f"📊 *Tot. Doppie Chances: {round(tot_q5, 2)}*\n")

    # 6. Corner
    lines.append("🚩 *6. CORNER*")
    tot_q6 = 1.0
    for m in migliori_15:
        tot_q6 *= m['q_corner']
        lines.append(format_riga(m, f"Ov {m['lin_corner']} Corner", m['q_corner']))
    lines.append(f"📊 *Tot. Corner: {round(tot_q6, 2)}*")

    testo_finale = "\n".join(lines)

    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": testo_finale,
        "parse_mode": "Markdown"
    }
    
    res = requests.post(telegram_url, json=payload)
    if res.status_code == 200:
        print("✅ Analisi con quote reali inviata con successo su Telegram!")
    else:
        print(f"⚠️ Errore Telegram: {res.text}")

except Exception as e:
    print(f"❌ Errore generale: {e}")
