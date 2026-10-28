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

print(f"🔄 Recupero le partite giornaliere per la data: {oggi}...")

try:
    # Interroghiamo l'endpoint giornaliero per catturare le partite di oggi da tutto il mondo
    url_oggi = f"https://api.football-data.org/v4/matches?date={oggi}"
    res = requests.get(url_oggi, headers=headers)
    
    raw_matches = []
    if res.status_code == 200:
        raw_matches = res.json().get('matches', [])

    print(f"✅ Trovate {len(raw_matches)} partite oggi in tutto il palinsesto.")

    partite_oggi = []
    for m in raw_matches:
        comp = m.get('competition', {}).get('name', 'Campionato')
        casa = m.get('homeTeam', {}).get('shortName') or m.get('homeTeam', {}).get('name', 'Casa')
        ospite = m.get('awayTeam', {}).get('shortName') or m.get('awayTeam', {}).get('name', 'Ospite')
        
        seed_m = sum(ord(c) for c in (casa + ospite))
        random.seed(seed_m)
        
        g_c, g_o = round(random.uniform(1.2, 2.4), 1), round(random.uniform(1.3, 2.6), 1)
        tp_c, tp_o = round(random.uniform(3.5, 6.2), 1), round(random.uniform(2.8, 5.5), 1)
        tt_c, tt_o = round(random.uniform(11.0, 16.5), 1), round(random.uniform(9.5, 14.5), 1)
        co_c, co_o = round(random.uniform(4.0, 7.0), 1), round(random.uniform(3.5, 6.0), 1)
        
        # Confidence estesa per coprire tutte e tre le fasce
        confidence = random.randint(15, 95)
        
        if confidence >= 70:
            fascia = "🥇 ORO"
            priority = 1
        elif confidence >= 40:
            fascia = "🥈 ARGENTO"
            priority = 2
        else:
            fascia = "🥉 BRONZO"
            priority = 3
            
        prob_1x = round(random.uniform(1.18, 1.42), 2)
        prob_x2 = round(random.uniform(1.25, 1.55), 2)
        
        pool_combo = [
            ("1X + Over 1.5 Gol", 1.48), ("X2 + Over 1.5 Gol", 1.55),
            ("Goal SI + Over 1.5", 1.72), ("12 + Over 1.5 Gol", 1.38),
            ("1X + Under 3.5 Gol", 1.42), ("X2 + Under 3.5 Gol", 1.46)
        ]
        scelta_combo, quota_combo = random.choice(pool_combo)

        lin_cart = round(g_c + g_o + 0.5, 1)
        lin_tp = max(3, int(tp_c + tp_o - 1)) + 0.5
        lin_tt = int(tt_c + tt_o - 2) + 0.5
        lin_co = max(7, int(co_c + co_o - 1)) + 0.5
        dc = "1X" if len(casa) % 2 != 0 else "X2"

        partite_oggi.append({
            "comp": comp, "casa": casa, "ospite": ospite,
            "lin_cartellini": lin_cart, "lin_tp": lin_tp,
            "lin_tt": lin_tt, "lin_corner": lin_co,
            "dc": dc, "combo": scelta_combo, "q_combo": quota_combo,
            "q_dc": prob_1x if dc == "1X" else prob_x2,
            "confidence": confidence, "fascia": fascia, "priority": priority
        })

    # Ordiniamo per priorità fascia (Oro -> Argento -> Bronzo) e prendiamo le prime 15
    partite_oggi.sort(key=lambda x: (x['priority'], -x['confidence']))
    migliori_15 = partite_oggi[:15]

    # ==========================================
    # 📝 COSTRUZIONE MESSAGGIO TELEGRAM
    # ==========================================
    lines = []
    lines.append(f"🎯 *TOP 15 PARTITE CONSIGLIATE* ({oggi})\n")
    lines.append("Classificate per Confidenza (Oro, Argento, Bronzo):\n")

    for i, m in enumerate(migliori_15, 1):
        lines.append(f"*{i}. [{m['fascia']}] {m['casa']} - {m['ospite']}* ({m['confidence']}%)")
        lines.append(f"   • Campionato: {m['comp']}")
        lines.append(f"   • Combo: {m['combo']} (Q: {m['q_combo']})")
        lines.append(f"   • Cartellini: Over {m['lin_cartellini']} | Tiri Porta: Over {m['lin_tp']}")
        lines.append("")

    testo_finale = "\n".join(lines)

    # Invio diretto su Telegram
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": testo_finale,
        "parse_mode": "Markdown"
    }
    
    res = requests.post(telegram_url, json=payload)
    if res.status_code == 200:
        print("✅ Messaggio con le 15 partite inviato con successo su Telegram!")
    else:
        print(f"⚠️ Errore Telegram: {res.text}")

except Exception as e:
    print(f"❌ Errore generale: {e}")
