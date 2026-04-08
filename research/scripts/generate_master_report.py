import os
import json
import re

def parse_msport_blocks(content):
    blocks = re.split(r'===== MATCH #\d+', content)
    events = []
    for b in blocks:
        m = re.search(r'\{[\s\S]*\}', b)
        if m:
            try:
                data = json.loads(m.group())
                if "data" in data and "events" in data["data"]:
                    match_day = data["data"].get("matchDay", "Unknown")
                    season = data["data"].get("seasonId", "Unknown")
                    for e in data["data"]["events"]:
                        e["_matchDay"] = match_day
                        e["_season"] = season
                    events.extend(data["data"]["events"])
            except: pass
    return events

def analyze_events(events):
    results = []
    for e in events:
        home = e.get('homeTeam')
        away = e.get('awayTeam')
        m1x2 = next((m for m in e.get('markets', []) if m.get('id') == 1), None)
        if not m1x2: continue
        
        outcomes = m1x2.get('outcomes', [])
        try:
            h_odds = float(next(o['odds'] for o in outcomes if o['id'] == '1'))
            d_odds = float(next(o['odds'] for o in outcomes if o['id'] == '2'))
            a_odds = float(next(o['odds'] for o in outcomes if o['id'] == '3'))
        except: continue
        
        # Calculate EXACT bias mathematically
        implied_prob = (1 / h_odds) + (1 / d_odds) + (1 / a_odds)
        exact_bias = 1 / implied_prob
        
        hp = (1/h_odds) * exact_bias
        dp = (1/d_odds) * exact_bias
        ap = (1/a_odds) * exact_bias
        
        probs = [hp, dp, ap]
        labels = ["HOME", "DRAW", "AWAY"]
        best_idx = probs.index(max(probs))
        
        results.append({
            'fixture': f"{home} vs {away}",
            'match_day': f"Day {e.get('_matchDay', 'Unknown')} ({e.get('_season', 'Unknown')})",
            'odds': f"H:{h_odds} D:{d_odds} A:{a_odds}",
            'bias_factor': f"{exact_bias:.4f}",
            'prediction': labels[best_idx],
            'true_probs': f"H:{hp*100:.1f}% D:{dp*100:.1f}% A:{ap*100:.1f}%"
        })
    return results

def main():
    odds_dir = "extracted_odds"
    artifact_path = r"C:\Users\faith\.gemini\antigravity\brain\038f5c02-123d-4ffa-b545-9103b0ca2aaf\vfl_predictions_master.md"
    
    if not os.path.exists(odds_dir):
        print(f"Directory {odds_dir} not found.")
        return
        
    files = [f for f in os.listdir(odds_dir) if f.endswith('.txt')]
    all_results = {}
    
    for f in files:
        file_path = os.path.join(odds_dir, f)
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            events = parse_msport_blocks(content)
            if events:
                all_results[f] = analyze_events(events)
                
    with open(artifact_path, 'w', encoding='utf-8') as out:
        out.write("# 🏆 VFL Master Prediction Report\n\n")
        out.write("This document contains mathematically computed True Probabilities and Predictions for all harvested MSport API odds data. The bias factor is dynamically calculated per match to eliminate the bookmaker's overround.\n\n")
        
        for f, results in all_results.items():
            out.write(f"## Data Source: `{f}`\n\n")
            out.write("| Match Day | Fixture | Raw Odds | System Bias | Best Value Prediction | True Probabilities |\n")
            out.write("|---|---|---|---|---|---|\n")
            
            # Remove duplicates using fixture name
            seen = set()
            for r in results:
                if r['fixture'] not in seen:
                    seen.add(r['fixture'])
                    out.write(f"| {r['match_day']} | **{r['fixture']}** | {r['odds']} | {r['bias_factor']} | **{r['prediction']}** | {r['true_probs']} |\n")
            out.write("\n---\n\n")
            
    print(f"Generated master report at {artifact_path}")

if __name__ == "__main__":
    main()
