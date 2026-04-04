import json
import sys
import os
import pandas as pd

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import vfl_oracle_v5 as oracle

def predict_live(json_path):
    # 1. Load the upcoming odds
    with open(json_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    data = raw.get('data', {})
    sst = str(data.get('seasonStartTime', '0'))
    day = data.get('matchDay', '?')
    events = data.get('events', [])
    
    # 2. Initialize Oracle Brain
    df = oracle.load_vfl_history()
    profiles = oracle.get_team_profiles(df)
    
    print(f"\nVFL ORACLE V5.1 - MATCHDAY {day} SCORECARD")
    print(f"Season Seed (SST): {sst}")
    print("=" * 85)
    print(f"{'FIXTURE':<40} | {'PRED':<6} | {'CONF':<10} | {'REASON'}")
    print("-" * 85)
    
    for ev in events:
        ht, at = ev['homeTeam'].upper(), ev['awayTeam'].upper()
        # Find 1x2 market
        m1x2 = next((m for m in ev['markets'] if m['id'] == 1), None)
        if not m1x2: continue
        
        outs = m1x2['outcomes']
        oh = float(next(o['odds'] for o in outs if o['id'] == '1'))
        od = float(next(o['odds'] for o in outs if o['id'] == '2'))
        oa = float(next(o['odds'] for o in outs if o['id'] == '3'))
        
        fixture = {
            'home': ht, 'away': at, 'oh': oh, 'od': od, 'oa': oa, 'sst': sst
        }
        
        # Oracle Run
        res = oracle.predict_fixture(fixture, df, profiles)
        
        icon = "[STRONG]" if res['is_strong'] else "        "
        if res['is_mirror']: icon = "[**LOCK**]"
        
        print(f"{ht + ' vs ' + at:<40} | {res['prediction']:<6} | {res['confidence']:<10.1%} | {icon} {res['label']}")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        predict_live(sys.argv[1])
    else:
        predict_live('upcoming_md11.json')
