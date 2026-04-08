import sqlite3
import pandas as pd
import sys
import os

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import vfl_oracle_v5 as oracle

def audit_user_data():
    conn = sqlite3.connect('vfl_history.db')
    df = oracle.load_vfl_history()
    profiles = oracle.get_team_profiles(df)
    
    # Audit Season 4491 (Internal ID 3074000) for MatchDay 11
    # Note: We hard-ingested this ID '3074000'
    actuals = pd.read_sql_query("SELECT * FROM matches WHERE season='3074000' AND day=11 AND outcome IS NOT NULL", conn)
    
    if actuals.empty:
        print("ERROR: No ground truth results found in database for Season 4491 MD 11.")
        return

    print(f"\n--- FINAL AUDIT: SEASON 4491 (MD 11) ---")
    print("-" * 80)
    print(f"{'FIXTURE':<35} | {'PRED':<6} | {'ACTUAL':<8} | {'STATUS'} | {'ORACLE SIGNAL'}")
    print("-" * 80)
    
    hits = 0
    total = 0
    
    for _, row in actuals.iterrows():
        # Build Point-in-Time Fixture
        fixture = {
            'home': row['home'], 'away': row['away'],
            'oh': row['oh'], 'od': row['od'], 'oa': row['oa'],
            'sst': row['season_start_time'], 
            'day': 11, 
            'season': '3074000'
        }
        res = oracle.predict_fixture(fixture, df, profiles)
        
        # In DB outcome is HOME/DRAW/AWAY. res['prediction'] is H/D/A.
        actual_code = row['outcome'][0] 
        is_hit = (res['prediction'] == actual_code)
        if is_hit: hits += 1
        total += 1
        
        status = 'HIT' if is_hit else 'MISS'
        fixture_name = f"{row['home']} vs {row['away']}"
        print(f"{fixture_name:<35} | {res['prediction']:<6} | {actual_code:<8} | {status:<6} | {res['label']}")

    print("-" * 80)
    print(f"FINAL USER DATA ACCURACY: {hits/total:.1%} ({hits}/{total})")
    conn.close()

if __name__ == '__main__':
    audit_user_data()
