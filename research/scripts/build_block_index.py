"""
================================================================================
  VFL MATCHDAY BLOCK INDEXER
  ─────────────────────────────────────────────────────────────────────────────
  Builds two indexes:

  1. matchday_blocks.json
     Key:   A sorted tuple of (home, away, oh, od, oa) for ALL matches in a day
     Value: The exact outcome sequence + most common scorelines for that block

  2. scoreline_modes.json
     Key:   (home, away, oh, od, oa)  -- per-match signature
     Value: {scoreline -> count} distribution sorted by frequency

  This enables V4 to:
    a) Find an identical historical MatchDay block → instant full scorecard
    b) Fall back to per-match scoreline modes for individual score predictions
================================================================================
"""

import json
import os
import sys
import hashlib
from collections import defaultdict

ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT, 'extracted_results')
OUT_BLOCKS  = os.path.join(ROOT, 'matchday_blocks.json')
OUT_SCORES  = os.path.join(ROOT, 'scoreline_modes.json')

sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import predict as old_engine   # reuse parse_extracted_files


def round_odd(o):
    """Round odds to 1dp for fuzzy matching."""
    try:
        return round(float(o), 1)
    except:
        return 0.0


def block_key(matches):
    """
    Create a deterministic key for a MatchDay block from its odds.
    Sorted by home team so ordering doesn't matter.
    """
    parts = sorted([
        f"{m['home'].upper()}|{m['away'].upper()}|{round_odd(m.get('oh',0))}|{round_odd(m.get('od',0))}|{round_odd(m.get('oa',0))}"
        for m in matches
    ])
    return "::".join(parts)


def block_key_hash(matches):
    """MD5 hash of the block key — shorter storage key."""
    return hashlib.md5(block_key(matches).encode()).hexdigest()


def main():
    print("MATCHDAY BLOCK INDEXER")
    print("=" * 60)

    print("\nLoading all results...")
    all_events = old_engine.parse_extracted_files(RESULTS_DIR)
    results    = [e for e in all_events if e['type'] == 'result']
    print(f"  {len(results)} results loaded")

    # Group results by (season, day)
    day_groups = defaultdict(list)
    for r in results:
        key = (str(r.get('season', '')), str(r.get('day', '')))
        day_groups[key].append(r)
    print(f"  {len(day_groups)} (season, day) groups")

    # ── INDEX 1: MatchDay Blocks ─────────────────────────────────────────────
    # key  = block hash
    # value = list of {season, day, matches: [{home, away, oh, od, oa, outcome, h, a, firstGoal, halfTime}]}
    block_index = defaultdict(list)

    for (season, day), matches in day_groups.items():
        # Only index days with odds data
        valid = [m for m in matches if m.get('oh') and m.get('oh', 0) > 0]
        if len(valid) < 6:   # need at least 6 matches with odds
            continue

        bkey = block_key_hash(valid)
        block_index[bkey].append({
            'season': season,
            'day':    day,
            'raw_key': block_key(valid),
            'matches': [
                {
                    'home':      m['home'].upper(),
                    'away':      m['away'].upper(),
                    'oh':        round_odd(m.get('oh', 0)),
                    'od':        round_odd(m.get('od', 0)),
                    'oa':        round_odd(m.get('oa', 0)),
                    'outcome':   m['outcome'],
                    'h':         m['h'],
                    'a':         m['a'],
                    'first_goal': m.get('firstGoal', ''),
                    'half':      m.get('halfTime', ''),
                }
                for m in valid
            ]
        })

    # Keep only blocks that appear more than once (confirmed repeats)
    repeat_blocks = {k: v for k, v in block_index.items() if len(v) > 1}
    all_blocks    = dict(block_index)

    print(f"\n  Total unique odds blocks: {len(all_blocks)}")
    print(f"  Blocks that REPEAT (exact odds match): {len(repeat_blocks)}")

    # Save
    with open(OUT_BLOCKS, 'w', encoding='utf-8') as f:
        json.dump(all_blocks, f, separators=(',', ':'))
    print(f"  Saved all blocks -> {OUT_BLOCKS}")

    # ── INDEX 2: Per-Match Scoreline Modes ──────────────────────────────────
    # For each (home, away, oh, od, oa) signature, what are the most common
    # scorelines historically?
    score_index = defaultdict(lambda: defaultdict(int))  # sig -> score -> count
    ht_index    = defaultdict(lambda: defaultdict(int))  # sig -> halftime -> count
    fg_index    = defaultdict(lambda: defaultdict(int))  # sig -> firstgoal -> count

    for r in results:
        if not r.get('oh'):
            continue
        sig   = f"{r['home'].upper()}|{r['away'].upper()}|{round_odd(r.get('oh',0))}|{round_odd(r.get('od',0))}|{round_odd(r.get('oa',0))}"
        score = f"{r['h']}:{r['a']}"
        ht    = str(r.get('halfTime', '?'))
        fg    = str(r.get('firstGoal', '?'))
        score_index[sig][score]  += 1
        ht_index[sig][ht]        += 1
        fg_index[sig][fg]        += 1

    # Convert to sorted lists and add stats
    scoreline_modes = {}
    for sig, scores in score_index.items():
        total = sum(scores.values())
        if total < 2:
            continue
        sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
        top_score, top_count = sorted_scores[0]
        top_ht    = max(ht_index[sig], key=ht_index[sig].get) if ht_index[sig] else '?'
        top_fg    = max(fg_index[sig], key=fg_index[sig].get) if fg_index[sig] else '?'
        scoreline_modes[sig] = {
            'total':      total,
            'top_score':  top_score,
            'top_pct':    round(top_count / total * 100, 1),
            'top_ht':     top_ht,
            'top_ht_pct': round(ht_index[sig][top_ht] / total * 100, 1),
            'top_fg':     top_fg,
            'top_fg_pct': round(fg_index[sig][top_fg] / total * 100, 1),
            'all_scores': dict(sorted_scores[:10]),  # top 10
        }

    with open(OUT_SCORES, 'w', encoding='utf-8') as f:
        json.dump(scoreline_modes, f, separators=(',', ':'))
    print(f"  Saved scoreline modes -> {OUT_SCORES}")

    # ── SUMMARY STATS ─────────────────────────────────────────────────────────
    print("\n  SCORELINE PREDICTABILITY:")
    buckets = {'100%': 0, '>=80%': 0, '>=60%': 0, '>=50%': 0, '<50%': 0}
    for sig, data in scoreline_modes.items():
        if data['total'] >= 5:
            p = data['top_pct']
            if p == 100:   buckets['100%']  += 1
            elif p >= 80:  buckets['>=80%'] += 1
            elif p >= 60:  buckets['>=60%'] += 1
            elif p >= 50:  buckets['>=50%'] += 1
            else:          buckets['<50%']  += 1
    for k, v in buckets.items():
        print(f"    {k}: {v} signatures")

    # How many exact block repeats are IDENTICAL (same outcomes)?
    identical = 0
    partial   = 0
    for bkey, occurrences in repeat_blocks.items():
        # Compare outcome sequences across all occurrences
        seqs = [
            tuple(sorted([m['outcome'] for m in occ['matches']]))
            for occ in occurrences
        ]
        if len(set(seqs)) == 1:
            identical += 1
        else:
            partial   += 1

    print(f"\n  EXACT BLOCK REPEATS WITH IDENTICAL OUTCOMES: {identical}")
    print(f"  EXACT BLOCK REPEATS WITH DIFFERENT OUTCOMES: {partial}")
    print(f"  → Repeat rate consistency: "
          f"{identical/(identical+partial)*100:.1f}%" if (identical+partial) > 0 else "  N/A")

    print("\n" + "="*60)
    print("Indexing complete.")


if __name__ == '__main__':
    main()
