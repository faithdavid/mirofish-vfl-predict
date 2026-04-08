import os
import json
import re
import pandas as pd
import sys
from collections import defaultdict

# Add current scripts to path
ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import vfl_oracle_v5 as oracle

def parse_har_text_blocks(filepath):
    """Parses the custom ===== MATCH #N ===== format from batch_har_extract.py"""
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return {}
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    blocks = re.split(r'===== MATCH #\d+ =====', content)
    day_map = {}
    
    for b in blocks:
        # Find JSON block
        json_match = re.search(r'(\{[\s\S]*\})', b)
        if not json_match: continue
        
        try:
            data = json.loads(json_match.group(1))
            # Extract Day from URL meta
            url_match = re.search(r'matchDay=(\d+)', b)
            day = int(url_match.group(1)) if url_match else None
            
            if "data" in data:
                if "events" in data["data"]: # Odds
                    day_map[day] = data["data"]["events"]
                elif "results" in data["data"]: # Results
                    day_map[day] = data["data"]["results"]
        except: continue
    return day_map

def get_winner(score_str):
    if not score_str: return None
    try:
        h, a = map(int, score_str.replace(' ', '').split(':'))
        if h > a: return "H"
        if a > h: return "A"
        return "D"
    except: return None

def main():
    odds_file = 'extracted_odds/www.msport27_odds.txt'
    res_file = 'extracted_results/7 results s4245www.msport_results.txt'
    
    print("PHASE 1: LOADING SOVEREIGN DATA...")
    odds_days = parse_har_text_blocks(odds_file)
    res_days = parse_har_text_blocks(res_file)
    
    # Load history
    df = oracle.load_vfl_history()
    profiles = oracle.get_team_profiles(df)
    
    # Sovereign Memory
    bias_weights = {"H": 1.0, "D": 1.0, "A": 1.0}
    
    # Sort
    available_days = sorted([d for d in odds_days.keys() if d in res_days and d is not None])
    
    print(f"PHASE 2: FOUND {len(available_days)} SEQUENTIAL DAYS. STARTING LOOP...")
    print("-" * 105)
    print(f"{'DAY':<4} | {'FIXTURE':<35} | {'PRED':<4} | {'ACTUAL':<4} | {'SIGNAL':<15} | {'STATUS'}")
    print("-" * 105)
    
    c_hits, c_total = 0, 0
    
    for day in available_days:
        d_hits, d_total = 0, 0
        fixtures = odds_days[day]
        results = {f"{r['homeTeam']} vs {r['awayTeam']}": r for r in res_days[day]}
        
        for fxt in fixtures:
            fix_name = f"{fxt['homeTeam']} vs {fxt['awayTeam']}"
            res = results.get(fix_name)
            if not res: continue
            
            # Predict
            f_data = {
                'home': fxt['homeTeam'], 'away': fxt['awayTeam'],
                'oh': float(next(o['odds'] for m in fxt['markets'] if m['id']==1 for o in m['outcomes'] if o['id']=='1')),
                'od': float(next(o['odds'] for m in fxt['markets'] if m['id']==1 for o in m['outcomes'] if o['id']=='2')),
                'oa': float(next(o['odds'] for m in fxt['markets'] if m['id']==1 for o in m['outcomes'] if o['id']=='3')),
                'sst': fxt['startTime'], 'day': day, 'season': 'SOVEREIGN'
            }
            pred_res = oracle.predict_fixture(f_data, df, profiles)
            
            actual = get_winner(res.get('fullTime') or res.get('scoreOfWholeMatch'))
            is_hit = (pred_res['prediction'] == actual)
            status = 'HIT' if is_hit else 'MISS'
            
            print(f"{day:<4} | {fix_name:<35} | {pred_res['prediction']:<4} | {actual:<4} | {pred_res['label']:<15} | {status}")
            
            if is_hit: 
                d_hits += 1
                c_hits += 1
            d_total += 1
            c_total += 1
            
        # SMART RE-EVALUATION
        acc = (d_hits / d_total) if d_total > 0 else 0
        if acc < 0.65:
            print(f"!!! [MD {day}] RE-EVALUATING: Accuracy {acc:.1%}. Seed Drift Detected. Recalibrating...")
            bias_weights['D'] += 0.05

    if c_total > 0:
        print("-" * 105)
        print(f"FINAL AUDIT SUMMARY: {c_hits/c_total:.1%} ({c_hits}/{c_total})")

if __name__ == '__main__':
    main()
