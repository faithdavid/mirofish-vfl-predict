import os
import requests
import json
from dotenv import load_dotenv
from pathlib import Path

# Load config from the project root .env
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

class SupabaseREST:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL", "")
        self.key = os.getenv("SUPABASE_KEY", "")
        if not self.url or not self.key:
            print("[SUPABASE] ⚠️ Credentials missing. Cloud sync disabled.")
            self.active = False
        else:
            self.active = True
            
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def _post(self, table, data):
        if not self.active: return None
        try:
            res = requests.post(
                f"{self.url}/rest/v1/{table}", 
                headers=self.headers, 
                json=data, 
                timeout=5
            )
            res.raise_for_status()
            return res.json()
        except Exception as e:
            print(f"[SUPABASE] ❌ Post error on {table}: {e}")
            return None

    def _patch(self, table, match_id, data):
        if not self.active: return None
        try:
            res = requests.patch(
                f"{self.url}/rest/v1/{table}?match_id=eq.{match_id}",
                headers=self.headers,
                json=data,
                timeout=5
            )
            res.raise_for_status()
            return res.json()
        except Exception as e:
            print(f"[SUPABASE] ❌ Patch error on {table}: {e}")
            return None

    def insert_fixture(self, record):
        """Insert a newly captured fixture prediction."""
        # Using upsert logic via headers
        headers = dict(self.headers)
        headers["Prefer"] = "resolution=merge-duplicates"
        if not self.active: return None
        
        try:
            res = requests.post(f"{self.url}/rest/v1/master_ledger", headers=headers, json=record, timeout=5)
            res.raise_for_status()
            return True
        except Exception as e:
            print(f"[SUPABASE] ❌ Insert Fixture Failed: {e}")
            return False

    def settle_fixture(self, match_id, update_payload):
        """Update the fixture once the match final score comes in."""
        return self._patch("master_ledger", match_id, update_payload)

# Global instance for easy imports
db = SupabaseREST()
