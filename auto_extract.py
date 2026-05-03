#!/usr/bin/env python3
"""VFL Auto-Extraction & Supabase Sync Engine"""
import requests, json, time, os
from datetime import datetime

SUPABASE_URL = "https://oysfaaafiemteqznguug.supabase.co/rest/v1"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def get_vfl_data():
    """Extract VFL fixtures from msport API"""
    try:
        url = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/current/match/day/info"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return {"season": data.get("seasonId", ""), "match_day": data.get("matchDay", ""), "status": data.get("status")}
    except Exception as e:
        print(f"Extraction error: {e}")
    return None

def sync_to_supabase(data):
    """Send data to Supabase"""
    if not data:
        return
    payload = {"season_id": data.get("season"), "match_day": data.get("match_day"), "status": data.get("status"), "extracted_at": datetime.utcnow().isoformat()}
    try:
        r = requests.post(f"{SUPABASE_URL}/vfl_extractions", headers=HEADERS, json=payload)
        print(f"Synced to Supabase: {r.status_code}")
    except Exception as e:
        print(f"Sync error: {e}")

if __name__ == "__main__":
    data = get_vfl_data()
    sync_to_supabase(data)
    print(f"Extraction cycle completed at {datetime.utcnow()}")