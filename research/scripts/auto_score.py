"""
================================================================================
  VFL AUTO-SCORER
  ─────────────────────────────────────────────────────────────────────────────
  Automatically cross-matches saved pending predictions against extracted
  results files. No manual input needed — it looks up the actual score from
  the results database and scores every prediction.

  Usage:
    python scripts/auto_score.py                    # score all pending tests
    python scripts/auto_score.py msport27           # score a specific test
    python scripts/auto_score.py --summary          # show all scored results

  Writes scored reports to:
    pending_tests/SCORED_<timestamp>_<source>.txt
================================================================================
"""

import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PENDING_DIR = os.path.join(ROOT, 'pending_tests')
RESULTS_DIR = os.path.join(ROOT, 'extracted_results')
SIG_FILE    = os.path.join(ROOT, 'master_rng_signatures.json')

sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import predict as engine


# ── LOAD ALL RESULTS INTO A LOOKUP MAP ────────────────────────────────────────

def load_all_results():
    """
    Parse every results file and build a lookup:
      (season, day, home_upper, away_upper) -> {h, a, outcome, total, gg, o25}
    Also index by (day, home, away) without season for fuzzy matching.
    """
    result_events = engine.parse_extracted_files(RESULTS_DIR)
    exact_map  = {}   # (season, day, home, away) -> result
    fuzzy_map  = defaultdict(list)  # (day, home, away) -> [results...]

    for r in result_events:
        if r['type'] != 'result':
            continue
        key_exact = (str(r['season']), str(r['day']), r['home'].upper(), r['away'].upper())
        key_fuzzy = (str(r['day']), r['home'].upper(), r['away'].upper())
        exact_map[key_exact] = r
        fuzzy_map[key_fuzzy].append(r)

    return exact_map, fuzzy_map


def lookup_result(pick, exact_map, fuzzy_map):
    """Try to find the actual result for a prediction pick."""
    day   = str(pick['day'])
    home  = pick['home'].upper()
    away  = pick['away'].upper()
    season = str(pick.get('season', ''))

    # Try exact match first
    r = exact_map.get((season, day, home, away))
    if r:
        return r

    # Fuzzy: same day + teams, any season
    candidates = fuzzy_map.get((day, home, away), [])
    if candidates:
        return candidates[-1]  # most recent match

    return None


# ── SCORE A SINGLE PENDING CSV ─────────────────────────────────────────────────

def score_pending_file(pending_csv_path, exact_map, fuzzy_map, filter_str=None):
    source = os.path.basename(pending_csv_path).replace('.csv', '')
    if filter_str and filter_str.lower() not in source.lower():
        return None

    picks = list(csv.DictReader(open(pending_csv_path, encoding='utf-8')))
    high_picks = [p for p in picks if int(p.get('stars', 0)) >= 4]

    if not high_picks:
        return None

    results_found = []
    for p in high_picks:
        r = lookup_result(p, exact_map, fuzzy_map)
        results_found.append({'pick': p, 'result': r})

    matched = [x for x in results_found if x['result']]
    no_data = [x for x in results_found if not x['result']]

    if not matched:
        return {
            'source': source, 'status': 'NO_RESULTS',
            'picks': len(high_picks), 'matched': 0,
            'hits': 0, 'misses': 0, 'accuracy': None,
            'details': results_found
        }

    # Score result prediction
    hits   = [x for x in matched if x['result']['outcome'] == x['pick']['outcome']]
    misses = [x for x in matched if x['result']['outcome'] != x['pick']['outcome']]

    # Score goals prediction
    goals_hits   = [x for x in matched if (
        (x['pick']['goals'] == 'OVER 2.5'  and x['result']['o25'] == 1) or
        (x['pick']['goals'] == 'UNDER 2.5' and x['result']['o25'] == 0)
    )]
    # Score GG/NG prediction
    gg_hits = [x for x in matched if (
        (x['pick']['gg'] == 'GG' and x['result']['gg'] == 1) or
        (x['pick']['gg'] == 'NG' and x['result']['gg'] == 0)
    )]

    accuracy     = len(hits) / len(matched) * 100
    goals_acc    = len(goals_hits) / len(matched) * 100
    gg_acc       = len(gg_hits) / len(matched) * 100

    return {
        'source':       source,
        'status':       'SCORED',
        'picks':        len(high_picks),
        'matched':      len(matched),
        'no_data':      len(no_data),
        'hits':         len(hits),
        'misses':       len(misses),
        'accuracy':     round(accuracy, 1),
        'goals_hits':   len(goals_hits),
        'goals_acc':    round(goals_acc, 1),
        'gg_hits':      len(gg_hits),
        'gg_acc':       round(gg_acc, 1),
        'details':      results_found
    }


def save_score_report(score, out_dir):
    if not score or score['status'] == 'NO_RESULTS':
        return None

    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
    fname = f"SCORED_{timestamp}_{score['source']}.txt"
    path  = os.path.join(out_dir, fname)

    def day_key(x):
        try: return int(x['pick']['day'])
        except: return 99

    lines = []
    lines.append("=" * 72)
    lines.append(f"  SCORED TEST: {score['source']}")
    lines.append(f"  Scored: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 72)
    lines.append(f"  High-confidence picks : {score['picks']}")
    lines.append(f"  Matched to results    : {score['matched']}")
    lines.append(f"  No result data found  : {score['no_data']}")
    lines.append("")
    lines.append(f"  RESULT  accuracy : {score['hits']}/{score['matched']} = {score['accuracy']}%")
    lines.append(f"  GOALS   accuracy : {score['goals_hits']}/{score['matched']} = {score['goals_acc']}%")
    lines.append(f"  GG/NG   accuracy : {score['gg_hits']}/{score['matched']} = {score['gg_acc']}%")
    lines.append("")

    # Stars breakdown
    for star_lvl in [5, 4]:
        star_picks = [x for x in score['details'] if x['result'] and int(x['pick']['stars']) == star_lvl]
        if not star_picks:
            continue
        star_hits = [x for x in star_picks if x['result']['outcome'] == x['pick']['outcome']]
        lines.append(f"  {'*'*star_lvl} picks: {len(star_hits)}/{len(star_picks)} = {len(star_hits)/len(star_picks)*100:.1f}%")

    lines.append("")
    lines.append("-" * 72)
    lines.append(f"  {'#':<3} {'Match':<32} {'Stars':<6} {'Pred':<5} {'Actual':<7} {'Score':<5} {'Goals Pred':<12} {'Goals Act':<10}")
    lines.append(f"  {'-'*3} {'-'*32} {'-'*6} {'-'*5} {'-'*7} {'-'*5} {'-'*12} {'-'*10}")

    for idx, x in enumerate(sorted(score['details'], key=day_key), 1):
        p = x['pick']
        r = x['result']
        pred    = p['outcome']
        stars   = '*' * int(p['stars'])
        label   = f"MD{p['day']}: {p['home'][:13]} v {p['away'][:13]}"

        if r:
            actual  = r['outcome']
            hit     = 'HIT' if actual == pred else 'MISS'
            score_s = f"{r['h']}:{r['a']}"
            g_pred   = p.get('goals', '?')
            g_act    = 'OVER' if r['o25'] == 1 else 'UNDER'
            g_hit    = 'OK' if ((g_pred == 'OVER 2.5' and r['o25']) or (g_pred == 'UNDER 2.5' and not r['o25'])) else 'X'
            lines.append(f"  {idx:<3} {label:<32} {stars:<6} {pred:<5} {actual:<7} {hit:<5} {g_pred[:11]:<12} {g_act}({g_hit})")
        else:
            lines.append(f"  {idx:<3} {label:<32} {stars:<6} {pred:<5} {'?':<7} {'N/A':<5} {p.get('goals','?')[:11]:<12} ?")

    lines.append("=" * 72)

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return path


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def main():
    filter_str = None
    show_summary = False

    for arg in sys.argv[1:]:
        if arg == '--summary':
            show_summary = True
        elif not arg.startswith('--'):
            filter_str = arg

    if show_summary:
        scored = [f for f in os.listdir(PENDING_DIR) if f.startswith('SCORED') and f.endswith('.txt')]
        if not scored:
            print("No scored tests yet.")
            return
        print("\n" + "=" * 60)
        print("  SCORED TEST SUMMARY")
        print("=" * 60)
        for f in sorted(scored):
            path = os.path.join(PENDING_DIR, f)
            with open(path, encoding='utf-8') as fp:
                lines = fp.readlines()
            for line in lines:
                if 'RESULT  accuracy' in line or 'GOALS   accuracy' in line or 'GG/NG   accuracy' in line:
                    print(f"  {f[:40]}: {line.strip()}")
        print("=" * 60)
        return

    print("\nVFL AUTO-SCORER")
    print("=" * 50)
    print("Loading all results data...")
    exact_map, fuzzy_map = load_all_results()
    total_results = len(exact_map)
    print(f"  {total_results} actual results loaded for matching.")

    pending_csvs = sorted([
        f for f in os.listdir(PENDING_DIR)
        if f.endswith('.csv') and not f.startswith('SCORED')
    ])

    scored_count   = 0
    no_data_count  = 0
    all_scores     = []

    for fname in pending_csvs:
        path  = os.path.join(PENDING_DIR, fname)
        score = score_pending_file(path, exact_map, fuzzy_map, filter_str)

        if score is None:
            continue

        if score['status'] == 'NO_RESULTS':
            no_data_count += 1
            src_short = score['source'].replace('2026-04-04_17-02_', '')
            print(f"  [NO DATA]  {src_short}")
            continue

        all_scores.append(score)
        scored_count += 1
        report_path = save_score_report(score, PENDING_DIR)
        src_short = score['source'].replace('2026-04-04_17-02_', '')
        print(f"  [SCORED]   {src_short:<40}  Result: {score['hits']}/{score['matched']} ({score['accuracy']}%)  Goals: {score['goals_acc']}%  GG: {score['gg_acc']}%")
        if report_path:
            print(f"             -> {os.path.basename(report_path)}")

    print()
    print("=" * 72)
    if all_scores:
        total_matched = sum(s['matched'] for s in all_scores)
        total_hits    = sum(s['hits']    for s in all_scores)
        total_g_hits  = sum(s['goals_hits'] for s in all_scores)
        total_gg_hits = sum(s['gg_hits'] for s in all_scores)
        overall_acc   = total_hits / total_matched * 100 if total_matched else 0
        overall_g_acc = total_g_hits / total_matched * 100 if total_matched else 0
        overall_gg_acc= total_gg_hits / total_matched * 100 if total_matched else 0

        print(f"  OVERALL ACCURACY ACROSS ALL SCORED TESTS")
        print(f"  Total picks matched to results : {total_matched}")
        print(f"  RESULT  : {total_hits}/{total_matched} = {overall_acc:.1f}%")
        print(f"  GOALS   : {total_g_hits}/{total_matched} = {overall_g_acc:.1f}%")
        print(f"  GG/NG   : {total_gg_hits}/{total_matched} = {overall_gg_acc:.1f}%")
    print(f"  Scored: {scored_count}  |  No results yet: {no_data_count}")
    print("=" * 72)


if __name__ == '__main__':
    main()
