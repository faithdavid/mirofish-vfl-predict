import os
import json
import re
from collections import defaultdict

def parse_results_blocks(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'===== MATCH #\d+', content)
    events = []
    
    # Precise regex for fallbacks if JSON lacks them
    url_season = re.search(r'seasonId=vf:season:(\d+)', file_path)
    url_day = re.search(r'matchDay=(\d+)', file_path)
    
    for b in blocks:
        m = re.search(r'\{[\s\S]*\}', b)
        if m:
            try:
                data = json.loads(m.group())
                
                # Top level metadata
                d_obj = data.get('data', {})
                top_s = None
                top_d = None
                
                # Check all possible locations for MSport metadata
                for key in ['current', 'after', 'prev']:
                    if key in d_obj and isinstance(d_obj[key], dict):
                        if not top_s: top_s = d_obj[key].get('seasonId')
                        if not top_d: top_d = d_obj[key].get('matchDay')
                        
                if not top_s: top_s = d_obj.get('seasonId') or data.get('seasonId')
                if not top_d: top_d = d_obj.get('matchDay') or data.get('matchDay')
                
                # Check for list in result/selection format
                extracted_events = []
                if "data" in data:
                    if "events" in data["data"]: extracted_events = data["data"]["events"]
                    elif "results" in data["data"]: extracted_events = data["data"]["results"]
                elif "results" in data: extracted_events = data["results"]
                
                if extracted_events:
                    for e in extracted_events:
                        s = str(e.get('seasonId') or top_s or (url_season.group(1) if url_season else None))
                        d = str(e.get('matchDay') or top_d or (url_day.group(1) if url_day else None))
                        e['norm_season'] = s.split(':')[-1].strip()
                        e['norm_day'] = d.strip()
                        events.append(e)
            except: pass
    return events

def analyze_season_trends(events):
    print(f"\n--- MACRO TREND ANALYSIS: SEASONS & MATCH DAYS ---")
    
    # Structure: season -> match_day -> list of matches
    season_data = defaultdict(lambda: defaultdict(list))
    
    for e in events:
        s = e.get('norm_season')
        d = e.get('norm_day')
        if s and d and s != 'None' and d != 'None':
            season_data[s][d].append(e)
            
    if not season_data:
        print("No valid season/day data found.")
        return
        
    print(f"Total Seasons Found: {len(season_data)}")
    
    # 1. Overall Trend by Match Day (e.g. is Match Day 8 always full of draws?)
    day_stats = defaultdict(lambda: {'matches': 0, 'home_wins': 0, 'draws': 0, 'away_wins': 0, 'over_25': 0})
    
    for s, days in season_data.items():
        for d, matches in days.items():
            for m in matches:
                ft_score = m.get('fullTime', m.get('score'))
                if not ft_score: continue
                
                try:
                    h_score, a_score = map(int, ft_score.split(':'))
                    day_stats[d]['matches'] += 1
                    
                    if h_score > a_score: day_stats[d]['home_wins'] += 1
                    elif h_score == a_score: day_stats[d]['draws'] += 1
                    else: day_stats[d]['away_wins'] += 1
                    
                    if (h_score + a_score) > 2: day_stats[d]['over_25'] += 1
                except: pass

    print("\n[Global Match Day Profiles]")
    print(f"{'Day':<5} | {'Matches':<8} | {'1%':<6} | {'X%':<6} | {'2%':<6} | {'Ov2.5%':<6}")
    print("-" * 50)
    
    sorted_days = sorted(day_stats.keys(), key=lambda x: int(x) if x.isdigit() else 999)
    for d in sorted_days:
        stats = day_stats[d]
        total = stats['matches']
        if total == 0: continue
        
        h_pct = stats['home_wins'] / total
        x_pct = stats['draws'] / total
        a_pct = stats['away_wins'] / total
        o_pct = stats['over_25'] / total
        
        # Highlight anomalies (e.g., >35% draws or <40% home wins)
        anomaly = ""
        if x_pct > 0.35: anomaly = "<< HIGH DRAWS"
        if o_pct > 0.60: anomaly = "<< HIGH GOALS"
        if o_pct < 0.40: anomaly = "<< LOW GOALS"
        
        print(f"{d:<5} | {total:<8} | {h_pct:.1%} | {x_pct:.1%} | {a_pct:.1%} | {o_pct:.1%} {anomaly}")

def main():
    results_dir = "extracted_results"
    all_events = []
    
    if not os.path.exists(results_dir):
        print(f"Directory {results_dir} not found.")
        return
        
    for f in os.listdir(results_dir):
        if not f.endswith('.txt'): continue
        path = os.path.join(results_dir, f)
        events = parse_results_blocks(path)
        all_events.extend(events)
        
    analyze_season_trends(all_events)

if __name__ == "__main__":
    main()
