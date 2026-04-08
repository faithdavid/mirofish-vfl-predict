import sqlite3
import pandas as pd
import os

def mirror_audit():
    db_path = 'vfl_history.db'
    if not os.path.exists(db_path):
        print("Database not found.")
        return

    conn = sqlite3.connect(db_path)
    
    # The 8 MD 26 Fixtures from your request
    fixtures = [
        ('Brighton', 'Leeds'),
        ('Newcastle', 'Fulham'),
        ('West Ham', 'Manchester Blue'),
        ('Wolverhampton', 'Liverpool'),
        ('London Guns', 'Chelsea'),
        ('Aston Villa', 'Tottenham'),
        ('Crystal Palace', 'Everton'),
        ('Bournemouth', 'Manchester Red')
    ]
    
    print("--- VFL DETERMINISTIC MIRROR AUDIT: MATCHDAY 26 ---")
    print(f"{'FIXTURE':<35} | {'COUNT':<6} | {'OUTCOME CLUSTER'}")
    print("-" * 105)
    
    for h, a in fixtures:
        query = f"SELECT outcome, COUNT(*) as c FROM matches WHERE day = 26 AND home = '{h}' AND away = '{a}' GROUP BY outcome ORDER BY c DESC"
        results = conn.execute(query).fetchall()
        total = sum(r[1] for r in results)
        
        if total > 0:
            cluster_str = ", ".join([f"{r[0]}:{r[1]}" for r in results])
            # Highlight if one outcome is dominant (>= 50%)
            is_fixed = any(r[1]/total >= 0.5 for r in results)
            marker = " [FIXED POINT]" if is_fixed and total >= 3 else ""
            print(f"{h + ' vs ' + a:<35} | {total:<6} | {cluster_str}{marker}")
        else:
            print(f"{h + ' vs ' + a:<35} | 0      | NO DATA")

if __name__ == '__main__':
    mirror_audit()
