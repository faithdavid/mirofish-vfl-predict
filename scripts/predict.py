import io
"""
================================================================================
  VFL MASTER PREDICTION ENGINE  v2.0
  ─────────────────────────────────────────────────────────────────────────────
  Three-layer prediction system:

  LAYER 1 — SIGNATURE LOOKUP (highest trust)
    Looks up the exact (Home, Away, Odds) combination in master_rng_signatures.json.
    If found with 5+ samples and 70%+ hit rate → use it directly.

  LAYER 2 — STATISTICAL BLEND (medium trust)
    Blends three signals:
      • 40% Odds-implied probability (bookmaker margin removed)
      • 35% Head-to-head historical record  
      • 25% Individual team home/away win rates

  LAYER 3 — ODDS-BRACKET BIAS (fallback calibrator)
    Applies the proven RNG biases found in the data (e.g. heavy favourites win
    64.9% of the time) when no better signal is available.

  CONFIDENCE STARS
    ★★★★★  Exact signature, 90%+ hit rate, 5+ samples
    ★★★★   Exact signature, 70%+ hit rate, 5+ samples
    ★★★    Statistical blend, top outcome ≥ 60%
    ★★     Statistical blend, top outcome ≥ 50%
    ★      Weak signal, proceed with caution

  USAGE
    python scripts/predict.py <odds_txt_file>
    python scripts/predict.py              # uses extracted_odds/ folder
================================================================================
"""

import json
import re
import os
import sys
import csv
from collections import defaultdict
from datetime import datetime

# ── PATHS ──────────────────────────────────────────────────────────────────
ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIG_FILE    = os.path.join(ROOT, 'master_rng_signatures.json')
ODDS_DIR    = os.path.join(ROOT, 'extracted_odds')
RESULTS_DIR = os.path.join(ROOT, 'extracted_results')

# ── CONSTANTS ──────────────────────────────────────────────────────────────
MIN_SIG_SAMPLES     = 5      # minimum historical samples to trust a signature
SIG_HIGH_THRESHOLD  = 0.90   # 90%+ = 5 stars
SIG_MED_THRESHOLD   = 0.70   # 70%+ = 4 stars

# ── LAYER 1: SIGNATURE DATABASE ────────────────────────────────────────────

def load_signature_db():
    if not os.path.exists(SIG_FILE):
        print(f"  [WARN] Signature file not found at {SIG_FILE}. Layer 1 disabled.")
        return {}
    with open(SIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def sig_lookup(home, away, oh, od, oa, sig_db):
    """
    Tries to find this fixture+odds combo in the signature database.
    Also tries rounded variants (±0.05) for near-miss matching.
    Returns (best_outcome, hit_rate, total_samples, stars) or None.
    """
    def _try_key(key):
        entry = sig_db.get(key)
        if not entry or entry['total'] < MIN_SIG_SAMPLES:
            return None
        counts = entry['counts']
        best   = max(counts, key=counts.get)
        rate   = counts[best] / entry['total']
        if rate >= SIG_HIGH_THRESHOLD:
            stars = 5
        elif rate >= SIG_MED_THRESHOLD:
            stars = 4
        else:
            return None  # don't trust below 70%
        return best, rate, entry['total'], stars, counts

    h_name = home.upper()
    a_name = away.upper()

    # Exact match
    key = f"{h_name}|{a_name}|{oh:.1f}|{od:.1f}|{oa:.1f}"
    result = _try_key(key)
    if result:
        return result

    # Near-miss: try ±0.1 for each odd
    for dh in [0, 0.1, -0.1]:
        for dd in [0, 0.1, -0.1]:
            for da in [0, 0.1, -0.1]:
                if dh == 0 and dd == 0 and da == 0:
                    continue
                key2 = f"{h_name}|{a_name}|{oh+dh:.1f}|{od+dd:.1f}|{oa+da:.1f}"
                result = _try_key(key2)
                if result:
                    # Downgrade stars by 1 for near-miss
                    best, rate, total, stars, counts = result
                    return best, rate, total, max(1, stars - 1), counts

    return None

# ── LAYER 2: STATISTICAL MODEL ─────────────────────────────────────────────

def parse_extracted_files(folder):
    """Parse all extracted .txt files from a folder. Returns list of event dicts."""
    events = []
    if not os.path.exists(folder):
        return events
    for fname in os.listdir(folder):
        if not fname.endswith('.txt'):
            continue
        fpath = os.path.join(folder, fname)
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            blocks = re.split(r'={5} MATCH #\d+', content)
            for block in blocks:
                json_match = re.search(r'\{[\s\S]*?\}(?=\s*(?:=====|$))', block)
                # Try to find the largest JSON object in the block
                all_json = re.findall(r'\{[\s\S]*\}', block)
                if not all_json:
                    continue
                raw = max(all_json, key=len)
                try:
                    data = json.loads(raw)
                    d = data.get('data', {})
                    # Results format
                    if 'results' in d:
                        day = str(d.get('current', {}).get('matchDay', '0'))
                        season = d.get('current', {}).get('seasonId', '')
                        for r in d.get('results', []):
                            try:
                                h, a = map(int, r['fullTime'].replace(' ', '').split(':'))
                                events.append({
                                    'type': 'result',
                                    'season': season,
                                    'day': day,
                                    'home': r['homeTeam'].upper(),
                                    'away': r['awayTeam'].upper(),
                                    'h': h, 'a': a,
                                    'outcome': 'HOME' if h > a else ('AWAY' if a > h else 'DRAW'),
                                    'total': h + a,
                                    'gg': int(h > 0 and a > 0),
                                    'o25': int(h + a > 2),
                                })
                            except:
                                pass
                    # Odds format
                    elif 'events' in d:
                        day = str(d.get('matchDay', '0'))
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
                            # Over/Under 2.5
                            ou25 = next((m for m in markets if m.get('id') == 18 and '2.5' in m.get('specifiers', '')), None)
                            o_o25 = o_u25 = None
                            if ou25:
                                try:
                                    o_o25 = float(next(o['odds'] for o in ou25.get('outcomes', []) if 'Over' in o.get('description', '')))
                                    o_u25 = float(next(o['odds'] for o in ou25.get('outcomes', []) if 'Under' in o.get('description', '')))
                                except:
                                    pass
                            # GG/NG
                            ggng = next((m for m in markets if m.get('id') == 29), None)
                            o_gg = o_ng = None
                            if ggng:
                                try:
                                    o_gg = float(next(o['odds'] for o in ggng.get('outcomes', []) if o.get('description') == 'Yes'))
                                    o_ng = float(next(o['odds'] for o in ggng.get('outcomes', []) if o.get('description') == 'No'))
                                except:
                                    pass
                            events.append({
                                'type': 'odds',
                                'season': season,
                                'day': day,
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
    return events


def build_stats(result_events):
    """Build team home/away stats and H2H map from results."""
    home_stats = defaultdict(lambda: {'n':0,'w':0,'d':0,'l':0,'gf':0,'ga':0,'o25':0,'gg':0})
    away_stats = defaultdict(lambda: {'n':0,'w':0,'d':0,'l':0,'gf':0,'ga':0,'o25':0,'gg':0})
    h2h_map    = defaultdict(list)

    for r in result_events:
        ht, at = r['home'], r['away']

        # Home team
        hs = home_stats[ht]
        hs['n'] += 1; hs['gf'] += r['h']; hs['ga'] += r['a']
        hs['o25'] += r['o25']; hs['gg'] += r['gg']
        if r['outcome'] == 'HOME': hs['w'] += 1
        elif r['outcome'] == 'DRAW': hs['d'] += 1
        else: hs['l'] += 1

        # Away team
        aws = away_stats[at]
        aws['n'] += 1; aws['gf'] += r['a']; aws['ga'] += r['h']
        aws['o25'] += r['o25']; aws['gg'] += r['gg']
        if r['outcome'] == 'AWAY': aws['w'] += 1
        elif r['outcome'] == 'DRAW': aws['d'] += 1
        else: aws['l'] += 1

        h2h_map[(ht, at)].append(r)

    return dict(home_stats), dict(away_stats), dict(h2h_map)


def pct(n, d): return round(100 * n / d, 1) if d else 0.0
def avg(n, d): return round(n / d, 2) if d else 0.0


def implied_probs(*odds_list):
    """Remove bookmaker margin, return true implied probabilities as percentages."""
    raws = [1/o if o and o > 0 else 0 for o in odds_list]
    total = sum(raws)
    if total == 0:
        return [0.0] * len(odds_list)
    return [round(r / total * 100, 1) for r in raws]


def statistical_prediction(home, away, oh, od, oa, o_o25, o_u25, o_gg, o_ng,
                            home_stats, away_stats, h2h_map):
    """Layer 2: Statistical blend prediction."""
    hs = home_stats.get(home, {})
    aws = away_stats.get(away, {})
    h2h = h2h_map.get((home, away), [])

    hn  = hs.get('n', 1) or 1
    an  = aws.get('n', 1) or 1
    h2n = len(h2h)

    # Team stats
    home_wr   = pct(hs.get('w', 0), hn)
    home_dr   = pct(hs.get('d', 0), hn)
    home_o25  = pct(hs.get('o25', 0), hn)
    home_gg   = pct(hs.get('gg', 0), hn)
    away_wr   = pct(aws.get('w', 0), an)
    away_dr   = pct(aws.get('d', 0), an)
    away_o25  = pct(aws.get('o25', 0), an)
    away_gg   = pct(aws.get('gg', 0), an)
    avg_dr    = (home_dr + away_dr) / 2

    # Implied probabilities
    ip_h, ip_d, ip_a = implied_probs(oh, od, oa)
    ip_o25 = ip_u25 = 50.0
    if o_o25 and o_u25:
        ip_o25, ip_u25 = implied_probs(o_o25, o_u25)
    ip_gg = ip_ng = 50.0
    if o_gg and o_ng:
        ip_gg, ip_ng = implied_probs(o_gg, o_ng)

    # H2H
    h2h_hw = h2h_dr = h2h_aw = h2h_o25 = h2h_gg = 0.0
    last5_outcomes = last5_scores = ''
    if h2n:
        hw = sum(1 for g in h2h if g['outcome'] == 'HOME')
        dr = sum(1 for g in h2h if g['outcome'] == 'DRAW')
        aw = sum(1 for g in h2h if g['outcome'] == 'AWAY')
        h2h_hw  = pct(hw, h2n)
        h2h_dr  = pct(dr, h2n)
        h2h_aw  = pct(aw, h2n)
        h2h_o25 = pct(sum(g['o25'] for g in h2h), h2n)
        h2h_gg  = pct(sum(g['gg']  for g in h2h), h2n)
        last5   = h2h[-5:]
        last5_outcomes = ','.join('H' if g['outcome']=='HOME' else ('D' if g['outcome']=='DRAW' else 'A') for g in last5)
        last5_scores   = ','.join(f"{g['h']}:{g['a']}" for g in last5)

    # Blend
    W_ODDS = 0.40; W_H2H = 0.35; W_STATS = 0.25
    if h2n >= 5:
        bl_h   = W_ODDS*ip_h   + W_H2H*h2h_hw  + W_STATS*home_wr
        bl_d   = W_ODDS*ip_d   + W_H2H*h2h_dr  + W_STATS*avg_dr
        bl_a   = W_ODDS*ip_a   + W_H2H*h2h_aw  + W_STATS*away_wr
        bl_o25 = W_ODDS*ip_o25 + W_H2H*h2h_o25 + W_STATS*(home_o25+away_o25)/2
        bl_gg  = W_ODDS*ip_gg  + W_H2H*h2h_gg  + W_STATS*(home_gg+away_gg)/2
    else:
        bl_h   = 0.50*ip_h   + 0.50*home_wr
        bl_d   = 0.50*ip_d   + 0.50*avg_dr
        bl_a   = 0.50*ip_a   + 0.50*away_wr
        bl_o25 = 0.50*ip_o25 + 0.50*(home_o25+away_o25)/2
        bl_gg  = 0.50*ip_gg  + 0.50*(home_gg+away_gg)/2

    # Pick outcomes
    outcome_map = {'HOME': bl_h, 'DRAW': bl_d, 'AWAY': bl_a}
    top_outcome = max(outcome_map, key=outcome_map.get)
    top_score   = round(outcome_map[top_outcome], 1)

    goals_pick  = 'OVER 2.5' if bl_o25 >= 50 else 'UNDER 2.5'
    goals_score = round(bl_o25 if bl_o25 >= 50 else 100 - bl_o25, 1)

    gg_pick   = 'GG' if bl_gg >= 50 else 'NG'
    gg_score  = round(bl_gg if bl_gg >= 50 else 100 - bl_gg, 1)

    # Stars based on outcome confidence
    if top_score >= 65: stars = 3
    elif top_score >= 55: stars = 2
    else: stars = 1

    return {
        'method':       'STATS_BLEND',
        'outcome':      top_outcome,
        'outcome_pct':  top_score,
        'goals':        goals_pick,
        'goals_pct':    goals_score,
        'gg':           gg_pick,
        'gg_pct':       gg_score,
        'stars':        stars,
        'ip_h': ip_h, 'ip_d': ip_d, 'ip_a': ip_a,
        'ip_o25': ip_o25, 'ip_gg': ip_gg,
        'home_wr': home_wr, 'home_gf': avg(hs.get('gf',0), hn),
        'away_wr': away_wr, 'away_gf': avg(aws.get('gf',0), an),
        'h2h_n': h2n, 'h2h_hw': h2h_hw, 'h2h_dr': h2h_dr, 'h2h_aw': h2h_aw,
        'last5_outcomes': last5_outcomes, 'last5_scores': last5_scores,
        'blend_h': round(bl_h,1), 'blend_d': round(bl_d,1), 'blend_a': round(bl_a,1),
    }


# ── LAYER 3: ODDS-BRACKET BIAS ─────────────────────────────────────────────
# From empirical analysis of 6,382 data points

BRACKET_BIAS = {
    # (fav_odds_min, fav_odds_max): (home_win_pct, draw_pct, away_win_pct)
    (1.0,  1.5):  (64.9, 18.4, 16.7),
    (1.5,  2.0):  (41.9, 24.8, 33.3),
    (2.0,  2.5):  (36.6, 26.0, 37.4),
    (2.5, 99.0):  (27.1, 25.0, 47.9),
}

def bracket_bias(oh, oa):
    """Return the expected distribution for this odds bracket."""
    # Favourite = team with lower odds
    fav_odds = min(oh, oa)
    for (lo, hi), (h_pct, d_pct, a_pct) in BRACKET_BIAS.items():
        if lo <= fav_odds < hi:
            # If the favourite is the away team, flip home/away
            if oa < oh:
                return a_pct, d_pct, h_pct  # away is fav
            return h_pct, d_pct, a_pct
    return 33.3, 33.3, 33.3


# ── MAIN PREDICTION FUNCTION ───────────────────────────────────────────────

def predict(fixture, sig_db, home_stats, away_stats, h2h_map):
    home = fixture['home'].upper()
    away = fixture['away'].upper()
    oh   = fixture.get('oh', 0)
    od   = fixture.get('od', 0)
    oa   = fixture.get('oa', 0)

    if not oh or not od or not oa:
        return None

    o_o25 = fixture.get('o_o25')
    o_u25 = fixture.get('o_u25')
    o_gg  = fixture.get('o_gg')
    o_ng  = fixture.get('o_ng')

    pred = {'home': home, 'away': away, 'oh': oh, 'od': od, 'oa': oa,
            'o_o25': o_o25, 'o_u25': o_u25, 'o_gg': o_gg, 'o_ng': o_ng,
            'day': fixture.get('day', '?'), 'season': fixture.get('season', '?'),
            'home_rank': fixture.get('home_rank'), 'away_rank': fixture.get('away_rank')}

    # LAYER 1: Signature lookup
    sig = sig_lookup(home, away, oh, od, oa, sig_db)
    if sig:
        best, rate, total, stars, counts = sig
        stat = statistical_prediction(home, away, oh, od, oa, o_o25, o_u25, o_gg, o_ng,
                                       home_stats, away_stats, h2h_map)
        pred.update(stat)
        pred.update({
            'method':      'SIGNATURE',
            'sig_outcome': best,
            'sig_rate':    round(rate * 100, 1),
            'sig_total':   total,
            'sig_counts':  counts,
            'outcome':     best,
            'outcome_pct': round(rate * 100, 1),
            'stars':       stars,
        })
        return pred

    # LAYER 2: Statistical blend
    stat = statistical_prediction(home, away, oh, od, oa, o_o25, o_u25, o_gg, o_ng,
                                   home_stats, away_stats, h2h_map)
    pred.update(stat)
    return pred


# ── OUTPUT FORMATTING ──────────────────────────────────────────────────────

STAR_ICONS = {5:'★★★★★', 4:'★★★★', 3:'★★★', 2:'★★', 1:'★'}
METHOD_LABELS = {'SIGNATURE': '[SIG MATCH]', 'STATS_BLEND': '[STATS]'}

def format_rank_edge(home_rank, away_rank):
    if not home_rank or not away_rank:
        return ''
    diff = away_rank - home_rank
    if diff >= 4:   return f"  RANK: Home ranked {diff} higher"
    if diff <= -4:  return f"  RANK: Away ranked {-diff} higher"
    return ''

def format_report(preds):
    lines = []
    lines.append("=" * 65)
    lines.append("  VFL MASTER PREDICTION ENGINE  v2.0")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 65)

    # Sorted by day then stars (descending)
    sorted_preds = sorted(preds, key=lambda p: (str(p['day']), -p['stars']))

    current_day = None
    for p in sorted_preds:
        if p['day'] != current_day:
            current_day = p['day']
            lines.append(f"\n{'─'*65}")
            lines.append(f"  MATCH DAY {current_day}")
            lines.append(f"{'─'*65}")

        stars = STAR_ICONS.get(p['stars'], '★')
        method = METHOD_LABELS.get(p['method'], '')
        rank_edge = format_rank_edge(p.get('home_rank'), p.get('away_rank'))

        lines.append(f"\n  {p['home']} vs {p['away']}")
        lines.append(f"  Odds: {p['oh']} / {p['od']} / {p['oa']}  (H/D/A)")

        if p['method'] == 'SIGNATURE':
            lines.append(f"  {stars} SIGNATURE MATCH  {p['sig_rate']}% ({p['sig_counts']}) over {p['sig_total']} games")
        else:
            lines.append(f"  {stars} {method}  blend: H={p['blend_h']}%  D={p['blend_d']}%  A={p['blend_a']}%")

        if p.get('h2h_n', 0) > 0:
            lines.append(f"  H2H ({p['h2h_n']} games): H={p['h2h_hw']}%  D={p['h2h_dr']}%  A={p['h2h_aw']}%  |  Last 5: {p.get('last5_outcomes','')}  ({p.get('last5_scores','')})")

        if rank_edge:
            lines.append(rank_edge)

        lines.append(f"  ── PICK ── RESULT: {p['outcome']} ({p['outcome_pct']}%)   GOALS: {p['goals']} ({p['goals_pct']}%)   GG: {p['gg']} ({p['gg_pct']}%)")

    lines.append(f"\n{'='*65}")
    lines.append(f"  TOTAL FIXTURES: {len(preds)}")
    high_conf = [p for p in preds if p['stars'] >= 4]
    lines.append(f"  HIGH CONFIDENCE (4-5 stars): {len(high_conf)}")
    if high_conf:
        lines.append(f"\n  BEST BETS (4+ stars):")
        for p in sorted(high_conf, key=lambda x: -x['stars']):
            lines.append(f"    {STAR_ICONS[p['stars']]}  MD{p['day']}  {p['home']} vs {p['away']}  →  {p['outcome']} @ odds {p['oh'] if p['outcome']=='HOME' else (p['od'] if p['outcome']=='DRAW' else p['oa'])}")
    lines.append("=" * 65)

    return '\n'.join(lines)


def write_csv(preds, out_path):
    if not preds:
        return
    fields = ['day','season','home','away','oh','od','oa','o_o25','o_u25','o_gg','o_ng',
              'method','stars','outcome','outcome_pct','goals','goals_pct','gg','gg_pct',
              'ip_h','ip_d','ip_a','ip_o25','ip_gg',
              'home_wr','home_gf','away_wr','away_gf',
              'h2h_n','h2h_hw','h2h_dr','h2h_aw','last5_outcomes','last5_scores',
              'blend_h','blend_d','blend_a',
              'sig_rate','sig_total']
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(preds)


# ── ENTRY POINT ────────────────────────────────────────────────────────────

def main():
    print("\nVFL MASTER PREDICTION ENGINE  v2.0")
    print("=" * 45)

    # Determine odds source
    if len(sys.argv) > 1:
        odds_source = sys.argv[1]
        if not os.path.exists(odds_source):
            print(f"[ERROR] File not found: {odds_source}")
            sys.exit(1)
        odds_files = [odds_source]
    else:
        # Use all files in extracted_odds/
        if not os.path.exists(ODDS_DIR):
            print(f"[ERROR] No odds directory found at {ODDS_DIR}")
            sys.exit(1)
        odds_files = [os.path.join(ODDS_DIR, f) for f in os.listdir(ODDS_DIR) if f.endswith('.txt')]

    print(f"\n[1/4] Loading signature database...")
    sig_db = load_signature_db()
    print(f"  Loaded {len(sig_db)} signatures.")

    print(f"\n[2/4] Loading historical results...")
    result_events = parse_extracted_files(RESULTS_DIR)
    results_only  = [e for e in result_events if e['type'] == 'result']
    home_stats, away_stats, h2h_map = build_stats(results_only)
    print(f"  {len(results_only)} match results indexed.")
    print(f"  {len(home_stats)} teams tracked in home stats.")
    print(f"  {sum(len(v) for v in h2h_map.values())} H2H entries across {len(h2h_map)} pairings.")

    print(f"\n[3/4] Loading odds fixtures...")
    all_fixtures = []
    for fp in odds_files:
        events = parse_extracted_files(os.path.dirname(fp)) if os.path.isfile(fp) else []
        # If a specific file was given, parse it directly  
        if os.path.isfile(fp):
            events = []
            try:
                with open(fp, 'r', encoding='utf-8', errors='replace') as f:
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
                            day = str(d.get('matchDay', '0'))
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
                                events.append({
                                    'type': 'odds',
                                    'season': season,
                                    'day': day,
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
        all_fixtures.extend([e for e in events if e['type'] == 'odds'])

    if not all_fixtures:
        print("[WARN] No fixtures found in provided odds files.")
        print("Tip: Run 'python scripts/batch_har_extract.py <har_folder>' first.")
        sys.exit(0)

    print(f"  {len(all_fixtures)} fixtures to predict.")

    print(f"\n[4/4] Generating predictions...")
    predictions = []
    for fix in all_fixtures:
        p = predict(fix, sig_db, home_stats, away_stats, h2h_map)
        if p:
            predictions.append(p)

    sig_count   = sum(1 for p in predictions if p['method'] == 'SIGNATURE')
    stat_count  = sum(1 for p in predictions if p['method'] == 'STATS_BLEND')
    star5_count = sum(1 for p in predictions if p['stars'] >= 5)
    star4_count = sum(1 for p in predictions if p['stars'] == 4)

    print(f"  {len(predictions)} predictions generated.")
    print(f"  Method: SIGNATURE={sig_count}  STATS_BLEND={stat_count}")
    print(f"  5-star picks: {star5_count}   4-star picks: {star4_count}")

    # Write outputs
    report_txt = os.path.join(ROOT, 'live_preds.txt')
    report_md  = os.path.join(ROOT, 'live_preds.md')
    report_csv = os.path.join(ROOT, 'predictions.csv')

    report = format_report(predictions)

    with open(report_txt, 'w', encoding='utf-8') as f:
        f.write(report)
    with open(report_md, 'w', encoding='utf-8') as f:
        f.write("```\n" + report + "\n```")
    write_csv(predictions, report_csv)

    print(f"\nOutput written to:")
    print(f"  {report_txt}")
    print(f"  {report_csv}")
    print()
    # Write report to stdout safely (handles Windows console encoding)
    sys.stdout.buffer.write((report + '\n').encode('utf-8', errors='replace'))


if __name__ == "__main__":
    main()
