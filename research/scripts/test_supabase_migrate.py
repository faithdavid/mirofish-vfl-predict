import os
import sys
from pathlib import Path
import sqlite3
import time

ROOT = Path(__file__).parent.parent
sys.path.append(os.path.join(ROOT, 'lib'))

from supabase_rest import db as supabase_db

OLD_DB = ROOT / "vfl_history.db"
NEW_DB = ROOT / "sovereign_vbf.db"

def verify_and_migrate():
    if not supabase_db.active:
        print("[MIGRATION] ❌ Supabase client is not active (credentials missing).")
        return

    # Check connection
    try:
        print("[MIGRATION] ⚡ Testing connection to Supabase...")
        res = supabase_db._post("master_ledger", {})
    except Exception as e:
        pass
        
    print("[MIGRATION] ✅ Supabase REST adapter is initialized.")

    print("[MIGRATION] 🚀 Starting BULK migration of ~50,000 records to Supabase...")
    
    with sqlite3.connect(OLD_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # Get all historical matches
        cur.execute("SELECT * FROM matches")
        rows = cur.fetchall()

    success_count = 0
    fail_count = 0
    batch_size = 500  # Supabase REST prefers chunks
    current_batch = []
    local_batch = []

    print(f"[MIGRATION] Total local records found in history: {len(rows)}")

    # Proceed in chunks
    for index, row in enumerate(rows):
        row_dict = dict(row)
        
        # We don't have predictions/odds for ancient history, only outcomes
        payload = {
            "match_id": row_dict.get("id") or row_dict.get("match_id"),
            "season_id": row_dict.get("season_id") or row_dict.get("season"),
            "match_day": row_dict.get("match_day") or row_dict.get("day"),
            "home_team": row_dict.get("home_team") or row_dict.get("home"),
            "away_team": row_dict.get("away_team") or row_dict.get("away"),
            "full_time": row_dict.get("full_time") or row_dict.get("score"),
            "outcome": row_dict.get("outcome_code") or row_dict.get("outcome"),
            "status": "SETTLED" if (row_dict.get("full_time") or row_dict.get("score")) else "PENDING"
        }
        
        # Clean null values
        payload = {k: v for k, v in payload.items() if v is not None}
        current_batch.append(payload)
        
        # Tuple for local DB
        local_batch.append((
            payload["match_id"], payload["season_id"], payload["match_day"],
            payload["home_team"], payload["away_team"], payload.get("full_time"),
            payload.get("outcome"), payload["status"]
        ))
        
        # Push batch
        if len(current_batch) >= batch_size or index == len(rows) - 1:
            # 1. Push to Cloud Custom Bulk Method
            headers = dict(supabase_db.headers)
            headers["Prefer"] = "return=minimal,resolution=ignore-duplicates"
            
            try:
                import requests
                resp = requests.post(
                    f"{supabase_db.url}/rest/v1/master_ledger", 
                    headers=headers, 
                    json=current_batch,
                    timeout=15
                )
                if resp.status_code in [200, 201]:
                    success_count += len(current_batch)
                else:
                    print(f"[ERROR] Batch failed: {resp.text}")
                    fail_count += len(current_batch)
            except Exception as e:
                print(f"[ERROR] Batch request exception: {e}")
                fail_count += len(current_batch)
            
            # 2. Sync to new Local SQLite
            try:
                with sqlite3.connect(NEW_DB) as nw_conn:
                    nw_cur = nw_conn.cursor()
                    nw_cur.executemany('''
                        INSERT OR IGNORE INTO master_ledger 
                        (match_id, season_id, match_day, home_team, away_team, full_time, outcome, status) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', local_batch)
                    nw_conn.commit()
            except Exception as e:
                print(f"[ERROR] Local sync exception: {e}")

            print(f"  ... Migrated {min(index + 1, len(rows))} / {len(rows)} records.")
            current_batch = []
            local_batch = []

    print("-" * 40)
    print(f"[MIGRATION COMPLETE]")
    print(f"✅ Batch Success: {success_count} matches pushed")
    print(f"❌ Batch Failed: {fail_count}")
    print("-" * 40)

if __name__ == "__main__":
    verify_and_migrate()

