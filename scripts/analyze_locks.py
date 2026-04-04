"""
V4 DEEP ANALYSIS
- Who are the 71 signatures with 100% outcome lock?
- What is their minimum sample size?
- How many are in the current pending test files?
- Can we improve score prediction by looking at SCORE DISTRIBUTION within those 71?
"""
import sys, os
from collections import defaultdict

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import predict_v4 as v4

def main():
    print("V4 DEEP ANALYSIS: FINDING THE LOCKS")
    print("=" * 72)

    joined, block_index, match_index, noOdds_index = v4.build_all_indexes()

    # ── 1. The 100% Lock Signatures ──────────────────────────────────────────
    locks = {sig: data for sig, data in match_index.items()
             if data['total'] >= 5 and max(data['outcomes'].values()) == data['total']}

    print(f"\n{'='*72}")
    print(f"  100% OUTCOME LOCK SIGNATURES ({len(locks)} total)")
    print(f"  These are fixtures where in ALL historical occurrences (min 5), the same result always happens")
    print(f"{'='*72}")
    print(f"  {'Signature':<48} {'N':>4} {'Outcome':<6} {'Top Score':<8} {'Score%'}")
    print("  " + "-"*70)

    for sig, data in sorted(locks.items(), key=lambda x: -x[1]['total']):
        parts   = sig.split('|')
        home, away = parts[0], parts[1]
        odds_str   = f"{parts[2]}/{parts[3]}/{parts[4]}"
        outcome    = max(data['outcomes'], key=data['outcomes'].get)
        top_score  = max(data['scores'], key=data['scores'].get)
        top_scr_n  = data['scores'][top_score]
        scr_pct    = f"{top_scr_n}/{data['total']} = {top_scr_n/data['total']*100:.0f}%"
        print(f"  {home[:12]} vs {away[:12]} @ {odds_str}  {data['total']:>4}x  {outcome:<6} {top_score:<8} {scr_pct}")

    # ── 2. Distribution within locks (for score prediction) ──────────────────
    print(f"\n{'='*72}")
    print("  SCORE DISTRIBUTION WITHIN LOCKS:")
    score_pct_dist = defaultdict(int)
    for sig, data in locks.items():
        top_scr   = max(data['scores'], key=data['scores'].get)
        top_scr_n = data['scores'][top_scr]
        p = round(top_scr_n / data['total'] * 100)
        if   p == 100: score_pct_dist['100%'] += 1
        elif p >= 80:  score_pct_dist['>=80%'] += 1
        elif p >= 60:  score_pct_dist['>=60%'] += 1
        elif p >= 50:  score_pct_dist['>=50%'] += 1
        else:          score_pct_dist['<50%'] += 1
    for k in ['100%', '>=80%', '>=60%', '>=50%', '<50%']:
        print(f"  Score lock rate {k}: {score_pct_dist.get(k,0)} signatures")

    # ── 3. How many 100% outcome locks appear in pending test files? ──────────
    import csv, glob
    PENDING_DIR = os.path.join(ROOT, 'pending_tests')
    pending_csvs = [f for f in os.listdir(PENDING_DIR) if f.endswith('.csv') and not f.startswith('SCORED')]

    lock_sigs = set(locks.keys())
    found_in_pending = 0
    for fname in pending_csvs:
        path = os.path.join(PENDING_DIR, fname)
        with open(path, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                sig = f"{row['home']}|{row['away']}|{row.get('oh','0')}|{row.get('od','0')}|{row.get('oa','0')}"
                # round odds
                try:
                    parts = sig.split('|')
                    sig_r = f"{parts[0]}|{parts[1]}|{float(parts[2]):.1f}|{float(parts[3]):.1f}|{float(parts[4]):.1f}"
                    if sig_r in lock_sigs:
                        found_in_pending += 1
                except:
                    pass
    print(f"\n  Lock signatures appearing in pending test files: {found_in_pending}")

    # ── 4. Block mirror analysis ──────────────────────────────────────────────
    repeat_blocks = {k: v for k, v in block_index.items() if v['occurrences'] > 1}
    print(f"\n{'='*72}")
    print(f"  BLOCK MIRROR ANALYSIS ({len(repeat_blocks)} repeating blocks)")
    perfect_blocks = sum(1 for v in repeat_blocks.values()
                         if all(m['outcome_confidence'] == 1.0 for m in v['matches']))
    print(f"  Blocks where ALL matches have 100% outcome consistency: {perfect_blocks}")

    for bkey, bdata in sorted(repeat_blocks.items(), key=lambda x: -x[1]['occurrences'])[:10]:
        n_matches = len(bdata['matches'])
        avg_conf  = sum(m['outcome_confidence'] for m in bdata['matches']) / n_matches
        print(f"    {bdata['occurrences']}x occurrences | {n_matches} matches/day | avg outcome conf: {avg_conf:.1%}")
        for m in bdata['matches']:
            print(f"      {m['home'][:14]} vs {m['away'][:14]}  => {m['outcome']} ({m['outcome_confidence']:.0%})  "
                  f"score: {m['score']} ({m['score_confidence']:.0%})")
        print()

    print("=" * 72)

if __name__ == '__main__':
    main()
