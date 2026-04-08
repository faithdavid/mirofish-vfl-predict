import sqlite3
import os

def recursive_audit():
    db_path = 'vfl_history.db'
    if not os.path.exists(db_path):
        print("Database not found.")
        return

    conn = sqlite3.connect(db_path)
    
    # Query for transitions: MD 26, Season N -> Season N_NEXT
    query = """
        WITH MatchesWithNext AS (
            SELECT m1.home, m1.away, m1.day, m1.season, m1.outcome as result_n,
                   (SELECT outcome FROM matches m2 
                    WHERE m2.home=m1.home AND m2.away=m1.away AND m2.day=m1.day AND m2.season > m1.season 
                    ORDER BY m2.season ASC LIMIT 1) as result_next
            FROM matches m1
            WHERE m1.day = 26 AND m1.outcome IS NOT NULL
        )
        SELECT result_n, result_next, COUNT(*) as c
        FROM MatchesWithNext
        WHERE result_next IS NOT NULL
        GROUP BY result_n, result_next
        ORDER BY result_n, c DESC
    """
    
    results = conn.execute(query).fetchall()
    
    print("--- VFL SOVEREIGN AUDIT: RECURSIVE TRANSITION MATRIX (MD 26) ---")
    print(f"{'PREV RESULT':<15} | {'NEXT RESULT':<15} | {'FREQUENCY'} | {'PROBABILITY'}")
    print("-" * 75)
    
    # Calculate group totals for percentages
    totals = {}
    for r in results:
        res_n = r[0] if r[0] else "NULL"
        totals[res_n] = totals.get(res_n, 0) + r[2]
        
    if not results:
        print("No recursive MD 26 data found.")
    else:
        for row in results:
            prev, nxt, count = row
            if prev is None: prev = "NULL"
            if nxt is None: nxt = "NULL"
            
            total = totals.get(prev, 1)
            prob = (count / total) * 100
            print(f"{prev:<15} | {nxt:<15} | {count:<9} | {prob:3.0f}%")

if __name__ == '__main__':
    recursive_audit()
