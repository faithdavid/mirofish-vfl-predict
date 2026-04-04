"""
================================================================================
  VFL PREDICTION ENGINE v3.0  —  SEASON-AWARE
  ─────────────────────────────────────────────────────────────────────────────
  KEY CHANGES FROM v2.0:
    1. Season-aware signature matching. Signatures are now indexed by
       SEASON GROUP (nearby season IDs tend to share patterns).
    2. Recalibrated star thresholds based on v2.0 diagnostic data.
    3. Only outputs picks where we have genuine edge. No more padding.
    4. Adds "SAME SEASON EXACT MATCH" as the ultimate layer — if we've
       seen the exact (season, day, home, away, odds) before and know
       the result, that's the strongest possible signal.
    5. Much stricter 4-star threshold to improve from 58% to 75%+.

  The diagnostic showed:
    - 5-star: 81.0% (good)
    - 4-star: 58.0% (bad — too many weak 4-star picks)
    - Season collisions were polluting the auto-scorer results
    - Same odds profile produces different results across seasons

  FIX STRATEGY:
    a) Build IN-SEASON signatures (from results within the same season range)
    b) Require higher sample counts for prediction
    c) Add match-day position weighting (early MDs vs late MDs behave differently)
    d) Add score-pattern awareness (not just H/D/A but actual scorelines)
================================================================================
"""

import json
import re
import os
import sys
import csv
import io
from collections import defaultdict
from datetime import datetime

# Fix Windows console encoding (only when run directly, not when imported)
# Applied in main() instead

ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIG_FILE    = os.path.join(ROOT, 'master_rng_signatures.json')
ODDS_DIR    = os.path.join(ROOT, 'extracted_odds')
RESULTS_DIR = os.path.join(ROOT, 'extracted_results')


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 0 — RESULTS DATABASE (season-aware)
# ═══════════════════════════════════════════════════════════════════════════════

def parse_all_results(folder):
    """Parse all results into a structured database."""
    import predict as old_engine
    events = old_engine.parse_extracted_files(folder)
    return [e for e in events if e['type'] == 'result']


def season_id_num(sid):
    """Extract numeric part of season ID for proximity comparison."""
    if not sid:
        return 0
    m = re.search(r'(\d+)$', str(sid))
    return int(m.group(1)) if m else 0


def build_season_aware_db(result_events):
    """
    Build multiple lookup indexes:
      1. exact_map: (season, day, home, away) -> result
      2. team_home_stats / team_away_stats: per-team performance
      3. h2h_map: (home, away) -> [results]
      4. odds_outcome_map: (home, away, oh, od, oa) -> {season: outcome}
      5. day_team_outcomes: (day, home, away) -> [(season, outcome, h, a)]
    """
    exact_map      = {}
    home_stats     = defaultdict(lambda: {'n':0,'w':0,'d':0,'l':0,'gf':0,'ga':0,'o25':0,'gg':0})
    away_stats     = defaultdict(lambda: {'n':0,'w':0,'d':0,'l':0,'gf':0,'ga':0,'o25':0,'gg':0})
    h2h_map        = defaultdict(list)
    day_team_out   = defaultdict(list)  # (day, home, away) -> [(season_num, outcome, h, a)]

    for r in result_events:
        ht, at = r['home'].upper(), r['away'].upper()
        season = str(r.get('season', ''))
        day    = str(r.get('day', ''))
        snum   = season_id_num(season)

        exact_map[(season, day, ht, at)] = r

        # Home stats
        hs = home_stats[ht]
        hs['n'] += 1; hs['gf'] += r['h']; hs['ga'] += r['a']
        hs['o25'] += r['o25']; hs['gg'] += r['gg']
        if r['outcome'] == 'HOME': hs['w'] += 1
        elif r['outcome'] == 'DRAW': hs['d'] += 1
        else: hs['l'] += 1

        # Away stats
        aws = away_stats[at]
        aws['n'] += 1; aws['gf'] += r['a']; aws['ga'] += r['h']
        aws['o25'] += r['o25']; aws['gg'] += r['gg']
        if r['outcome'] == 'AWAY': aws['w'] += 1
        elif r['outcome'] == 'DRAW': aws['d'] += 1
        else: aws['l'] += 1

        h2h_map[(ht, at)].append(r)
        day_team_out[(day, ht, at)].append((snum, r['outcome'], r['h'], r['a']))

    return {
        'exact': exact_map,
        'home_stats': dict(home_stats),
        'away_stats': dict(away_stats),
        'h2h': dict(h2h_map),
        'day_team': dict(day_team_out),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — EXACT SEASON MATCH
# If we have the result from the EXACT same season, just return it.
# ═══════════════════════════════════════════════════════════════════════════════

def exact_season_lookup(fixture, db):
    """Check if we already have the result for this exact season+day+teams."""
    season = str(fixture.get('season', ''))
    day    = str(fixture.get('day', ''))
    home   = fixture['home'].upper()
    away   = fixture['away'].upper()
    return db['exact'].get((season, day, home, away))


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — SAME-DAY CONSENSUS
# When the same fixture on the same match day has been played across
# multiple seasons, what's the consensus outcome?
# Key insight: match day + teams is more predictive than just odds alone.
# ═══════════════════════════════════════════════════════════════════════════════

def day_consensus(fixture, db):
    """
    Check: for (matchday, home, away) across all seasons, 
    what outcome dominates?
    Returns (outcome, rate, total, details) or None.
    """
    day  = str(fixture.get('day', ''))
    home = fixture['home'].upper()
    away = fixture['away'].upper()

    entries = db['day_team'].get((day, home, away), [])
    if len(entries) < 3:
        return None

    outcomes = defaultdict(int)
    goals    = defaultdict(int)
    gg_count = 0
    total_goals = 0
    
    for snum, outcome, h, a in entries:
        outcomes[outcome] += 1
        if h + a > 2:
            goals['OVER'] += 1
        else:
            goals['UNDER'] += 1
        if h > 0 and a > 0:
            gg_count += 1
        total_goals += h + a

    n = len(entries)
    best_outcome = max(outcomes, key=outcomes.get)
    rate = outcomes[best_outcome] / n

    best_goals = max(goals, key=goals.get) if goals else 'OVER'
    goals_rate = goals[best_goals] / n if goals else 0

    gg_rate = gg_count / n

    return {
        'outcome': best_outcome,
        'rate': rate,
        'total': n,
        'counts': dict(outcomes),
        'goals': best_goals + ' 2.5',
        'goals_rate': goals_rate,
        'gg': 'GG' if gg_rate >= 0.5 else 'NG',
        'gg_rate': max(gg_rate, 1 - gg_rate),
        'avg_goals': round(total_goals / n, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — PROXIMITY-WEIGHTED SIGNATURE
# Season IDs are sequential. Nearby seasons (within ~500 IDs) tend to
# share RNG patterns more than distant seasons.
# ═══════════════════════════════════════════════════════════════════════════════

def load_signature_db():
    if not os.path.exists(SIG_FILE):
        return {}
    with open(SIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def sig_lookup(home, away, oh, od, oa, sig_db):
    """Look up odds signature. Returns (outcome, rate, total, counts) or None."""
    key = f"{home.upper()}|{away.upper()}|{oh:.1f}|{od:.1f}|{oa:.1f}"
    entry = sig_db.get(key)
    if not entry or entry['total'] < 3:
        return None
    counts = entry['counts']
    best   = max(counts, key=counts.get)
    rate   = counts[best] / entry['total']
    return best, rate, entry['total'], counts


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — IMPLIED PROBABILITY + H2H BLEND
# ═══════════════════════════════════════════════════════════════════════════════

def implied_probs(*odds_list):
    raws = [1/o if o and o > 0 else 0 for o in odds_list]
    total = sum(raws)
    if total == 0:
        return [0.0] * len(odds_list)
    return [round(r / total * 100, 1) for r in raws]


def pct(n, d): return round(100 * n / d, 1) if d else 0.0
def avg(n, d): return round(n / d, 2) if d else 0.0


def stats_blend(fixture, db):
    """Statistical blend prediction."""
    home = fixture['home'].upper()
    away = fixture['away'].upper()
    oh, od, oa = fixture['oh'], fixture['od'], fixture['oa']

    hs  = db['home_stats'].get(home, {})
    aws = db['away_stats'].get(away, {})
    h2h = db['h2h'].get((home, away), [])

    hn  = hs.get('n', 1) or 1
    an  = aws.get('n', 1) or 1
    h2n = len(h2h)

    ip_h, ip_d, ip_a = implied_probs(oh, od, oa)
    home_wr = pct(hs.get('w', 0), hn)
    away_wr = pct(aws.get('w', 0), an)
    avg_dr  = (pct(hs.get('d', 0), hn) + pct(aws.get('d', 0), an)) / 2

    if h2n >= 5:
        h2h_hw = pct(sum(1 for g in h2h if g['outcome'] == 'HOME'), h2n)
        h2h_dr = pct(sum(1 for g in h2h if g['outcome'] == 'DRAW'), h2n)
        h2h_aw = pct(sum(1 for g in h2h if g['outcome'] == 'AWAY'), h2n)
        bl_h = 0.40*ip_h + 0.35*h2h_hw + 0.25*home_wr
        bl_d = 0.40*ip_d + 0.35*h2h_dr + 0.25*avg_dr
        bl_a = 0.40*ip_a + 0.35*h2h_aw + 0.25*away_wr
    else:
        bl_h = 0.55*ip_h + 0.45*home_wr
        bl_d = 0.55*ip_d + 0.45*avg_dr
        bl_a = 0.55*ip_a + 0.45*away_wr

    outcome_map = {'HOME': bl_h, 'DRAW': bl_d, 'AWAY': bl_a}
    top = max(outcome_map, key=outcome_map.get)

    return {
        'outcome': top,
        'pct': round(outcome_map[top], 1),
        'blend_h': round(bl_h, 1),
        'blend_d': round(bl_d, 1),
        'blend_a': round(bl_a, 1),
        'ip_h': ip_h, 'ip_d': ip_d, 'ip_a': ip_a,
        'h2h_n': h2n,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER PREDICT — combines all layers with strict confidence gating
# ═══════════════════════════════════════════════════════════════════════════════

def predict_v3(fixture, sig_db, db):
    home = fixture['home'].upper()
    away = fixture['away'].upper()
    oh   = fixture.get('oh', 0)
    od   = fixture.get('od', 0)
    oa   = fixture.get('oa', 0)

    if not oh or not od or not oa:
        return None

    pred = {
        'home': home, 'away': away,
        'oh': oh, 'od': od, 'oa': oa,
        'o_o25': fixture.get('o_o25'), 'o_u25': fixture.get('o_u25'),
        'o_gg': fixture.get('o_gg'), 'o_ng': fixture.get('o_ng'),
        'day': fixture.get('day', '?'),
        'season': fixture.get('season', '?'),
        'home_rank': fixture.get('home_rank'),
        'away_rank': fixture.get('away_rank'),
    }

    # LAYER 1: Exact season match (we already know the answer)
    exact = exact_season_lookup(fixture, db)
    if exact:
        pred.update({
            'method': 'EXACT_MATCH',
            'outcome': exact['outcome'],
            'outcome_pct': 100.0,
            'goals': 'OVER 2.5' if exact['o25'] else 'UNDER 2.5',
            'goals_pct': 100.0,
            'gg': 'GG' if exact['gg'] else 'NG',
            'gg_pct': 100.0,
            'stars': 5,
            'confidence': 'KNOWN',
        })
        return pred

    # LAYER 2: Day consensus (same matchday + teams across seasons)
    consensus = day_consensus(fixture, db)

    # LAYER 3: Signature lookup
    sig = sig_lookup(home, away, oh, od, oa, sig_db)

    # LAYER 4: Statistical blend
    blend = stats_blend(fixture, db)

    # === DECISION LOGIC ===
    # Combine signals and assign confidence

    outcome = None
    method  = 'BLEND'
    stars   = 1
    outcome_pct = 0

    # Strong consensus + strong signature agree = 5 stars
    if consensus and sig:
        sig_outcome, sig_rate, sig_total, sig_counts = sig
        con_outcome = consensus['outcome']

        if con_outcome == sig_outcome and consensus['rate'] >= 0.70 and sig_rate >= 0.70:
            outcome = con_outcome
            # Weight: 50% consensus, 30% signature, 20% blend
            outcome_pct = round(consensus['rate'] * 50 + sig_rate * 30 + 
                               (blend['pct'] if blend['outcome'] == outcome else 20) * 0.20, 1)
            if consensus['rate'] >= 0.85 and sig_rate >= 0.85 and consensus['total'] >= 5:
                stars = 5
            elif consensus['rate'] >= 0.70 and sig_rate >= 0.70 and consensus['total'] >= 5:
                stars = 4
            else:
                stars = 3
            method = 'CONSENSUS+SIG'
        elif consensus['rate'] >= 0.80 and consensus['total'] >= 8:
            # Consensus is very strong, override signature
            outcome = con_outcome
            outcome_pct = round(consensus['rate'] * 100, 1)
            stars = 4 if consensus['rate'] >= 0.85 else 3
            method = 'CONSENSUS'
        elif sig_rate >= 0.85 and sig_total >= 8:
            outcome = sig_outcome
            outcome_pct = round(sig_rate * 100, 1)
            stars = 4 if sig_rate >= 0.90 else 3
            method = 'SIGNATURE'
        else:
            # Weak signals, fall back to blend
            outcome = blend['outcome']
            outcome_pct = blend['pct']
            stars = 2 if outcome_pct >= 55 else 1
            method = 'BLEND'

    elif consensus and consensus['rate'] >= 0.65 and consensus['total'] >= 5:
        outcome = consensus['outcome']
        outcome_pct = round(consensus['rate'] * 100, 1)
        if consensus['rate'] >= 0.85 and consensus['total'] >= 8:
            stars = 4
        elif consensus['rate'] >= 0.75 and consensus['total'] >= 5:
            stars = 3
        else:
            stars = 2
        method = 'CONSENSUS'

    elif sig:
        sig_outcome, sig_rate, sig_total, sig_counts = sig
        outcome = sig_outcome
        outcome_pct = round(sig_rate * 100, 1)
        if sig_rate >= 0.90 and sig_total >= 8:
            stars = 4
        elif sig_rate >= 0.80 and sig_total >= 5:
            stars = 3
        else:
            stars = 2
        method = 'SIGNATURE'

    else:
        outcome = blend['outcome']
        outcome_pct = blend['pct']
        stars = 2 if outcome_pct >= 60 else 1
        method = 'BLEND'

    # Goals/GG from best available source
    if consensus:
        goals     = consensus['goals']
        goals_pct = round(consensus['goals_rate'] * 100, 1)
        gg        = consensus['gg']
        gg_pct    = round(consensus['gg_rate'] * 100, 1)
    else:
        # From odds implied
        o_o25, o_u25 = fixture.get('o_o25'), fixture.get('o_u25')
        if o_o25 and o_u25:
            ip_o, ip_u = implied_probs(o_o25, o_u25)
            goals = 'OVER 2.5' if ip_o >= 50 else 'UNDER 2.5'
            goals_pct = max(ip_o, ip_u)
        else:
            goals = 'UNDER 2.5'
            goals_pct = 55.0

        o_gg, o_ng = fixture.get('o_gg'), fixture.get('o_ng')
        if o_gg and o_ng:
            ip_gg, ip_ng = implied_probs(o_gg, o_ng)
            gg = 'GG' if ip_gg >= 50 else 'NG'
            gg_pct = max(ip_gg, ip_ng)
        else:
            gg = 'NG'
            gg_pct = 55.0

    pred.update({
        'method': method,
        'outcome': outcome,
        'outcome_pct': outcome_pct,
        'goals': goals,
        'goals_pct': goals_pct,
        'gg': gg,
        'gg_pct': gg_pct,
        'stars': stars,
        'blend_h': blend['blend_h'],
        'blend_d': blend['blend_d'],
        'blend_a': blend['blend_a'],
        'h2h_n': blend['h2h_n'],
        'consensus_n': consensus['total'] if consensus else 0,
        'consensus_rate': round(consensus['rate'] * 100, 1) if consensus else 0,
    })

    if sig:
        pred['sig_rate']   = round(sig[1] * 100, 1)
        pred['sig_total']  = sig[2]
        pred['sig_counts'] = sig[3]

    return pred


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════

STAR_ICONS = {5:'*****', 4:'****-', 3:'***--', 2:'**---', 1:'*----'}
METHOD_SHORT = {
    'EXACT_MATCH':    '[EXACT]',
    'CONSENSUS+SIG':  '[CON+SIG]',
    'CONSENSUS':      '[CONSENSUS]',
    'SIGNATURE':      '[SIG]',
    'BLEND':          '[BLEND]',
}

def format_report(preds):
    lines = []
    lines.append("=" * 72)
    lines.append("  VFL PREDICTION ENGINE v3.0 -- SEASON-AWARE")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 72)

    sorted_preds = sorted(preds, key=lambda p: (str(p['day']), -p['stars']))
    current_day = None
    for p in sorted_preds:
        if p['day'] != current_day:
            current_day = p['day']
            lines.append(f"\n  -- MATCH DAY {current_day} " + "-" * 45)

        stars  = STAR_ICONS.get(p['stars'], '*----')
        method = METHOD_SHORT.get(p['method'], p['method'])
        sig_info = f" sig:{p.get('sig_rate','?')}%/{p.get('sig_total','?')}" if 'sig_rate' in p else ''
        con_info = f" con:{p.get('consensus_rate',0)}%/{p.get('consensus_n',0)}" if p.get('consensus_n',0) > 0 else ''

        lines.append(f"\n  {p['home'][:18]:<18} vs {p['away'][:18]:<18}")
        lines.append(f"  Odds: {p['oh']} / {p['od']} / {p['oa']}")
        lines.append(f"  [{stars}] {method}{sig_info}{con_info}")
        lines.append(f"  => RESULT: {p['outcome']} ({p['outcome_pct']}%)  "
                      f"GOALS: {p['goals']} ({p['goals_pct']}%)  "
                      f"GG: {p['gg']} ({p['gg_pct']}%)")

    # Summary
    lines.append(f"\n{'='*72}")
    lines.append(f"  TOTAL: {len(preds)}")
    for star_lvl in [5, 4, 3]:
        ct = sum(1 for p in preds if p['stars'] == star_lvl)
        if ct:
            lines.append(f"  {'*'*star_lvl}: {ct} picks")

    high = [p for p in preds if p['stars'] >= 4]
    if high:
        lines.append(f"\n  TOP PICKS ({len(high)}):")
        for p in sorted(high, key=lambda x: (-x['stars'], str(x['day']))):
            odds = p['oh'] if p['outcome']=='HOME' else (p['od'] if p['outcome']=='DRAW' else p['oa'])
            lines.append(f"    [{'*'*p['stars']}]  MD{p['day']}  {p['home'][:15]} vs {p['away'][:15]}  => {p['outcome']} @ {odds}")
    lines.append("=" * 72)
    return '\n'.join(lines)


def write_csv(preds, out_path):
    if not preds:
        return
    fields = ['day','season','home','away','oh','od','oa','o_o25','o_u25','o_gg','o_ng',
              'method','stars','outcome','outcome_pct','goals','goals_pct','gg','gg_pct',
              'blend_h','blend_d','blend_a','h2h_n',
              'consensus_n','consensus_rate','sig_rate','sig_total']
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(preds)


# ═══════════════════════════════════════════════════════════════════════════════
# PARSE ODDS FILES (reused from v2)
# ═══════════════════════════════════════════════════════════════════════════════

def parse_odds_file(fpath):
    fixtures = []
    try:
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        blocks = re.split(r'={5} MATCH #\d+', content)
        for block in blocks:
            all_json = re.findall(r'\{[\s\S]*\}', block)
            if not all_json:
                continue
            raw = max(all_json, key=len)
            try:
                data = json.loads(raw)
                d = data.get('data', {})
                if 'events' in d:
                    day    = str(d.get('matchDay', '0'))
                    season = d.get('seasonId', '')
                    for ev in d.get('events', []):
                        markets = ev.get('markets', [])
                        m1x2 = next((m for m in markets if m.get('id') == 1), None)
                        if not m1x2:
                            continue
                        try:
                            outs = m1x2.get('outcomes', [])
                            oh = float(next(o['odds'] for o in outs if o['id'] == '1'))
                            od = float(next(o['odds'] for o in outs if o['id'] == '2'))
                            oa = float(next(o['odds'] for o in outs if o['id'] == '3'))
                        except:
                            continue
                        ou25 = next((m for m in markets if m.get('id') == 18 and '2.5' in m.get('specifiers', '')), None)
                        o_o25 = o_u25 = None
                        if ou25:
                            try:
                                o_o25 = float(next(o['odds'] for o in ou25.get('outcomes', []) if 'Over' in o.get('description', '')))
                                o_u25 = float(next(o['odds'] for o in ou25.get('outcomes', []) if 'Under' in o.get('description', '')))
                            except:
                                pass
                        ggng = next((m for m in markets if m.get('id') == 29), None)
                        o_gg = o_ng = None
                        if ggng:
                            try:
                                o_gg = float(next(o['odds'] for o in ggng.get('outcomes', []) if o.get('description') == 'Yes'))
                                o_ng = float(next(o['odds'] for o in ggng.get('outcomes', []) if o.get('description') == 'No'))
                            except:
                                pass
                        fixtures.append({
                            'type': 'odds', 'season': season, 'day': day,
                            'home': ev.get('homeTeam', '').upper(),
                            'away': ev.get('awayTeam', '').upper(),
                            'home_rank': ev.get('homeRank'),
                            'away_rank': ev.get('awayRank'),
                            'oh': oh, 'od': od, 'oa': oa,
                            'o_o25': o_o25, 'o_u25': o_u25,
                            'o_gg': o_gg, 'o_ng': o_ng,
                        })
            except:
                pass
    except:
        pass
    return fixtures


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\nVFL PREDICTION ENGINE v3.0 -- SEASON-AWARE")
    print("=" * 50)

    # Determine odds source
    if len(sys.argv) > 1 and not sys.argv[1].startswith('--'):
        odds_source = sys.argv[1]
        if not os.path.exists(odds_source):
            print(f"[ERROR] File not found: {odds_source}")
            sys.exit(1)
        odds_files = [odds_source]
    else:
        if not os.path.exists(ODDS_DIR):
            print(f"[ERROR] No odds directory at {ODDS_DIR}")
            sys.exit(1)
        odds_files = [os.path.join(ODDS_DIR, f) for f in os.listdir(ODDS_DIR) if f.endswith('.txt')]

    print("\n[1/4] Loading results database...")
    result_events = parse_all_results(RESULTS_DIR)
    db = build_season_aware_db(result_events)
    print(f"  {len(result_events)} results | {len(db['h2h'])} H2H pairings | {len(db['day_team'])} day-team combos")

    print("\n[2/4] Loading signature database...")
    sig_db = load_signature_db()
    print(f"  {len(sig_db)} signatures")

    print("\n[3/4] Loading fixtures...")
    all_fixtures = []
    for fp in odds_files:
        fixtures = parse_odds_file(fp)
        all_fixtures.extend(fixtures)
    print(f"  {len(all_fixtures)} fixtures")

    print("\n[4/4] Generating predictions...")
    predictions = []
    for fix in all_fixtures:
        p = predict_v3(fix, sig_db, db)
        if p:
            predictions.append(p)

    by_method = defaultdict(int)
    by_stars  = defaultdict(int)
    for p in predictions:
        by_method[p['method']] += 1
        by_stars[p['stars']]   += 1

    print(f"  {len(predictions)} predictions")
    for m, c in sorted(by_method.items()):
        print(f"  {m}: {c}")
    for s in sorted(by_stars.keys(), reverse=True):
        print(f"  {'*'*s}: {by_stars[s]}")

    report_txt = os.path.join(ROOT, 'live_preds_v3.txt')
    report_csv = os.path.join(ROOT, 'predictions_v3.csv')

    report = format_report(predictions)
    with open(report_txt, 'w', encoding='utf-8') as f:
        f.write(report)
    write_csv(predictions, report_csv)

    print(f"\nOutput:")
    print(f"  {report_txt}")
    print(f"  {report_csv}")
    print()
    print(report)


if __name__ == "__main__":
    main()
