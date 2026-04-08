import os
import json
import re

def parse_blocks(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'===== MATCH #\d+', content)
    events_with_meta = []
    
    url_season = re.search(r'seasonId=vf:season:(\d+)', file_path)
    url_day = re.search(r'matchDay=(\d+)', file_path)
    
    for b in blocks:
        m = re.search(r'\{[\s\S]*\}', b)
        if m:
            try:
                data = json.loads(m.group())
                top_s = data.get('data', {}).get('seasonId') or data.get('seasonId')
                top_d = data.get('data', {}).get('matchDay') or data.get('matchDay')
                
                if not top_d or not top_s:
                    current = data.get('data', {}).get('current', {})
                    if current:
                        top_d = top_d or current.get('matchDay')
                        top_s = top_s or current.get('seasonId')
                
                events = []
                if "data" in data:
                    if "events" in data["data"]: events = data["data"]["events"]
                    elif "results" in data["data"]: events = data["data"]["results"]
                elif "results" in data: events = data["results"]
                
                if events:
                    for e in events:
                        s = str(e.get('seasonId') or top_s or (url_season.group(1) if url_season else None))
                        d = str(e.get('matchDay') or top_d or (url_day.group(1) if url_day else None))
                        e['norm_season'] = s.split(':')[-1].strip() if s else 'Unknown'
                        e['norm_day'] = d.strip() if d else 'Unknown'
                        events_with_meta.append(e)
            except: pass
    return events_with_meta

def get_outcome(home_score, away_score):
    if home_score > away_score: return "HOME"
    if home_score == away_score: return "DRAW"
    return "AWAY"

def main():
    odds_dir = "extracted_odds"
    results_dir = "extracted_results"
    
    if not os.path.exists(odds_dir) or not os.path.exists(results_dir):
        print("Data directories not found.")
        return
        
    odds_map = {}
    for f in os.listdir(odds_dir):
        if not f.endswith('.txt'): continue
        path = os.path.join(odds_dir, f)
        for e in parse_blocks(path):
            s, d = e.get('norm_season'), e.get('norm_day')
            if (s, d) not in odds_map: odds_map[(s, d)] = []
            odds_map[(s, d)].append(e)
            
    results_map_files = {}
    for f in os.listdir(results_dir):
        if not f.endswith('.txt'): continue
        path = os.path.join(results_dir, f)
        for e in parse_blocks(path):
            s, d = e.get('norm_season'), e.get('norm_day')
            if (s, d) not in results_map_files: results_map_files[(s, d)] = []
            results_map_files[(s, d)].append(e)
            
    # Statistics Tracking
    confidence_brackets = {
        "> 70%": {"hits": 0, "total": 0, "matches": []},
        "60% - 70%": {"hits": 0, "total": 0, "matches": []},
        "50% - 60%": {"hits": 0, "total": 0, "matches": []},
        "< 50%": {"hits": 0, "total": 0, "matches": []}
    }
    
    total_matches = 0
    total_hits = 0

    for key in results_map_files:
        if key in odds_map:
            r_events = results_map_files[key]
            o_events = odds_map[key]
            
            r_dict = {f"{str(r.get('homeTeam')).strip()} vs {str(r.get('awayTeam')).strip()}": r for r in r_events}
            
            seen_odds = set()
            for o in o_events:
                fixture = f"{str(o.get('homeTeam')).strip()} vs {str(o.get('awayTeam')).strip()}"
                if fixture in seen_odds: continue
                seen_odds.add(fixture)
                
                if fixture in r_dict:
                    r = r_dict[fixture]
                    
                    m1x2 = next((m for m in o.get('markets', []) if m.get('id') == 1), None)
                    if not m1x2: continue
                    try:
                        h_odds = float(next(oc['odds'] for oc in m1x2.get('outcomes', []) if oc['id'] == '1'))
                        d_odds = float(next(oc['odds'] for oc in m1x2.get('outcomes', []) if oc['id'] == '2'))
                        a_odds = float(next(oc['odds'] for oc in m1x2.get('outcomes', []) if oc['id'] == '3'))
                    except: continue

                    implied_prob = (1 / h_odds) + (1 / d_odds) + (1 / a_odds)
                    exact_bias = 1 / implied_prob
                    
                    hp = (1/h_odds) * exact_bias
                    dp = (1/d_odds) * exact_bias
                    ap = (1/a_odds) * exact_bias
                    
                    probs = [hp, dp, ap]
                    labels = ["HOME", "DRAW", "AWAY"]
                    best_prob = max(probs)
                    pred = labels[probs.index(best_prob)]
                    
                    full_time = r.get('fullTime', '0:0')
                    try:
                        h_score = int(full_time.split(':')[0])
                        a_score = int(full_time.split(':')[1])
                    except:
                        h_score, a_score = 0, 0
                    actual = get_outcome(h_score, a_score)
                    
                    is_hit = pred == actual
                    total_matches += 1
                    if is_hit: total_hits += 1
                    
                    match_data = {
                        "fixture": fixture,
                        "day_season": f"Day {key[1]} ({key[0]})",
                        "odds": f"H:{h_odds} D:{d_odds} A:{a_odds}",
                        "prob": best_prob,
                        "pred": pred,
                        "actual": actual,
                        "score": f"{h_score}-{a_score}",
                        "hit": is_hit
                    }
                    
                    if best_prob > 0.70: bracket = "> 70%"
                    elif best_prob > 0.60: bracket = "60% - 70%"
                    elif best_prob > 0.50: bracket = "50% - 60%"
                    else: bracket = "< 50%"
                    
                    confidence_brackets[bracket]["total"] += 1
                    if is_hit: confidence_brackets[bracket]["hits"] += 1
                    confidence_brackets[bracket]["matches"].append(match_data)
                    
    artifact_path = r"C:\Users\faith\.gemini\antigravity\brain\038f5c02-123d-4ffa-b545-9103b0ca2aaf\vfl_backtest_results.md"
    
    with open(artifact_path, "w", encoding="utf-8") as out:
        out.write("# 📈 VFL RNG Backtest Report\n\n")
        out.write("This report compares the mathematical **True Probability** predictions against the **Actual Harvested Results** of the VFL games to determine the model's accuracy against the RNG algorithm.\n\n")
        
        out.write("## 📊 Overall Performance\n")
        out.write(f"- **Total Matches Matched**: {total_matches}\n")
        out.write(f"- **Total Accurate Predictions**: {total_hits}\n")
        if total_matches > 0:
            out.write(f"- **Overall Win Rate**: **{total_hits/total_matches:.2%}**\n\n")
            
        out.write("## 🎯 Performance by Confidence Bracket\n\n")
        out.write("| Confidence (True Prob) | Total Bets | Hits | Win Rate |\n")
        out.write("|---|---|---|---|\n")
        for b, data in confidence_brackets.items():
            if data["total"] > 0:
                rate = data["hits"] / data["total"]
                out.write(f"| **{b}** | {data['total']} | {data['hits']} | **{rate:.2%}** |\n")
                
        out.write("\n---\n\n")
        out.write("## 🔍 Detailed Match Logs\n\n")
        
        for b, data in confidence_brackets.items():
            if data["total"] == 0: continue
            out.write(f"### {b} Confidence\n\n")
            out.write("| Match Day | Fixture | Odds | Highest Prob | Prediction | Actual Result | Score | Status |\n")
            out.write("|---|---|---|---|---|---|---|---|\n")
            
            for m in data["matches"]:
                status = "✅ HIT" if m["hit"] else "❌ MISS"
                out.write(f"| {m['day_season']} | **{m['fixture']}** | {m['odds']} | {m['prob']:.1%} | **{m['pred']}** | {m['actual']} | {m['score']} | {status} |\n")
            out.write("\n")

    print(f"Backtest complete. Artifact saved to {artifact_path}")

if __name__ == "__main__":
    main()
