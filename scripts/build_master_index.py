import os
import json
import re
from collections import defaultdict

def parse_msport_json(content):
    blocks = re.split(r'===== MATCH #\d+', content)
    found = []
    for b in blocks:
        json_match = re.search(r'\{[\s\S]*\}', b)
        if not json_match: continue
        try:
            data = json.loads(jm := json_match.group())
            # Results
            if "data" in data and "current" in data["data"]:
                day = str(data["data"]["current"].get("matchDay", "0"))
                for r in data["data"].get("results", []):
                    r['_day'] = day
                    found.append(r)
            # Odds
            elif "data" in data and "events" in data["data"]:
                day = str(data["data"].get("matchDay", "0"))
                for e in data["data"]["events"]:
                    e['_day'] = day
                    found.append(e)
        except: continue
    return found

def main():
    print("MASTER RNG INDEXER: ANALYZING ALL 30,000+ DATA POINTS...")
    
    # Structure: Map[(Home, Away, Day, OH, OD, OA)] -> List of Outcomes
    signature_map = defaultdict(list)
    
    search_paths = [
        'extracted_odds',
        'extracted_results',
        'moneymspport-money/ExtractedData'
    ]
    
    # 1. First, build a full Result Database indexed by (Season, Day, Home, Away)
    # This is necessary because some files have odds but no results, and vice versa.
    results_db = {}
    
    print("PHASE 1: Building Results Database...")
    for folder in search_paths:
        if not os.path.exists(folder): continue
        for f in os.listdir(folder):
            path = os.path.join(folder, f)
            if not os.path.isfile(path) or '.txt' not in path: continue
            content = open(path, 'r', encoding='utf-8').read()
            events = parse_msport_json(content)
            for ev in events:
                if ev.get('fullTime'):
                    h, a = ev['homeTeam'].upper(), ev['awayTeam'].upper()
                    # We use a fuzzy season match or just day/teams if season is missing
                    results_db[(ev['_day'], h, a)] = ev['fullTime']

    print(f"Found {len(results_db)} unique match results.")

    # 2. Second, crawl all Odds and correlate with results to build Signatures
    print("PHASE 2: Indexing Odds Signatures with Outcomes...")
    match_count = 0
    for folder in search_paths:
        if not os.path.exists(folder): continue
        for f in os.listdir(folder):
            path = os.path.join(folder, f)
            if not os.path.isfile(path) or '.txt' not in path: continue
            content = open(path, 'r', encoding='utf-8').read()
            events = parse_msport_json(content)
            for ev in events:
                if 'markets' in ev:
                    h_name = ev['homeTeam'].upper()
                    a_name = ev['awayTeam'].upper()
                    day = ev['_day']
                    
                    m1x2 = next((m for m in ev['markets'] if m['id'] == 1), None)
                    if not m1x2: continue
                    try:
                        oh = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '1'))
                        od = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '2'))
                        oa = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '3'))
                    except: continue
                    
                    # See if we have a result for this (Day, Teams)
                    res = results_db.get((day, h_name, a_name))
                    if res:
                        # KEY = (Home, Away, Roundup(OH,1), Roundup(OD,1), Roundup(OA,1))
                        # Removing Day allows us to find recurring patterns across the entire season
                        sig_key = f"{h_name}|{a_name}|{oh:.1f}|{od:.1f}|{oa:.1f}"
                        
                        r_h, r_a = map(int, res.replace(' ', '').split(':'))
                        winner = "HOME" if r_h > r_a else ("AWAY" if r_a > r_h else "DRAW")
                        signature_map[sig_key].append(winner)
                        match_count += 1

    # 3. Save the Master Signature Map
    # Map[Sig] -> {Winner: Count}
    final_output = {}
    for sig, winners in signature_map.items():
        counts = {w: winners.count(w) for w in set(winners)}
        final_output[sig] = {
            "counts": counts,
            "total": len(winners)
        }

    with open('master_rng_signatures.json', 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=2)

    print(f"Master Index Created. Mapped {match_count} signatures across {len(final_output)} unique odd profiles.")
    print("Saved to master_rng_signatures.json")

if __name__ == "__main__":
    main()
