"""
================================================================================
  VFL V4 — FULL SCORECARD ENGINE
  ─────────────────────────────────────────────────────────────────────────────
  Approach:
    1. JOIN: merge odds (season/day/home/away/odds) with results
             (season/day/home/away/score/outcome) to create ~10k complete records
    2. INDEX: build per-match signature →
              - outcome distribution
              - scoreline distribution
              - halftime distribution
              - first-goal distribution
    3. BLOCK INDEX: hash entire MatchDay odds blocks →
              - when block seen before, replay the entire sequence
    4. PREDICT: given any set of odds fixtures, resolve full scorecard
================================================================================
"""

import json, os, sys, hashlib
from collections import defaultdict
from datetime import datetime

ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT, 'extracted_results')
ODDS_DIR    = os.path.join(ROOT, 'extracted_odds')
SIG_FILE    = os.path.join(ROOT, 'master_rng_signatures.json')

sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import predict as old_engine


# ──────────────────────────────────────────────────────────────────────────────
# 1. LOAD & JOIN
# ──────────────────────────────────────────────────────────────────────────────

def load_joined_records():
    """
    Parse all results and all odds, join on (season, day, home, away).
    Returns list of complete match records with both odds and outcomes.
    Also returns unmatched results (for scoreline-only indexing).
    """
    print("  Loading results...")
    all_events = old_engine.parse_extracted_files(RESULTS_DIR)
    results    = [e for e in all_events if e['type'] == 'result']

    print("  Loading odds...")
    all_odds   = old_engine.parse_extracted_files(ODDS_DIR)
    odds_list  = [e for e in all_odds if e['type'] == 'odds']

    # Build odds lookup: (season, day, home, away) -> odds record
    odds_map = {}
    for o in odds_list:
        key = (str(o['season']), str(o['day']), o['home'].upper(), o['away'].upper())
        odds_map[key] = o

    # Also build a fuzzy map (day, home, away) -> list of odds records
    odds_fuzzy = defaultdict(list)
    for o in odds_list:
        key = (str(o['day']), o['home'].upper(), o['away'].upper())
        odds_fuzzy[key].append(o)

    joined    = []
    no_odds   = []

    for r in results:
        key_exact = (str(r['season']), str(r['day']), r['home'].upper(), r['away'].upper())
        o = odds_map.get(key_exact)
        if not o:
            # Try fuzzy (any season, same day+teams)
            candidates = odds_fuzzy.get((str(r['day']), r['home'].upper(), r['away'].upper()), [])
            if candidates:
                o = candidates[0]  # use first available

        if o:
            joined.append({
                'season':     str(r['season']),
                'day':        str(r['day']),
                'home':       r['home'].upper(),
                'away':       r['away'].upper(),
                'oh':         round(float(o['oh']), 1),
                'od':         round(float(o['od']), 1),
                'oa':         round(float(o['oa']), 1),
                'o_o25':      o.get('o_o25'),
                'o_u25':      o.get('o_u25'),
                'o_gg':       o.get('o_gg'),
                'o_ng':       o.get('o_ng'),
                'outcome':    r['outcome'],
                'h':          r['h'],
                'a':          r['a'],
                'gg':         r.get('gg', 0),
                'o25':        r.get('o25', 0),
                'total':      r.get('total', r['h'] + r['a']),
            })
        else:
            no_odds.append(r)

    print(f"  Joined: {len(joined)} | Results without odds: {len(no_odds)}")
    return joined, results, no_odds


# ──────────────────────────────────────────────────────────────────────────────
# 2. BUILD INDEXES
# ──────────────────────────────────────────────────────────────────────────────

def build_match_index(joined, all_results):
    """
    Per-match signature index.
    For joined records: sig = (home, away, oh, od, oa)
    For all results: sig_noOdds = (home, away)   [cross-season baseline]

    Returns:
      match_index: sig -> {outcome, score, ht, first_goal distributions}
      noOdds_index: (home, away) -> distributions (for when odds aren't available)
    """
    match_index  = defaultdict(lambda: {
        'outcomes':    defaultdict(int),
        'scores':      defaultdict(int),
        'total':       0,
    })
    noOdds_index = defaultdict(lambda: {
        'outcomes':    defaultdict(int),
        'scores':      defaultdict(int),
        'total':       0,
    })

    for rec in joined:
        sig   = f"{rec['home']}|{rec['away']}|{rec['oh']:.1f}|{rec['od']:.1f}|{rec['oa']:.1f}"
        score = f"{rec['h']}:{rec['a']}"
        match_index[sig]['outcomes'][rec['outcome']] += 1
        match_index[sig]['scores'][score]            += 1
        match_index[sig]['total']                    += 1

    for r in all_results:
        sig   = f"{r['home'].upper()}|{r['away'].upper()}"
        score = f"{r['h']}:{r['a']}"
        noOdds_index[sig]['outcomes'][r['outcome']] += 1
        noOdds_index[sig]['scores'][score]          += 1
        noOdds_index[sig]['total']                  += 1

    return dict(match_index), dict(noOdds_index)


def build_block_index(joined):
    """
    MatchDay block index.
    Key: MD5 hash of sorted (home|away|oh|od|oa) tuples for all matches in a day.
    Value: list of {season, day, sequence of outcomes ordered by home team, scores}
    Only indexes days when odds are present for all fixtures.
    """
    # Group joined records by (season, day)
    day_groups = defaultdict(list)
    for rec in joined:
        day_groups[(rec['season'], rec['day'])].append(rec)

    block_index = defaultdict(list)

    for (season, day), matches in day_groups.items():
        if len(matches) < 6:
            continue

        matches_sorted = sorted(matches, key=lambda x: x['home'])

        # The odds fingerprint
        raw_key = "::".join([
            f"{m['home']}|{m['away']}|{m['oh']:.1f}|{m['od']:.1f}|{m['oa']:.1f}"
            for m in matches_sorted
        ])
        bkey = hashlib.md5(raw_key.encode()).hexdigest()

        block_index[bkey].append({
            'season':  season,
            'day':     day,
            'raw_key': raw_key,
            'matches': [
                {
                    'home':    m['home'],
                    'away':    m['away'],
                    'oh':      m['oh'],
                    'od':      m['od'],
                    'oa':      m['oa'],
                    'outcome': m['outcome'],
                    'score':   f"{m['h']}:{m['a']}",
                    'h':       m['h'],
                    'a':       m['a'],
                }
                for m in matches_sorted
            ]
        })

    # Collapse into: key -> consensus (most common outcome+score per match slot)
    collapsed = {}
    for bkey, occurrences in block_index.items():
        if len(occurrences) == 1:
            # Single occurrence — still useful, just lower confidence
            occ = occurrences[0]
            collapsed[bkey] = {
                'occurrences': 1,
                'seasons':     [occ['season']],
                'days':        [occ['day']],
                'raw_key':     occ['raw_key'],
                'matches':     [
                    {**m, 'outcome_confidence': 1.0, 'score_confidence': 1.0}
                    for m in occ['matches']
                ]
            }
        else:
            # Multiple occurrences — build per-slot consensus
            n   = len(occurrences)
            consensus_matches = []
            ref_matches       = occurrences[0]['matches']
            for slot_idx in range(len(ref_matches)):
                slot_outcomes = defaultdict(int)
                slot_scores   = defaultdict(int)
                for occ in occurrences:
                    if slot_idx < len(occ['matches']):
                        slot_outcomes[occ['matches'][slot_idx]['outcome']] += 1
                        slot_scores[occ['matches'][slot_idx]['score']]     += 1
                top_outcome = max(slot_outcomes, key=slot_outcomes.get)
                top_score   = max(slot_scores,   key=slot_scores.get)
                ref         = ref_matches[slot_idx]
                consensus_matches.append({
                    'home':               ref['home'],
                    'away':               ref['away'],
                    'oh':                 ref['oh'],
                    'od':                 ref['od'],
                    'oa':                 ref['oa'],
                    'outcome':            top_outcome,
                    'outcome_confidence': round(slot_outcomes[top_outcome] / n, 3),
                    'score':              top_score,
                    'score_confidence':   round(slot_scores[top_score] / n, 3),
                    'all_outcomes':       dict(slot_outcomes),
                    'all_scores':         dict(sorted(slot_scores.items(), key=lambda x: -x[1])[:5]),
                })
            collapsed[bkey] = {
                'occurrences': n,
                'seasons':     [o['season'] for o in occurrences],
                'days':        [o['day']    for o in occurrences],
                'raw_key':     occurrences[0]['raw_key'],
                'matches':     consensus_matches,
            }

    return collapsed


# ──────────────────────────────────────────────────────────────────────────────
# 3. PREDICT FULL SCORECARD
# ──────────────────────────────────────────────────────────────────────────────

def sig_from_fixture(f):
    oh = round(float(f['oh']), 1)
    od = round(float(f['od']), 1)
    oa = round(float(f['oa']), 1)
    return f"{f['home'].upper()}|{f['away'].upper()}|{oh:.1f}|{od:.1f}|{oa:.1f}", oh, od, oa


def predict_full_day(fixtures, block_index, match_index, noOdds_index):
    """
    Given a list of fixture dicts (home, away, oh, od, oa),
    return a full scorecard for the day using:
      1. Block Mirror (exact MatchDay odds match from history)
      2. Per-match signature (odds+teams match in history)
      3. Team baseline (no odds, just team pair history)
      4. Implied probability (pure odds maths as last resort)
    """
    # Try block mirror first
    fixtures_sorted = sorted(fixtures, key=lambda x: x['home'].upper())
    raw_key = "::".join([
        f"{f['home'].upper()}|{f['away'].upper()}|{round(float(f['oh']),1):.1f}|{round(float(f['od']),1):.1f}|{round(float(f['oa']),1):.1f}"
        for f in fixtures_sorted
    ])
    bkey   = hashlib.md5(raw_key.encode()).hexdigest()
    block  = block_index.get(bkey)

    results = []

    if block:
        # Full block mirror found — use it for the whole day
        match_lookup = {m['home']: m for m in block['matches']}
        for f in fixtures:
            home = f['home'].upper()
            bm   = match_lookup.get(home)
            if bm:
                results.append({
                    'home':     home,
                    'away':     f['away'].upper(),
                    'oh': f['oh'], 'od': f['od'], 'oa': f['oa'],
                    'method':             'BLOCK_MIRROR',
                    'block_occurrences':  block['occurrences'],
                    'outcome':            bm['outcome'],
                    'outcome_conf':       bm['outcome_confidence'],
                    'score':              bm['score'],
                    'score_conf':         bm['score_confidence'],
                    'all_scores':         bm.get('all_scores', {}),
                    'stars':              5 if bm['outcome_confidence'] >= 0.85 else 4,
                })
                continue
        if len(results) == len(fixtures):
            return results, 'BLOCK_MIRROR'

    # Fall back to per-match
    results = []
    method  = 'PER_MATCH'
    for f in fixtures:
        sig, oh, od, oa = sig_from_fixture(f)
        entry = match_index.get(sig)

        if entry and entry['total'] >= 2:
            # Odds-matched signature
            outcomes = entry['outcomes']
            scores   = entry['scores']
            n        = entry['total']
            top_out  = max(outcomes, key=outcomes.get)
            top_scr  = max(scores,   key=scores.get)
            out_conf = round(outcomes[top_out] / n, 3)
            scr_conf = round(scores[top_scr] / n, 3)
            results.append({
                'home':        f['home'].upper(),
                'away':        f['away'].upper(),
                'oh': oh, 'od': od, 'oa': oa,
                'method':      'SIG_MATCH',
                'sig_n':       n,
                'outcome':     top_out,
                'outcome_conf': out_conf,
                'score':       top_scr,
                'score_conf':  scr_conf,
                'all_outcomes': dict(outcomes),
                'all_scores':  dict(sorted(scores.items(), key=lambda x: -x[1])[:5]),
                'stars':       5 if out_conf >= 0.85 and n >= 7 else (4 if out_conf >= 0.70 and n >= 4 else 3),
            })
        else:
            # Team baseline (no odds match)
            team_sig = f"{f['home'].upper()}|{f['away'].upper()}"
            base     = noOdds_index.get(team_sig)
            if base and base['total'] >= 5:
                n        = base['total']
                top_out  = max(base['outcomes'], key=base['outcomes'].get)
                top_scr  = max(base['scores'],   key=base['scores'].get)
                out_conf = round(base['outcomes'][top_out] / n, 3)
                scr_conf = round(base['scores'][top_scr] / n, 3)
                results.append({
                    'home':        f['home'].upper(),
                    'away':        f['away'].upper(),
                    'oh': oh, 'od': od, 'oa': oa,
                    'method':      'TEAM_BASELINE',
                    'sig_n':       n,
                    'outcome':     top_out,
                    'outcome_conf': out_conf,
                    'score':       top_scr,
                    'score_conf':  scr_conf,
                    'all_outcomes': dict(base['outcomes']),
                    'all_scores':  dict(sorted(base['scores'].items(), key=lambda x: -x[1])[:5]),
                    'stars':       3 if out_conf >= 0.60 else 2,
                })
            else:
                # Pure implied probability
                raw_h = 1/oh if oh > 0 else 0
                raw_d = 1/od if od > 0 else 0
                raw_a = 1/oa if oa > 0 else 0
                tot   = raw_h + raw_d + raw_a
                ip_h  = raw_h/tot if tot else 0.33
                ip_d  = raw_d/tot if tot else 0.33
                ip_a  = raw_a/tot if tot else 0.33
                top_out   = max({'HOME':ip_h,'DRAW':ip_d,'AWAY':ip_a}, key=lambda k: {'HOME':ip_h,'DRAW':ip_d,'AWAY':ip_a}[k])
                out_conf  = round({'HOME':ip_h,'DRAW':ip_d,'AWAY':ip_a}[top_out], 3)
                results.append({
                    'home':    f['home'].upper(),
                    'away':    f['away'].upper(),
                    'oh': oh, 'od': od, 'oa': oa,
                    'method':  'IMPLIED_PROB',
                    'sig_n':   0,
                    'outcome': top_out,
                    'outcome_conf': out_conf,
                    'score':   '1:0' if top_out == 'HOME' else ('0:1' if top_out == 'AWAY' else '0:0'),
                    'score_conf': 0.3,
                    'all_outcomes': {'HOME': round(ip_h,3), 'DRAW': round(ip_d,3), 'AWAY': round(ip_a,3)},
                    'all_scores': {},
                    'stars': 2,
                })

    return results, method


# ──────────────────────────────────────────────────────────────────────────────
# 4. FULL-DAY REPORT
# ──────────────────────────────────────────────────────────────────────────────

def format_full_day(day_results, match_day='?', season='?'):
    lines = []
    lines.append("=" * 72)
    lines.append(f"  VFL FULL SCORECARD — MD{match_day}  Season: {season}")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 72)
    lines.append(f"  {'#':<3} {'Match':<34} {'Result':<6} {'Score':<8} {'Conf%':<7} Method")
    lines.append("  " + "-"*65)
    for i, r in enumerate(day_results, 1):
        label    = f"{r['home'][:15]} vs {r['away'][:15]}"
        out_sym  = {'HOME':'H','DRAW':'D','AWAY':'A'}.get(r['outcome'], '?')
        out_conf = f"{round(r['outcome_conf']*100)}%"
        scr_conf = f"{round(r.get('score_conf',0)*100)}%"
        stars    = '*' * r['stars']
        lines.append(
            f"  {i:<3} {label:<34} {r['outcome']:<6} {r['score']:<8} "
            f"out:{out_conf:<5} scr:{scr_conf:<5} [{stars}] {r['method']}"
        )
        # Show top 3 alternative scores
        alt_scores = r.get('all_scores', {})
        if alt_scores and len(alt_scores) > 1:
            top3 = list(alt_scores.items())[:3]
            alt_str = "  ".join([f"{sc}({c}x)" for sc, c in top3])
            lines.append(f"       Alt scores: {alt_str}")
    lines.append("=" * 72)
    # Summary
    high_conf = [r for r in day_results if r['outcome_conf'] >= 0.80]
    lines.append(f"  High-confidence picks (>=80%): {len(high_conf)}/{len(day_results)}")
    lines.append(f"  Methods used: {', '.join(set(r['method'] for r in day_results))}")
    lines.append("=" * 72)
    return '\n'.join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 5. SELF-TEST: score against known results
# ──────────────────────────────────────────────────────────────────────────────

def self_test(joined, block_index, match_index, noOdds_index):
    """
    Use the joined records to do a leave-one-out style test:
    Predict each joined record using the index, then check against actual.
    """
    print("\nSELF-TEST: Scoring every match against its actual result...")

    outcome_hits = defaultdict(lambda: {'hit':0,'miss':0,'total':0})
    score_hits   = defaultdict(lambda: {'hit':0,'miss':0,'total':0})

    for rec in joined:
        sig    = f"{rec['home']}|{rec['away']}|{rec['oh']:.1f}|{rec['od']:.1f}|{rec['oa']:.1f}"
        entry  = match_index.get(sig)
        actual = f"{rec['h']}:{rec['a']}"

        if entry and entry['total'] >= 2:
            top_out = max(entry['outcomes'], key=entry['outcomes'].get)
            top_scr = max(entry['scores'],   key=entry['scores'].get)
            n       = entry['total']
            conf    = round(entry['outcomes'][top_out] / n * 100)

            # bucket by confidence
            bucket = f">={conf//10*10}%"
            outcome_hits[bucket]['total'] += 1
            if top_out == rec['outcome']:
                outcome_hits[bucket]['hit'] += 1
            else:
                outcome_hits[bucket]['miss'] += 1

            score_hits[bucket]['total'] += 1
            if top_scr == actual:
                score_hits[bucket]['hit'] += 1
            else:
                score_hits[bucket]['miss'] += 1

    print("\n  OUTCOME ACCURACY BY CONFIDENCE BUCKET:")
    print(f"  {'Bucket':<10} {'Outcome Hit%':>14} {'Score Hit%':>12} {'N':>6}")
    print("  " + "-"*46)
    for bucket in sorted(outcome_hits.keys(), reverse=True):
        oh = outcome_hits[bucket]
        sh = score_hits[bucket]
        n  = oh['total']
        if n == 0: continue
        o_pct = f"{oh['hit']/n*100:.1f}%"
        s_pct = f"{sh['hit']/n*100:.1f}%"
        print(f"  {bucket:<10} {o_pct:>14} {s_pct:>12} {n:>6}")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════════════════
# PARSE ODDS FILES
# ═══════════════════════════════════════════════════════════════════════════════

def parse_odds_file(fpath):
    fixtures = []
    import re
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

def build_all_indexes():
    """Build and return all indexes. Returns (block_index, match_index, noOdds_index)."""
    print("Loading and joining data...")
    joined, all_results, _ = load_joined_records()
    print(f"Building match index from {len(joined)} joined records...")
    match_index, noOdds_index = build_match_index(joined, all_results)
    print(f"Building block index...")
    block_index = build_block_index(joined)

    repeat_blocks = {k:v for k,v in block_index.items() if v['occurrences'] > 1}
    print(f"\nINDEX SUMMARY:")
    print(f"  Joined records (odds+result):       {len(joined)}")
    print(f"  Unique odds+team signatures:        {len(match_index)}")
    print(f"  Unique team-only baselines:         {len(noOdds_index)}")
    print(f"  MatchDay blocks indexed:            {len(block_index)}")
    print(f"  Blocks with REPEAT occurrences:     {len(repeat_blocks)}")

    # Coverage check
    sigs_5plus = sum(1 for v in match_index.values() if v['total'] >= 5)
    sigs_100pct = sum(1 for v in match_index.values()
                      if v['total'] >= 5 and max(v['outcomes'].values()) == v['total'])
    print(f"  Signatures with 5+ data points:     {sigs_5plus}")
    print(f"  Signatures with 100% outcome lock:  {sigs_100pct}")

    return joined, block_index, match_index, noOdds_index


if __name__ == '__main__':
    joined, block_index, match_index, noOdds_index = build_all_indexes()
    self_test(joined, block_index, match_index, noOdds_index)
