import sqlite3
import os
import sys
from collections import defaultdict

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import predict_v4 as v4

def find_collision():
    print("SEARCHING FOR SIGNATURE COLLISIONS...")
    joined, _, _, _ = v4.build_all_indexes()
    
    # sig -> list of records
    sig_map = defaultdict(list)
    for rec in joined:
        sig = f"{rec['home']}|{rec['away']}|{rec['oh']}|{rec['od']}|{rec['oa']}"
        sig_map[sig].append(rec)
        
    for sig, occurrences in sig_map.items():
        outcomes = set(occ['outcome'] for occ in occurrences)
        if len(outcomes) > 1 and len(occurrences) >= 10:
            print(f"\n[COLLISION FOUND] Signature: {sig}")
            print(f"  Count: {len(occurrences)} matches total")
            for occ in occurrences:
                print(f"  Season: {occ['season']} | Day: {occ['day']} | Result: {occ['outcome']} ({occ['h']}:{occ['a']})")
            
            # Return the first significant collision for deep probing
            return occurrences

if __name__ == '__main__':
    occ_list = find_collision()
    if occ_list:
        # Save to a temp file for the next step
        with open('collision_cases.json', 'w') as f:
            import json
            json.dump(occ_list, f)
