import json
import re
import os

def parse_blocks(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'===== MATCH #\d+', content)
    events_with_meta = []
    
    # Precise regex for fallbacks if JSON lacks them
    # Some HARs might have them in the URL but not the body
    url_season = re.search(r'seasonId=vf:season:(\d+)', file_path)
    url_day = re.search(r'matchDay=(\d+)', file_path)
    
    for b in blocks:
        m = re.search(r'\{[\s\S]*\}', b)
        if m:
            try:
                data = json.loads(m.group())
                # Top level metadata
                top_s = data.get('data', {}).get('seasonId') or data.get('seasonId')
                top_d = data.get('data', {}).get('matchDay') or data.get('matchDay')
                
                # MSport specific nested matchDay in results
                if not top_d:
                    top_d = data.get('data', {}).get('current', {}).get('matchDay')
                
                # Check for list in result/selection format
                events = []
                if "data" in data:
                    if "events" in data["data"]: events = data["data"]["events"]
                    elif "results" in data["data"]: events = data["data"]["results"]
                elif "results" in data: events = data["results"]
                
                if events:
                    for e in events:
                        # Normalize and ensure season/day exist
                        s = str(e.get('seasonId') or top_s or (url_season.group(1) if url_season else None))
                        d = str(e.get('matchDay') or top_d or (url_day.group(1) if url_day else None))
                        e['norm_season'] = s.split(':')[-1].strip()
                        e['norm_day'] = d.strip()
                        events_with_meta.append(e)
            except Exception as e: 
                # print(f"DEBUG: JSON parse error in block: {e}") 
                pass
    return events_with_meta

def get_outcome(home_score, away_score):
    if home_score > away_score: return "1"
    if home_score == away_score: return "X"
    return "2"

def backtest(odds_file, results_file, bias=0.8):
    odds_events = parse_blocks(odds_file)
    results_events = parse_blocks(results_file)
    
    # Map results by matchId or teams
    results_map = {}
    for r in results_events:
        key = (r.get('norm_season'), r.get('norm_day'), str(r.get('homeTeam')).strip(), str(r.get('awayTeam')).strip())
        results_map[key] = r
    
    hits = 0
    total = 0
    
    print(f"\nBacktesting: {os.path.basename(odds_file)} vs {os.path.basename(results_file)}")
    
    for o in odds_events:
        key = (o.get('norm_season'), o.get('norm_day'), str(o.get('homeTeam')).strip(), str(o.get('awayTeam')).strip())
        
        if key in results_map:
            r = results_map[key]
            
            # Get Odds
            m1x2 = next((m for m in o.get('markets', []) if m.get('id') == 1), None)
            if not m1x2: continue
            outcomes = m1x2.get('outcomes', [])
            try:
                h_odds = float(next(oc['odds'] for oc in outcomes if oc['id'] == '1'))
                d_odds = float(next(oc['odds'] for oc in outcomes if oc['id'] == '2'))
                a_odds = float(next(oc['odds'] for oc in outcomes if oc['id'] == '3'))
            except: continue
            
            # Predictions via Bias
            hp = (1/h_odds) * bias
            dp = (1/d_odds) * bias
            ap = (1/a_odds) * bias
            probs = [hp, dp, ap]
            best_idx = probs.index(max(probs))
            pred = ["1", "X", "2"][best_idx]
            
            # Actual
            h_score = int(r.get('homeScore', 0))
            a_score = int(r.get('awayScore', 0))
            actual = get_outcome(h_score, a_score)
            
            is_hit = (pred == actual)
            if is_hit: hits += 1
            total += 1
            
            match_name = f"{o.get('homeTeam')} vs {o.get('awayTeam')}"
            score_str = f"{h_score}-{a_score}"
            hit_str = "HIT" if is_hit else "MISS"
            print(f"{match_name:<40} | {pred:<5} | {actual:<5} | {score_str:<10} | {hit_str}")
            
    return hits, total

def main():
    print("Auto-discovering matching Odds/Results pairs...")
    
    odds_dir = "extracted_odds"
    results_dir = "extracted_results"
    
    # Map (season, day) -> list of files
    odds_map = {}
    for f in os.listdir(odds_dir):
        if not f.endswith('.txt'): continue
        path = os.path.join(odds_dir, f)
        events = parse_blocks(path)
        if events:
            # Map all unique (season, day) pairs in the file
            for e in events:
                s = e.get('norm_season')
                d = e.get('norm_day')
                if (s, d) not in odds_map: odds_map[(s, d)] = []
                if path not in odds_map[(s, d)]:
                    odds_map[(s, d)].append(path)
            
    results_map_files = {}
    for f in os.listdir(results_dir):
        if not f.endswith('.txt'): continue
        path = os.path.join(results_dir, f)
        events = parse_blocks(path)
        if events:
            for e in events:
                s = e.get('norm_season')
                d = e.get('norm_day')
                if (s, d) not in results_map_files: results_map_files[(s, d)] = []
                if path not in results_map_files[(s, d)]:
                    results_map_files[(s, d)].append(path)
    
    total_hits = 0
    total_matches = 0
    
    # Iterate through all intersections
    for key in results_map_files:
        if key in odds_map:
            for o_f in odds_map[key]:
                for r_f in results_map_files[key]:
                    h, t = backtest(o_f, r_f)
                    total_hits += h
                    total_matches += t
            
    if total_matches > 0:
        print(f"\nOVERALL SUMMARY (Bias: 0.8)")
        print(f"Total Matches: {total_matches}")
        print(f"Total Hits:    {total_hits}")
        print(f"Hit Rate:      {total_hits/total_matches:.2%}")
    else:
        print("\nNo matching (Season, Day) sessions found for backtest.")

if __name__ == "__main__":
    main()
