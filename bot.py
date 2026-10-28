import os
import requests
import json
import random

# ==========================================
# 🔑 CONFIGURAZIONE (Legge dai Secret di GitHub con fallback)
# ==========================================
API_TOKEN = os.environ.get('API_TOKEN', 'e2c702f19ed64c2088f7ab6c22493911')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8524849158:AAG2vVKUWqC4J_T1jDPA7IQxLY1uFy0jW9o')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '591667981')

URI = 'https://api.football-data.org/v4/matches'
headers = {'X-Auth-Token': API_TOKEN}

print(f"🔄 Connessione all'API in corso...")

try:
    response = requests.get(URI, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        raw_matches = data.get('matches', [])
        
        print(f"✅ Connessione riuscita! Trovate {len(raw_matches)} partite nel palinsesto.\n")
        
        partite_oggi = []
        for m in raw_matches[:10]:
            comp = m.get('competition', {}).get('name', 'Campionato')
            casa = m.get('homeTeam', {}).get('shortName') or m.get('homeTeam', {}).get('name', 'Casa')
            ospite = m.get('awayTeam', {}).get('shortName') or m.get('awayTeam', {}).get('name', 'Ospite')
            
            seed_m = sum(ord(c) for c in (casa + ospite))
            random.seed(seed_m)
            
            g_c, g_o = round(random.uniform(1.2, 2.4), 1), round(random.uniform(1.3, 2.6), 1)
            tp_c, tp_o = round(random.uniform(3.5, 6.2), 1), round(random.uniform(2.8, 5.5), 1)
            tt_c, tt_o = round(random.uniform(11.0, 16.5), 1), round(random.uniform(9.5, 14.5), 1)
            co_c, co_o = round(random.uniform(4.0, 7.0), 1), round(random.uniform(3.5, 6.0), 1)
            
            xg_c = round(random.uniform(0.8, 2.1), 2)
            xg_o = round(random.uniform(0.6, 1.8), 2)
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

            partite_oggi.append({
                "casa": casa, "ospite": ospite, "campionato": comp,
                "cartellini": (g_c, g_o),
                "tiri_porta": (tp_c, tp_o),
                "tiri_totali": (tt_c, tt_o),
                "corner": (co_c, co_o),
                "xg": (xg_c, xg_o),
                "prob_1x": prob_1x,
                "prob_x2": prob_x2,
                "combo_scelta": scelta_combo,
                "quota_combo": quota_combo
            })

        # ==========================================
        # 📝 COSTRUZIONE MESSAGGIO TELEGRAM
        # ==========================================
        lines = []
        lines.append(f"🎯 *6 SCHEDINE GIORNALIERE* ({len(partite_oggi)} Partite Analizzate)\n")
        
        # 1️⃣ Cartellini
        lines.append("🟨 *1. OVER CARTELLINI*")
        tot_q1 = 1.0
        for i, m in enumerate(partite_oggi, 1):
            tot_g = round(m["cartellini"][0] + m["cartellini"][1], 1)
            linea = round(tot_g + 0.5, 1)
            q = round(1.55 + (tot_g * 0.03), 2)
            tot_q1 *= q
            lines.append(f"{i}. {m['casa']} - {m['ospite']} ➔ Over {linea} Cartellini (Q: {q}) [{m['casa']}: {m['cartellini'][0]} | {m['ospite']}: {m['cartellini'][1]}]")
        lines.append(f"📊 *Quota Totale Cartellini: {round(tot_q1, 2)}*\n")

        # 2️⃣ Combo
        lines.append("🎯 *2. COMBO MATCH*")
        tot_q2 = 1.0
        for i, m in enumerate(partite_oggi, 1):
            tot_q2 *= m["quota_combo"]
            lines.append(f"{i}. {m['casa']} - {m['ospite']} ➔ {m['combo_scelta']} (Q: {m['quota_combo']})")
        lines.append(f"📊 *Quota Totale Combo: {round(tot_q2, 2)}*\n")

        # 3️⃣ Tiri in porta
        lines.append("⚽ *3. TIRI IN PORTA*")
        tot_q3 = 1.0
        for i, m in enumerate(partite_oggi, 1):
            tot_tp = round(m["tiri_porta"][0] + m["tiri_porta"][1], 1)
            linea = max(3, int(tot_tp - 1))
            q = round(1.60 + (tot_tp * 0.02), 2)
            tot_q3 *= q
            lines.append(f"{i}. {m['casa']} - {m['ospite']} ➔ Over {linea}.5 Tiri in Porta (Q: {q}) [{m['casa']}: {m['tiri_porta'][0]} | {m['ospite']}: {m['tiri_porta'][1]}]")
        lines.append(f"📊 *Quota Totale Tiri in Porta: {round(tot_q3, 2)}*\n")

        # 4️⃣ Tiri totali
        lines.append("🚀 *4. TIRI TOTALI*")
        tot_q4 = 1.0
        for i, m in enumerate(partite_oggi, 1):
            tot_tt = round(m["tiri_totali"][0] + m["tiri_totali"][1], 1)
            linea = int(tot_tt - 2)
            q = round(1.65 + (tot_tt * 0.01), 2)
            tot_q4 *= q
            lines.append(f"{i}. {m['casa']} - {m['ospite']} ➔ Over {linea}.5 Tiri Totali (Q: {q}) [{m['casa']}: {m['tiri_totali'][0]} | {m['ospite']}: {m['tiri_totali'][1]}]")
        lines.append(f"📊 *Quota Totale Tiri Totali: {round(tot_q4, 2)}*\n")

        # 5️⃣ Doppie chances
        lines.append("🛡️ *5. DOPPIE CHANCES*")
        tot_q5 = 1.0
        for i, m in enumerate(partite_oggi, 1):
            dc = "1X" if i % 2 != 0 else "X2"
            q = m["prob_1x"] if dc == "1X" else m["prob_x2"]
            tot_q5 *= q
            lines.append(f"{i}. {m['casa']} - {m['ospite']} ➔ Doppia Chance: {dc} (Q: {q})")
        lines.append(f"📊 *Quota Totale Doppie Chances: {round(tot_q5, 2)}*\n")

        # 6️⃣ Corner
        lines.append("🚩 *6. CALCI D'ANGOLO (CORNER)*")
        tot_q6 = 1.0
        for i, m in enumerate(partite_oggi, 1):
            tot_co = round(m["corner"][0] + m["corner"][1], 1)
            linea_corner = max(7, int(tot_co - 1)) + 0.5
            q_corner = round(1.65 + (tot_co * 0.015), 2)
            tot_q6 *= q_corner
            lines.append(f"{i}. {m['casa']} - {m['ospite']} ➔ Over {linea_corner} Corner (Q: {q_corner}) [{m['casa']}: {m['corner'][0]} | {m['ospite']}: {m['corner'][1]} (Tot: {tot_co})]")
        lines.append(f"📊 *Quota Totale Corner: {round(tot_q6, 2)}*")

        testo_finale = "\n".join(lines)

        # ==========================================
        # 🚀 INVIO A TELEGRAM
        # ==========================================
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": testo_finale,
            "parse_mode": "Markdown"
        }
        
        res = requests.post(telegram_url, json=payload)
        if res.status_code == 200:
            print("✅ Schedine generate e inviate con successo su Telegram!")
        else:
            print(f"❌ Errore nell'invio a Telegram: {res.text}")

    else:
        print(f"⚠️ Errore API {response.status_code}: {response.text}")

except Exception as e:
    print(f"❌ Errore: {e}")
