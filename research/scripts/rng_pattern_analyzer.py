import sys
import json
import re
import math
import os

def parse_blocks(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'===== MATCH #\d+', content)
    events = []
    
    for b in blocks:
        m = re.search(r'\{[\s\S]*\}', b)
        if m:
            try:
                data = json.loads(m.group())
                ev_list = []
                if "data" in data:
                    if "events" in data["data"]: ev_list = data["data"]["events"]
                elif "events" in data: ev_list = data["events"]
                
                for e in ev_list:
                    events.append(e)
            except: pass
    return events

def get_distance(m1, m2):
    # Euclidean distance between 1x2 and O/U odds
    d1x2 = (m1['h'] - m2['h_odds'])**2 + (m1['d'] - m2['d_odds'])**2 + (m1['a'] - m2['a_odds'])**2
    dou = (m1['o'] - m2['o_odds'])**2 + (m1['u'] - m2['u_odds'])**2
    return math.sqrt(d1x2 + dou)

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/rng_pattern_analyzer.py <path_to_odds_file.txt>")
        return
        
    target_file = sys.argv[1]
    if not os.path.exists(target_file):
        print(f"File not found: {target_file}")
        return
        
    model_path = 'backend/resources/rng_model.json'
    if not os.path.exists(model_path):
        print(f"RNG Database missing! Run 'python scripts/build_rng_model.py' first.")
        return
        
    with open(model_path, 'r', encoding='utf-8') as f:
        database = json.load(f)
        
    print(f"Loading incoming fixtures from {target_file}...")
    events = parse_blocks(target_file)
    if not events:
        print("No valid MSport odds JSON found in the file.")
        return
        
    print(f"\n🔍 Analyzing {len(events)} fixtures against {len(database)} historical RNG patterns...\n")
    print("="*70)
    print("   🔥 HIGH CONFIDENCE HISTORICAL PATTERN MATCHES 🔥")
    print("="*70)
    
    found_any = False
    output_lines = []
    
    for e in events:
        fixture = f"{e.get('homeTeam')} vs {e.get('awayTeam')}"
        
        m1x2 = next((m for m in e.get('markets', []) if m.get('id') == 1), None)
        if not m1x2: continue
        try:
            h = float(next(oc['odds'] for oc in m1x2.get('outcomes', []) if oc['id'] == '1'))
            d = float(next(oc['odds'] for oc in m1x2.get('outcomes', []) if oc['id'] == '2'))
            a = float(next(oc['odds'] for oc in m1x2.get('outcomes', []) if oc['id'] == '3'))
        except: continue

        m_ou = next((m for m in e.get('markets', []) if m.get('id') == 18 and 'total=2.5' in m.get('specifiers', '')), None)
        o_ou = u_ou = 0.0
        if m_ou:
            try:
                o_ou = float(next(oc['odds'] for oc in m_ou.get('outcomes', []) if oc['id'] == '12'))
                u_ou = float(next(oc['odds'] for oc in m_ou.get('outcomes', []) if oc['id'] == '13'))
            except: pass
            
        target = {'h': h, 'd': d, 'a': a, 'o': o_ou, 'u': u_ou}
        
        # Calculate distances to all history
        distances = []
        for row in database:
            # Only compare if they have valid O/U if target has valid O/U
            if o_ou > 0 and row['o_odds'] == 0: continue
            dist = get_distance(target, row)
            distances.append((dist, row))
            
        distances.sort(key=lambda x: x[0])
        top_k = 15 # Look at 15 closest historical occurrences
        closest = [x[1] for x in distances[:top_k]]
        
        
        if not closest: continue
            
        outcomes_1x2 = {"HOME": 0, "DRAW": 0, "AWAY": 0}
        outcomes_ou = {"OVER": 0, "UNDER": 0}
        
        for c in closest:
            outcomes_1x2[c['actual_1x2']] += 1
            outcomes_ou[c['actual_ou']] += 1
            
        best_1x2 = max(outcomes_1x2, key=outcomes_1x2.get)
        rate_1x2 = outcomes_1x2[best_1x2] / top_k
        
        best_ou = max(outcomes_ou, key=outcomes_ou.get)
        rate_ou = outcomes_ou[best_ou] / top_k
        
        # Only print highly confident empirical patterns!
        if rate_1x2 >= 0.70 or rate_ou >= 0.70:
            found_any = True
            output_lines.append(f"\n### ⚽ {fixture}")
            output_lines.append(f"- **Raw Odds**: H:{h} D:{d} A:{a} | O2.5:{o_ou} U2.5:{u_ou}")
            
            if rate_1x2 >= 0.70:
                output_lines.append(f"- 🔥 **1X2 PATTERN WIN:** `{best_1x2}` (Historically hits **{rate_1x2*100:.1f}%** of the time on exact matching odds)")
            if rate_ou >= 0.70:
                output_lines.append(f"- 🔥 **O/U PATTERN WIN:** `{best_ou} 2.5` (Historically hits **{rate_ou*100:.1f}%** of the time on exact matching odds)")

    if not found_any:
        output_lines.append("\nNo highly confident historical patterns (>70%) found for these fixtures.")
        
    with open('rng_empirical_picks.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
        
    print("Done. Saved to rng_empirical_picks.md!")

if __name__ == "__main__":
    main()
