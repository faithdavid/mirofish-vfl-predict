import argparse
import sqlite3
import pandas as pd
from pathlib import Path
import os

# --- CONFIG ---
ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "vfl_history.db"
BET_LOG = ROOT / "ANalysis" / "bet_log.csv"

def update_results():
    if not BET_LOG.exists():
        print("[ERROR] No bet_log.csv found. Run bot.py first.")
        return

    df = pd.read_csv(BET_LOG)
    pending = df[df['status'] == 'PENDING']
    
    if pending.empty:
        print("[LOG] No pending bets to resolve.")
        return
        
    print(f"--- MIROFISH VFL RESOLUTION: {len(pending)} BETS ---")
    
    resolved_count = 0
    for index, row in pending.iterrows():
        print(f"\nFixture: {row['fixture']} | Pick: {row['target']} | Odds: {row['odds']}")
        result = input("Actual Result (H/D/A) or 'S' to skip: ").upper()
        
        if result == 'S': continue
        
        # Calculate P&L
        status = 'WIN' if result == row['target'] else 'LOSS'
        profit = (row['stake'] * (row['odds'] - 1)) if status == 'WIN' else -row['stake']
        
        # Update DF
        df.at[index, 'status'] = status
        df.at[index, 'profit'] = round(profit, 2)
        resolved_count += 1
        
        # ─── RECURSIVE FEEDBACK: Update History DB ───
        # This keeps the V8.0 Global Balancer updated with the latest trends
        try:
            conn = sqlite3.connect(DB_PATH)
            # Find the ID for this fixture if possible, or insert as new
            # We insert into 'matches' to keep the training data fresh
            # Using current dummy season and day for MD 27+
            conn.execute("""
                INSERT INTO matches (season, day, home, away, outcome)
                VALUES ('4494', '27', ?, ?, ?)
            """, (row['fixture'].split(' vs ')[0], row['fixture'].split(' vs ')[1], result))
            conn.commit()
            conn.close()
            print(f"[RECURSIVE] Result fed back into vfl_history.db for training.")
        except Exception as e:
            print(f"[ERROR] Database feedback failed: {e}")

    # Save CSV
    df.to_csv(BET_LOG, index=False)
    print(f"\n[LOG] {resolved_count} bets resolved. P&L updated in ANalysis/bet_log.csv")

if __name__ == '__main__':
    update_results()
