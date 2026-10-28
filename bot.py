import os
import requests
import random
from datetime import datetime

# ==========================================
# 🔑 CONFIGURAZIONE
# ==========================================
API_TOKEN = os.environ.get('API_TOKEN', 'e2c702f19ed64c2088f7ab6c22493911')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8524849158:AAG2vVKUWqC4J_T1jDPA7IQxLY1uFy0jW9o')
CHAT_ID = os.environ.get('CHAT_ID', '591667981')

headers = {'X-Auth-Token': API_TOKEN}
oggi = datetime.now().strftime('%Y-%m-%d')

print(f"🔄 Recupero le partite dalle 00:00 alle 23:59 per la data: {oggi}...")

try:
    url_oggi = f"https://api.football-data.org/v4/matches?date={oggi}"
    res = requests.get(url_oggi, headers=headers)
    
    raw_matches = []
    if res.status_code == 200:
        raw_matches = res.json().get('matches', [])

    print(f"✅ Trovate {len(raw_matches)} partite nel palinsesto odierno.")

    partite_oggi = []
    for m in raw_matches:
        status_match = m.get('status', 'TIMED')
        
        casa = m.get('homeTeam', {}).get('shortName') or m.get('homeTeam', {}).get('name', 'Casa')
        ospite = m.get('awayTeam', {}).get('shortName') or m.get('awayTeam', {}).get('name', 'Ospite')
        
        seed_m = sum(ord(c) for c in (casa + ospite))
        random.seed(seed_m)
        
        g_c, g_o = round(random.uniform(1.2, 2.4), 1), round(random.uniform(1.3, 2.6), 1)
        tp_c, tp_o = round(random.uniform(3.5, 6.2), 1), round(random.uniform(2.8, 5.5), 1)
        tt_c, tt_o = round(random.uniform(11.0, 16.5), 1), round(random.uniform(9.5, 14.5), 1)
        co_c, co_o = round(random.uniform(4.0, 7.0), 1), round(random.uniform(3.5, 6.0), 1)
        
        confidence = random.randint(15, 95)
        
        # Sostituzione delle fasce con i semafori
        if confidence >= 70:
            fascia = "🟢 SEMAFORO VERDE"
            priority = 1
        elif confidence >= 40:
            fascia = "🟡 SEMAFORO GIALLO"
            priority = 2
        else:
            fascia = "🔴 SEMAFORO ROSSO"
            priority = 3
            
        prob_1x = round(random.uniform(1.18, 1.42), 2)
        prob_x2 = round(random.uniform(1.25, 1.55), 2)
        
        pool_combo = [
            ("1X + Over 1.5 Gol", 1.48), ("X2 + Over 1.5 Gol", 1.55),
            ("Goal SI + Over 1.5", 1.72), ("12 + Over 1.5 Gol", 1.38),
            ("1X + Under 3.5 Gol", 1.42), ("X2 + Under 3.5 Gol", 1.46)
        ]
        scelta_combo, quota_combo = random.choice(pool_combo)

        raw_cart = g_c + g_o + 0.5
        lin_cart = round(raw_cart * 2) / 2
        
        raw_tp = tp_c + tp_o - 0.5
        lin_tp = max(3.0, round(raw_tp * 2) / 2)
        
        raw_tt = tt_c + tt_o - 1.5
        lin_tt = round(raw_tt * 2) / 2
        
        raw_co = co_c + co_o - 0.5
        lin_co = max(7.0, round(raw_co * 2) / 2)
        
        dc = "1X" if len(casa) % 2 != 0 else "X2"
        q_dc = prob_1x if dc == "1X" else prob_x2

        is_rinviata = status_match in ['POSTPONED', 'SUSPENDED', 'CANCELLED']

        partite_oggi.append({
            "casa": casa, "ospite": ospite,
            "status": status_match, "is_rinviata": is_rinviata,
            "lin_cartellini": lin_cart, "q_cart": 1.0 if is_rinviata else round(1.50 + (lin_cart * 0.04), 2),
            "lin_tp": lin_tp, "q_tp": 1.0 if is_rinviata else round(1.55 + (lin_tp * 0.03), 2),
            "lin_tt": lin_tt, "q_tt": 1.0 if is_rinviata else round(1.60 + (lin_tt * 0.02), 2),
            "lin_corner": lin_co, "q_corner": 1.0 if is_rinviata else round(1.55 + (lin_co * 0.025), 2),
            "dc": dc, "q_dc": 1.0 if is_rinviata else q_dc,
            "combo": scelta_combo, "q_combo": 1.0 if is_rinviata else quota_combo,
            "confidence": confidence, "fascia": fascia, "priority": priority
        })

    partite_oggi.sort(key=lambda x: (x['priority'], -x['confidence']))
    migliori_15 = partite_oggi[:15]

    # ==========================================
    # 📝 COSTRUZIONE DELLE 6 SCHEDINE A GRUPPI
    # ==========================================
    lines = []
    lines.append(f"🎯 *6 SCHEDINE GIORNALIERE (TOP 15 MONDIALI)* ({oggi})\n")

    def format_riga(m, pronostico_txt, quota):
        if m['is_rinviata']:
            return f"{m['casa']} - {m['ospite']} ➔ ⏳ *In attesa (Rinviata/Sospesa)* | {m['fascia']}"
        else:
            return f"{m['casa']} - {m['ospite']} ➔ {pronostico_txt} | *Quota: {quota}* | {m['fascia']} ({m['confidence']}%)"

    # 1. Cartellini
    lines.append("🟨 *1. SCHEDINA CARTELLINI*")
    tot_q1 = 1.0
    for i, m in enumerate(migliori_15, 1):
        tot_q1 *= m['q_cart']
        prono = f"Over {m['lin_cartellini']} Cartellini"
        lines.append(f"{i}. {format_riga(m, prono, m['q_cart'])}")
    lines.append(f"📊 *Quota Totale Cartellini: {round(tot_q1, 2)}*\n")

    # 2. Combo Match
    lines.append("🎯 *2. SCHEDINA COMBO MATCH*")
    tot_q2 = 1.0
    for i, m in enumerate(migliori_15, 1):
        tot_q2 *= m['q_combo']
        lines.append(f"{i}. {format_riga(m, m['combo'], m['q_combo'])}")
    lines.append(f"📊 *Quota Totale Combo: {round(tot_q2, 2)}*\n")

    # 3. Tiri in Porta
    lines.append("⚽ *3. SCHEDINA TIRI IN PORTA*")
    tot_q3 = 1.0
    for i, m in enumerate(migliori_15, 1):
        tot_q3 *= m['q_tp']
        prono = f"Over {m['lin_tp']} Tiri in Porta"
        lines.append(f"{i}. {format_riga(m, prono, m['q_tp'])}")
    lines.append(f"📊 *Quota Totale Tiri in Porta: {round(tot_q3, 2)}*\n")

    # 4. Tiri Totali
    lines.append("🚀 *4. SCHEDINA TIRI TOTALI*")
    tot_q4 = 1.0
    for i, m in enumerate(migliori_15, 1):
        tot_q4 *= m['q_tt']
        prono = f"Over {m['lin_tt']} Tiri Totali"
        lines.append(f"{i}. {format_riga(m, prono, m['q_tt'])}")
    lines.append(f"📊 *Quota Totale Tiri Totali: {round(tot_q4, 2)}*\n")

    # 5. Doppie Chances
    lines.append("🛡️ *5. SCHEDINA DOPPIE CHANCES*")
    tot_q5 = 1.0
    for i, m in enumerate(migliori_15, 1):
        tot_q5 *= m['q_dc']
        prono = f"Doppia Chance: {m['dc']}"
        lines.append(f"{i}. {format_riga(m, prono, m['q_dc'])}")
    lines.append(f"📊 *Quota Totale Doppie Chances: {round(tot_q5, 2)}*\n")

    # 6. Corner
    lines.append("🚩 *6. SCHEDINA CORNER*")
    tot_q6 = 1.0
    for i, m in enumerate(migliori_15, 1):
        tot_q6 *= m['q_corner']
        prono = f"Over {m['lin_corner']} Corner"
        lines.append(f"{i}. {format_riga(m, prono, m['q_corner'])}")
    lines.append(f"📊 *Quota Totale Corner: {round(tot_q6, 2)}*")

    testo_finale = "\n".join(lines)

    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": testo_finale,
        "parse_mode": "Markdown"
    }
    
    res = requests.post(telegram_url, json=payload)
    if res.status_code == 200:
        print("✅ Schedine con semafori inviate con successo su Telegram!")
    else:
        print(f"⚠️ Errore Telegram: {res.text}")

except Exception as e:
    print(f"❌ Errore generale: {e}")
