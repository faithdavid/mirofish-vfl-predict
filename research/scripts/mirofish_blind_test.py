import json
import os
import requests
import re
from collections import defaultdict

# --- CONFIG ---
MIRO_API = "http://localhost:5001"
H2H_MODEL = "h2h_model.json"
TEST_COUNT = 10

def get_h2h(h, a, db):
    key = f"{h.strip().upper()} VS {a.strip().upper()}"
    return db.get(key, {"HOME_RATE": 0.33, "DRAW_RATE": 0.33, "AWAY_RATE": 0.33, "TOTAL": 0})

def simulate_swarm(fixture, oh, od, oa, h2h):
    prompt = f"""
    ### REALITY SEED: {fixture['homeTeam']} vs {fixture['awayTeam']}
    - ODDS: H:{oh}, D:{od}, A:{oa}
    - H2H WIN RATE: H:{h2h['HOME_RATE']:.1%}, D:{h2h['DRAW_RATE']:.1%}, A:{h2h['AWAY_RATE']:.1%}
    - SAMPLES: {h2h['TOTAL']}
    ### ROLE: Expert Swarm Analysis. Choose ONLY ONE: HOME, DRAW, or AWAY.
    """
    
    api_key = "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"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=15)
        res = r.json()
        if 'choices' in res:
            reply = res['choices'][0]['message']['content'].upper()
            verdict = "HOME" if "HOME" in reply else ("AWAY" if "AWAY" in reply else "DRAW")
            return verdict, reply[:80] + "..."
        return ("HOME" if oh < oa else "AWAY"), "Fallback (API Error)"
    except:
        return ("HOME" if oh < oa else "AWAY"), "Fallback (Exception)"

def main():
    print("🧠 MiroFish Blind Test: Starting...")
    h2h_db = json.load(open(H2H_MODEL, 'r', encoding='utf-8'))
    
    # Simple harvesting
    odds_data = []
    res_data = {}
    for folder in ['extracted_odds', 'extracted_results']:
        if not os.path.exists(folder): continue
        for f in os.listdir(folder):
            path = os.path.join(folder, f)
            content = open(path, 'r', encoding='utf-8').read()
            blocks = re.split(r'===== MATCH #\d+', content)
            for b in blocks:
                jm = re.search(r'\{[\s\S]*\}', b)
                if not jm: continue
                try:
                    data = json.loads(jm.group())
                    if "data" in data and "current" in data["data"]:
                        s = data["data"]["current"].get("seasonName", "unknown").upper()
                        d = str(data["data"]["current"].get("matchDay", "unknown"))
                        for r in data["data"].get("results", []):
                            res_data[(s, d, r['homeTeam'].upper(), r['awayTeam'].upper())] = r.get('fullTime')
                    elif "data" in data and "events" in data["data"]:
                        s = data["data"].get("seasonName", "unknown").upper()
                        d = str(data["data"].get("matchDay", "unknown"))
                        for e in data["data"]["events"]:
                            e['_s'], e['_d'] = s, d
                            odds_data.append(e)
                except: continue

    samples = []
    for o in odds_data:
        h, a = o['homeTeam'].upper(), o['awayTeam'].upper()
        res = res_data.get((o['_s'], o['_d'], h, a))
        if res: samples.append((o, res))
        if len(samples) >= TEST_COUNT: break

    report = ["# 🏁 MiroFish Blind Test Results", "", "| Fixture | Debate | Verdict | Reality | Acc |", "| :-- | :-- | :-- | :-- | :-- |"]
    correct = 0
    for o, res_score in samples:
        m1x2 = next(m for m in o['markets'] if m['id'] == 1)
        oh = float(next(oc['odds'] for oc in m1x2['outcomes'] if oc['id'] == '1'))
        od = float(next(oc['odds'] for oc in m1x2['outcomes'] if oc['id'] == '2'))
        oa = float(next(oc['odds'] for oc in m1x2['outcomes'] if oc['id'] == '3'))
        
        h2h = get_h2h(o['homeTeam'], o['awayTeam'], h2h_db)
        verdict, debate = simulate_swarm(o, oh, od, oa, h2h)
        
        try:
            h, a = map(int, res_score.replace(' ', '').split(':'))
            real_winner = "HOME" if h > a else ("AWAY" if a > h else "DRAW")
        except: real_winner = "UNKNOWN"
        
        is_ok = verdict == real_winner
        if is_ok: correct += 1
        report.append(f"| {o['homeTeam']} vs {o['awayTeam']} | {debate} | **{verdict}** | {real_winner} | {'✅' if is_ok else '❌'} |")

    accuracy = (correct / len(samples)) * 100
    report.append(f"\n### FINAL ACCURACY: {accuracy:.1f}%")
    with open('mirofish_blind_test_results.md', 'w', encoding='utf-8') as f:
        f.write("\n".join(report))
    print(f"Done. Accuracy: {accuracy:.1f}%")

if __name__ == "__main__":
    main()
