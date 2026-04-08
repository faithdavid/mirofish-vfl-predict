import json
import re
import argparse
import os

# Base paths for MSport extraction
RESULT_BASE = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/result"
ODDS_BASE = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/match/day/event/list"

def parse_msport_blocks(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'===== MATCH #\d+', content)
    events = []
    for b in blocks:
        m = re.search(r'\{[\s\S]*\}', b)
        if m:
            try:
                data = json.loads(m.group())
                if "data" in data and "events" in data["data"]:
                    events.extend(data["data"]["events"])
            except: pass
    return events

def generate_report(events, bias=0.8):
    if not events:
        return "No events found."
        
    day = events[0].get('matchDay')
    season = events[0].get('seasonId')
    
    report = [f"# Match Day {day} Prediction Report (Season: {season})"]
    report.append(f"Bias Factor applied: {bias}\n")
    report.append(f"{'Fixture':<40} | {'1 (Home)%':<10} | {'X (Draw)%':<10} | {'2 (Away)%':<10} | {'BEST VALUE'}")
    report.append("-" * 100)
    
    for e in events[:8]:
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
        
        # True Probs
        hp = (1/h_odds) * bias
        dp = (1/d_odds) * bias
        ap = (1/a_odds) * bias
        
        # Simple "Value" heuristic (highest true prob since we don't have historical results to compare ROI)
        probs = [hp, dp, ap]
        labels = ["HOME", "DRAW", "AWAY"]
        best_idx = probs.index(max(probs))
        
        report.append(f"{f'{home} vs {away}':<40} | {hp*100:<8.1f}% | {dp*100:<8.1f}% | {ap*100:<8.1f}% | {labels[best_idx]}")
        
    return "\n".join(report)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--bias", type=float, default=0.8)
    args = parser.parse_args()
    
    events = parse_msport_blocks(args.file)
    print(generate_report(events, args.bias))

if __name__ == "__main__":
    main()
