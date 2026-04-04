import json
import re
import os

def parse_blocks(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'===== MATCH #\d+', content)
    found = []
    for b in blocks:
        m = re.search(r'\{[\s\S]*\}', b)
        if m:
            try:
                data = json.loads(m.group())
                top_s = data.get('data', {}).get('seasonId')
                top_d = data.get('data', {}).get('matchDay')
                if "data" in data and "events" in data["data"]:
                    for e in data["data"]["events"]:
                        e['file_season'] = top_s
                        e['file_day'] = top_d
                        found.append(e)
            except: pass
    return found

def main():
    o_file = "extracted_odds/www.msport12c_odds.txt"
    r_file = "extracted_results/results s4292www.msport_results.txt"
    
    print(f"DEBUG: Comparing {o_file} and {r_file}")
    
    odds = parse_blocks(o_file)
    results = parse_blocks(r_file)
    
    print(f"DEBUG: Found {len(odds)} odds events and {len(results)} results events.")
    
    # Check first odds event metadata
    if odds:
        e = odds[0]
        print(f"DEBUG: Odds[0] metadata: seasonId={e.get('seasonId')}, matchDay={e.get('matchDay')}, file_season={e.get('file_season')}, file_day={e.get('file_day')}")
        print(f"DEBUG: Odds[0] teams: '{e.get('homeTeam')}' vs '{e.get('awayTeam')}'")
        
    # Check first results event
    if results:
        e = results[0]
        print(f"DEBUG: Result[0] metadata: seasonId={e.get('seasonId')}, matchDay={e.get('matchDay')}, file_season={e.get('file_season')}, file_day={e.get('file_day')}")
        print(f"DEBUG: Result[0] teams: '{e.get('homeTeam')}' vs '{e.get('awayTeam')}'")

    # Try matching one specific team pair manually
    target_home = "Manchester Blue"
    o_match = [e for e in odds if e.get('homeTeam') == target_home and (str(e.get('matchDay')) == '8' or str(e.get('file_day')) == '8')]
    r_match = [e for e in results if e.get('homeTeam') == target_home and (str(e.get('matchDay')) == '8' or str(e.get('file_day')) == '8')]
    
    print(f"DEBUG: Matches for '{target_home}' on Day 8 - Odds: {len(o_match)}, Results: {len(r_match)}")

if __name__ == "__main__":
    main()
