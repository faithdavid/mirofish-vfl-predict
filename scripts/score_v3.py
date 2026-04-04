"""
VFL v3 AUTO-SCORER
Runs v3 predictions on ALL odds files, then immediately scores against
all known results. Outputs a comprehensive accuracy report.
"""
import csv
import os
import sys
import io
import json
import re
from collections import defaultdict
from datetime import datetime




ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ODDS_DIR    = os.path.join(ROOT, 'extracted_odds')
RESULTS_DIR = os.path.join(ROOT, 'extracted_results')

sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import predict_v3 as v3


def main():
    print("\nVFL v3 AUTO-SCORER -- EVALUATE EVERYTHING")
    print("=" * 72)

    # Build the v3 database
    print("\n[1] Loading results database...")
    result_events = v3.parse_all_results(RESULTS_DIR)
    db = v3.build_season_aware_db(result_events)
    print(f"  {len(result_events)} results loaded")

    print("\n[2] Loading signature database...")
    sig_db = v3.load_signature_db()
    print(f"  {len(sig_db)} signatures")

    # Build results lookup for scoring
    exact_results = {}
    fuzzy_results = defaultdict(list)
    for r in result_events:
        season = str(r.get('season', ''))
        day    = str(r.get('day', ''))
        home   = r['home'].upper()
        away   = r['away'].upper()
        exact_results[(season, day, home, away)] = r
        fuzzy_results[(day, home, away)].append(r)

    # Process ALL odds files
    print("\n[3] Processing all odds files...")
    odds_files = sorted([os.path.join(ODDS_DIR, f) for f in os.listdir(ODDS_DIR) if f.endswith('.txt')])
    print(f"  {len(odds_files)} odds files found")

    all_preds = []
    for fp in odds_files:
        fixtures = v3.parse_odds_file(fp)
        for fix in fixtures:
            p = v3.predict_v3(fix, sig_db, db)
            if p:
                p['_source'] = os.path.basename(fp)
                all_preds.append(p)

    print(f"  {len(all_preds)} total predictions generated")

    # Score each prediction against known results
    print("\n[4] Scoring against known results...")
    scored = []
    for p in all_preds:
        season = str(p.get('season', ''))
        day    = str(p.get('day', ''))
        home   = p['home'].upper()
        away   = p['away'].upper()

        # Find actual result - prefer exact season match
        actual = exact_results.get((season, day, home, away))
        if not actual:
            # Try fuzzy (any season, same day+teams)
            candidates = fuzzy_results.get((day, home, away), [])
            if candidates:
                actual = candidates[-1]

        if actual:
            hit_result = (p['outcome'] == actual['outcome'])
            hit_goals  = (
                (p['goals'] == 'OVER 2.5' and actual['o25'] == 1) or
                (p['goals'] == 'UNDER 2.5' and actual['o25'] == 0)
            )
            hit_gg = (
                (p['gg'] == 'GG' and actual['gg'] == 1) or
                (p['gg'] == 'NG' and actual['gg'] == 0)
            )
            season_match = str(actual.get('season', '')) == season
            scored.append({
                'pred': p, 'actual': actual,
                'hit_result': hit_result,
                'hit_goals': hit_goals,
                'hit_gg': hit_gg,
                'season_match': season_match,
            })

    print(f"  {len(scored)} predictions matched to results\n")

    if not scored:
        print("No predictions could be matched to results.")
        return

    # ── OVERALL RESULTS ────────────────────────────────────────────────
    print("=" * 72)
    print("  OVERALL RESULTS")
    print("=" * 72)

    total = len(scored)
    hits  = sum(1 for s in scored if s['hit_result'])
    ghits = sum(1 for s in scored if s['hit_goals'])
    gghits= sum(1 for s in scored if s['hit_gg'])

    print(f"  All picks:     Result {hits}/{total} = {hits/total*100:.1f}%   "
          f"Goals {ghits}/{total} = {ghits/total*100:.1f}%   "
          f"GG {gghits}/{total} = {gghits/total*100:.1f}%")

    # ── BY STAR LEVEL ──────────────────────────────────────────────────
    print(f"\n  BY STAR LEVEL:")
    for star in [5, 4, 3, 2, 1]:
        bucket = [s for s in scored if s['pred']['stars'] == star]
        if not bucket:
            continue
        h = sum(1 for s in bucket if s['hit_result'])
        g = sum(1 for s in bucket if s['hit_goals'])
        gg= sum(1 for s in bucket if s['hit_gg'])
        n = len(bucket)
        print(f"    {'*'*star:<5}  Result: {h}/{n} = {h/n*100:.1f}%   "
              f"Goals: {g}/{n} = {g/n*100:.1f}%   "
              f"GG: {gg}/{n} = {gg/n*100:.1f}%")

    # ── BY METHOD ──────────────────────────────────────────────────────
    print(f"\n  BY METHOD:")
    methods = set(s['pred']['method'] for s in scored)
    for method in sorted(methods):
        bucket = [s for s in scored if s['pred']['method'] == method]
        h = sum(1 for s in bucket if s['hit_result'])
        n = len(bucket)
        print(f"    {method:<15}  {h}/{n} = {h/n*100:.1f}%")

    # ── ONLY 4+ STAR, SAME SEASON ─────────────────────────────────────
    print(f"\n  4+ STARS, SAME SEASON ONLY:")
    high_same = [s for s in scored if s['pred']['stars'] >= 4 and s['season_match']]
    if high_same:
        h = sum(1 for s in high_same if s['hit_result'])
        g = sum(1 for s in high_same if s['hit_goals'])
        n = len(high_same)
        print(f"    Result: {h}/{n} = {h/n*100:.1f}%   Goals: {g}/{n} = {g/n*100:.1f}%")

    # ── ONLY 4+ STAR, DIFFERENT SEASON ────────────────────────────────
    print(f"\n  4+ STARS, DIFFERENT SEASON:")
    high_diff = [s for s in scored if s['pred']['stars'] >= 4 and not s['season_match']]
    if high_diff:
        h = sum(1 for s in high_diff if s['hit_result'])
        n = len(high_diff)
        print(f"    Result: {h}/{n} = {h/n*100:.1f}%")

    # ── BY CONSENSUS STRENGTH ─────────────────────────────────────────
    print(f"\n  BY CONSENSUS STRENGTH (day+team agreement across seasons):")
    for threshold in [90, 85, 80, 75, 70]:
        bucket = [s for s in scored if float(s['pred'].get('consensus_rate', 0)) >= threshold]
        if bucket:
            h = sum(1 for s in bucket if s['hit_result'])
            n = len(bucket)
            print(f"    Consensus >= {threshold}%: {h}/{n} = {h/n*100:.1f}%")

    # ── MISSES ON 5-STAR (excluding EXACT_MATCH) ──────────────────────
    print(f"\n  5-STAR MISSES (excluding exact match):")
    five_star_miss = [s for s in scored 
                      if s['pred']['stars'] == 5 
                      and not s['hit_result']
                      and s['pred']['method'] != 'EXACT_MATCH']
    if five_star_miss:
        for s in five_star_miss[:20]:
            p = s['pred']
            a = s['actual']
            print(f"    MD{p['day']}: {p['home'][:14]} vs {p['away'][:14]}  "
                  f"pred:{p['outcome']} actual:{a['outcome']} ({a['h']}:{a['a']})  "
                  f"{p['method']} con:{p.get('consensus_rate',0)}%/{p.get('consensus_n',0)}")
    else:
        print("    None!")

    # ── SAVE FULL REPORT ──────────────────────────────────────────────
    report_path = os.path.join(ROOT, 'v3_accuracy_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"VFL v3 Accuracy Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Total scored: {total}\n")
        f.write(f"Overall result accuracy: {hits}/{total} = {hits/total*100:.1f}%\n\n")
        for star in [5, 4, 3, 2, 1]:
            bucket = [s for s in scored if s['pred']['stars'] == star]
            if bucket:
                h = sum(1 for s in bucket if s['hit_result'])
                n = len(bucket)
                f.write(f"{'*'*star}: {h}/{n} = {h/n*100:.1f}%\n")

    print(f"\n  Full report saved to: {report_path}")
    print("=" * 72)


if __name__ == '__main__':
    main()
