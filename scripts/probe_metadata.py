import json
import re
import os

HAR_DIR = 'ANalysis'

def probe_collision_json():
    print("PROBING RAW HAR JSON FOR CRYSTAL PALACE vs ASTON VILLA (4.2/3.6/1.8)")
    print("=" * 80)
    
    # We are looking for Crystal Palace vs Aston Villa with 4.2 odds
    # Pattern to find the match block and its parent data
    pattern = re.compile(r'CRYSTAL PALACE', re.IGNORECASE)
    
    found_blocks = []
    
    for fname in os.listdir(HAR_DIR):
        if not fname.endswith('.har'): continue
        path = os.path.join(HAR_DIR, fname)
        
        print(f"Scanning {fname}...")
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # Scan for the team name
                for match in re.finditer(r'\"homeTeam\":\"Crystal Palace\"', content, re.IGNORECASE):
                    # Found a match, now grab the surrounding JSON block (approx 5000 chars)
                    start = max(0, match.start() - 1000)
                    end = min(len(content), match.end() + 4000)
                    chunk = content[start:end]
                    
                    # Also look for the seasonId/matchDay which is usually higher up in the same response
                    # or in the queryString
                    season_match = re.search(r'\"seasonId\":\"(vf:season:\d+)\"', chunk)
                    day_match = re.search(r'\"matchDay\":(\d+)', chunk)
                    
                    if season_match and day_match:
                        sid = season_match.group(1)
                        md = day_match.group(1)
                        
                        # Only keep if it matches our collision seasons/days
                        # (Adjusted to capture a few different examples)
                        found_blocks.append({
                            'season': sid,
                            'day': md,
                            'file': fname,
                            'raw': chunk[:2000] # Representative slice
                        })
        except Exception as e:
            print(f"Error reading {fname}: {e}")

    # Compare the blocks
    print(f"\nFound {len(found_blocks)} potential blocks.")
    for i, b in enumerate(found_blocks[:3]): # Show a few for comparison
        print(f"\n--- BLOCK {i+1} ({b['season']} MD{b['day']}) ---")
        print(f"Source: {b['file']}")
        # Look for unique markers like ID strings
        ids = re.findall(r'\"[a-zA-Z0-9_\-]{20,}\"', b['raw'])
        print(f"Unique IDs found: {ids[:5]}")
        print(f"Sample: {b['raw'][:500]}...")

if __name__ == '__main__':
    probe_collision_json()
