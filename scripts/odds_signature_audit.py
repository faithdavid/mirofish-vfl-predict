import sqlite3
import os

def odds_audit():
    db_path = 'vfl_history.db'
    if not os.path.exists(db_path):
        print("Database not found.")
        return

    conn = sqlite3.connect(db_path)
    
    # Query for exact fixture/odds signatures that recur
    query = """
        SELECT home, away, oh, od, oa, outcome, count_outcome, total_played
        FROM (
            SELECT home, away, oh, od, oa, outcome, 
                   COUNT(*) as count_outcome,
                   SUM(COUNT(*)) OVER (PARTITION BY home, away, oh, od, oa) as total_played
            FROM matches 
            WHERE oh IS NOT NULL AND od IS NOT NULL AND oa IS NOT NULL 
              AND home IS NOT NULL AND away IS NOT NULL
            GROUP BY home, away, oh, od, oa, outcome
        )
        WHERE count_outcome >= 2
        ORDER BY total_played DESC, count_outcome DESC
        LIMIT 40
    """
    
    results = conn.execute(query).fetchall()
    
    print("--- VFL SOVEREIGN AUDIT: THE ODDS-KEYED BARCODE ---")
    print(f"{'FIXTURE':<30} | {'ODDS (H/D/A)':<22} | {'OUTCOME'} | {'RATIO'} | {'PRECISION'}")
    print("-" * 100)
    
    if not results:
        print("No identical odds-signature repetitions found.")
    else:
        for row in results:
            home, away, oh, od, oa, outcome, count_out, total = row
            if outcome is None: continue
            
            odds_key = f"{oh}/{od}/{oa}"
            fixture_key = f"{home} vs {away}"
            
            precision = (count_out / total) * 100 if total > 0 else 0
            
            # Highlight Barcode Locks (100% and total >= 2)
            lock_status = " [BARCODE LOCK]" if precision == 100 and total >= 3 else ""
            
            print(f"{fixture_key:<30} | {odds_key:<22} | {outcome:<7} | {count_out}/{total} | {precision:3.0f}%{lock_status}")

if __name__ == '__main__':
    odds_audit()
