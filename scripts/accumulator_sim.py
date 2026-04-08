"""
MiroFish ₦30 → ₦1M Accumulator Simulator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strategy:
  1. Pick the Top 2 highest-certainty "LOCK" fixtures per matchday.
  2. Form a double accumulator (odds ~3.4x).
  3. All-in compound staking (100% of balance).
  4. Target: ₦1,000,000 (reached in 9 consecutive hits).
  5. If any leg fails, balance = 0 (Bankrupt) — restart from ₦30.

Data: Uses historical 45k match history to determine win rates.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import sys
import os
import random
import pandas as pd
from pathlib import Path

# Add scripts to path for Oracle
sys.path.append(str(Path(__file__).parent))
import vfl_oracle_v6 as oracle

def run_simulation(start_stake=30.0, target=1000000.0):
    print("━" * 50)
    print(" ₦30 → ₦1M ACCUMULATOR BACKTEST")
    print("━" * 50)

    # 1. Load History
    df = oracle.load_vfl_history()
    if df is None:
        print("❌ History file not found (ANalysis/vfl_history.csv)")
        return
    
    sigs = oracle.load_signature_db()
    profiles = oracle.get_team_profiles(df)
    
    # 2. Iterate by Season + Matchday
    # Since we need 2 per matchday, we simulate Oracle V6 on each MD
    results = []
    
    # Let's slice the last 10 seasons for a faster/relevant backtest (300 MDs)
    seasons = sorted(df['season'].unique())[-10:]
    print(f"Replaying last {len(seasons)} seasons ({len(seasons)*30} matchdays)...")

    ladder_step = 0
    balance = start_stake
    bankruptcies = 0
    successes = 0
    max_step = 0
    
    for season in seasons:
        # Pass the full season ID to accounting if needed, or follow Oracle's cleaning
        accounting = oracle.get_seasonal_accounting(df, season)
        for md in range(1, 31):
            # Get fixtures for this MD
            fxts_df = df[(df['season'] == season) & (df['day'] == md)]
            if len(fxts_df) < 2: continue
            
            # Predict all fixtures
            day_preds = []
            for _, f in fxts_df.iterrows():
                f_in = {
                    'home': f['home'], 'away': f['away'],
                    'oh': f['oh'], 'od': f['od'], 'oa': f['oa'],
                    'day': md, 'season': f"vf:season:{season}" 
                }
                p = oracle.predict_fixture_v6(f_in, df, profiles, sigs, accounting)
                p['actual'] = f['outcome_code'] # Use outcome_code from DB
                day_preds.append(p)
            
            # Pick Top 2 LOCKs
            # Filter for only those that reached LOCK or SIGNAL threshold
            day_preds.sort(key=lambda x: x['certainty_score'], reverse=True)
            top_two = day_preds[:2]
            
            # Evaluate Accumulator
            # A 'None' outcome in Oracle means we didn't pick anything
            is_win = all(p['prediction'] == p['actual'] for p in top_two)
            combined_odds = top_two[0]['target_odds'] * top_two[1]['target_odds']

            
            if is_win:
                ladder_step += 1
                balance *= combined_odds
                max_step = max(max_step, ladder_step)
                # print(f"  ✅ HIT! [Step {ladder_step}] Balance: ₦{balance:,.2f}")
                
                if balance >= target:
                    print(f"  💰 TARGET REACHED! ₦{balance:,.2f} after {ladder_step} rounds.")
                    successes += 1
                    balance = start_stake # Reset to try again
                    ladder_step = 0
            else:
                # print(f"  ❌ MISS. [Step {ladder_step}] Resetting...")
                ladder_step = 0
                balance = start_stake
                bankruptcies += 1

    print("━" * 50)
    print(f" FINAL REPORT")
    print(f" Total Attempts: {bankruptcies + successes}")
    print(f" Successful 1M Runs: {successes}")
    print(f" Bankruptcies: {bankruptcies}")
    print(f" Deepest Run: {max_step} / 9 rounds")
    print(f" Hit Rate: {(successes / max(1, bankruptcies + successes)) * 100:.2f}%")
    print("━" * 50)

if __name__ == "__main__":
    run_simulation()
