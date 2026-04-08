import json
import os
import re

HAR_DIR = 'ANalysis'

def find_raw_json(target_season, target_day, target_home, target_away):
    print(f"SEARCHING FOR {target_home} vs {target_away} (Season: {target_season}, Day: {target_day})")
    print("-" * 60)
    
    for fname in os.listdir(HAR_DIR):
        if not fname.endswith('.har'): continue
        path = os.path.join(HAR_DIR, fname)
        
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # Find all occurrences of the seasonId
                for sid_match in re.finditer(f'\"seasonId\":\"{target_season}\"', content):
                    # Within the same response block (approx 10k chars), look for matchDay and Teams
                    start = max(0, sid_match.start() - 1000)
                    end = min(len(content), sid_match.end() + 15000)
                    chunk = content[start:end]
                    
                    if f'\"matchDay\":{target_day}' in chunk or f'\"matchDay\":\"{target_day}\"' in chunk:
                        if target_home.lower() in chunk.lower() and target_away.lower() in chunk.lower():
                            print(f"[FOUND] In {fname}")
                            # Extract the full JSON object for the event
                            # Try to find the specific event object
                            event_pattern = re.compile(r'\{[^{}]*\"homeTeam\":\"'+target_home+r'\"[^{}]*\"awayTeam\":\"'+target_away+r'\"[^{}]*\}', re.IGNORECASE)
                            event_match = event_pattern.search(chunk)
                            if event_match:
                                return event_match.group(0), chunk
        except Exception as e:
            # print(f"Error reading {fname}: {e}")
            pass
    return None, None

def main():
    # Case 1: Season 3072444 Day 30 (HOME WIN)
    # Case 2: Season 3073372 Day 30 (DRAW)
    
    print("VFL METADATA FORENSICS: CASE STUDY 1")
    res1, chunk1 = find_raw_json('vf:season:3072444', '30', 'Crystal Palace', 'Aston Villa')
    
    print("\nVFL METADATA FORENSICS: CASE STUDY 2")
    res2, chunk2 = find_raw_json('vf:season:3073372', '30', 'Crystal Palace', 'Aston Villa')
    
    if res1 and res2:
        print("\n" + "=" * 80)
        print("COMPARING RAW METADATA")
        print("=" * 80)
        
        # Parse them
        j1 = json.loads(res1)
        j2 = json.loads(res2)
        
        print("\nBLOCK 1 (HOME WIN):")
        print(json.dumps(j1, indent=2))
        
        print("\nBLOCK 2 (DRAW):")
        print(json.dumps(j2, indent=2))
        
        # Now look for the DIFFERENCE in the parent chunk (headers, IDs, etc)
        print("\nSEARCHING FOR DIFFERENCES IN PARENT CONTEXT...")
        # (Compare sequence of match IDs, timestamps etc)
        
    else:
        print("\n[ERROR] Both cases not found. Check if the season IDs are correct in the HAR files.")

if __name__ == '__main__':
    main()
