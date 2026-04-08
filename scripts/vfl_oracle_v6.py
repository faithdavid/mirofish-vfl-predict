"""
================================================================================
  VFL ORACLE V6 — SOVEREIGN UNIFIED ENGINE
  ─────────────────────────────────────────────────────────────────────────────
  Three-tier prediction system with Certainty Scoring:

  TIER 1 — SIGNATURE LOCK (Certainty: 70-100)
    Checks master_rng_signatures.json for this exact fixture+odds combo.
    5+ samples + 90% hit rate → LOCK (certainty 90+)
    5+ samples + 70% hit rate → SIGNAL (certainty 75)

  TIER 2 — QUOTA WALL / DRAW FORCE (Certainty: 65-85)
    Detects teams at their seasonal win-ceiling (algorithm forces non-wins).
    Uses 57.3 draw quota to detect when draws are mathematically due.

  TIER 3 — STATISTICAL BLEND (Certainty: 40-65)
    40% Odds-implied probability
    35% Head-to-head historical (from vfl_history.db)
    25% Individual team home/away stats

  DRAW SCORING — 5-Signal Draw Detector
    Composite draw confidence score (0-100) per fixture.
    Signals: H2H draw rate, Seasonal quota deficit, Odds bracket,
             Win cap detection, Signature DB DRAW patterns.

  SAFE PICKS
    Ranked by certainty_score descending, not by EV.
    Staking: LOCK (certainty≥85)→NGN50, WALL (≥70)→NGN30, MOD (≥60)→NGN15

  USAGE
    import vfl_oracle_v6 as oracle
    df = oracle.load_vfl_history()
    profiles = oracle.get_team_profiles(df)
    sig_db = oracle.load_signature_db()
    result = oracle.predict_fixture_v6(fixture, df, profiles, sig_db)
================================================================================
"""

import pandas as pd
import numpy as np
import sqlite3
import os
import json
from pathlib import Path

# ── PATHS ──────────────────────────────────────────────────────────────────────
_HERE      = Path(__file__).parent
_ROOT      = _HERE.parent
DB_PATH    = str(_ROOT / 'vfl_history.db')
SIG_PATH   = str(_ROOT / 'master_rng_signatures.json')

# ── SEASONAL CONSTANTS (from 184-season audit) ────────────────────────────────
D_MEAN = 57.3    # draws per 30-day season (league-wide)
H_MEAN = 101.7
A_MEAN = 71.2
MATCHES_PER_DAY = 8

# ── CERTAINTY TIER THRESHOLDS ─────────────────────────────────────────────────
TIER_LOCK     = 85   # Signature 90%+ hit rate
TIER_SIGNAL   = 70   # Signature 70%+ hit rate / Quota Wall
TIER_MODERATE = 55   # Statistical blend ≥62%
TIER_WEAK     = 0    # Display only, no stake

# ── STAKING BY CERTAINTY ──────────────────────────────────────────────────────
def get_stake(certainty_score):
    if certainty_score >= TIER_LOCK:     return 50.0
    if certainty_score >= TIER_SIGNAL:   return 30.0
    if certainty_score >= TIER_MODERATE: return 15.0
    return 0.0


# ════════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ════════════════════════════════════════════════════════════════════════════════

def load_vfl_history():
    """Loads the VFL match history database."""
    if not os.path.exists(DB_PATH):
        print(f"[ORACLE V6] WARNING: Database not found at {DB_PATH}")
        return None
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM matches WHERE outcome IS NOT NULL", conn)
    conn.close()

    df['season'] = df['season'].astype(str).str.replace('vf:season:', '', regex=False)
    numeric_cols = ['oh', 'od', 'oa', 'h', 'a', 'total', 'day']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['outcome_code'] = df['outcome'].map({'HOME': 'H', 'DRAW': 'D', 'AWAY': 'A'})
    return df


def load_signature_db():
    """Loads the RNG signature database."""
    if not os.path.exists(SIG_PATH):
        print(f"[ORACLE V6] WARNING: Signature DB not found at {SIG_PATH}")
        return {}
    with open(SIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_team_profiles(df):
    """Build team home/away performance profiles."""
    if df is None or df.empty:
        return {}
    teams = pd.concat([df['home'], df['away']]).unique()
    profiles = {}
    for team in teams:
        h_games = df[df['home'] == team]
        a_games = df[df['away'] == team]
        profiles[team] = {
            'h_win_p':  (h_games['outcome_code'] == 'H').mean() if len(h_games) > 0 else 0.33,
            'h_draw_p': (h_games['outcome_code'] == 'D').mean() if len(h_games) > 0 else 0.33,
            'a_win_p':  (a_games['outcome_code'] == 'A').mean() if len(a_games) > 0 else 0.33,
            'a_draw_p': (a_games['outcome_code'] == 'D').mean() if len(a_games) > 0 else 0.33,
        }
    return profiles


def get_seasonal_accounting(df, season_id):
    """Returns the current H/D/A tally for a season."""
    if not season_id or season_id == 'SOVEREIGN':
        return {'H': 0, 'D': 0, 'A': 0}
    s_id = str(season_id).replace('vf:season:', '')
    s_df = df[df['season'] == s_id] if df is not None else pd.DataFrame()
    if s_df.empty:
        return {'H': 0, 'D': 0, 'A': 0}
    s_df = s_df.copy()
    s_df['o'] = s_df['outcome'].apply(lambda x: str(x)[0] if x else None)
    counts = s_df['o'].value_counts()
    return {
        'H': int(counts.get('H', 0)),
        'D': int(counts.get('D', 0)),
        'A': int(counts.get('A', 0)),
    }


# ════════════════════════════════════════════════════════════════════════════════
# TIER 1 — SIGNATURE LOOKUP
# ════════════════════════════════════════════════════════════════════════════════

def _sig_lookup(home, away, oh, od, oa, sig_db):
    """
    Returns (prediction, hit_rate, total_samples, certainty_score) or None.
    Tries exact match → ±0.1 near-miss (penalised by -10 certainty).
    Minimum: 5 samples AND 70% hit rate.
    """
    MIN_SAMPLES = 5
    HIGH_RATE   = 0.90   # LOCK
    MED_RATE    = 0.70   # SIGNAL

    def _score_entry(entry, penalty=0):
        if not entry or entry.get('total', 0) < MIN_SAMPLES:
            return None
        counts = entry['counts']
        best   = max(counts, key=counts.get)
        rate   = counts[best] / entry['total']
        if rate >= HIGH_RATE:
            certainty = int(90 + (rate - HIGH_RATE) * 100) - penalty
            return best, rate, entry['total'], min(certainty, 100)
        if rate >= MED_RATE:
            certainty = int(70 + (rate - MED_RATE) * 100) - penalty
            return best, rate, entry['total'], min(certainty, 100)
        return None

    h_name = home.upper()
    a_name = away.upper()

    # Exact match
    key = f"{h_name}|{a_name}|{oh:.1f}|{od:.1f}|{oa:.1f}"
    result = _score_entry(sig_db.get(key))
    if result:
        return result

    # Near-miss ±0.1 for each leg
    for dh in [0.1, -0.1]:
        for dd in [0.1, -0.1]:
            for da in [0.1, -0.1]:
                key2 = f"{h_name}|{a_name}|{oh+dh:.1f}|{od+dd:.1f}|{oa+da:.1f}"
                result = _score_entry(sig_db.get(key2), penalty=10)
                if result:
                    return result
    return None


# ════════════════════════════════════════════════════════════════════════════════
# TIER 2 — QUOTA / WIN-CAP ANALYSIS
# ════════════════════════════════════════════════════════════════════════════════

def _get_home_wins(team, season_id, day, df):
    """Returns how many HOME wins the team has this season before `day`."""
    if df is None:
        return 0
    s_id = str(season_id).replace('vf:season:', '')
    played = df[(df['season'] == s_id) & (df['day'] < day)]
    wins = len(played[(played['home'] == team) & (played['outcome'] == 'HOME')])
    return wins


def _quota_analysis(home, away, oh, od, oa, day, season_id, accounting, df):
    """
    Detects Quota Walls and global draw pressure.
    Returns dict: { prediction, certainty_score, label, quota_penalty }
    or None if no strong wall detected.
    """
    h_wins = _get_home_wins(home.upper(), season_id, day, df)
    target_d = (day / 30) * D_MEAN

    # ABSOLUTE WIN WALL — algorithm historically forces a non-win here
    if h_wins >= 21:
        return {
            'prediction': 'D',   # or A — Draw is more common response
            'certainty_score': 78,
            'label': 'QUOTA WIN WALL (21+ wins)',
            'quota_penalty': 0.45,
            'h_wins': h_wins,
        }

    # HIGH WIN COUNT + favourable draw odds
    relative_threshold = max(8, int(day * 0.75))
    if h_wins >= 18 or (day > 5 and h_wins >= relative_threshold):
        if od <= 3.95:
            return {
                'prediction': 'D',
                'certainty_score': 68,
                'label': f'QUOTA DRAW ALERT ({h_wins} wins)',
                'quota_penalty': 0.22,
                'h_wins': h_wins,
            }

    # GLOBAL DRAW SURGE (season-wide shortage)
    if day >= 20 and accounting.get('D', 0) < target_d * 0.85:
        deficit = int(target_d - accounting.get('D', 0))
        return {
            'prediction': 'D',
            'certainty_score': 62,
            'label': f'GLOBAL DRAW SURGE ({deficit} draws due)',
            'quota_penalty': 0.10,
            'h_wins': h_wins,
        }

    # Mathematical rupture point
    if day >= 25 and accounting.get('D', 0) < 40:
        return {
            'prediction': 'D',
            'certainty_score': 72,
            'label': 'MATHEMATICAL DRAW FORCE',
            'quota_penalty': 0.20,
            'h_wins': h_wins,
        }

    return None


# ════════════════════════════════════════════════════════════════════════════════
# TIER 3 — STATISTICAL BLEND
# ════════════════════════════════════════════════════════════════════════════════

def _true_probs(oh, od, oa):
    """Remove bookmaker margin."""
    probs = [1/oh, 1/od, 1/oa]
    margin = sum(probs)
    return [p / margin for p in probs]


def _stat_blend(home, away, oh, od, oa, profiles, quota_penalty=0.0):
    """
    Blended prediction: 40% odds + 35% H2H/team profile + 25% uniform prior.
    Returns (prediction, certainty_score, blend_h, blend_d, blend_a).
    """
    p_h, p_d, p_a = _true_probs(oh, od, oa)
    hp = profiles.get(home.upper(), {'h_win_p': 0.33, 'h_draw_p': 0.33})
    ap = profiles.get(away.upper(), {'a_win_p': 0.33, 'a_draw_p': 0.33})

    final_h = (p_h * 0.40) + (hp['h_win_p'] * 0.35) + (0.33 * 0.25)
    final_d = (p_d * 0.40) + (hp['h_draw_p'] * 0.35) + (0.33 * 0.25)
    final_a = (p_a * 0.40) + (ap['a_win_p'] * 0.35) + (0.33 * 0.25)

    # Apply quota pressure if present
    if quota_penalty > 0:
        final_h -= quota_penalty
        final_d += quota_penalty

    outcomes = {'H': final_h, 'D': final_d, 'A': final_a}
    best = max(outcomes, key=outcomes.get)
    total = sum(outcomes.values())
    conf = outcomes[best] / total if total > 0 else 0.33

    # Certainty score: map confidence [0.33-1.0] → [40-65]
    certainty = int(40 + (conf - 0.33) / 0.67 * 25)
    certainty = max(40, min(65, certainty))

    return best, certainty, round(final_h, 3), round(final_d, 3), round(final_a, 3)


# ════════════════════════════════════════════════════════════════════════════════
# DRAW SCORING — 5-Signal Detector
# ════════════════════════════════════════════════════════════════════════════════

def compute_draw_score(home, away, oh, od, oa, day, season_id, accounting, df, sig_db):
    """
    5-signal composite Draw Score (0-100).
    Score >= 65 = Draw candidate worth flagging.
    """
    score = 0
    signals = []

    home_u = home.upper()
    away_u = away.upper()

    # Signal 1 (30%): H2H draw rate for this pairing
    if df is not None:
        s_id = str(season_id).replace('vf:season:', '')
        h2h = df[(df['home'] == home_u) & (df['away'] == away_u)]
        if len(h2h) >= 5:
            draw_rate = (h2h['outcome_code'] == 'D').mean()
            s1 = int(draw_rate * 100 * 0.30)
            score += s1
            signals.append(f"H2H {draw_rate:.0%}")

    # Signal 2 (25%): Seasonal draw quota deficit
    target_d = (day / 30) * D_MEAN
    current_d = accounting.get('D', 0)
    if current_d < target_d:
        deficit_pct = min(1.0, (target_d - current_d) / max(1, target_d))
        s2 = int(deficit_pct * 100 * 0.25)
        score += s2
        signals.append(f"Quota deficit {int(target_d - current_d)}")

    # Signal 3 (20%): Odds bracket — draw odds in the "balanced market" zone
    if 2.80 <= od <= 3.80:
        bracket_score = 20 if 3.00 <= od <= 3.50 else 12
        score += bracket_score
        signals.append(f"Balanced odds {od}")

    # Signal 4 (15%): Home team win cap
    h_wins = _get_home_wins(home_u, season_id, day, df) if df is not None else 0
    if h_wins >= 21:
        score += 15
        signals.append(f"WIN WALL ({h_wins} wins)")
    elif h_wins >= 18:
        score += 9
        signals.append(f"Win cap ({h_wins} wins)")

    # Signal 5 (10%): Signature DB shows DRAW pattern for this fixture
    sig = _sig_lookup(home_u, away_u, oh, od, oa, sig_db)
    if sig and sig[0] == 'D':
        s5 = int(sig[1] * 100 * 0.10)  # weight by hit rate
        score += s5
        signals.append(f"SIG DRAW {sig[1]:.0%}")

    return min(100, score), signals


# ════════════════════════════════════════════════════════════════════════════════
# MASTER PREDICTION FUNCTION
# ════════════════════════════════════════════════════════════════════════════════

def predict_fixture_v6(fixture, df, profiles, sig_db, accounting=None):
    """
    Unified V6 prediction. Returns a rich dict with certainty_score.

    fixture keys: home, away, oh, od, oa, day, season (season_id string)
    accounting: {'H': int, 'D': int, 'A': int} — current season tally
    """
    home = fixture['home']
    away = fixture['away']
    oh   = float(fixture['oh'])
    od   = float(fixture['od'])
    oa   = float(fixture['oa'])
    day  = int(fixture.get('day', 15))
    season_id = str(fixture.get('season', ''))

    if accounting is None:
        accounting = get_seasonal_accounting(df, season_id)

    result = {
        'home': home, 'away': away,
        'oh': oh, 'od': od, 'oa': oa,
        'day': day, 'season': season_id,
        'prediction':      None,
        'certainty_score': 0,
        'tier':            'UNKNOWN',
        'label':           '',
        'is_draw_alert':   False,
        'draw_score':      0,
        'draw_signals':    [],
        'blend_h':         0, 'blend_d': 0, 'blend_a': 0,
        'h_wins':          0,
    }

    # ── TIER 1: SIGNATURE DB ─────────────────────────────────────────────────
    sig = _sig_lookup(home, away, oh, od, oa, sig_db)
    if sig:
        pred, rate, total, certainty = sig
        result.update({
            'prediction':      pred,
            'certainty_score': certainty,
            'tier':            'LOCK' if certainty >= TIER_LOCK else 'SIGNAL',
            'label':           f'SIG {rate:.0%} ({total} samples)',
        })
    else:
        # ── TIER 2: QUOTA / WIN-CAP ──────────────────────────────────────────
        quota = _quota_analysis(home, away, oh, od, oa, day, season_id, accounting, df)

        # ── TIER 3: STATISTICAL BLEND ─────────────────────────────────────────
        quota_penalty = quota['quota_penalty'] if quota else 0.0
        stat_pred, stat_certainty, bh, bd, ba = _stat_blend(home, away, oh, od, oa, profiles, quota_penalty)

        result.update({'blend_h': bh, 'blend_d': bd, 'blend_a': ba})

        if quota:
            # Quota Wall overrides blend prediction
            result.update({
                'prediction':      quota['prediction'],
                'certainty_score': quota['certainty_score'],
                'tier':            'WALL',
                'label':           quota['label'],
                'h_wins':          quota.get('h_wins', 0),
            })
        else:
            result.update({
                'prediction':      stat_pred,
                'certainty_score': stat_certainty,
                'tier':            'MODERATE' if stat_certainty >= TIER_MODERATE else 'WEAK',
                'label':           f'BLEND H{bh:.0%}/D{bd:.0%}/A{ba:.0%}',
            })

    # ── DRAW SCORING (always computed independently) ──────────────────────────
    draw_score, draw_signals = compute_draw_score(
        home, away, oh, od, oa, day, season_id, accounting, df, sig_db
    )
    result['draw_score']   = draw_score
    result['draw_signals'] = draw_signals
    result['is_draw_alert'] = draw_score >= 65

    # ── STAKE CALCULATION ─────────────────────────────────────────────────────
    result['stake'] = get_stake(result['certainty_score'])

    # ── EV CALCULATION (for reference, not for ranking) ──────────────────────
    pred = result['prediction']
    target_odds = oh if pred == 'H' else (od if pred == 'D' else oa)
    true_p, _, _ = _true_probs(oh, od, oa)
    conf_approx = result['certainty_score'] / 100.0
    result['ev'] = round((conf_approx * target_odds) - 1, 3)
    result['target_odds'] = target_odds

    # ── PREDICTION LABEL ─────────────────────────────────────────────────────
    pred_labels = {'H': 'HOME (1)', 'D': 'DRAW (X)', 'A': 'AWAY (2)'}
    result['prediction_label'] = pred_labels.get(pred, pred)

    # ── SIGNAL / STATUS (for UI) ──────────────────────────────────────────────
    cs = result['certainty_score']
    if cs >= TIER_LOCK:
        result['signal'], result['status'] = 'LOCK', 'positive'
    elif cs >= TIER_SIGNAL:
        result['signal'], result['status'] = 'STRONG BUY', 'positive'
    elif cs >= TIER_MODERATE:
        result['signal'], result['status'] = 'MODERATE', 'neutral'
    else:
        result['signal'], result['status'] = 'AVOID', 'negative'

    return result


# ════════════════════════════════════════════════════════════════════════════════
# COMPATIBILITY SHIM — keep old callers working
# ════════════════════════════════════════════════════════════════════════════════

def predict_fixture(fixture, df, profiles, sig_db=None, accounting=None):
    """Backward-compatible wrapper for predict_fixture_v6."""
    if sig_db is None:
        sig_db = {}
    return predict_fixture_v6(fixture, df, profiles, sig_db, accounting)


def apply_global_balancing(pred, stats, day):
    """Compatibility shim — balancing is now internal to V6."""
    return pred
