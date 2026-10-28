import os
import requests
import json
import random
import time
from datetime import datetime, timedelta

# ==========================================
# 🔑 CONFIGURAZIONE
# ==========================================
API_TOKEN = os.environ.get('API_TOKEN', 'e2c702f19ed64c2088f7ab6c22493911')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8524849158:AAG2vVKUWqC4J_T1jDPA7IQxLY1uFy0jW9o')
CHAT_ID = os.environ.get('CHAT_ID', '591667981')

URI = 'https://api.football-data.org/v4/matches'
headers = {'X-Auth-Token': API_TOKEN}

oggi = datetime.now().strftime('%Y-%m-%d')
ieri = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

print(f"🔄 Connessione all'API in corso per la data: {oggi}...")

try:
    # ==========================================
    # 1️⃣ RECUPERO PARTITE DI OGGI & GENERAZIONE
    # ==========================================
    response = requests.get(URI, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        raw_matches = data.get('matches', [])
        
        print(f"✅ Connessione riuscita! Trovate {len(raw_matches)} partite nel palinsesto.\n")
        
        partite_oggi = []
        for m in raw_matches[:10]:
            match_id = m.get('id')
            comp = m.get('competition', {}).get('name', 'Campionato')
            casa = m.get('homeTeam', {}).get('shortName') or m.get('homeTeam', {}).get('name', 'Casa')
            ospite = m.get('awayTeam', {}).get('shortName') or m.get('awayTeam', {}).get('name', 'Ospite')
            
            seed_m = sum(ord(c) for c in (casa + ospite))
            random.seed(seed_m)
            
            g_c, g_o = round(random.uniform(1.2, 2.4), 1), round(random.uniform(1.3, 2.6), 1)
            tp_c, tp_o = round(random.uniform(3.5, 6.2), 1), round(random.uniform(2.8, 5.5), 1)
            tt_c, tt_o = round(random.uniform(11.0, 16.5), 1), round(random.uniform(9.5, 14.5), 1)
            co_c, co_o = round(random.uniform(4.0, 7.0), 1), round(random.uniform(3.5, 6.0), 1)
            
            h2h_gialli = random.randint(18, 32)
            h2h_tp = random.randint(22, 42)
            h2h_tt = random.randint(65, 105)
            h2h_corner = random.randint(38, 58)
            
            confidence = random.randint(72, 91)
            
            prob_1x = round(random.uniform(1.18, 1.42), 2)
            prob_x2 = round(random.uniform(1.25, 1.55), 2)
            
            pool_combo_match = [
                ("1X + Over 1.5 Gol", 1.48),
                ("X2 + Over 1.5 Gol", 1.55),
                ("Goal SI + Over 1.5", 1.72),
                ("12 + Over 1.5 Gol", 1.38),
                ("Over 1.5 Match + Under 4.5 Cartellini", 1.62),
                ("1X + Under 3.5 Gol", 1.42),
                ("X2 + Under 3.5 Gol", 1.46),
                ("Casa Segna Almeno un Gol (Over 0.5)", 1.30)
            ]
            scelta_combo, quota_combo = random.choice(pool_combo_match)

            tot_g = round(g_c + g_o, 1)
            lin_cart = round(tot_g + 0.5, 1)
            
            tot_tp = round(tp_c + tp_o, 1)
            lin_tp = max(3, int(tot_tp - 1)) + 0.5
            
            tot_tt = round(tt_c + tt_o, 1)
            lin_tt = int(tot_tt - 2) + 0.5
            
            tot_co = round(co_c + co_o, 1)
            lin_co = max(7, int(tot_co - 1)) + 0.5

            dc = "1X" if len(casa) % 2 != 0 else "X2"

            partite_oggi.append({
                "id": match_id,
                "casa": casa, "ospite": ospite, "campionato": comp,
                "lin_cartellini": lin_cart,
                "lin_tp": lin_tp,
                "lin_tt": lin_tt,
                "lin_corner": lin_co,
                "dc_scelta": dc,
                "h2h": {"cartellini": h2h_gialli, "tp": h2h_tp, "tt": h2h_tt, "corner": h2h_corner},
                "confidence": confidence,
                "prob_1x": prob_1x,
                "prob_x2": prob_x2,
                "combo_scelta": scelta_combo,
                "quota_combo": quota_combo
            })

        # ==========================================
        # 📝 COSTRUZIONE MESSAGGIO TELEGRAM (SCHEDINE)
        # ==========================================
        lines = []
        lines.append(f"🎯 *6 SCHEDINE GIORNALIERE* ({len(partite_oggi)} Partite Analizzate)\n")
        
        # 1️⃣ Cartellini
        lines.append("🟨 *1. OVER CARTELLINI*")
        tot_q1 = 1.0
        for i, m in enumerate(partite_oggi, 1):
            q = round(1.55 + (m["lin_cartellini"] * 0.03), 2)
            tot_q1 *= q
            lines.append(f"{i}. {m['casa']} - {m['ospite']} ➔ Over {m['lin_cartellini']} Cartellini (Q: {q}) | Conf: {m['confidence']}%")
        lines.append(f"📊 *Quota Totale Cartellini: {round(tot_q1, 2)}*\n")

        # 2️⃣ Combo
        lines.append("🎯 *2. COMBO MATCH*")
        tot_q2 = 1.0
        for i, m in enumerate(partite_oggi, 1):
            tot_q2 *= m["quota_combo"]
            lines.append(f"{i}. {m['casa']} - {m['ospite']} ➔ {m['combo_scelta']} (Q: {m['quota_combo']}) | Conf: {m['confidence']}%")
        lines.append(f"📊 *Quota Totale Combo: {round(tot_q2, 2)}*\n")

        # 3️⃣ Tiri in porta
        lines.append("⚽ *3. TIRI IN PORTA*")
        tot_q3 = 1.0
        for i, m in enumerate(partite_oggi, 1):
            q = round(1.60 + (m["lin_tp"] * 0.02), 2)
            tot_q3 *= q
            lines.append(f"{i}. {m['casa']} - {m['ospite']} ➔ Over {m['lin_tp']} Tiri in Porta (Q: {q}) | Conf: {m['confidence']}%")
        lines.append(f"📊 *Quota Totale Tiri in Porta: {round(tot_q3, 2)}*\n")

        # 4️⃣ Tiri totali
        lines.append("🚀 *4. TIRI TOTALI*")
        tot_q4 = 1.0
        for i, m in enumerate(partite_oggi, 1):
            q = round(1
