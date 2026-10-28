import os
import requests
json
from datetime import datetime

# ==========================================
# 🔑 CONFIGURAZIONE API
# ==========================================
API_TOKEN = os.environ.get('API_TOKEN', 'e2c702f19ed64c2088f7ab6c22493911')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8524849158:AAG2vVKUWqC4J_T1jDPA7IQxLY1uFy0jW9o')
CHAT_ID = os.environ.get('CHAT_ID', '591667981')

headers_fd = {'X-Auth-Token': API_TOKEN}
oggi = datetime.now().strftime('%Y-%m-%d')

print(f"🔄 Recupero palinsesto e analisi confidenza basata su classifica per la data: {oggi}...")

try:
    # 1. Recupero delle partite odierne da football-data.org
    url_oggi = f"https://api.football-data.org/v4/matches?date={oggi}"
    res_fd = requests.get(url_oggi, headers=headers_fd)
    
    raw_matches = []
    if res_fd.status_code == 200:
        raw_matches = res_fd.json().get('matches', [])

    print(f"✅ Trovate {len(raw_matches)} partite nel palinsesto odierno.")

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
        
        diff_pos = pos_ospite - pos_casa
        diff_punti = punti_casa - punti_ospite
        forza_match = abs(diff_punti) + abs(diff_pos) * 0.5
        
        # Calcolo analitico della confidenza in base ai valori reali
        if forza_match > 15 or (pos_casa <= 4 and pos_ospite >= 15):
            confidence = 85
            fascia = "🟢"
            dc = "1X" if pos_casa < pos_ospite else "X2"
            combo = "1X + Over 1.5 Gol" if pos_casa < pos_ospite else "X2 + Over 1.5 Gol"
        elif forza_match > 8:
            confidence = 68
            fascia = "🟡"
            dc = "1X" if pos_casa <= pos_ospite else "X2"
            combo = "Goal SI + Over 1.5"
        else:
            confidence = 45
            fascia = "🔴"
            dc = "1X"
            combo = "12 + Over 1.5 Gol"

        # --- LOGICA DI INCREMENTO (.50 + 1.0) ---
        base_cart = 2.5
        lin_cart = base_cart + int(abs(pos_casa - pos_ospite) % 3)

        base_tp = 4.5
        lin_tp = base_tp + int((12 - min(pos_casa, pos_ospite)) % 4)

        base_tt = 21.5
        lin_tt = base_tt + int(abs(pos_casa - pos_ospite) % 6)

        base_co = 8.5
        lin_co = base_co + int(forza_match % 4)

        is_rinviata = status_match in ['POSTPONED', 'SUSPENDED', 'CANCELLED']

        partite_analizzate.append({
            "casa": casa, "ospite": ospite,
            "status": status_match, "is_rinviata": is_rinviata,
            "lin_cartellini": lin_cart,
            "lin_tp": lin_tp,
            "lin_tt": lin_tt,
            "lin_corner": lin_co,
            "dc": dc,
            "combo": combo,
            "confidence": 0 if is_rinviata else confidence, 
            "fascia": fascia, 
            "priority": 1 if fascia=="🟢" else (2 if fascia=="🟡" else 3)
        })

    partite_analizzate.sort(key=lambda x: (x['priority'], -x['confidence']))
    migliori_15 = partite_analizzate[:15]

    # ==========================================
    # 📝 COMPOSIZIONE REPORT PER TELEGRAM (SOLO CONFIDENZA)
    # ==========================================
    lines = []
    lines.append(f"🧠 *ANALISI STRUTTURALE & CONFIDENZA* ({oggi})\n")

    def format_riga(m, prono_txt):
        if m['is_rinviata']:
            return f"• {m['casa']} - {m['ospite']} ➔ ⏳ In attesa | {m['fascia']}"
        else:
            return f"• {m['casa']} - {m['ospite']} ➔ {prono_txt} | {m['fascia']} *({m['confidence']}%)*"

    # 1. Cartellini
    lines.append("🟨 *1. CARTELLINI*")
    for m in migliori_15:
        lines.append(format_riga(m, f"Ov {m['lin_cartellini']:.2f} Cart."))
    lines.append("")

    # 2. Combo Match
    lines.append("🎯 *2. COMBO MATCH*")
    for m in migliori_15:
        lines.append(format_riga(m, m['combo']))
    lines.append("")

    # 3. Tiri in Porta
    lines.append("⚽ *3. TIRI IN PORTA*")
    for m in migliori_15:
        lines.append(format_riga(m, f"Ov {m['lin_tp']:.2f} T.Porta"))
    lines.append("")

    # 4. Tiri Totali
    lines.append("🚀 *4. TIRI TOTALI*")
    for m in migliori_15:
        lines.append(format_riga(m, f"Ov {m['lin_tt']:.2f} T.Tot"))
    lines.append("")

    # 5. Doppie Chances
    lines.append("🛡️ *5. DOPPIE CHANCES*")
    for m in migliori_15:
        lines.append(format_riga(m, f"DC {m['dc']}"))
    lines.append("")

    # 6. Corner
    lines.append("🚩 *6. CORNER*")
    for m in migliori_15:
        lines.append(format_riga(m, f"Ov {m['lin_corner']:.2f} Corner"))

    testo_finale = "\n".join(lines)

    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": testo_finale,
        "parse_mode": "Markdown"
    }
    
    res = requests.post(telegram_url, json=payload)
    if res.status_code == 200:
        print("✅ Analisi basata su confidenza percentuale inviata con successo su Telegram!")
    else:
        print(f"⚠️ Errore Telegram: {res.text}")

except Exception as e:
    print(f"❌ Errore generale: {e}")
