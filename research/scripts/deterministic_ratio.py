import sqlite3
import os

def check_ratio():
    db_path = 'vfl_history.db'
    if not os.path.exists(db_path):
        print("Database not found.")
        return

    conn = sqlite3.connect(db_path)
    
    # Query for MD 26 fixtures with total played vs outcome count
    query = """
        SELECT home, away, outcome, count_outcome, total_played
        FROM (
            SELECT home, away, outcome, 
                   COUNT(*) as count_outcome,
                   SUM(COUNT(*)) OVER (PARTITION BY home, away) as total_played
            FROM matches 
            WHERE day = 26 
            GROUP BY home, away, outcome
        )
        WHERE count_outcome >= 1
        ORDER BY total_played DESC, count_outcome DESC
        LIMIT 40
    """
    
    results = conn.execute(query).fetchall()
    
    print("--- VFL SOVEREIGN AUDIT: DETERMINISTIC RATIO (MD 26) ---")
    print(f"{'FIXED FIXTURE':<35} | {'OUTCOME'} | {'RATIO'} | {'PRECISION'}")
    print("-" * 85)
    
    seen = set()
    for row in results:
        home, away, outcome, count_out, total = row
        if not home or not away or outcome is None:
            continue
            
        fixture_key = f"{home} vs {away}"
        precision = (count_out / total) * 100 if total > 0 else 0
        
        # Highlight Universal Locks (100% and total >= 3)
        status = " [UNIVERSAL LOCK]" if precision == 100 and total >= 3 else ""
        
        print(f"{fixture_key:<35} | {outcome:<7} | {count_out}/{total} | {precision:3.0f}%{status}")

if __name__ == '__main__':
    check_ratio()
