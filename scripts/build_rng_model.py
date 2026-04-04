import os
import json
import re
import math

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
                
                # Season and Day
                top_s = data.get('data', {}).get('seasonId') or data.get('seasonId')
                top_d = data.get('data', {}).get('matchDay') or data.get('matchDay')
                if not top_d or not top_s:
                    current = data.get('data', {}).get('current', {})
                    if current:
                        top_d = top_d or current.get('matchDay')
                        top_s = top_s or current.get('seasonId')
                
                ev_list = []
                if "data" in data:
                    if "events" in data["data"]: ev_list = data["data"]["events"]
                    elif "results" in data["data"]: ev_list = data["data"]["results"]
                elif "results" in data: ev_list = data["results"]
                
                for e in ev_list:
                    s = str(e.get('seasonId') or top_s)
                    d = str(e.get('matchDay') or top_d)
                    e['norm_season'] = s.split(':')[-1].strip() if s else 'Unknown'
                    e['norm_day'] = d.strip() if d else 'Unknown'
                    events.append(e)
            except: pass
    return events

def get_outcome(home_score, away_score):
    if home_score > away_score: return "HOME"
    if home_score == away_score: return "DRAW"
    return "AWAY"

def main():
    print("Building Historical RNG Database...")
    odds_dir = "extracted_odds"
    results_dir = "extracted_results"
    
    odds_map = {}
    for f in os.listdir(odds_dir):
        if not f.endswith('.txt'): continue
        path = os.path.join(odds_dir, f)
        for e in parse_blocks(path):
            s, d = e.get('norm_season'), e.get('norm_day')
            if (s, d) not in odds_map: odds_map[(s, d)] = []
            odds_map[(s, d)].append(e)
            
    results_map_files = {}
    for f in os.listdir(results_dir):
        if not f.endswith('.txt'): continue
        path = os.path.join(results_dir, f)
        for e in parse_blocks(path):
            s, d = e.get('norm_season'), e.get('norm_day')
            if (s, d) not in results_map_files: results_map_files[(s, d)] = []
            results_map_files[(s, d)].append(e)
            
    database = []
    
    # Match odds with results
    for key in results_map_files:
        if key in odds_map:
            r_events = results_map_files[key]
            o_events = odds_map[key]
            
            r_dict = {f"{str(r.get('homeTeam')).strip()} vs {str(r.get('awayTeam')).strip()}": r for r in r_events}
            seen_odds = set()
            
            for o in o_events:
                fixture = f"{str(o.get('homeTeam')).strip()} vs {str(o.get('awayTeam')).strip()}"
                if fixture in seen_odds: continue
                seen_odds.add(fixture)
                
                if fixture in r_dict:
                    r = r_dict[fixture]
                    
                    # 1X2 market
                    m1x2 = next((m for m in o.get('markets', []) if m.get('id') == 1), None)
                    if not m1x2: continue
                    try:
                        h_odds = float(next(oc['odds'] for oc in m1x2.get('outcomes', []) if oc['id'] == '1'))
                        d_odds = float(next(oc['odds'] for oc in m1x2.get('outcomes', []) if oc['id'] == '2'))
                        a_odds = float(next(oc['odds'] for oc in m1x2.get('outcomes', []) if oc['id'] == '3'))
                    except: continue

                    # O/U 2.5
                    m_ou = next((m for m in o.get('markets', []) if m.get('id') == 18 and 'total=2.5' in m.get('specifiers', '')), None)
                    ou_over = ou_under = 0.0
                    if m_ou:
                        try:
                            ou_over = float(next(oc['odds'] for oc in m_ou.get('outcomes', []) if oc['id'] == '12'))
                            ou_under = float(next(oc['odds'] for oc in m_ou.get('outcomes', []) if oc['id'] == '13'))
                        except: pass
                        
                    # Target Results
                    full_time = r.get('fullTime', '0:0')
                    try:
                        h_score = int(full_time.split(':')[0])
                        a_score = int(full_time.split(':')[1])
                    except:
                        h_score, a_score = 0, 0
                    actual_1x2 = get_outcome(h_score, a_score)
                    total_goals = h_score + a_score
                    actual_ou = "OVER" if total_goals > 2.5 else "UNDER"
                    
                    database.append({
                        "fixture": fixture,
                        "season": key[0],
                        "day": key[1],
                        "h_odds": h_odds,
                        "d_odds": d_odds,
                        "a_odds": a_odds,
                        "o_odds": ou_over,
                        "u_odds": ou_under,
                        "actual_1x2": actual_1x2,
                        "actual_ou": actual_ou,
                        "total_goals": total_goals,
                        "score": full_time
                    })
                    
    with open('backend/resources/rng_model.json', 'w', encoding='utf-8') as f:
        json.dump(database, f, indent=2)
        
    print(f"✅ Successfully compiled {len(database)} exact Match Data points into the RNG Model Database.")
    print("Database saved at: backend/resources/rng_model.json")

if __name__ == "__main__":
    main()
