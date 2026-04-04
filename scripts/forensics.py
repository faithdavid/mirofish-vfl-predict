import csv
import os
import sys
import json
from collections import defaultdict

ROOT = os.getcwd()
PENDING_DIR = os.path.join(ROOT, 'pending_tests')
RESULTS_DIR = os.path.join(ROOT, 'extracted_results')
SIG_FILE = os.path.join(ROOT, 'master_rng_signatures.json')

sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import predict_v3 as v3
import score_v3

def deep_analyze_misses():
    print("PHASE 1: 5-STAR MISS FORENSICS")
    print("=" * 72)
    
    # 1. Load everything
    result_events = v3.parse_all_results(RESULTS_DIR)
    db = v3.build_season_aware_db(result_events)
    sig_db = v3.load_signature_db()
    
    exact_results = {}
    for r in result_events:
        key = (str(r.get('season', '')), str(r.get('day', '')), r['home'].upper(), r['away'].upper())
        exact_results[key] = r

    # 2. Get all 5-star picks from pending tests
    pending_csvs = [f for f in os.listdir(PENDING_DIR) if f.endswith('.csv') and not f.startswith('SCORED')]
    
    misses = []
    
    for fname in pending_csvs:
        path = os.path.join(PENDING_DIR, fname)
        with open(path, encoding='utf-8') as f:
            picks = list(csv.DictReader(f))
        
        for p in picks:
            if int(p['stars']) == 5:
                key = (str(p.get('season', '')), str(p.get('day', '')), p['home'].upper(), p['away'].upper())
                actual = exact_results.get(key)
                if actual and actual['outcome'] != p['outcome']:
                    misses.append({'pick': p, 'actual': actual, 'src': fname})

    print(f"Found {len(misses)} unique 5-star misses to analyze.")
    
    for m in misses:
        p = m['pick']
        a = m['actual']
        print(f"\nANALYZING MISS: MD{p['day']} {p['home']} vs {p['away']}")
        print(f"  PREDICTED: {p['outcome']} | ACTUAL: {a['outcome']} ({a['h']}:{a['a']})")
        print(f"  ODDS: {p['oh']} / {p['od']} / {p['oa']}")
        print(f"  METHOD: {p['method']} | Consensus: {p.get('consensus_rate')}%")
        
        # Now look for HITS with this exact same signature
        sig_key = f"{p['home'].upper()}|{p['away'].upper()}|{float(p['oh']):.1f}|{float(p['od']):.1f}|{float(p['oa']):.1f}"
        sig_entry = sig_db.get(sig_key)
        
        if sig_entry:
            print(f"  HISTORICAL SIG DATA: {sig_entry['counts']} (Total {sig_entry['total']})")
            
        # Check for Season ID patterns
        print(f"  SEASON ID: {p.get('season')} (Numeric: {v3.season_id_num(p.get('season'))})")
        
        # Check for Match Day patterns - are misses more common at the end of the season?
        day_val = int(p['day']) if p['day'].isdigit() else 0
        if day_val > 25:
            print("  [ALERT] Miss occurred in LATE season (MD 26-30). Possible pattern decay?")
        elif day_val < 5:
            print("  [ALERT] Miss occurred in EARLY season (MD 1-5). Possible fresh RNG seed?")

if __name__ == '__main__':
    deep_analyze_misses()
