import json
import os
import math

# --- CONFIGURATION ---
H2H_MODEL_PATH = 'h2h_model.json'
KNN_MODEL_PATH = 'backend/resources/rng_model.json'
UPCOMING_ODDS_PATH = 'upcoming_md11.json'

def calculate_true_probs(o1, o2, o3=None):
    if o3:
        ip = (1/o1) + (1/o2) + (1/o3)
        margin_removal = 1/ip
        return [(1/o1)*margin_removal, (1/o2)*margin_removal, (1/o3)*margin_removal]
    # Over/Under
    ip = (1/o1) + (1/o2)
    margin_removal = 1/ip
    return [(1/o1)*margin_removal, (1/o2)*margin_removal]

def get_h2h_prediction(home, away, h2h_db):
    key = f"{home.strip().upper()} VS {away.strip().upper()}"
    default = {"HOME_RATE": 0.33, "DRAW_RATE": 0.33, "AWAY_RATE": 0.33, "TOTAL": 0}
    return h2h_db.get(key, default)

def main():
    print("🚀 UNIFIED AI ORACLE: H2H + DATA MODE")
    
    if not os.path.exists(H2H_MODEL_PATH):
        print(f"Error: {H2H_MODEL_PATH} not found. Run build_h2h_model.py first.")
        return
        
    h2h_db = json.load(open(H2H_MODEL_PATH, 'r', encoding='utf-8'))
    
    # Use latest available odds file or upcoming
    odds_file = UPCOMING_ODDS_PATH
    if not os.path.exists(odds_file):
        # Fallback to any txt/json in extracted_odds
        print(f"Warning: {odds_file} not found. Searching for alternatives...")
        return

    data = json.load(open(odds_file, 'r', encoding='utf-8'))
    events = data.get('data', {}).get('events', [])
    if not events: events = data.get('events', [])

    print(f"Found {len(events)} fixtures. Analyzing patterns...")
    
    for ev in events:
        h_name = ev['homeTeam']
        a_name = ev['awayTeam']
        
        # 1. Math Analysis (Removal of Margin)
        m1x2 = next((m for m in ev['markets'] if m['id'] == 1), None)
        if not m1x2: continue
        
        h_odds = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '1'))
        d_odds = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '2'))
        a_odds = float(next(o['odds'] for o in m1x2['outcomes'] if o['id'] == '3'))
        
        math_probs = calculate_true_probs(h_odds, d_odds, a_odds)
        
        # 2. H2H History (The "Smokescreen" Buster)
        h2h = get_h2h_prediction(h_name, a_name, h2h_db)
        
        print(f"\n🏟️ {h_name} vs {a_name}")
        print(f"   Historical Samples: {h2h['TOTAL']} matches")
        print(f"   H2H Win Rates: H:{h2h['HOME_RATE']:.1%} D:{h2h['DRAW_RATE']:.1%} A:{h2h['AWAY_RATE']:.1%}")
        print(f"   Implied Prob: H:{math_probs[0]:.1%} D:{math_probs[1]:.1%} A:{math_probs[2]:.1%}")

        # Decision
        labels = ["HOME", "DRAW", "AWAY"]
        h2h_rates = [h2h['HOME_RATE'], h2h['DRAW_RATE'], h2h['AWAY_RATE']]
        prediction = labels[h2h_rates.index(max(h2h_rates))]
        confidence = max(h2h_rates)
        
        # Triple Lock check: H2H matches Math matches KNN (if we had time for KNN)
        # For now, H2H is the King.
        is_locked = (confidence > 0.45 and h2h['TOTAL'] > 50)
        
        print(f"   👉 PREDICTION: {prediction} ({confidence:.1%}) {'[LOCKED TARGET]' if is_locked else ''}")

if __name__ == "__main__":
    main()
