"""
DEEP DIAGNOSTIC: Analyze WHY predictions are failing.
Breaks down accuracy by method (SIGNATURE vs STATS), by star level,
and identifies the specific failure patterns.
"""
import csv
import os
import sys
import json
from collections import defaultdict

ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PENDING_DIR = os.path.join(ROOT, 'pending_tests')
RESULTS_DIR = os.path.join(ROOT, 'extracted_results')

sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import predict as engine
import auto_score

def main():
    print("\nDEEP DIAGNOSTIC: WHY ARE WE MISSING?")
    print("=" * 72)

    print("Loading results database...")
    exact_map, fuzzy_map = auto_score.load_all_results()
    print(f"  {len(exact_map)} exact results | {len(fuzzy_map)} fuzzy keys")

    # Check for season collision in fuzzy_map
    collision_count = 0
    for key, results in fuzzy_map.items():
        seasons = set(str(r['season']) for r in results)
        if len(seasons) > 1:
            collision_count += 1
    print(f"  Season collisions in fuzzy map: {collision_count} (keys matching multiple seasons)")

    # Gather ALL scored picks from ALL pending CSVs
    pending_csvs = sorted([
        f for f in os.listdir(PENDING_DIR)
        if f.endswith('.csv') and not f.startswith('SCORED')
    ])

    all_picks = []  # list of {pick, result, source}

    for fname in pending_csvs:
        path = os.path.join(PENDING_DIR, fname)
        picks = list(csv.DictReader(open(path, encoding='utf-8')))
        high_picks = [p for p in picks if int(p.get('stars', 0)) >= 4]
        for p in high_picks:
            r = auto_score.lookup_result(p, exact_map, fuzzy_map)
            if r:
                hit = (r['outcome'] == p['outcome'])
                all_picks.append({
                    'pick': p, 'result': r, 'hit': hit,
                    'source': fname,
                    'season_match': str(p.get('season','')) == str(r.get('season',''))
                })

    print(f"\n  Total scoreable picks: {len(all_picks)}")
    
    # ── DIAGNOSIS 1: Season mismatch ──────────────────────────────────
    same_season = [x for x in all_picks if x['season_match']]
    diff_season = [x for x in all_picks if not x['season_match']]
    
    print(f"\n--- DIAGNOSIS 1: SEASON MATCHING ---")
    print(f"  Same season (prediction & result): {len(same_season)}")
    if same_season:
        hits = sum(1 for x in same_season if x['hit'])
        print(f"    Accuracy: {hits}/{len(same_season)} = {hits/len(same_season)*100:.1f}%")
    print(f"  Different season: {len(diff_season)}")
    if diff_season:
        hits = sum(1 for x in diff_season if x['hit'])
        print(f"    Accuracy: {hits}/{len(diff_season)} = {hits/len(diff_season)*100:.1f}%")

    # ── DIAGNOSIS 2: Method breakdown ─────────────────────────────────
    print(f"\n--- DIAGNOSIS 2: METHOD BREAKDOWN ---")
    sig_picks   = [x for x in all_picks if x['pick']['method'] == 'SIGNATURE']
    stat_picks  = [x for x in all_picks if x['pick']['method'] == 'STATS_BLEND']

    if sig_picks:
        sig_hits = sum(1 for x in sig_picks if x['hit'])
        print(f"  SIGNATURE picks : {sig_hits}/{len(sig_picks)} = {sig_hits/len(sig_picks)*100:.1f}%")
    if stat_picks:
        stat_hits = sum(1 for x in stat_picks if x['hit'])
        print(f"  STATS_BLEND picks : {stat_hits}/{len(stat_picks)} = {stat_hits/len(stat_picks)*100:.1f}%")

    # ── DIAGNOSIS 3: Star level breakdown ─────────────────────────────
    print(f"\n--- DIAGNOSIS 3: STAR LEVEL BREAKDOWN ---")
    for star in [5, 4]:
        star_picks = [x for x in all_picks if int(x['pick']['stars']) == star]
        if star_picks:
            hits = sum(1 for x in star_picks if x['hit'])
            print(f"  {'*'*star} ({star}-star): {hits}/{len(star_picks)} = {hits/len(star_picks)*100:.1f}%")

    # ── DIAGNOSIS 4: Signature confidence vs actual ───────────────────
    print(f"\n--- DIAGNOSIS 4: SIGNATURE CONFIDENCE vs ACTUAL ---")
    for threshold in [100, 90, 80, 70]:
        bucket = [x for x in sig_picks 
                  if float(x['pick'].get('sig_rate', x['pick'].get('outcome_pct', 0))) >= threshold]
        if bucket:
            hits = sum(1 for x in bucket if x['hit'])
            print(f"  Sig rate >= {threshold}%: {hits}/{len(bucket)} = {hits/len(bucket)*100:.1f}%")

    # ── DIAGNOSIS 5: Show first 30 MISSES on 5-star picks ────────────
    print(f"\n--- DIAGNOSIS 5: 5-STAR MISSES (what went wrong) ---")
    five_star_misses = [x for x in all_picks if int(x['pick']['stars']) == 5 and not x['hit']]
    for x in five_star_misses[:30]:
        p = x['pick']
        r = x['result']
        season_match = 'SAME' if x['season_match'] else f"DIFF(pred:{p.get('season','?')} res:{r.get('season','?')})"
        print(f"  MD{p['day']}: {p['home'][:14]} vs {p['away'][:14]}  "
              f"pred:{p['outcome']}  actual:{r['outcome']}  "
              f"score:{r['h']}:{r['a']}  "
              f"odds:{p['oh']}/{p['od']}/{p['oa']}  "
              f"sig_rate:{p.get('sig_rate','?')}%  "
              f"season:{season_match}")

    # ── DIAGNOSIS 6: Check if same (day,home,away) has different results across seasons
    print(f"\n--- DIAGNOSIS 6: SAME FIXTURE, DIFFERENT RESULTS ACROSS SEASONS ---")
    fixture_outcomes = defaultdict(list)
    for x in all_picks:
        r = x['result']
        key = (str(r['day']), r['home'], r['away'])
        fixture_outcomes[key].append(r['outcome'])
    
    inconsistent = 0
    for key, outcomes in fixture_outcomes.items():
        uniq = set(outcomes)
        if len(uniq) > 1:
            inconsistent += 1
    print(f"  Fixtures with inconsistent outcomes across seasons: {inconsistent}/{len(fixture_outcomes)}")
    print(f"  This means the RNG gives DIFFERENT results for the same fixture in different seasons")

    # ── DIAGNOSIS 7: What's the distribution of picks matched to wrong seasons?
    print(f"\n--- DIAGNOSIS 7: UNIQUE SEASONS IN DATA ---")
    pred_seasons = set(x['pick'].get('season', '?') for x in all_picks)
    result_seasons = set(str(x['result'].get('season', '?')) for x in all_picks)
    print(f"  Prediction seasons: {sorted(pred_seasons)}")
    print(f"  Result seasons:     {sorted(result_seasons)}")

    print("\n" + "=" * 72)

if __name__ == '__main__':
    main()
