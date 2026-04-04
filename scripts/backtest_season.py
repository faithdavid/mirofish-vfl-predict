import pandas as pd
import numpy as np
import sqlite3
import os
import sys

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import vfl_oracle_v5 as oracle

def run_backtest(target_season='3073917'):
    """Simulates a full 30-day season cycle using the V5 Oracle."""
    df = oracle.load_vfl_history()
    if df is None: return
    
    # Task 5: Select a complete season for the test
    test_data = df[df['season'] == target_season].sort_values('day')
    if len(test_data) == 0:
        print(f"[ERROR] No data found for season {target_season}")
        return
        
    # We build profiles from ALL data EXCEPT the test season
    train_data = df[df['season'] != target_season]
    profiles = oracle.get_team_profiles(train_data)
    
    print(f"\n--- STARTING FULL-SEASON BACKTEST (Season {target_season}) ---")
    print(f"Total Matches to Predict: {len(test_data)}")
    print("-" * 65)
    
    results = []
    
    for _, row in test_data.iterrows():
        # Prepare fixture data with the V5 Meta-Key (SST)
        fixture = {
            'home': row['home'], 'away': row['away'],
            'oh': row['oh'], 'od': row['od'], 'oa': row['oa'],
            'sst': row['season_start_time']
        }
        
        # Predict using Hybrid Oracle
        pred = oracle.predict_fixture(fixture, train_data, profiles)
        
        # Cross-reference with actual result
        actual = row['outcome_code']
        hit = 1 if pred['prediction'] == actual else 0
        
        results.append({
            'day': row['day'], 'home': row['home'], 'away': row['away'],
            'pred': pred['prediction'], 'actual': actual, 'hit': hit,
            'conf': pred['confidence'], 'label': pred['label'], 
            'strong': pred['is_strong'], 'mirror': pred['is_mirror']
        })
        
    res_df = pd.DataFrame(results)
    
    # PERFORMANCE METRICS
    total_acc = res_df['hit'].mean()
    strong_df = res_df[res_df['strong'] == True]
    strong_acc = strong_df['hit'].mean() if len(strong_df) > 0 else 0
    
    mirror_df = res_df[res_df['mirror'] == True]
    mirror_acc = mirror_df['hit'].mean() if len(mirror_df) > 0 else 0

    print(f"\nBACKTEST SUMMARY:")
    print(f"Overall Accuracy: {total_acc:.1%} ({len(res_df)} matches)")
    print(f"DETERMINISTIC MIRROR LOCKS: {mirror_acc:.1%} ({len(mirror_df)} matches)")
    print(f"3-SIGNAL AGREEMENT (STRONG CALLS): {strong_acc:.1%} ({len(strong_df)} matches)")
    print("-" * 65)
    
    if strong_acc > 0.8:
        print("RESULT: SUCCESS. The 3-Signal Filter is identifying high-value deterministic patterns.")
    else:
        print("RESULT: RE-CALIBRATION NEEDED. Need to adjust weights.")

    return res_df

if __name__ == '__main__':
    # Test on the latest full season in our DB
    run_backtest()
