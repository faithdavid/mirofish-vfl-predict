import os
import json
import re
from collections import defaultdict

def parse_msport_json(content):
    blocks = re.split(r'===== MATCH #\d+', content)
    found = []
    for b in blocks:
        json_match = re.search(r'\{[\s\S]*\}', b)
        if not json_match: continue
        try:
            data = json.loads(json_match.group())
            # Results JSON
            if "data" in data and "current" in data["data"]:
                results_list = data["data"].get("results", [])
                for res in results_list:
                    found.append(res)
            # Odds JSON might have scores too if it's a 'prev' match
            elif "data" in data and "events" in data["data"]:
                for ev in data["data"]["events"]:
                    if ev.get('scoreOfWholeMatch') and ev.get('scoreOfWholeMatch') != "0:0":
                        found.append(ev)
        except: continue
    return found

def get_winner(score_str):
    if not score_str: return None
    try:
        h, a = map(int, score_str.replace(' ', '').split(':'))
        if h > a: return "HOME"
        if a > h: return "AWAY"
        return "DRAW"
    except: return None

def main():
    search_paths = [
        'extracted_odds',
        'extracted_results',
        'moneymspport-money/ExtractedData'
    ]
    
    # Key format: "TEAM_A vs TEAM_B" (alphabetical to handle both home/away directions as H2H)
    # However, in VFL, Home/Away advantage might exist. Let's keep direction.
    h2h_db = defaultdict(lambda: {"HOME_WIN": 0, "DRAW": 0, "AWAY_WIN": 0, "TOTAL": 0, "SCORES": []})
    
    print("🚀 PHASE 1: Harvesting all 26,000+ results for H2H mapping...")
    for folder in search_paths:
        if not os.path.exists(folder): continue
        for f in os.listdir(folder):
            path = os.path.join(folder, f)
            if not os.path.isfile(path): continue
            content = open(path, 'r', encoding='utf-8').read()
            events = parse_msport_json(content)
            for ev in events:
                score = ev.get('fullTime') or ev.get('scoreOfWholeMatch')
                if score and score != "0:0":
                    h = str(ev['homeTeam']).strip().upper()
                    a = str(ev['awayTeam']).strip().upper()
                    pair_key = f"{h} VS {a}"
                    
                    winner = get_winner(score)
                    if winner:
                        h2h_db[pair_key]["TOTAL"] += 1
                        if winner == "HOME": h2h_db[pair_key]["HOME_WIN"] += 1
                        elif winner == "AWAY": h2h_db[pair_key]["AWAY_WIN"] += 1
                        else: h2h_db[pair_key]["DRAW"] += 1
                        h2h_db[pair_key]["SCORES"].append(score)

    print(f"✅ H2H Model built. Analyzed {len(h2h_db)} unique team pairings.")
    
    # Convert to regular dict for JSON
    final_db = {}
    for k, v in h2h_db.items():
        if v["TOTAL"] > 0:
            final_db[k] = v
            # Calculate win rates
            v["HOME_RATE"] = v["HOME_WIN"] / v["TOTAL"]
            v["AWAY_RATE"] = v["AWAY_WIN"] / v["TOTAL"]
            v["DRAW_RATE"] = v["DRAW"] / v["TOTAL"]

    with open('h2h_model.json', 'w', encoding='utf-8') as f:
        json.dump(final_db, f, indent=2)
        
    print("📈 Saved 380+ pairings to h2h_model.json")

if __name__ == "__main__":
    main()
