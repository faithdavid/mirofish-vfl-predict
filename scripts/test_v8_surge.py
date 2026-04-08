import sqlite3
import pandas as pd
import sys
import os

# Add current scripts to path
ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import vfl_oracle_v5 as oracle

def audit_v8_surge():
    conn = sqlite3.connect('vfl_history.db')
    df = oracle.load_vfl_history()
    profiles = oracle.get_team_profiles(df)
    
    # Test Season vf:season:3037483 (MD 26-30) - Historical Surge: 16 Draws
    test_matches = pd.read_sql_query("SELECT * FROM matches WHERE season='vf:season:3037483' AND day > 25", conn)
    
    print('--- V8.0 PREDICTIVE AUDIT: UNDER-QUOTA SURGE (Season 3037483) ---')
    print(f'Total matches to resolve: {len(test_matches)}')
    
    hits, total = 0, 0
    draw_hits, draw_total = 0, 0
    surge_count = 0
    
    for _, row in test_matches.iterrows():
        fxt = {
            'home': row['home'], 'away': row['away'], 
            'oh': row['oh'], 'od': row['od'], 'oa': row['oa'], 
            'sst': row['season_start_time'], 'day': row['day'], 
            'season': row['season']
        }
        res = oracle.predict_fixture(fxt, df, profiles)
        actual = str(row['outcome'])[0] if row['outcome'] else None
        
        total += 1
        if res['prediction'] == actual: hits += 1
        
        if actual == 'D':
            draw_total += 1
            if res['prediction'] == 'D': 
                draw_hits += 1
                
        if '[MATHEMATICAL DRAW FORCE]' in res['label']:
            surge_count += 1
            if surge_count < 10: # Sample print
                print(f"MD {row['day']} | {row['home']} vs {row['away']} | Pred: {res['prediction']} | Actual: {actual} | Signal: {res['label']}")

    print('-' * 100)
    print(f"Total Matches: {total}")
    print(f"Overall Accuracy: {hits/total:.1%} ({hits}/{total})")
    print(f"DRAW SURGE CAPTURE: {draw_hits/draw_total:.1%} ({draw_hits}/{draw_total} draws identified)")
    print(f"Sovereign Signals Triggered: {surge_count}")
    conn.close()

if __name__ == '__main__':
    audit_v8_surge()
