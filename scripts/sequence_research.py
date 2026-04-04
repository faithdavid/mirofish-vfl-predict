import json
import os
import sys
from collections import defaultdict

ROOT = os.getcwd()
RESULTS_DIR = os.path.join(ROOT, 'extracted_results')

def find_block_repeats():
    print("RESEARCH: CRACKING THE FULL MATCHDAY BLOCK")
    print("=" * 72)
    
    # 1. Load results and group by (Season, Day)
    import predict_v3 as v3
    results = v3.parse_all_results(RESULTS_DIR)
    
    blocks = defaultdict(list)
    for r in results:
        key = (str(r.get('season', '')), str(r.get('day', '')))
        blocks[key].append(r)
    
    print(f"Found {len(blocks)} complete MatchDay blocks in history.")
    
    # 2. Stringify each block's outcome sequence (e.g. H-D-A-H-H-A-D-D-H-A)
    # and its scoreline sequence (e.g. 1:0-2:2-0:1...)
    sequences = defaultdict(list)
    score_sequences = defaultdict(list)
    
    for (season, day), matches in blocks.items():
        if len(matches) != 8: # msport usually has 8 or 10
            continue
            
        # Sort matches by home team to ensure consistent ordering
        matches.sort(key=lambda x: x['home'])
        
        outcome_seq = "-".join([m['outcome'] for m in matches])
        score_seq   = "-".join([f"{m['h']}:{m['a']}" for m in matches])
        
        sequences[outcome_seq].append((season, day))
        score_sequences[score_seq].append((season, day))

    # 3. Analyze Repeats
    repeat_outcomes = {k: v for k, v in sequences.items() if len(v) > 1}
    repeat_scores   = {k: v for k, v in score_sequences.items() if len(v) > 1}
    
    print(f"\nOUTCOME SEQUENCE REPEATS: {len(repeat_outcomes)}")
    print(f"SCORELINE SEQUENCE REPEATS: {len(repeat_scores)}")
    
    if repeat_scores:
        print("\n[DETECTED] EXACT FULL MATCHDAY SCORELINE REPEATS:")
        for seq, occurrences in list(repeat_scores.items())[:5]:
            print(f"  Sequence: {seq}")
            print(f"  Occurred in Seasons/Days: {occurrences}")

    # 4. Scoreline Determinism per Signature
    print("\n--- SCORELINE DETERMINISM PER SIGNATURE ---")
    sig_scores = defaultdict(lambda: defaultdict(int))
    for r in results:
        # Simple sig: Teams + Odds (rounded)
        sig = f"{r['home']}|{r['away']}|{r.get('oh',0)}|{r.get('od',0)}|{r.get('oa',0)}"
        score = f"{r['h']}:{r['a']}"
        sig_scores[sig][score] += 1
        
    perfect_scores = 0
    total_with_data = 0
    for sig, scores in sig_scores.items():
        total_sig = sum(scores.values())
        if total_sig >= 5:
            total_with_data += 1
            best_score = max(scores, key=scores.get)
            if scores[best_score] == total_sig:
                perfect_scores += 1
                
    print(f"Signatures with 5+ matches: {total_with_data}")
    print(f"Signatures with 100% identical SCORELINE: {perfect_scores}")

if __name__ == '__main__':
    find_block_repeats()
