import os
import sys
import pandas as pd
import sqlite3
import json

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import vfl_oracle_v5 as oracle

def run_multi_season_simulation(seasons):
    # 1. Load History (Ground Truth)
    df = oracle.load_vfl_history()
    profiles = oracle.get_team_profiles(df)
    
    all_results = []
    
    print(f"\nV5.2 FULL-SPECTRUM SIMULATION - 10 SEASONS (800 MATCHES)")
    print("-" * 85)
    
    for season_id in seasons:
        s_id = str(season_id).replace('vf:season:', '')
        season_df = df[df['season'] == s_id].sort_values('day')
        days = season_df['day'].unique()
        
        # Simulation Logic: MD by MD
        for day in days:
            # Matches for the current day
            day_matches = season_df[season_df['day'] == day]
            
            for _, match in day_matches.iterrows():
                # Build Fixture for Prediction (Zero Ground Truth Contamination)
                # The Oracle will only see matches < day for the win-counts in df
                fixture = {
                    'home': match['home'], 'away': match['away'],
                    'oh': match['oh'], 'od': match['od'], 'oa': match['oa'],
                    'sst': match['season_start_time'], 
                    'day': day, 'season': season_id
                }
                
                # Oracle V5.2 Prediction
                res = oracle.predict_fixture(fixture, df, profiles)
                
                # Check against ground truth
                actual = match['outcome_code']
                is_hit = (res['prediction'] == actual)
                
                # Data Capture for Audit
                all_results.append({
                    'season': season_id,
                    'day': day,
                    'fixture': f"{match['home']} vs {match['away']}",
                    'pred': res['prediction'],
                    'actual': actual,
                    'conf': res['confidence'],
                    'label': res['label'],
                    'is_hit': is_hit,
                    'is_strong': res['is_strong'],
                    'is_mirror': res['is_mirror']
                })

    # 3. Final Accuracy Audit
    results_df = pd.DataFrame(all_results)
    
    print("\n" + "=" * 60)
    print("V5.2 FINAL ACCURACY AUDIT (800 MATCHES)")
    print("=" * 60)
    
    # 1. Mirror Lock Resolution (Target 100%)
    mirror_hits = results_df[results_df['is_mirror']]
    if not mirror_hits.empty:
        acc = mirror_hits['is_hit'].mean()
        print(f"MIRROR LOCK ACCURACY:   {acc:.1%} ({len(mirror_hits[mirror_hits['is_hit']])}/{len(mirror_hits)})")

    # 2. Quota Wall Resolution (Target 100%)
    # Logic: If predicted D or A because of Quota Wall and it was indeed not a win
    wall_hits = results_df[results_df['label'].str.contains('WALL', na=False)]
    if not wall_hits.empty:
        acc = wall_hits['is_hit'].mean()
        # Also count if we predicted a non-win and it was a non-win
        non_win_hit = ((wall_hits['pred'].isin(['D', 'A'])) & (wall_hits['actual'].isin(['D', 'A']))).mean()
        print(f"QUOTA WIN WALL ACC:    {acc:.1%} ({len(wall_hits[wall_hits['is_hit']])}/{len(wall_hits)})")
        print(f"WIN SUPPRESSION ACC:   {non_win_hit:.1%} (Correctly avoided a trap)")

    # 3. Quota Draw Resolution (The High Multiplier Targets)
    draw_hits = results_df[results_df['label'].str.contains('DRAW', na=False)]
    if not draw_hits.empty:
        acc = draw_hits['is_hit'].mean()
        print(f"QUOTA DRAW ALERT ACC:   {acc:.1%} ({len(draw_hits[draw_hits['is_hit']])}/{len(draw_hits)})")

    # 4. Overall Strong Signals
    strong_hits = results_df[results_df['is_strong']]
    overall_acc = strong_hits['is_hit'].mean()
    print(f"OVERALL STRONG ACC:     {overall_acc:.1%} ({len(strong_hits[strong_hits['is_hit']])}/{len(strong_hits)})")
    print("-" * 60)
    print(f"TOTAL MATCHES AUDITED:  {len(results_df)}")
    print("=" * 60)

if __name__ == '__main__':
    test_seasons = [
        '3035337', '3035366', '3035396', '3035425', '3035452',
        '3035481', '3035508', '3035533', '3035569', '3035594'
    ]
    run_multi_season_simulation(test_seasons)
