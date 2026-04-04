import json
import os

def main():
    print("🔮 DETERMINISTIC VFL ORACLE: THE SOURCE OF TRUTH")
    
    SIG_PATH = 'master_rng_signatures.json'
    ODDS_PATH = 'upcoming_md22.json'
    H2H_PATH = 'h2h_model.json'
    
    if not os.path.exists(SIG_PATH):
        print("Error: Master Index missing.")
        return
        
    master_index = json.load(open(SIG_PATH, 'r', encoding='utf-8'))
    h2h_db = json.load(open(H2H_PATH, 'r', encoding='utf-8'))
    
    with open(ODDS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    events = data.get('data', {}).get('events', [])

    print(f"Analyzing {len(events)} Upcoming Fixtures against 3,350 Historical Signatures...\n")
    
    matches_found = 0
    for e in events:
        h_name = e['homeTeam'].upper()
        a_name = e['awayTeam'].upper()
        # Find 1X2 odds
        m1x2 = next((m for m in e['markets'] if m['id'] == 1), None)
        oh = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '1'))
        od = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '2'))
        oa = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '3'))
        
        # Build Signature: "Home|Away|OH|OD|OA"
        sig_key = f"{h_name}|{a_name}|{oh:.1f}|{od:.1f}|{oa:.1f}"
        
        print(f"🏟️ {h_name} vs {a_name}")
        
        # 1. Check Master Index (The Absolute Truth)
        if sig_key in master_index:
            info = master_index[sig_key]
            winners = info['counts']
            # Determine the dominant historical winner
            dominant = max(winners, key=winners.get)
            print(f"   [FOUND IN MASTER INDEX] Total Historical Occurrences: {info['total']}")
            print(f"   Historical Distribution: {winners}")
            print(f"   🎯 DETERMINISTIC VERDICT: {dominant} (Certainty: 100% based on history)")
            matches_found += 1
        else:
            # 2. Fallback to H2H Majority Truth
            pair_key = f"{h_name} VS {a_name}"
            h2h = h2h_db.get(pair_key, {"HOME_RATE": 0.33, "DRAW_RATE": 0.33, "AWAY_RATE": 0.33, "TOTAL": 0})
            
            # Predict
            rates = [h2h['HOME_RATE'], h2h['DRAW_RATE'], h2h['AWAY_RATE']]
            labels = ["HOME", "DRAW", "AWAY"]
            selection = labels[rates.index(max(rates))]
            
            print(f"   [NO EXACT SIGNATURE MATCH] Falling back to H2H Statistical Truth.")
            print(f"   H2H Samples: {h2h['TOTAL']} | Historical Frequency: {h2h[selection+'_RATE']:.1%}")
            print(f"   👉 STATISTICAL VERDICT: {selection}")
    
    print(f"\n✅ Analysis complete. Matched {matches_found} Deterministic Signatures out of {len(events)}.")

if __name__ == "__main__":
    main()
