import sqlite3
import pandas as pd
import sys
import os

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import vfl_oracle_v5 as oracle

DB_PATH = 'vfl_history.db'
SEASON = '3073974'
DAY = 6

def run_blind_proof():
    # 1. Load History (excluding the target day for true blinding)
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM matches WHERE outcome IS NOT NULL", conn)
    conn.close()
    
    # Standardify
    df['season'] = df['season'].str.replace('vf:season:', '')
    numeric_cols = ['oh', 'od', 'oa', 'h', 'a', 'total', 'gg', 'o25', 'day']
    for col in numeric_cols: df[col] = pd.to_numeric(df[col], errors='coerce')
    df['outcome_code'] = df['outcome'].map({'HOME': 'H', 'DRAW': 'D', 'AWAY': 'A'})
    
    # Filter for Blind Evaluation
    test_match = df[(df['season'] == SEASON) & (df['day'] == DAY)]
    train_data = df[~((df['season'] == SEASON) & (df['day'] == DAY))]
    profiles = oracle.get_team_profiles(train_data)
    
    print(f"\nVFL ORACLE V5.1 - BLIND PROOF OF ACCURACY (Season {SEASON} Day {DAY})")
    print("=" * 105)
    print(f"{'FIXTURE':<35} | {'PRED':<4} | {'ACTUAL':<6} | {'STATUS':<8} | {'REASON'}")
    print("-" * 105)

    hits = 0
    strong_hits = 0
    total_strong = 0

    for _, row in test_match.iterrows():
        fixture = {
            'home': row['home'], 'away': row['away'],
            'oh': row['oh'], 'od': row['od'], 'oa': row['oa'],
            'sst': row['season_start_time']
        }
        
        pred = oracle.predict_fixture(fixture, train_data, profiles)
        actual = row['outcome_code']
        
        hit_str = "CORRECT" if pred['prediction'] == actual else "MISS"
        if pred['prediction'] == actual:
            hits += 1
            if pred['is_strong']: strong_hits += 1
        
        if pred['is_strong']: total_strong += 1
        
        icon = "[LOCK]" if pred['is_mirror'] else ("[STRONG]" if pred['is_strong'] else "        ")
        
        print(f"{row['home'] + ' vs ' + row['away']:<35} | {pred['prediction']:<4} | {actual:<6} | {hit_str:<8} | {icon} {pred['label']}")

    print("-" * 105)
    print(f"Overall Accuracy: {hits/len(test_match):.1%} ({len(test_match)} matches)")
    if total_strong > 0:
        print(f"STRONG CALLS ACCURACY: {strong_hits/total_strong:.1%} ({total_strong} calls)")
    print("=" * 105)

if __name__ == '__main__':
    run_blind_proof()
