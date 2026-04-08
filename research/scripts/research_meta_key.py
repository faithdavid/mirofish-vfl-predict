import sqlite3
import os

DB_PATH = 'vfl_history.db'

def analyze_collisions():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    print("VFL V5 FORENSIC AUDIT: META-KEY RESOLUTION")
    print("=" * 80)
    
    # 1. Find all signatures that produce multiple outcomes
    c.execute('''
        SELECT home, away, oh, od, oa, COUNT(DISTINCT outcome) as out_count, COUNT(*) as match_count
        FROM matches
        WHERE oh IS NOT NULL AND outcome IS NOT NULL
        GROUP BY home, away, oh, od, oa
        HAVING out_count > 1
        ORDER BY match_count DESC
    ''')
    collisions = c.fetchall()
    
    if not collisions:
        print("No collisions found! Either the data is too small or every signature is already 100% deterministic.")
        return

    print(f"Found {len(collisions)} signatures with multiple historical outcomes.")
    print("-" * 80)
    
    resolved = 0
    total_col = len(collisions)
    
    for home, away, oh, od, oa, out_cnt, m_cnt in collisions[:10]: # Analyze top 10
        print(f"\n[SIGNATURE] {home} vs {away} | Odds: {oh}/{od}/{oa} | Matches: {m_cnt}")
        
        # 2. Check if season_start_time resolves it
        c.execute('''
            SELECT season_start_time, outcome, COUNT(*)
            FROM matches
            WHERE home=? AND away=? AND oh=? AND od=? AND oa=?
            GROUP BY season_start_time, outcome
        ''', (home, away, oh, od, oa))
        sst_groups = c.fetchall()
        
        # If every SST only ever produces ONE outcome, then SST is the key!
        sst_map = {}
        is_deterministic = True
        for sst, out, cnt in sst_groups:
            if sst not in sst_map: sst_map[sst] = out
            elif sst_map[sst] != out:
                is_deterministic = False
                break
        
        if is_deterministic:
            print(f"  + RESOLVED: season_start_time is the DETERMINISTIC KEY.")
            resolved += 1
            # Show the mapping
            for sst, out in list(sst_map.items())[:3]:
                print(f"    Seed {sst} => Always {out}")
        else:
            print(f"  - FAILED: Multiple outcomes even for the same season_start_time.")

    print("\n" + "=" * 80)
    print(f"Resolution Rate for Top Collisions: {resolved}/{min(10, total_col)} solved via Metadata.")
    conn.close()

if __name__ == '__main__':
    analyze_collisions()
