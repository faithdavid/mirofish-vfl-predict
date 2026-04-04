import re
import sys
import os

def parse_odds_text(text):
    """
    Parses pasted text containing lines like:
    12,Newcastle,,,,,,
    10,Brighton,2.55,3.45,2.50,2.5,2.20,1.60
    ,+33 >,,,,,,
    """
    matches = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    current_home = None
    
    for line in lines:
        if line.startswith(',+'):
            continue
            
        parts = line.split(',')
        if len(parts) >= 2:
            team_pos = parts[0]
            team_name = parts[1]
            
            # Check if this is an odds line (has more than 2 parts and part 2 is not empty)
            if len(parts) >= 5 and parts[2] != '':
                try:
                    h_odds = float(parts[2])
                    d_odds = float(parts[3])
                    a_odds = float(parts[4])
                    
                    if current_home:
                        matches.append({
                            'home': current_home,
                            'away': team_name,
                            'odds': {'1': h_odds, 'X': d_odds, '2': a_odds}
                        })
                        current_home = None
                except ValueError:
                    pass
            else:
                # Typically the home team line
                current_home = team_name
                
    return matches

def calculate_predictions(matches):
    results = []
    for m in matches:
        h_odds = m['odds']['1']
        d_odds = m['odds']['X']
        a_odds = m['odds']['2']
        
        # Calculate exactly what the bookmaker's overround (implied probability) is for this specific match
        implied_prob = (1 / h_odds) + (1 / d_odds) + (1 / a_odds)
        
        # The true bias factor is the inverse of the implied probability
        exact_bias = 1 / implied_prob
        
        # Calculate the mathematically pure True Probabilities (summing exactly to 1.0)
        hp = (1 / h_odds) * exact_bias
        dp = (1 / d_odds) * exact_bias
        ap = (1 / a_odds) * exact_bias
        
        probs = [hp, dp, ap]
        best_idx = probs.index(max(probs))
        pred = ["1", "X", "2"][best_idx]
        
        results.append({
            'fixture': f"{m['home']} vs {m['away']}",
            'odds': f"H:{h_odds} D:{d_odds} A:{a_odds}",
            'prediction': pred,
            'true_probs': f"H:{hp:.1%} D:{dp:.1%} A:{ap:.1%}",
            'bias_factor': f"{exact_bias:.4f}"
        })
    return results

def generate_reality_seed(predictions, raw_table=""):
    seed = "# VIRTUAL SPORTS REALITY SEED\n\n"
    seed += "## LEAGUE STATE (Context)\n"
    seed += "```text\n"
    seed += raw_table if raw_table else "Table data not provided."
    seed += "\n```\n\n"
    
    seed += "## PRE-MATCH ODDS & DYNAMIC TRUE PROBABILITIES\n"
    seed += "The following probabilities are calculated by deriving the exact mathematical bias (inverse overround) injected into each specific fixture's raw odds.\n\n"
    
    seed += "| Fixture | Raw Odds | System Bias | Predicted True Value | True Probabilities |\n"
    seed += "|---|---|---|---|---|\n"
    for p in predictions:
        seed += f"| {p['fixture']} | {p['odds']} | {p['bias_factor']} | **{p['prediction']}** | {p['true_probs']} |\n"
        
    seed += "\n## MIROFISH DIRECTIVES\n"
    seed += "> **To the System Auditors:** Review the league table context against these mathematically pure 'True Probabilities'. The system bias varies slightly per match—identify any anomalies where the mathematical prediction drastically contradicts team form (e.g., win streaks/slumps), indicating a potential premeditated 'System Reset'.\n"
    
    return seed

def process_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extremely rough split assuming user pastes table then odds, or just odds
    table_section = ""
    odds_section = content
    
    if ",,1,X,2" in content:
        parts = content.split(",,1,X,2")
        table_section = parts[0].strip()
        odds_section = parts[1].strip()
        
    matches = parse_odds_text(odds_section)
    if not matches:
        print("No valid match odds found in input.")
        return
        
    preds = calculate_predictions(matches)
    seed_md = generate_reality_seed(preds, table_section)
    
    out_file = "mirofish_daily_seed.md"
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(seed_md)
        
    print(f"\n✅ Generated Reality Seed: {out_file}")
    print("This file is ready to be pasted into the MiroFish UI for Swarm Intelligence simulation.\n")
    
    print("--- QUICK PREDICTIONS ---")
    for p in preds:
        print(f"{p['fixture']:<30} | RAW: {p['odds']:<20} | PRED: {p['prediction']}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        process_file(sys.argv[1])
    else:
        print("Usage: python scripts/generate_daily_seed.py <input_text_file>")
