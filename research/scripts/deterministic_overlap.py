import sqlite3
import os

def check_overlap():
    db_path = 'vfl_history.db'
    if not os.path.exists(db_path):
        print("Database not found.")
        return

    conn = sqlite3.connect(db_path)
    
    # Query for MD 26 fixtures that recur with the SAME outcome
    query = """
        SELECT home, away, outcome, COUNT(*) as c 
        FROM matches 
        WHERE day = 26 
        GROUP BY home, away, outcome 
        HAVING c > 1 
        ORDER BY c DESC 
        LIMIT 20
    """
    
    results = conn.execute(query).fetchall()
    
    print("--- VFL FORENSIC PROOF: DETERMINISTIC OVERLAP (MD 26) ---")
    print(f"{'FIXED FIXTURE':<35} | {'OUTCOME'} | {'RECURRENCE'}")
    print("-" * 75)
    
    if not results:
        print("No exact MD 26 overlaps found in current dataset.")
    else:
        for home, away, outcome, count in results:
            print(f"{home + ' vs ' + away:<35} | {outcome:<7} | {count}x Mirror")

if __name__ == '__main__':
    check_overlap()
