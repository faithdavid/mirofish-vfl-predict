import pandas as pd
import numpy as np
import sqlite3
import os
import sys

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import vfl_oracle_v5 as oracle

def self_evaluate_latest(target_season='3073974'):
    """Evaluates the Oracle's accuracy on the most recent matches in the DB."""
    df = oracle.load_vfl_history()
    if df is None: return
    
    # 1. Blind the oracle to the latest season
    test_data = df[df['season'] == target_season].sort_values('day')
    train_data = df[df['season'] != target_season]
    
    # Re-build profiles from training data only
    profiles = oracle.get_team_profiles(train_data)
    
    print(f"\n--- SELF-EVALUATION: BLIND TEST ON LATEST DATA ({target_season}) ---")
    print(f"Total Matches to Evaluate: {len(test_data)}")
    print("-" * 75)
    
    results = []
    
    for _, row in test_data.iterrows():
        fixture = {
            'home': row['home'], 'away': row['away'],
            'oh': row['oh'], 'od': row['od'], 'oa': row['oa'],
            'sst': row['season_start_time']
        }
        
        pred = oracle.predict_fixture(fixture, train_data, profiles)
        actual = row['outcome_code']
        hit = 1 if pred['prediction'] == actual else 0
        
        results.append({
            'day': row['day'], 'fixture': f"{row['home']} vs {row['away']}",
            'pred': pred['prediction'], 'actual': actual, 'hit': hit,
            'is_strong': pred['is_strong'], 'is_mirror': pred['is_mirror']
        })
        
    res_df = pd.DataFrame(results)
    
    # Analyze
    total_acc = res_df['hit'].mean()
    mirror_df = res_df[res_df['is_mirror'] == True]
    mirror_acc = mirror_df['hit'].mean() if len(mirror_df) > 0 else 0
    strong_df = res_df[res_df['is_strong'] == True]
    strong_acc = strong_df['hit'].mean() if len(strong_df) > 0 else 0
    
    print(f"OVERALL ACCURACY: {total_acc:.1%} ({len(res_df)} matches)")
    print(f"MIRROR LOCKS: {mirror_acc:.1%} ({len(mirror_df)} matches)")
    print(f"STRONG CALLS (3-SIGNAL): {strong_acc:.1%} ({len(strong_df)} matches)")
    print("-" * 75)
    
    if total_acc < 0.6:
        print("ACTION: SHIFT DETECTED. Accuracy on latest data is below target. Moving to Layer 3 Improvement.")
    else:
        print("ACTION: ENGINE STABLE. Accuracy on latest data holding above 60%.")

    return res_df

if __name__ == '__main__':
    self_evaluate_latest()
