"""
================================================================================
  VFL V4 — FULL SCORECARD RESOLVER (THE CHALLENGE)
  ─────────────────────────────────────────────────────────────────────────────
  1. Loads joined indexes (Block Mirror + Score Modes).
  2. Parses target odds file.
  3. Finds the "Mirror" or best-fit for every fixture.
  4. Outputs a complete "Predicted Scorecard" including exact scorelines.
================================================================================
"""

import sys, os, json, argparse, hashlib
from datetime import datetime

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import predict_v4 as v4

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', help="Path to odds file (e.g. extracted_odds/www.msport27_odds.txt)")
    args = parser.parse_args()

    print("\nVFL CHALLENGE SOLVER v4.0")
    print("=" * 72)
    
    # 1. Load Data
    joined, block_index, match_index, noOdds_index = v4.build_all_indexes()
    
    # 2. Parse Fixtures from input
    fixtures = v4.parse_odds_file(args.input_file)
    if not fixtures:
        print(f"[ERROR] No fixtures found in {args.input_file}")
        return

    # Group fixtures by MatchDay
    day_fixtures = {}
    for f in fixtures:
        d = f['day']
        if d not in day_fixtures: day_fixtures[d] = []
        day_fixtures[d].append(f)

    # 3. Resolve Full Scorecard Day by Day
    for day in sorted(day_fixtures.keys(), key=lambda x: int(x) if x.isdigit() else 99):
        day_fixes = day_fixtures[day]
        print(f"\n--- RESOLVING MATCH DAY {day} ({len(day_fixes)} matches) ---")
        
        results, method = v4.predict_full_day(day_fixes, block_index, match_index, noOdds_index)
        
        # Calculate summary metrics
        out_conf_avg = sum(r['outcome_conf'] for r in results) / len(results)
        
        # Print scorecard
        print(f"Outcome Sequence: {'-'.join([r['outcome'][0] for r in sorted(results, key=lambda x: x['home'])])}")
        print(f"Method: {method} | Overall Day Confidence: {out_conf_avg:.1%}")
        print("-" * 85)
        print(f"{'#':<3} {'Home':<15} vs {'Away':<15} {'Odds':<14} {'Result':<6} {'Score':<6} {'Conf'}")
        print("-" * 85)
        
        for i, r in enumerate(results, 1):
            stars = "*" * r['stars']
            odds_str = f"{r['oh']}/{r['od']}/{r['oa']}"
            conf_str = f"{r['outcome_conf']:.0%}/{r.get('score_conf', 0):.0%}"
            print(f"{i:<3} {r['home'][:15]:<15} vs {r['away'][:15]:<15} {odds_str:<14} {r['outcome']:<6} {r['score']:<6} {conf_str} {stars}")
            
            # If precision is high, flag it
            if r['stars'] >= 4:
                top_scores = r.get('all_scores', {})
                if top_scores:
                    sorted_sc = sorted(top_scores.items(), key=lambda x: -x[1])
                    if len(sorted_sc) > 1:
                        top2 = ", ".join([f"{s}({c}x)" for s, c in sorted_sc[:3]])
                        print(f"    History: {top2}")

    print("\n" + "=" * 72)
    print(f"Challenge Resolution Complete. Results saved for verification.")

if __name__ == '__main__':
    main()
