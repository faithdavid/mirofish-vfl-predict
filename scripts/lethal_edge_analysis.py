import json
import os
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
    margin_removal = 1/ip
    return [(1/h)*margin_removal, (1/d)*margin_removal, (1/a)*margin_removal]

def main():
    search_paths = ['extracted_odds', 'extracted_results', 'moneymspport-money/ExtractedData']
    
    odds_data = defaultdict(list)
    res_data = {}
    h2h_historical = json.load(open('h2h_model.json', 'r', encoding='utf-8')) if os.path.exists('h2h_model.json') else {}
    
    print("🚀 PHASE 1: Correlating Odds with H2H Truth...")
    for folder in search_paths:
        if not os.path.exists(folder): continue
        for f in os.listdir(folder):
            path = os.path.join(folder, f)
            content = open(path, 'r', encoding='utf-8').read()
            events = parse_msport_json(content)
            for ev in events:
                if 'markets' in ev:
                    odds_data[(ev['_season'], ev['_day'])].append(ev)
                elif ev.get('fullTime') or ev.get('scoreOfWholeMatch'):
                    score = ev.get('fullTime') or ev.get('scoreOfWholeMatch')
                    if score and score != "0:0":
                        h_name = str(ev['homeTeam']).strip().upper()
                        a_name = str(ev['awayTeam']).strip().upper()
                        res_data[(ev['_season'], ev['_day'], h_name, a_name)] = score

    edges = []
    
    for (season, day), fixtures in odds_data.items():
        for fxt in fixtures:
            # Check if we have BOTH odds and result for this specific match
            h_name = str(fxt['homeTeam']).strip().upper()
            a_name = str(fxt['awayTeam']).strip().upper()
            res_score = res_data.get((season, day, h_name, a_name))
            if not res_score: continue
            
            # Get Market Implied Prob (True Prob)
            m1x2 = next((m for m in fxt.get('markets', []) if m['id'] == 1), None)
            if not m1x2: continue
            try:
                oh = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '1'))
                od = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '2'))
                oa = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '3'))
            except: continue
            
            math_h, math_d, math_a = get_true_probs(oh, od, oa)
            
            # Get H2H Historical Win Rate for this specific pairing
            h2h = h2h_historical.get(f"{h_name} VS {a_name}", {"HOME_RATE": 0.33, "DRAW_RATE": 0.33, "AWAY_RATE": 0.33, "TOTAL": 0})
            if h2h["TOTAL"] < 20: continue # Need decent sample size
            
            # Calculation of Edge (H2H Reality vs Market Illusion)
            edge_h = h2h["HOME_RATE"] - math_h
            edge_d = h2h["DRAW_RATE"] - math_d
            edge_a = h2h["AWAY_RATE"] - math_a
            
            edges.append({
                "fixture": f"{h_name} vs {a_name}",
                "edge_h": edge_h,
                "edge_d": edge_d,
                "edge_a": edge_a,
                "samples": h2h["TOTAL"]
            })

    # Sort edges to find the biggest market blindspots
    best_edges = sorted(edges, key=lambda x: max(x['edge_h'], x['edge_d'], x['edge_a']), reverse=True)
    
    report = ["# 🎯 Lethal Edge: H2H vs Pre-Match Odds Blindspots", ""]
    report.append("This analysis identifies pairings where the bookmaker consistently misprices the outcome relative to historical H2H reality.")
    report.append("")
    report.append("| Fixture | Best Target | Historical Edge | Confidence | Samples |")
    report.append("| :--- | :--- | :--- | :--- | :--- |")
    
    seen_fixtures = set()
    for e in best_edges:
        if e['fixture'] in seen_fixtures: continue
        seen_fixtures.add(e['fixture'])
        
        # Find index of max edge
        vals = [e['edge_h'], e['edge_d'], e['edge_a']]
        labels = ["HOME", "DRAW", "AWAY"]
        best_idx = vals.index(max(vals))
        
        if max(vals) > 0.05: # Only show edge > 5%
            report.append(f"| {e['fixture']} | **{labels[best_idx]}** | +{max(vals):.1%} | ELITE | {e['samples']} |")

    with open('lethal_edge_report.md', 'w', encoding='utf-8') as f:
        f.write("\n".join(report))
        
    print(f"✅ Lethal Edge analysis complete. Found {len(seen_fixtures)} unique high-value pairings.")
    print("📈 Saved to lethal_edge_report.md")

if __name__ == "__main__":
    main()
