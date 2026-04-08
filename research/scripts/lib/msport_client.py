"""
MSport VFL API Client - V2
==========================
Endpoints:
  Heartbeat : GET /virtual/current/match/day/info
  Odds      : GET /virtual/match/day/event/list?seasonId=X&matchDay=Y
  Results   : GET /virtual/result?seasonId=X&matchDay=Y
"""
import requests
import json
import os

class MSportClient:
    def __init__(self, auth_file='msport_auth.json'):
        self.auth_file = auth_file
        self.headers = {}
        self.cookies = {}
        self.base_url = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual"
        self.verbose = True
        self.load_auth()

    def load_auth(self):
        if os.path.exists(self.auth_file):
            try:
                with open(self.auth_file, 'r') as f:
                    data = json.load(f)
                    self.headers = data.get('headers', {})
                    self.cookies = data.get('cookies', {})
            except Exception as e:
                print(f"[MSPORT] Auth load error: {e}")

    def save_auth(self, headers, cookies):
        with open(self.auth_file, 'w') as f:
            json.dump({'headers': headers, 'cookies': cookies}, f, indent=4)
        self.headers = headers
        self.cookies = cookies

    def heartbeat(self):
        """
        Returns the CURRENT matchday state.
        Response shape: {matchDay: int, seasonId: str, status: str, ...}
        status is one of: PRE_MATCH, MATCH, SETTLED, etc.
        """
        url = f"{self.base_url}/current/match/day/info"
        if self.verbose:
            print(f"[MSPORT] Heartbeat -> {url}")
        try:
            r = requests.get(url, headers=self.headers, cookies=self.cookies, timeout=10)
            if r.status_code == 200:
                body = r.json()
                if body.get('bizCode') == 10000:
                    return body.get('data', {})
                else:
                    print(f"[MSPORT] Heartbeat bizCode: {body.get('bizCode')} - {body.get('message','')}")
            else:
                print(f"[MSPORT] Heartbeat HTTP {r.status_code}")
        except Exception as e:
            print(f"[MSPORT] Heartbeat error: {e}")
        return None

    # Backwards-compat alias
    def get_active_season(self):
        d = self.heartbeat()
        if d:
            return {"current": d, "status": d.get("status")}
        return None

    def get_odds(self, season_id, match_day):
        """Fetch 1X2 odds for a specific matchday. Returns data dict or None."""
        url = f"{self.base_url}/match/day/event/list"
        params = {"seasonId": season_id, "matchDay": match_day}
        if self.verbose:
            print(f"[MSPORT] Odds -> MD {match_day} | {season_id}")
        try:
            r = requests.get(url, headers=self.headers, cookies=self.cookies, params=params, timeout=10)
            if r.status_code == 200:
                body = r.json()
                if body.get('bizCode') == 10000:
                    return body.get('data')
                else:
                    print(f"[MSPORT] Odds bizCode: {body.get('bizCode')} (not ready yet)")
            else:
                print(f"[MSPORT] Odds HTTP {r.status_code}")
        except Exception as e:
            print(f"[MSPORT] Odds error: {e}")
        return None

    def get_results(self, season_id, match_day):
        """Fetch fullTime results for a completed matchday. Returns data dict or None."""
        url = f"{self.base_url}/result"
        params = {"seasonId": season_id, "matchDay": match_day}
        if self.verbose:
            print(f"[MSPORT] Results -> MD {match_day} | {season_id}")
        try:
            r = requests.get(url, headers=self.headers, cookies=self.cookies, params=params, timeout=10)
            if r.status_code == 200:
                body = r.json()
                if body.get('bizCode') == 10000:
                    return body.get('data')
                else:
                    print(f"[MSPORT] Results bizCode: {body.get('bizCode')}")
            else:
                print(f"[MSPORT] Results HTTP {r.status_code}")
        except Exception as e:
            print(f"[MSPORT] Results error: {e}")
        return None


if __name__ == "__main__":
    client = MSportClient()
    print("--- MSport Client Self-Test ---")
    hb = client.heartbeat()
    if hb:
        md   = hb.get('matchDay')
        sid  = hb.get('seasonId')
        st   = hb.get('status')
        print(f"  Current: MD {md} | Season: {sid} | Status: {st}")

        print(f"  Fetching odds for MD {md}...")
        odds = client.get_odds(sid, md)
        if odds:
            evts = odds.get('events', odds.get('matches', []))
            print(f"  ✅ Odds OK: {len(evts)} matches")
        else:
            print(f"  ⚠️  Odds not available (match may be in progress)")

        if md > 1:
            print(f"  Fetching results for MD {md - 1}...")
            res = client.get_results(sid, md - 1)
            if res:
                rl = res.get('results', [])
                print(f"  ✅ Results OK: {len(rl)} matches")
                for r in rl[:3]:
                    print(f"     {r.get('homeTeam')} vs {r.get('awayTeam')}: {r.get('fullTime')}")
            else:
                print(f"  ⚠️  Results not available yet")
    else:
        print("  [FAIL] Heartbeat failed - check network/auth")
