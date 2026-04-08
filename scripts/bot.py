import argparse
import sqlite3
import pandas as pd
import numpy as np
import time
from datetime import datetime
from pathlib import Path
import os
import sys
import json

# Add scripts folder to sys.path to import vfl_oracle_v5
sys.path.append(os.path.dirname(__file__))
try:
    import vfl_oracle_v5 as oracle
except ImportError:
    oracle = None

# --- CONFIG ---
ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "vfl_history.db"
BET_LOG = ROOT / "ANalysis" / "bet_log.csv"
SIM_DB = ROOT / "ANalysis" / "simulated_pnl.db"
BANKROLL = 5000.0
KELLY_FRACTION = 0.25  # Quarter-Kelly for risk mitigation
MIN_EDGE = 0.05       # 5% edge required over house odds

def calculate_ev(prob, odds):
    """(Winning Probability * Decimal Odds) - 1"""
    return (prob * odds) - 1

def calculate_kelly_stake(bankroll, prob, odds):
    """Fractional Kelly stake sizing."""
    b = odds - 1
    if b <= 0: return 0
    f_star = (b * prob - (1 - prob)) / b
    stake = bankroll * max(0, f_star) * KELLY_FRACTION
    # Rules: Max 5% per bet, Min NGN 100
    stake = min(stake, bankroll * 0.05)
    return max(0, round(stake, 2))

def run_bot(mode='dry-run'):
    print(f"--- MIROFISH VFL BOT: {mode.upper()} MODE ---")
    
    # Verify Oracle integration
    if oracle is None:
        print("[ERROR] vfl_oracle_v5.py not found. Bot cannot calculate probabilities.")
        return

    # In a real scenario, we'd fetch live fixtures here. 
    # For now, we simulate the 'Upcoming' MatchDay scanning MD 27-30.
    # Replace with real JSON scraping when ready.
    print("[LOG] Scanning for upcoming MatchDay 27 fixtures...")
    
    # 1. Load the Historical Data Memory (V5.2)
    df = oracle.load_vfl_history()
    profiles = oracle.get_team_profiles(df)
    
    # 2. Get Seasonal Accounting (V8.0)
    # Using 'SOVEREIGN' as a default if not specified
    accounting = oracle.get_seasonal_accounting(df, 'SOVEREIGN')
    print(f"[ACCOUNTING] Current Draws: {accounting['D']} / Total in DB")
    
    # Day is usually dynamic, we mock 27 for now or extract from JSON later
    current_day = 27
    
    # 3. Simulate Fixture Analysis 
    radar_path = ROOT / "ANalysis" / "radar_live.json"
    fixtures = []
    
    if radar_path.exists():
        with open(radar_path, 'r') as f:
            radar_data = json.load(f)
            raw_fixtures = radar_data.get('fixtures', [])
            current_day = int(radar_data.get('matchDay', 27))
            
            for fxt in raw_fixtures:
                # Format: (home, away, draw_odds)
                fixtures.append((fxt['home'], fxt['away'], fxt['odds'][1]))
        print(f"[LOG] Loaded {len(fixtures)} fixtures from Radar (MD {current_day})")
    else:
        print("[WARNING] radar_live.json not found. Using fallback mock fixtures.")
        fixtures = [
            ('London Guns', 'Chelsea', 3.45), # High probability Draw point
            ('Manchester Red', 'Bournemouth', 1.55),
            ('Brighton', 'Leeds', 2.85)
        ]
    
    qualified_bets = []
    for home, away, odds in fixtures:
        # Get Sovereign Prediction from the V8.0 Oracle
        # In a real bot, we'd pass OH/OD/OA from MSport
        f_data = {
            'home': home, 'away': away, 'oh': odds, 'od': 3.0, 'oa': 3.0, # Mocking other odds for now
            'sst': '0', 'day': current_day, 'season': 'SOVEREIGN'
        }
        pred_res = oracle.predict_fixture(f_data, df, profiles)
        
        # Apply Global Balancing V5.2
        pred_res = oracle.apply_global_balancing(pred_res, accounting, current_day)
        
        # We are targeting DRAWS in this specific bot logic
        prob = pred_res['confidence'] if pred_res['prediction'] == 'D' else (1.0 - pred_res['confidence']) / 2
        
        prob = min(0.95, prob) # Cap
        
        ev = calculate_ev(prob, odds)
        edge = prob - (1/odds)
        
        if edge >= MIN_EDGE:
            stake = calculate_kelly_stake(BANKROLL, prob, odds)
            if stake >= 100:
                qualified_bets.append({
                    'fixture': f"{home} vs {away}",
                    'target': 'DRAW',
                    'prob': round(prob, 2),
                    'odds': odds,
                    'edge': round(edge, 2),
                    'ev': round(ev, 2),
                    'stake': stake,
                    'status': 'PENDING'
                })

    if not qualified_bets:
        print("[LOG] No qualifying +EV bets found for this cycle.")
        return

    # Log to CSV
    BET_LOG.parent.mkdir(exist_ok=True)
    df_bets = pd.DataFrame(qualified_bets)
    if BET_LOG.exists():
        df_bets.to_csv(BET_LOG, mode='a', header=False, index=False)
    else:
        df_bets.to_csv(BET_LOG, index=False)

    print(f"[LOG] {len(qualified_bets)} qualifying bets logged to bet_log.csv")
    for b in qualified_bets:
        print(f"  -> {b['fixture']} [DRAW] | EV: {b['ev']} | STAKE: NGN{b['stake']}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['dry-run', 'live'], default='dry-run')
    args = parser.parse_args()
    run_bot(args.mode)
