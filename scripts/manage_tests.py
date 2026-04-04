"""
================================================================================
  VFL PENDING TEST MANAGER
  ─────────────────────────────────────────────────────────────────────────────
  Scans for odds files that DON'T have a matching results file yet,
  runs the prediction engine on each one, and saves the picks to
  pending_tests/ so they can be verified once results come in.

  Usage:
    python scripts/manage_tests.py            # auto-scan and predict all pending
    python scripts/manage_tests.py verify     # score previously saved predictions
    python scripts/manage_tests.py status     # show status of all test sets

  Pending test files are saved as:
    pending_tests/YYYY-MM-DD_HH-MM_<source>.txt   (human scorecard)
    pending_tests/YYYY-MM-DD_HH-MM_<source>.csv   (machine picks)
================================================================================
"""

import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

ROOT         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ODDS_DIR     = os.path.join(ROOT, 'extracted_odds')
RESULTS_DIR  = os.path.join(ROOT, 'extracted_results')
PENDING_DIR  = os.path.join(ROOT, 'pending_tests')
SIG_FILE     = os.path.join(ROOT, 'master_rng_signatures.json')

os.makedirs(PENDING_DIR, exist_ok=True)


# ── Import the prediction engine ──────────────────────────────────────────────

sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import predict as engine


# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_source_name(odds_filename):
    """Strip _odds.txt suffix to get the base source name."""
    return odds_filename.replace('_odds.txt', '')


def has_results(source_name):
    """Check if there's a corresponding results file for this odds file."""
    results_name = source_name + '_results.txt'
    return os.path.exists(os.path.join(RESULTS_DIR, results_name))


def already_predicted(source_name):
    """Check if we've already saved pending predictions for this source."""
    for f in os.listdir(PENDING_DIR):
        if source_name in f and f.endswith('.csv'):
            return True
    return False


def list_pending_sources():
    """Returns list of odds files that have no matching results file."""
    pending = []
    if not os.path.exists(ODDS_DIR):
        return []
    for fname in sorted(os.listdir(ODDS_DIR)):
        if not fname.endswith('_odds.txt'):
            continue
        source = get_source_name(fname)
        if not has_results(source):
            pending.append((source, fname))
    return pending


def star_str(n):
    return '*' * n + '-' * (5 - n)


def save_scorecard(source_name, predictions, timestamp):
    """Save a human-readable scorecard and CSV of the predictions."""
    label = f"{timestamp}_{source_name}"
    txt_path = os.path.join(PENDING_DIR, label + '.txt')
    csv_path = os.path.join(PENDING_DIR, label + '.csv')

    # CSV
    fields = ['day','season','home','away','oh','od','oa','o_o25','o_u25','o_gg','o_ng',
              'method','stars','outcome','outcome_pct','goals','goals_pct','gg','gg_pct',
              'h2h_n','h2h_hw','h2h_dr','h2h_aw','last5_outcomes','last5_scores',
              'sig_rate','sig_total','blend_h','blend_d','blend_a']
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(predictions)

    # Human scorecard
    high = [p for p in predictions if p['stars'] >= 4]
    med  = [p for p in predictions if p['stars'] == 3]

    def day_key(p):
        try: return int(p['day'])
        except: return 999

    lines = []
    lines.append("=" * 72)
    lines.append(f"  PENDING BLIND TEST  --  {source_name}")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  Total fixtures: {len(predictions)}")
    lines.append(f"  High-confidence (4+*): {len(high)}  |  Medium (3*): {len(med)}")
    lines.append("=" * 72)
    lines.append("")
    lines.append("  STATUS: AWAITING RESULTS")
    lines.append("  When you have the results, run:")
    lines.append(f"    python scripts/manage_tests.py verify")
    lines.append("")

    # Sort by day then stars
    for_display = sorted(high, key=lambda p: (day_key(p), -p['stars']))
    current_day = None
    for p in for_display:
        if p['day'] != current_day:
            current_day = p['day']
            lines.append(f"\n  -- MATCH DAY {current_day} " + "-" * 45)
        outcome = p['outcome']
        odds = p['oh'] if outcome == 'HOME' else (p['od'] if outcome == 'DRAW' else p['oa'])
        sig = f" (sig:{p.get('sig_rate','?')}%)" if p['method'] == 'SIGNATURE' else ''
        lines.append(
            f"  [{star_str(p['stars'])}]  "
            f"{p['home'][:16]:<16} vs {p['away'][:16]:<16}  =>  "
            f"{outcome:<4}  odds:{odds:<6} {p['outcome_pct']}%{sig}"
        )
        lines.append(
            f"              Goals: {p['goals']} ({p['goals_pct']}%)   "
            f"GG: {p['gg']} ({p['gg_pct']}%)"
        )

    lines.append("")
    lines.append("=" * 72)
    lines.append(f"  VERIFICATION TABLE  ({len(high)} picks)")
    lines.append("=" * 72)
    lines.append(f"  {'#':<3} {'Match':<34} {'Stars':<7} {'Pred':<6} {'Actual':<8} HIT?")
    lines.append(f"  {'-'*3} {'-'*34} {'-'*7} {'-'*6} {'-'*8} ----")
    for idx, p in enumerate(sorted(high, key=day_key), 1):
        outcome = p['outcome']
        label = f"MD{p['day']}: {p['home'][:13]} v {p['away'][:13]}"
        lines.append(
            f"  {idx:<3} {label:<34} [{star_str(p['stars'])}]  "
            f"{outcome:<6} {'?':<8} ?"
        )
    lines.append("=" * 72)

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return txt_path, csv_path, len(high)


# ── VERIFY MODE ───────────────────────────────────────────────────────────────

def verify_mode():
    """
    Interactive: loads a pending test CSV, asks you to input actual results,
    calculates and saves the accuracy score.
    """
    # Find all pending CSVs
    pending_csvs = sorted(
        [f for f in os.listdir(PENDING_DIR) if f.endswith('.csv') and not f.startswith('SCORED')],
        reverse=True
    )
    if not pending_csvs:
        print("No pending test CSVs found in pending_tests/")
        return

    print("\nAvailable pending tests:")
    for i, f in enumerate(pending_csvs):
        print(f"  {i+1}. {f}")

    choice = input("\nEnter number to verify (or press Enter for most recent): ").strip()
    if not choice:
        choice = "1"
    chosen = pending_csvs[int(choice) - 1]
    csv_path = os.path.join(PENDING_DIR, chosen)

    # Load picks
    with open(csv_path, encoding='utf-8') as f:
        picks = list(csv.DictReader(f))

    high_picks = [p for p in picks if int(p['stars']) >= 4]

    print(f"\nLoaded {len(high_picks)} high-confidence picks from {chosen}")
    print("\nFor each match, enter the ACTUAL result: H, D, A, or SKIP")
    print("(Press Enter to skip a match)")
    print()

    results = []
    for p in sorted(high_picks, key=lambda x: (int(x['day']) if x['day'].isdigit() else 99)):
        outcome = p['outcome']
        label = f"MD{p['day']}: {p['home'][:13]} vs {p['away'][:13]}"
        predicted = f"=> {outcome}"
        actual = input(f"  {label:<36} {predicted:<12}  Actual? ").strip().upper()
        if actual in ('H', 'HOME'):   actual = 'HOME'
        elif actual in ('D', 'DRAW'): actual = 'DRAW'
        elif actual in ('A', 'AWAY'): actual = 'AWAY'
        elif actual in ('', 'SKIP'):
            results.append({'pick': p, 'actual': 'SKIP', 'hit': None})
            continue

        hit = (actual == outcome)
        results.append({'pick': p, 'actual': actual, 'hit': hit})

    # Score
    scored = [r for r in results if r['hit'] is not None]
    hits   = [r for r in scored if r['hit']]
    misses = [r for r in scored if not r['hit']]

    print("\n" + "=" * 60)
    print(f"  RESULTS: {len(hits)}/{len(scored)} CORRECT")
    if scored:
        print(f"  HIT RATE: {len(hits)/len(scored)*100:.1f}%")
    print()

    if hits:
        print("  HITS:")
        for r in hits:
            p = r['pick']
            print(f"    [{'*'*int(p['stars'])}] MD{p['day']}: {p['home']} vs {p['away']}  => {p['outcome']} (CORRECT)")
    if misses:
        print("\n  MISSES:")
        for r in misses:
            p = r['pick']
            print(f"    [{'*'*int(p['stars'])}] MD{p['day']}: {p['home']} vs {p['away']}  => predicted:{p['outcome']} actual:{r['actual']}")

    # Save scored file
    score_label = f"SCORED_{datetime.now().strftime('%Y-%m-%d_%H-%M')}_{chosen}"
    score_path = os.path.join(PENDING_DIR, score_label.replace('.csv', '.txt'))
    with open(score_path, 'w', encoding='utf-8') as f:
        f.write(f"SCORED TEST: {chosen}\n")
        f.write(f"Date scored: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Result: {len(hits)}/{len(scored)} = {len(hits)/len(scored)*100:.1f}% accuracy\n\n")
        for r in results:
            p = r['pick']
            status = 'HIT' if r['hit'] else ('MISS' if r['hit'] is False else 'SKIP')
            f.write(f"  {'*'*int(p['stars'])} MD{p['day']}: {p['home']} vs {p['away']}  "
                    f"pred:{p['outcome']}  actual:{r['actual']}  [{status}]\n")

    print(f"\n  Score saved to: {score_label.replace('.csv', '.txt')}")
    print("=" * 60)


# ── STATUS MODE ───────────────────────────────────────────────────────────────

def status_mode():
    print("\n" + "=" * 60)
    print("  PENDING TESTS STATUS")
    print("=" * 60)

    pending = list_pending_sources()
    predicted_files = [f for f in os.listdir(PENDING_DIR) if f.endswith('.csv') and not f.startswith('SCORED')]
    scored_files    = [f for f in os.listdir(PENDING_DIR) if f.startswith('SCORED')]

    print(f"\n  Odds files WITHOUT results yet: {len(pending)}")
    for src, fname in pending[:10]:
        already = "[predicted]" if already_predicted(src) else "[NOT YET PREDICTED]"
        print(f"    {fname:<45} {already}")

    print(f"\n  Saved blind tests (awaiting verification): {len(predicted_files)}")
    for f in predicted_files:
        print(f"    {f}")

    print(f"\n  Completed scored tests: {len(scored_files)}")
    for f in scored_files:
        path = os.path.join(PENDING_DIR, f)
        with open(path, encoding='utf-8') as fp:
            for line in fp:
                if 'Result:' in line:
                    print(f"    {f}: {line.strip()}")
                    break
    print("=" * 60)


# ── AUTO MODE: predict all pending ────────────────────────────────────────────

def auto_mode(force=False):
    print("\nVFL PENDING TEST MANAGER")
    print("=" * 50)

    # Load shared resources once
    print("Loading prediction engine resources...")
    sig_db = engine.load_signature_db()
    result_events = engine.parse_extracted_files(RESULTS_DIR)
    results_only  = [e for e in result_events if e['type'] == 'result']
    home_stats, away_stats, h2h_map = engine.build_stats(results_only)
    print(f"  {len(results_only)} results | {len(sig_db)} signatures | {len(h2h_map)} H2H pairings")

    pending = list_pending_sources()
    if not pending:
        print("\nNo pending odds files found (all have matching results already).")
        return

    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
    total_new = 0

    for source_name, odds_fname in pending:
        if already_predicted(source_name) and not force:
            print(f"\n  SKIP (already predicted): {odds_fname}")
            continue

        print(f"\n  Processing: {odds_fname}")
        odds_path = os.path.join(ODDS_DIR, odds_fname)

        # Parse fixtures from this file
        fixtures = []
        try:
            with open(odds_path, 'r', encoding='utf-8', errors='replace') as f:
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
        except Exception as e:
            print(f"    ERROR reading {odds_fname}: {e}")
            continue

        if not fixtures:
            print(f"    No fixtures found in {odds_fname}, skipping.")
            continue

        # Predict
        predictions = []
        for fix in fixtures:
            p = engine.predict(fix, sig_db, home_stats, away_stats, h2h_map)
            if p:
                predictions.append(p)

        if not predictions:
            print(f"    No predictions generated, skipping.")
            continue

        high_count = sum(1 for p in predictions if p['stars'] >= 4)
        print(f"    {len(predictions)} predictions | {high_count} high-confidence (4+*)")

        # Save
        txt_path, csv_path, n_picks = save_scorecard(source_name, predictions, timestamp)
        print(f"    Saved: {os.path.basename(txt_path)}")
        total_new += 1

    print("\n" + "=" * 50)
    print(f"Done. {total_new} new blind test sets saved to: pending_tests/")
    print("\nTo verify when results are available:")
    print("  python scripts/manage_tests.py verify")
    print("\nTo see all test statuses:")
    print("  python scripts/manage_tests.py status")


# ── ENTRY POINT ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else 'auto'

    if mode == 'verify':
        verify_mode()
    elif mode == 'status':
        status_mode()
    elif mode in ('auto', 'run'):
        auto_mode(force='--force' in sys.argv)
    elif mode == 'force':
        auto_mode(force=True)
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python scripts/manage_tests.py [auto|verify|status|force]")
