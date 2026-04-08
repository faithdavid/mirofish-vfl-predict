"""
MIROFISH SOVEREIGN — Server V7 (Clean Architecture)
═══════════════════════════════════════════════════
Single source of truth: sovereign_vbf.db at project ROOT.
All legacy CSV/JSON code paths removed.
EV calculated from real oracle certainty.
"""
from flask import Flask, jsonify, send_from_directory, request
from datetime import datetime
from pathlib import Path
import os, sys, json, sqlite3

# ── 1. Paths (must be first) ──────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
sys.path.append(str(ROOT / "lib"))

import vfl_oracle_v6 as oracle
from supabase_rest import db as supabase_db
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── 2. Constants ──────────────────────────────────────────────────────────────
DASHBOARD_DIR = ROOT / "dashboard"
DB_PATH       = ROOT / "sovereign_vbf.db"
HISTORY_DB    = ROOT / "vfl_history.db"
AUTH_FILE     = ROOT / "msport_auth.json"
LOG_DIR       = ROOT / "ANalysis" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

# ── 3. Oracle Brain (in-memory, hot-reloaded after each settlement) ───────────
print("[SERVER] Loading Oracle Knowledge Base...")
df_global       = oracle.load_vfl_history()
profiles_global = oracle.get_team_profiles(df_global)
sig_db_global   = oracle.load_signature_db()
print(f"[ORACLE V6] Loaded {len(df_global)} matches. Draw Mean: {oracle.D_MEAN:.2f}")
print("[SERVER] Initializing Autonomous Engine Routes...")

def _reload_oracle():
    """Hot-reloads the oracle brain from vfl_history.db after new results are settled.
    This closes the self-learning loop — every settled match improves future predictions."""
    global df_global, profiles_global, sig_db_global
    try:
        df_global       = oracle.load_vfl_history()
        profiles_global = oracle.get_team_profiles(df_global)
        sig_db_global   = oracle.load_signature_db()
        print(f"[ORACLE] 🧠 Brain reloaded — {len(df_global)} matches in memory.")
    except Exception as e:
        print(f"[ORACLE] ⚠️  Reload failed: {e}")

# ── 4. In-memory daemon status (updated by heartbeat) ─────────────────────────
_DAEMON_STATUS = {
    "matchday":  "?",
    "season":    "?",
    "status":    "OFFLINE",
    "last_sync": None,
    "last_settle_md": None,
    "last_settle_profit": None,
}

# --- 6. Raw Data Cache (for dashboard inspector) -------------------------------
_RAW_CACHE = {
    "odds":    None,
    "results": None,
    "last_updated": None
}

# ── 5. DB helpers ─────────────────────────────────────────────────────────────
def query_db(sql, args=(), one=False):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql, args)
        rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows

def exec_db(sql, args=()):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(sql, args)
        conn.commit()
        return cur.rowcount


# ── 6. Internal helpers ───────────────────────────────────────────────────────
def _parse_odds_events(events):
    """Extract raw fixtures [{home, away, odds:[oh,od,oa], event_id}] from MSport events list."""
    out = []
    for ev in events:
        m1x2 = next(
            (m for m in ev.get("markets", [])
             if m.get("name") == "1x2" or m.get("id") == 1),
            None
        )
        if not m1x2:
            continue
        try:
            outs = m1x2.get("outcomes", [])
            oh = float(next(o["odds"] for o in outs if o.get("description") == "Home" or o.get("id") == "1"))
            od = float(next(o["odds"] for o in outs if o.get("description") == "Draw" or o.get("id") == "2"))
            oa = float(next(o["odds"] for o in outs if o.get("description") == "Away" or o.get("id") == "3"))
        except (StopIteration, KeyError, ValueError):
            continue
        out.append({
            "home":     ev["homeTeam"],
            "away":     ev["awayTeam"],
            "odds":     [oh, od, oa],
            "event_id": ev.get("id", f"gen:{ev['homeTeam']}_{ev['awayTeam']}"),
        })
    return out


def _run_oracle(raw_fixtures, matchday, season):
    """Run Oracle V6 on a list of raw fixtures, return enriched list sorted by certainty DESC."""
    accounting = oracle.get_seasonal_accounting(df_global, season)
    results = []
    for fxt in raw_fixtures:
        f_input = {
            "home": fxt["home"], "away": fxt["away"],
            "oh": fxt["odds"][0], "od": fxt["odds"][1], "oa": fxt["odds"][2],
            "day": int(matchday), "season": season,
        }
        pred = oracle.predict_fixture_v6(f_input, df_global, profiles_global, sig_db_global, accounting)
        pred["bet_type"]  = pred["prediction_label"]
        pred["event_id"]  = fxt.get("event_id", "")
        # Real EV: expected_value = p(win) * decimal_odds - 1
        certainty_pct = pred.get("certainty_score", 0) / 100
        target_odds   = pred["oh"] if pred["prediction"] == "H" else (pred["od"] if pred["prediction"] == "D" else pred["oa"])
        pred["ev"]    = round(certainty_pct * target_odds - 1, 4)
        # Kelly stake: f = (bp - q) / b  where b=odds-1, p=certainty, q=1-p
        b = target_odds - 1
        p = certainty_pct
        q = 1 - p
        kelly_f = max(0, (b * p - q) / b) if b > 0 else 0
        pred["kelly_fraction"] = round(kelly_f, 4)
        results.append(pred)
    results.sort(key=lambda x: x["certainty_score"], reverse=True)
    return results


def _settle_results(results_list, season, matchday):
    """
    Core settlement:
      1. Updates master_ledger in sovereign_vbf.db
      2. Writes match to vfl_history.db for self-learning
      3. Pushes to Supabase cloud
    Returns (settled_count, total_profit)
    """
    settled_count = 0
    total_profit  = 0.0

    with sqlite3.connect(DB_PATH) as conn_m, sqlite3.connect(HISTORY_DB) as conn_h:
        cm = conn_m.cursor()
        ch = conn_h.cursor()

        for res in results_list:
            match_id = res.get("id")
            home     = res.get("homeTeam", "")
            away     = res.get("awayTeam", "")
            score    = res.get("fullTime", "0:0")
            
            try:
                h_score, a_score = map(int, score.split(":"))
            except ValueError:
                continue

            outcome = "D"
            if h_score > a_score: outcome = "H"
            elif a_score > h_score: outcome = "A"

            # ── Compute P&L (Match by ID or composite key) ───────────────────
            if match_id:
                cm.execute(
                    "SELECT prediction, stake, odds_h, odds_d, odds_a, match_id FROM master_ledger WHERE match_id = ?",
                    (match_id,)
                )
            else:
                cm.execute("""
                    SELECT prediction, stake, odds_h, odds_d, odds_a, match_id FROM master_ledger 
                    WHERE home_team = ? AND away_team = ? AND season_id = ? AND match_day = ?
                """, (home, away, season, matchday))
            
            row = cm.fetchone()
            p_l = 0.0
            oh, od, oa = 0.0, 0.0, 0.0
            real_match_id = match_id
            
            if row:
                pred, stake, oh, od, oa, real_match_id = row
                if stake and stake > 0:
                    odds_used = oh if pred == "H" else (od if pred == "D" else oa)
                    won = (pred == outcome)
                    p_l = round((stake * odds_used) - stake, 2) if won else -stake
                    total_profit += p_l

            # ── Update master_ledger ──────────────────────────────────────────
            if real_match_id:
                cm.execute("""
                    UPDATE master_ledger SET
                        full_time = ?, actual_h = ?, actual_a = ?, outcome = ?,
                        p_l = ?, settled_at = CURRENT_TIMESTAMP, status = 'SETTLED'
                    WHERE match_id = ?
                """, (score, h_score, a_score, outcome, p_l, real_match_id))

            # ── Persist to vfl_history for oracle self-learning ───────────────
            # Schema: id (INTEGER), season, day, home, away, oh, od, oa, outcome
            try:
                h_id = int(real_match_id)
            except (ValueError, TypeError):
                # Fallback to a stable integer hash of the composite key
                h_id = hash(f"vf:{season}:{matchday}:{home}:{away}") & 0x7FFFFFFFFFFFFFFF

            ch.execute("""
                INSERT OR REPLACE INTO matches (
                    id, season, day, home, away,
                    oh, od, oa, outcome
                ) VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                h_id, season, matchday,
                home, away,
                oh, od, oa,
                outcome
            ))

            # ── Push to Supabase ──────────────────────────────────────────────
            if supabase_db.active and real_match_id:
                supabase_db.settle_fixture(real_match_id, {
                    "full_time": score, "actual_h": h_score, "actual_a": a_score,
                    "outcome": outcome, "p_l": p_l, "status": "SETTLED"
                })

            settled_count += 1

        conn_m.commit()
        conn_h.commit()

    print(f"[SETTLE] MD {matchday}: {settled_count} settled. P&L: {total_profit:+.2f}")
    # ── Self-learning: reload oracle brain with fresh history data ────────────
    if settled_count > 0:
        _reload_oracle()
    return settled_count, total_profit


# ═══════════════════════════════════════════════════════════════════════════════
# STATIC ROUTES
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/")
@app.route("/dashboard")
def index():
    return send_from_directory(DASHBOARD_DIR, "index.html")

@app.route("/style.css")
def style():
    return send_from_directory(DASHBOARD_DIR, "style.css")

@app.route("/app.js")
def js():
    return send_from_directory(DASHBOARD_DIR, "app.js")


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/status  — Daemon heartbeat summary for dashboard header
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/status")
def api_status():
    auth_ok = AUTH_FILE.exists()
    return jsonify({
        **_DAEMON_STATUS,
        "auth": "ACTIVE" if auth_ok else "AUTH_REQUIRED",
        "server": "ONLINE",
    })

# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/last_raw — Raw JSON inspector for dashboard
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/last_raw")
def get_last_raw():
    return jsonify(_RAW_CACHE)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/data  — Live dashboard HUD feed
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/data")
def get_data():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Latest matchday
            cur.execute("SELECT MAX(match_day), season_id FROM master_ledger")
            row = cur.fetchone()
            matchday = row[0] if row and row[0] is not None else 0
            season   = row[1] if row and row[1] else "UNKNOWN"

            # Current fixtures
            cur.execute(
                "SELECT * FROM master_ledger WHERE match_day = ? AND season_id = ? ORDER BY certainty DESC",
                (matchday, season)
            )
            fixture_rows = cur.fetchall()

            # All-time P&L stats
            cur.execute("""
                SELECT
                    SUM(p_l),
                    COUNT(CASE WHEN p_l > 0 THEN 1 END),
                    COUNT(CASE WHEN p_l < 0 THEN 1 END)
                FROM master_ledger WHERE status = 'SETTLED'
            """)
            stats = cur.fetchone()

        pnl    = stats[0] or 0.0
        wins   = stats[1] or 0
        losses = stats[2] or 0
        total  = wins + losses
        strike = round(wins / total * 100, 1) if total > 0 else 0

        # Build fixture list with all required fields
        fixtures = []
        for r in fixture_rows:
            pred = r["prediction"]
            target_odds = r["odds_h"] if pred == "H" else (r["odds_d"] if pred == "D" else r["odds_a"])
            certainty_pct = (r["certainty"] or 0) / 100
            ev = round(certainty_pct * (target_odds or 1) - 1, 4)
            fixtures.append({
                "match_id":        r["match_id"],
                "home":            r["home_team"],
                "away":            r["away_team"],
                "prediction":      pred,
                "prediction_label": r["label"] or pred,
                "certainty_score": r["certainty"] or 0,
                "tier":            r["tier"] or "MOD",
                "odds_h":          r["odds_h"],
                "odds_d":          r["odds_d"],
                "odds_a":          r["odds_a"],
                "target_odds":     target_odds,
                "stake":           r["stake"] or 0,
                "ev":              ev,
                "status":          r["status"],
            })

        # Seasonal draw accounting
        accounting   = oracle.get_seasonal_accounting(df_global, season)
        target_draws = (int(matchday) / 30) * oracle.D_MEAN
        current_d    = accounting.get("D", 0)
        draw_pct     = round(current_d / max(1, target_draws) * 100, 1) if target_draws > 0 else 0
        draw_force   = 1.15 if current_d < target_draws * 0.85 and int(matchday) >= 20 else 1.0

        return jsonify({
            "status":    "success",
            "season":    season,
            "matchday":  matchday,
            "pnl":       round(pnl, 2),
            "wins":      wins,
            "losses":    losses,
            "strike_rate": strike,
            "mode":      "autonomous",
            "fixtures":  fixtures,
            "draw_alerts": [],
            "accounting": {
                "draws":         current_d,
                "target_draws":  round(target_draws, 1),
                "draw_pct":      draw_pct,
                "draw_pressure": draw_pct,
                "draw_force":    draw_force,
            },
            "force":    draw_force,
            "daemon":   _DAEMON_STATUS,
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/history  — Full performance ledger (settled + pending)
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/history")
def get_history():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM master_ledger
                WHERE status = 'SETTLED'
                ORDER BY settled_at DESC LIMIT 200
            """)
            settled_rows = cur.fetchall()
            cur.execute("""
                SELECT * FROM master_ledger
                WHERE status = 'PENDING'
                ORDER BY created_at DESC LIMIT 50
            """)
            pending_rows = cur.fetchall()

        def fmt_settled(r):
            pred        = r["prediction"]
            target_odds = r["odds_h"] if pred == "H" else (r["odds_d"] if pred == "D" else r["odds_a"])
            return {
                "match_id":    r["match_id"],
                "fixture":     f"{r['home_team']} vs {r['away_team']}",
                "season":      r["season_id"],
                "matchday":    r["match_day"],
                "prediction":  pred,
                "outcome":     r["outcome"],
                "actual":      r["full_time"],
                "odds":        target_odds,
                "stake":       r["stake"],
                "profit":      r["p_l"] or 0,
                "tier":        r["tier"],
                "certainty":   r["certainty"],
                "settled_at":  r["settled_at"],
            }

        def fmt_pending(r):
            pred        = r["prediction"]
            target_odds = r["odds_h"] if pred == "H" else (r["odds_d"] if pred == "D" else r["odds_a"])
            return {
                "match_id":   r["match_id"],
                "fixture":    f"{r['home_team']} vs {r['away_team']}",
                "matchday":   r["match_day"],
                "prediction": pred,
                "odds":       target_odds,
                "stake":      r["stake"],
                "certainty":  r["certainty"],
                "tier":       r["tier"],
            }

        history = [fmt_settled(r) for r in settled_rows]
        pending = [fmt_pending(r) for r in pending_rows]

        pnl    = sum(h["profit"] for h in history)
        wins   = sum(1 for h in history if (h["profit"] or 0) > 0)
        losses = sum(1 for h in history if (h["profit"] or 0) < 0)
        total  = wins + losses
        strike = round(wins / total * 100, 1) if total > 0 else 0

        return jsonify({
            "total_pnl":   round(pnl, 2),
            "wins":        wins,
            "losses":      losses,
            "total":       total,
            "strike_rate": strike,
            "history":     history,
            "pending":     pending,
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/predict  — Manual JSON injection
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/predict", methods=["POST"])
def predict():
    try:
        data     = request.json
        if not data or "data" not in data:
            return jsonify({"error": "Invalid MSport JSON structure"}), 400
        events   = data["data"].get("events", [])
        matchday = str(data["data"].get("matchDay", "0"))
        season   = data["data"].get("seasonId") or data["data"].get("seasonName", "Unknown")
        raw      = _parse_odds_events(events)
        fixtures = _run_oracle(raw, matchday, season)
        return jsonify({"season": season, "matchday": matchday, "fixtures": fixtures})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/sync/matchday  — Scavenger push: new matchday odds → oracle → DB
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/sync/matchday", methods=["POST"])
def sync_matchday():
    global _DAEMON_STATUS
    try:
        data      = request.json
        matchday  = data.get("matchday")
        season    = data.get("season")
        odds_data = data.get("odds")

        if not odds_data:
            return jsonify({"error": "No odds data"}), 400

        events = odds_data.get("events", [])
        raw    = _parse_odds_events(events)

        # Update cache
        _RAW_CACHE["odds"] = odds_data
        _RAW_CACHE["last_updated"] = datetime.now().isoformat()

        if not raw:
            return jsonify({"error": "No parseable fixtures in odds data"}), 400

        enriched = _run_oracle(raw, matchday, season)

        inserted = 0
        for p in enriched:
            match_id = p.get("event_id") or f"vf:{season}:{matchday}:{p['home']}:{p['away']}"
            rows = exec_db("""
                INSERT OR IGNORE INTO master_ledger (
                    match_id, season_id, match_day, home_team, away_team,
                    odds_h, odds_d, odds_a,
                    prediction, certainty, tier, stake, label, status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING')
            """, (
                match_id, season, matchday, p["home"], p["away"],
                p["oh"], p["od"], p["oa"],
                p["prediction"], p["certainty_score"], p["tier"],
                p.get("stake", 0), p.get("label", p["prediction"]),
            ))
            if rows:
                inserted += 1
                if supabase_db.active:
                    supabase_db.insert_fixture({
                        "match_id": match_id, "season_id": season, "match_day": matchday,
                        "home_team": p["home"], "away_team": p["away"],
                        "odds_h": p["oh"], "odds_d": p["od"], "odds_a": p["oa"],
                        "prediction": p["prediction"], "certainty": p["certainty_score"],
                        "tier": p["tier"], "stake": p.get("stake", 0),
                        "label": p.get("label", p["prediction"]), "status": "PENDING",
                    })

        _DAEMON_STATUS.update({
            "matchday":  str(matchday),
            "season":    str(season),
            "status":    "PRE_MATCH",
            "last_sync": datetime.now().isoformat(),
        })

        locks = sum(1 for p in enriched if p.get("tier") == "LOCK")
        print(f"[SYNC] MD {matchday}: {inserted} fixtures → ledger. {locks} LOCKs.")
        return jsonify({"status": "synced", "matchday": matchday, "inserted": inserted, "locks": locks})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/sync/settle  — Scavenger push: results → settlement
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/sync/settle", methods=["POST"])
def sync_settle():
    global _DAEMON_STATUS
    try:
        data         = request.json
        season       = data.get("season")
        matchday     = data.get("matchday")
        results_list = data.get("results", [])
        if not results_list:
            return jsonify({"error": "No results provided"}), 400

        # Update cache
        _RAW_CACHE["results"] = data
        _RAW_CACHE["last_updated"] = datetime.now().isoformat()

        settled, profit = _settle_results(results_list, season, matchday)

        _DAEMON_STATUS.update({
            "status":              "SETTLED",
            "last_settle_md":      matchday,
            "last_settle_profit":  round(profit, 2),
        })

        return jsonify({"status": "settled", "matchday": matchday, "settled": settled, "profit": round(profit, 2)})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/sync/heartbeat  — Daemon alive signal
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/sync/heartbeat", methods=["POST"])
def sync_heartbeat():
    global _DAEMON_STATUS
    try:
        data = request.json
        _DAEMON_STATUS.update({
            "matchday":  str(data.get("matchday", _DAEMON_STATUS["matchday"])),
            "season":    str(data.get("season",   _DAEMON_STATUS["season"])),
            "status":    str(data.get("status",   _DAEMON_STATUS["status"])),
            "last_sync": datetime.now().isoformat(),
        })
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/audit  — Manual result paste (from dashboard)
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/audit", methods=["POST"])
def audit_results():
    try:
        raw      = request.json
        body     = raw.get("data", raw)
        matchday = (body.get("current", {}).get("matchDay") or
                    body.get("prev",    {}).get("matchDay") or "?")
        season   = (body.get("current", {}).get("seasonId") or
                    body.get("prev",    {}).get("seasonId") or "?")
        results  = body.get("results", [])
        settled, profit = _settle_results(results, season, matchday)
        return jsonify({
            "status":        "success",
            "matchday":      matchday,
            "settled_count": settled,
            "total_profit":  round(profit, 2),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/sync/auth  — Hot-reload MSport credentials
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/sync/auth", methods=["POST"])
def update_auth():
    try:
        payload = request.json
        with open(AUTH_FILE, "w") as f:
            json.dump(payload, f, indent=4)
        return jsonify({"status": "auth_updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/sync/status  — Auth check for UI badge
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/sync/status")
def sync_status():
    return jsonify({"status": "ACTIVE" if AUTH_FILE.exists() else "AUTH_REQUIRED"})


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("--- MIROFISH SOVEREIGN V7 SERVER ---")
    print(f"Dashboard: http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
