import sqlite3
import pandas as pd
import numpy as np
import os
from pathlib import Path

# --- CONFIG ---
ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "vfl_history.db"
BANKROLL = 5000.0
KELLY_FRACTION = 0.25  # Quarter-Kelly for safety
MIN_EDGE = 0.05       # 5% edge required

def backtest():
    if not os.path.exists(DB_PATH):
        print("Database not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    
    # Load all historical matches with odds and outcomes
    # We focus on Home/Draw/Away (1x2) markets
    query = """
        SELECT season, day, home, away, oh, od, oa, outcome 
        FROM matches 
        WHERE oh IS NOT NULL AND od IS NOT NULL AND oa IS NOT NULL AND outcome IS NOT NULL
        ORDER BY id ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("No historical data with odds found.")
        return

    print(f"--- VFL SOVEREIGN BACKTEST: {len(df):,} MATCHES ---")
    print(f"Simulating Bankroll: NGN{BANKROLL:,.0f} | Kelly: {KELLY_FRACTION}x")
    
    current_bankroll = BANKROLL
    peak_bankroll = BANKROLL
    max_drawdown = 0
    bets_placed = 0
    wins = 0
    
    # Simple probability model for backtest (Historical Win Rate per Odds Cluster)
    # In live mode, this is replaced by vfl_oracle_v5.get_probability()
    for index, row in df.iterrows():
        # Identify the 'Value' pick based on historical frequency (simulating Oracle)
        # We simplify for the core backtest logic
        probs = [1/row['oh'], 1/row['od'], 1/row['oa']]
        total_p = sum(probs)
        probs = [p/total_p for p in probs] # House-adjusted base prob
        
        # Determine the pick (Simplistic logic: Follow the lowest odds with simulated edge)
        # In actual bot.py, this will call vfl_oracle_v5
        pick_idx = np.argmin([row['oh'], row['od'], row['oa']])
        odds = [row['oh'], row['od'], row['oa']][pick_idx]
        outcome_map = ['H', 'D', 'A']
        pick_outcome = outcome_map[pick_idx]
        
        # Win probability (Simulated 5% edge over house)
        p_win = (1/odds) + MIN_EDGE
        # EV Calculation: (Win Probability * Odds) - 1
        ev = (p_win * odds) - 1
        
        # KEY REFINEMENT: Only bet if EV is significantly positive (+5% edge)
        if ev < 0.05: continue
        
        b = odds - 1
        
        # Kelly Stake
        f_star = (b * p_win - (1 - p_win)) / b if b > 0 else 0
        f_star = max(0, f_star) * KELLY_FRACTION
        f_star = min(f_star, 0.05) # Cap at 5% of bankroll
        
        stake = current_bankroll * f_star
        if stake < 100: continue # Min bet NGN 100
        
        # Normalization: Ensure 'HOME' matches 'H', etc.
        actual_outcome = str(row['outcome'])[0].upper() if row['outcome'] else None
        
        bets_placed += 1
        if actual_outcome == pick_outcome:
            current_bankroll += (stake * b)
            wins += 1
        else:
            current_bankroll -= stake
            
        # Stats
        peak_bankroll = max(peak_bankroll, current_bankroll)
        drawdown = (peak_bankroll - current_bankroll) / peak_bankroll
        max_drawdown = max(max_drawdown, drawdown)
        
        # If bust
        if current_bankroll < 100:
            print(f"BANKRUPTCY at Match {index}!")
            break

    print("-" * 50)
    print(f"Total Bets: {bets_placed}")
    print(f"Win Rate:   {wins/bets_placed:.1%}" if bets_placed > 0 else "N/A")
    print(f"Final Bankroll: NGN{current_bankroll:,.2f}")
    print(f"Total Profit:  {(current_bankroll - BANKROLL) / BANKROLL:.1%}")
    print(f"Max Drawdown:   {max_drawdown:.1%}")

if __name__ == '__main__':
    backtest()
