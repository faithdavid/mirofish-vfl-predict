"""
Extracts and prints a clean scorecard of high-confidence picks
from the predictions.csv file for blind test verification.
Usage: python scripts/show_picks.py [min_stars=4]
"""
import csv
import sys
import os
import io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Fix Windows console UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def star_str(n):
    return '*' * n + '-' * (5 - n)

def main():
    min_stars = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    csv_path = os.path.join(ROOT, 'predictions.csv')

    rows = []
    with open(csv_path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            stars = int(row.get('stars', 0))
            if stars >= min_stars:
                rows.append(row)

    # Group by day
    by_day = {}
    for r in rows:
        day = r['day']
        by_day.setdefault(day, []).append(r)

    def day_key(d):
        try: return int(d)
        except: return 999

    print("=" * 72)
    print(f"  BLIND TEST SCORECARD  --  {len(rows)} PICKS ({min_stars}+ stars)")
    print(f"  Source: www.msport27.har")
    print("=" * 72)

    total = 0
    for day in sorted(by_day.keys(), key=day_key):
        matches = sorted(by_day[day], key=lambda x: -int(x['stars']))
        print(f"\n  -- MATCH DAY {day} " + "-" * 45)
        for r in matches:
            stars       = int(r['stars'])
            outcome     = r['outcome']
            odds        = r['oh'] if outcome == 'HOME' else (r['od'] if outcome == 'DRAW' else r['oa'])
            method      = '[SIG]' if r['method'] == 'SIGNATURE' else '[STAT]'
            conf        = r['outcome_pct']
            sig_rate    = f" (sig:{r.get('sig_rate','?')}%)" if r['method'] == 'SIGNATURE' else ''

            print(f"  [{star_str(stars)}]  {r['home'][:16]:<16} vs {r['away'][:16]:<16}  =>  {outcome:<4}  odds:{odds:<6} {conf}%{sig_rate}  {method}")
            print(f"                Goals: {r['goals']} ({r['goals_pct']}%)   GG: {r['gg']} ({r['gg_pct']}%)")
            total += 1

    print()
    print("=" * 72)
    print(f"  VERIFICATION SCORECARD  ({total} picks)")
    print("=" * 72)
    print(f"  {'#':<3} {'Match':<32} {'Stars':<6} {'Predicted':<6} {'Actual':<8} HIT?")
    print(f"  {'-'*3} {'-'*32} {'-'*6} {'-'*6} {'-'*8} ----")
    idx = 1
    for day in sorted(by_day.keys(), key=day_key):
        for r in sorted(by_day[day], key=lambda x: -int(x['stars'])):
            outcome = r['outcome']
            label   = f"MD{r['day']}: {r['home'][:12]} v {r['away'][:12]}"
            stars   = int(r['stars'])
            print(f"  {idx:<3} {label:<32} {'*'*stars:<6} {outcome:<6} {'?':<8} ?")
            idx += 1
    print("=" * 72)

if __name__ == '__main__':
    main()
