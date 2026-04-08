"""
MIROFISH SOVEREIGN SCAVENGER DAEMON V4
---------------------------------------
Clean state-machine daemon. Polls MSport VFL every 10s.
Architecture:
  - PREDICT: when a new matchday is detected, push odds -> server oracle
  - SETTLE:  when previous matchday results are available, push -> server settle
  - BACKFILL: on startup, settle any missed matchdays from the last 5 MDs
  - HEARTBEAT: push alive signal to server every 30s
VFL Timing: ~4-minute matchday cycle.
---------------------------------------
"""
import time
import sqlite3
import requests
from pathlib import Path
import sys, os

# -- Paths ----------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
from core.client import MSportClient

# ── Config ─────────────────────────────────────────────────────────────────────
SERVER_URL    = "http://127.0.0.1:5000"
DB_PATH       = ROOT / "data" / "databases" / "sovereign.db"
POLL_INTERVAL = 10   # seconds — 24 polls per 4-min matchday window
MAX_MD        = 30   # MSport VFL seasons = 30 matchdays


def make_key(season, md):
    return f"{season}__md{md}"


def _recover_state(db_path: Path) -> tuple[set, set]:
    """Load already-predicted and already-settled keys from DB on startup."""
    predicted, settled = set(), set()
    if not db_path.exists():
        return predicted, settled
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT season_id, match_day FROM master_ledger")
            for s, m in cur.fetchall():
                predicted.add(make_key(s, m))
            cur.execute("SELECT DISTINCT season_id, match_day FROM master_ledger WHERE status = 'SETTLED'")
            for s, m in cur.fetchall():
                settled.add(make_key(s, m))
        print(f"[SCAV] DB Recovered {len(predicted)} predicted, {len(settled)} settled matchdays from DB.")
    except Exception as e:
        print(f"[SCAV] DB recovery error: {e}")
    return predicted, settled


def _push(endpoint: str, payload: dict, timeout: int = 15) -> dict | None:
    """POST to the local Flask server, return JSON response or None."""
    try:
        r = requests.post(f"{SERVER_URL}{endpoint}", json=payload, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        print(f"[SCAV] ERROR Server {endpoint} -> HTTP {r.status_code}: {r.text[:200]}")
    except requests.exceptions.ConnectionError:
        pass  # Server not up yet — silently retry
    except Exception as e:
        print(f"[SCAV] ERROR Push error to {endpoint}: {e}")
    return None


def run_scavenger():
    client = MSportClient()

    predicted_keys, settled_keys = _recover_state(DB_PATH)

    last_md      = None
    last_season  = None
    last_status  = None
    last_hb_time = 0

    print("-" * 60)
    print("  [SCAVENGER V4] MiroFish Autonomous Daemon - ACTIVE")
    print(f"  Poll: {POLL_INTERVAL}s | Server: {SERVER_URL} | DB: {DB_PATH.name}")
    print("-" * 60)

    while True:
        try:
            # -- 1. HEARTBEAT --------------------------------------------------
            hb = client.heartbeat()
            if not hb or hb.get("matchDay") is None:
                time.sleep(POLL_INTERVAL)
                continue

            curr_md     = hb["matchDay"]
            curr_season = hb["seasonId"]
            curr_status = hb.get("status", "UNKNOWN")

            if not curr_season:
                time.sleep(POLL_INTERVAL)
                continue

            # Log transitions
            if curr_md != last_md or curr_season != last_season or curr_status != last_status:
                print(f"\n[SCAV] -- MD {curr_md} | {str(curr_season)[-10:]} | {curr_status} --")

            # Push alive signal to server every 30s
            if time.time() - last_hb_time > 30:
                _push("/api/sync/heartbeat", {
                    "matchday": curr_md,
                    "season":   curr_season,
                    "status":   curr_status,
                })
                last_hb_time = time.time()

            curr_key = make_key(curr_season, curr_md)

            # -- 2. PREDICT ----------------------------------------------------
            if curr_key not in predicted_keys:
                odds_data = client.get_odds(curr_season, curr_md)
                if odds_data:
                    print(f"[SCAV] DONE Odds for MD {curr_md} received ({len(odds_data.get('events', []))} fixtures)")
                    result = _push("/api/sync/matchday", {
                        "matchday": curr_md,
                        "season":   curr_season,
                        "odds":     odds_data,
                    })
                    if result:
                        predicted_keys.add(curr_key)
                        print(f"[SCAV] OK Predicted MD {curr_md}: {result.get('inserted',0)} rows, {result.get('locks',0)} LOCKs")
                    else:
                        print(f"[SCAV] Prediction push failed -- will retry in {POLL_INTERVAL}s")
                elif curr_status == "PRE_MATCH":
                    print(f"[SCAV] Odds not ready for MD {curr_md} (PRE_MATCH, retrying...)")

            # -- 3. SETTLE PREVIOUS MD -----------------------------------------
            if curr_md > 1:
                prev_md, prev_season = curr_md - 1, curr_season
            elif last_season and last_season != curr_season:
                # Season rollover: settle final MD of the old season
                prev_md, prev_season = MAX_MD, last_season
            else:
                prev_md, prev_season = None, None

            if prev_md and prev_season:
                prev_key = make_key(prev_season, prev_md)
                if prev_key not in settled_keys:
                    results_data = client.get_results(prev_season, prev_md)
                    if results_data:
                        rl = results_data.get("results", [])
                        print(f"[SCAV] RESULTS Results for MD {prev_md}: {len(rl)} matches")
                        res = _push("/api/sync/settle", {
                            "season":   prev_season,
                            "matchday": prev_md,
                            "results":  rl,
                        })
                        if res:
                            settled_keys.add(prev_key)
                            print(f"[SCAV] DONE Settled MD {prev_md}: {res.get('settled',0)} matches, P&L: {res.get('profit',0):+.2f}")

            # -- 4. BACKFILL: catch missed matchdays ----------------------------
            if curr_md > 2:
                for bf_md in range(max(1, curr_md - 5), curr_md - 1):
                    bf_key = make_key(curr_season, bf_md)
                    if bf_key not in settled_keys:
                        rd = client.get_results(curr_season, bf_md)
                        if rd:
                            rl = rd.get("results", [])
                            r = _push("/api/sync/settle", {
                                "season":   curr_season,
                                "matchday": bf_md,
                                "results":  rl,
                            })
                            if r:
                                settled_keys.add(bf_key)
                                print(f"[SCAV] SYNC Backfilled MD {bf_md}: {r.get('settled',0)} settled")

            # -- Update state ---------------------------------------------------
            last_md     = curr_md
            last_season = curr_season
            last_status = curr_status

        except Exception as e:
            print(f"[SCAV] ERROR Unhandled loop error: {e}")
            import traceback; traceback.print_exc()

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_scavenger()
