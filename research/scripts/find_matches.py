import os
import json
import re

def get_metadata(directory):
    pairs = {} # (season, day) -> filename
    for filename in os.listdir(directory):
        if not filename.endswith('.txt'): continue
        path = os.path.join(directory, filename)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Look for seasonId and matchDay
        seasons = re.findall(r'"seasonId":\s*"([^"]+)"', content)
        days = re.findall(r'"matchDay":\s*(\d+)', content)
        
        if seasons and days:
            # Note: A file might contain multiple days, but usually one primary one from the query
            for s, d in zip(seasons, days):
                pairs[(s.split(':')[-1], d)] = filename
    return pairs

def main():
    print("Scanning Extracted Data for Matches...")
    odds_pairs = get_metadata("extracted_odds")
    results_pairs = get_metadata("extracted_results")
    
    match_count = 0
    print(f"\n{'Season':<15} | {'Day':<5} | {'Odds File':<30} | {'Results File':<30}")
    print("-" * 90)
    
    for (s, d), r_file in results_pairs.items():
        if (s, d) in odds_pairs:
            o_file = odds_pairs[(s, d)]
            print(f"{s:<15} | {d:<5} | {o_file:<30} | {r_file:<30}")
            match_count += 1
            
    if match_count == 0:
        print("\nNo matching (Season, Day) pairs found yet.")
    else:
        print(f"\nFound {match_count} matching pairs for backtesting.")

if __name__ == "__main__":
    main()
