"""
MSport VFL API Client
─────────────────────
Handles all HTTP communication with the MSport virtual football API.
Auth headers/cookies are loaded from msport_auth.json at ROOT level.
"""
import json
import requests
from pathlib import Path

# ── API Endpoints ──────────────────────────────────────────────────────────────
HEARTBEAT_URL = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/current/match/day/info"
ODDS_URL      = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/match/day/event/list"
RESULTS_URL   = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/result"

# Fallback headers if msport_auth.json is missing or malformed
DEFAULT_HEADERS = {
    "User-Agent":        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept":            "*/*",
    "Accept-Language":   "en-NG,en-US;q=0.9,en-GB;q=0.8,en;q=0.7",
    "apilevel":          "2",
    "clientid":          "WEB",
    "operid":            "2",
    "platform":          "WEB",
    "referer":           "https://www.msport.com/ng/web/virtual",
    "sec-fetch-dest":    "empty",
    "sec-fetch-mode":    "cors",
    "sec-fetch-site":    "same-origin",
}


class MSportClient:
    """
    Thin HTTP client for the MSport VFL API.

    Usage:
        client = MSportClient()
        hb = client.heartbeat()          # returns {matchDay, seasonId, status}
        odds = client.get_odds(s, md)    # returns {events: [...]}
        res  = client.get_results(s, md) # returns {results: [...]}
    """

    def __init__(self, auth_path: Path = None):
        # Locate msport_auth.json (two levels up from lib/)
        if auth_path is None:
            auth_path = Path(__file__).parent.parent / "data" / "msport_auth.json"
        self.headers = dict(DEFAULT_HEADERS)
        self.cookies = {}
        self._load_auth(auth_path)

    def _load_auth(self, auth_path: Path):
        """Load headers/cookies from msport_auth.json."""
        if auth_path.exists():
            try:
                with open(auth_path) as f:
                    auth = json.load(f)
                self.headers.update(auth.get("headers", {}))
                self.cookies.update(auth.get("cookies", {}))
                print("[MSPORT] [DONE] Auth loaded from msport_auth.json")
            except Exception as e:
                print(f"[MSPORT] [FAIL] Failed to load auth: {e} - using defaults")
        else:
            print("[MSPORT] [WARN] msport_auth.json not found - using default headers")

    def reload_auth(self, auth_path: Path = None):
        """Hot-reload credentials without restarting the daemon."""
        if auth_path is None:
            auth_path = Path(__file__).parent.parent / "data" / "msport_auth.json"
        self.headers = dict(DEFAULT_HEADERS)
        self.cookies = {}
        self._load_auth(auth_path)

    def _get(self, url: str, params: dict = None, timeout: int = 10) -> dict | None:
        """Execute a GET request, return parsed JSON or None on failure."""
        try:
            r = requests.get(
                url,
                headers=self.headers,
                cookies=self.cookies,
                params=params,
                timeout=timeout,
            )
            if r.status_code == 200:
                return r.json()
            print(f"[MSPORT] [WARN] HTTP {r.status_code} from {url}")
            return None
        except requests.exceptions.Timeout:
            print(f"[MSPORT] [TIMEOUT] Timeout hitting {url}")
            return None
        except Exception as e:
            print(f"[MSPORT] [ERROR] Request error: {e}")
            return None

    # ── Public API ─────────────────────────────────────────────────────────────

    def heartbeat(self) -> dict | None:
        """
        Poll the live VFL state.
        Returns: {matchDay, seasonId, status ('PRE_MATCH'|'MATCH'), ...}
        or None on failure.
        """
        print(f"[MSPORT] Heartbeat → {HEARTBEAT_URL}")
        raw = self._get(HEARTBEAT_URL)
        if not raw:
            return None
        data = raw.get("data", {})
        if not data:
            return None
        # Normalise field names — API uses camelCase
        return {
            "matchDay": data.get("matchDay") or data.get("current", {}).get("matchDay"),
            "seasonId": data.get("seasonId") or data.get("current", {}).get("seasonId"),
            "status":   data.get("status",   "UNKNOWN"),
            "raw":      data,
        }

    def get_odds(self, season_id: str, match_day: int) -> dict | None:
        """
        Fetch the 1x2 odds for all fixtures in a given matchday.
        Returns the raw `data` dict from the API response, or None.
        """
        raw = self._get(ODDS_URL, params={"seasonId": season_id, "matchDay": match_day})
        if not raw:
            return None
        data = raw.get("data")
        if not data:
            return None
        # Surface events in a consistent format
        events = data.get("events") or data.get("matches") or []
        if not events:
            return None
        return {"seasonId": season_id, "matchDay": match_day, "events": events}

    def get_results(self, season_id: str, match_day: int) -> dict | None:
        """
        Fetch final scores for a completed matchday.
        Returns {results: [{id, homeTeam, awayTeam, fullTime, halfTime}, ...]}
        or None if not yet available.
        """
        raw = self._get(RESULTS_URL, params={"seasonId": season_id, "matchDay": match_day})
        if not raw:
            return None
        data = raw.get("data", {})
        results = data.get("results", [])
        if not results:
            return None
        return {"seasonId": season_id, "matchDay": match_day, "results": results}
