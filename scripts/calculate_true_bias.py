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
                season = data["data"]["current"].get("seasonName", "unknown")
                day = data["data"]["current"].get("matchDay", "unknown")
                results_list = data["data"].get("results", [])
                for res in results_list:
                    res['_season'] = str(season).strip().upper()
                    res['_day'] = str(day).strip()
                    found.append(res)
            # Odds JSON
            elif "data" in data and "events" in data["data"]:
                season = data["data"].get("seasonName", "unknown")
                day = data["data"].get("matchDay", "unknown")
                for ev in data["data"]["events"]:
                    ev['_season'] = str(ev.get('seasonName', season)).strip().upper()
                    ev['_day'] = str(ev.get('matchDay', day)).strip()
                    found.append(ev)
        except: continue
    return found

def get_true_probs(h, d, a):
    ip = (1/h) + (1/d) + (1/a)
    bias = 1/ip
    return [(1/h)*bias, (1/d)*bias, (1/a)*bias]

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
    
    odds_data = defaultdict(list)
    res_data = {}
    
    print("🚀 PHASE 1: Harvesting all data from multiple repositories...")
    for folder in search_paths:
        if not os.path.exists(folder): continue
        for f in os.listdir(folder):
            path = os.path.join(folder, f)
            if not os.path.isfile(path) or '.txt' not in path: continue
            content = open(path, 'r', encoding='utf-8').read()
            events = parse_msport_json(content)
            for ev in events:
                # Is it an Odds object? (has markets)
                if 'markets' in ev:
                    odds_data[(ev['_season'], ev['_day'])].append(ev)
                # Is it a Result object? (has fullTime)
                elif ev.get('fullTime') or ev.get('scoreOfWholeMatch'):
                    score = ev.get('fullTime') or ev.get('scoreOfWholeMatch')
                    if score and score != "0:0":
                        h_name = str(ev['homeTeam']).strip().upper()
                        a_name = str(ev['awayTeam']).strip().upper()
                        res_data[(ev['_season'], ev['_day'], h_name, a_name)] = score

    print(f"✅ Harvested {len(odds_data)} Matchdays of Odds and {len(res_data)} Results.")
    
    # Analysis Logic
    bias_buckets = {
        "HOME": {"imp": 0, "obs": 0},
        "DRAW": {"imp": 0, "obs": 0},
        "AWAY": {"imp": 0, "obs": 0}
    }
    
    total_samples = 0
    
    print("🚀 PHASE 2: Calculating Empirical Bias (Truth vs Betting Line)...")
    for (season, day), fixtures in odds_data.items():
        for fxt in fixtures:
            h_name = str(fxt['homeTeam']).strip().upper()
            a_name = str(fxt['awayTeam']).strip().upper()
            res_score = res_data.get((season, day, h_name, a_name))
            if not res_score: continue
            
            # Predict
            m1x2 = next((m for m in fxt.get('markets', []) if m['id'] == 1), None)
            if not m1x2: continue
            try:
                ov_h = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '1'))
                ov_d = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '2'))
                ov_a = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '3'))
            except: continue
            
            true_h_prob, true_d_prob, true_a_prob = get_true_probs(ov_h, ov_d, ov_a)
            actual_winner = get_winner(res_score)
            
            total_samples += 1
            bias_buckets["HOME"]["imp"] += true_h_prob
            bias_buckets["DRAW"]["imp"] += true_d_prob
            bias_buckets["AWAY"]["imp"] += true_a_prob
            
            if actual_winner == "HOME": bias_buckets["HOME"]["obs"] += 1
            elif actual_winner == "DRAW": bias_buckets["DRAW"]["obs"] += 1
            elif actual_winner == "AWAY": bias_buckets["AWAY"]["obs"] += 1

    report = ["# 📊 Universal VFL Bias Calculation Report", ""]
    report.append(f"**Total Sample Size**: {total_samples} fixtures matched across historical records.")
    report.append("")
    report.append("| Outcome | Avg Implied Prob | Observed Win Rate | 🎯 ACTUAL BIAS FACTOR |")
    report.append("| :--- | :--- | :--- | :--- |")
    
    for outcome in ["HOME", "DRAW", "AWAY"]:
        avg_imp = (bias_buckets[outcome]["imp"] / total_samples) * 100
        obs_rate = (bias_buckets[outcome]["obs"] / total_samples) * 100
        # Bias = Observed / Implied
        # If Obs > Imp, BIAS > 1 (Value)
        # If Obs < Imp, BIAS < 1 (Sink)
        bias_factor = (obs_rate / avg_imp) if avg_imp > 0 else 0
        report.append(f"| {outcome} | {avg_imp:.2f}% | {obs_rate:.2f}% | **{bias_factor:.4f}** |")

    report.append("")
    report.append("> [!NOTE]")
    report.append("> **Bias Factor > 1.0**: Indicates the system is 'under-pricing' this outcome. This is where the long-term EDGE exists.")
    report.append("> **Bias Factor < 1.0**: Indicates the system is 'over-hyping' this outcome. Avoid betting here unless specific team-strength overrides exist.")

    with open('empirical_bias_report.md', 'w', encoding='utf-8') as f:
        f.write("\n".join(report))
        
    print(f"✅ Empirical calculation complete for {total_samples} fixtures.")
    print("📈 Saved to empirical_bias_report.md")

if __name__ == "__main__":
    main()
