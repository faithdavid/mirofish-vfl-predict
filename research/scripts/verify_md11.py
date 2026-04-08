import sqlite3
import pandas as pd

DB_PATH = 'vfl_history.db'
SEASON = '3073974'
DAY = 11

def verify_scorecard():
    conn = sqlite3.connect(DB_PATH)
    # 1. Get the actuals
    c = conn.cursor()
    c.execute(f"SELECT home, away, outcome FROM matches WHERE season LIKE '%{SEASON}%' AND day = {DAY}")
    actuals = {(r[0], r[1]): r[2] for r in c.fetchall()}
    conn.close()

    if not actuals:
        print(f"RESULTS FOR SEASON {SEASON} MD {DAY} NOT FOUND IN DB.")
        return

    # 2. Hard-coded predictions from our Oracle MD11 run
    predictions = [
        ('LEEDS', 'MANCHESTER RED', 'A', 'STRONG HIGH'),
        ('CRYSTAL PALACE', 'MANCHESTER BLUE', 'A', 'STRONG HIGH'),
        ('FULHAM', 'CHELSEA', 'A', 'STRONG HIGH'),
        ('ASTON VILLA', 'NEWCASTLE', 'H', 'STRONG HIGH'),
        ('LONDON GUNS', 'LIVERPOOL', 'H', 'LOW'),
        ('WOLVERHAMPTON', 'WEST HAM', 'A', 'LOW'),
        ('TOTTENHAM', 'BRIGHTON', 'H', 'STRONG MODERATE'),
        ('BOURNEMOUTH', 'EVERTON', 'A', 'MODERATE')
    ]

    print(f"\nVFL ORACLE V5.1 - PROOF OF ACCURACY (MD 11)")
    print("=" * 70)
    print(f"{'FIXTURE':<35} | {'PRED':<4} | {'ACTUAL':<6} | {'STATUS'}")
    print("-" * 70)

    hits = 0
    total_strong = 0
    strong_hits = 0

    for ht, at, pred, label in predictions:
        actual = actuals.get((ht, at), '?')
        # Map DB outcomes ('HOME', 'AWAY', 'DRAW') to 'H', 'A', 'D'
        actual_code = actual[0] if actual != '?' else '?'
        
        hit_str = "CORRECT" if pred == actual_code else "MISS"
        if pred == actual_code:
            hits += 1
            if 'STRONG' in label: strong_hits += 1
            
        if 'STRONG' in label: total_strong += 1
        
        print(f"{ht + ' vs ' + at:<35} | {pred:<4} | {actual_code:<6} | {hit_str}")

    print("-" * 70)
    print(f"Overall Accuracy: {hits/len(predictions):.1%}")
    if total_strong > 0:
        print(f"STRONG CALLS ACCURACY: {strong_hits/total_strong:.1%} ({total_strong} calls)")
    print("=" * 70)

if __name__ == '__main__':
    verify_scorecard()
