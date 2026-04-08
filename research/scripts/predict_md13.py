import json
from pathlib import Path
import sys

# Add scripts to path
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT / "scripts"))

import vfl_oracle_v5 as oracle

def run_predictions():
    input_path = ROOT / "ANalysis" / "radar_live_input.json"
    with open(input_path, 'r') as f:
        data = json.load(f)
    
    events = data['data']['events']
    matchday = data['data']['matchDay']
    season = data['data']['seasonName']
    
    print(f"DEBUG: Found {len(events)} events for MD {matchday} {season}")
    
    print(f"--- MIROFISH PREDICTIONS: {season} | MD {matchday} ---")
    
    # Load Oracle Brain
    df = oracle.load_vfl_history()
    profiles = oracle.get_team_profiles(df)
    accounting = oracle.get_seasonal_accounting(df, season)
    
    predictions = []
    
    for ev in events:
        home = ev['homeTeam']
        away = ev['awayTeam']
        
        # Extract 1x2 odds
        m1x2 = next((m for m in ev['markets'] if m['name'] == '1x2'), None)
        if not m1x2:
            print(f"DEBUG: No 1x2 market for {home} vs {away}")
            continue
        
        try:
            oh = float(next(o['odds'] for o in m1x2['outcomes'] if o['description'] == 'Home'))
            od = float(next(o['odds'] for o in m1x2['outcomes'] if o['description'] == 'Draw'))
            oa = float(next(o['odds'] for o in m1x2['outcomes'] if o['description'] == 'Away'))
        except StopIteration:
            print(f"DEBUG: Missing odds in 1x2 outcomes for {home} vs {away}")
            continue
        
        fxt = {
            'home': home, 'away': away,
            'oh': oh, 'od': od, 'oa': oa,
            'day': int(matchday), 'season': season
        }
        
        pred = oracle.predict_fixture(fxt, df, profiles)
        if not pred:
            print(f"DEBUG: Oracle returned None for {home} vs {away}")
            continue
            
        pred = oracle.apply_global_balancing(pred, accounting, int(matchday))
        
        # Calculate EV
        prob = pred['confidence']
        ev_val = (prob * od) - 1
        
        print(f"DEBUG: Processed {home} vs {away} | EV: {ev_val:.4f}")
        
        predictions.append({
            'fixture': f"{home} vs {away}",
            'prob': prob,
            'odds': od,
            'ev': ev_val,
            'rec': pred['prediction'],
            'label': pred['label']
        })
    
    # Sort by EV
    predictions.sort(key=lambda x: x['ev'], reverse=True)
    
    for p in predictions:
        status = "🔥 +EV" if p['ev'] > 0 else "❌ -EV"
        print(f"[{status}] {p['fixture']} | Draw {p['odds']} | Prob: {p['prob']*100:.1f}% | EV: {p['ev']*100:+.1f}% | {p['label']}")

if __name__ == "__main__":
    run_predictions()
