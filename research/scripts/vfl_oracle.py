import sys
import math

def calculate_true_probs(o1, o2, o3=None):
    if o3:
        # 3-way market (1X2)
        implied_prob = (1/o1) + (1/o2) + (1/o3)
        exact_bias = 1 / implied_prob
        
        p1 = (1/o1) * exact_bias
        p2 = (1/o2) * exact_bias
        p3 = (1/o3) * exact_bias
        
        return exact_bias, [p1, p2, p3]
    else:
        # 2-way market (Over/Under)
        implied_prob = (1/o1) + (1/o2)
        exact_bias = 1 / implied_prob
        
        p1 = (1/o1) * exact_bias
        p2 = (1/o2) * exact_bias
        
        return exact_bias, [p1, p2]

def print_header():
    print("=" * 60)
    print("         🔮 VFL MATCH ORACLE (True Probability) 🔮")
    print("=" * 60)
    print("This tool strips the bookmaker's Overround to find the")
    print("Exact Systemic Bias and exposes the hidden RNG probabilities.\n")

def get_float_list(prompt):
    while True:
        try:
            val = input(prompt).strip()
            if not val: return None
            # Allow splitting by spaces, commas, or tabs
            val = val.replace(',', ' ').replace('\t', ' ')
            parts = [float(x) for x in val.split() if x.strip()]
            if parts: return parts
        except ValueError:
            print("[!] Invalid input. Please enter numbers separated by spaces.")

def main():
    print_header()
    
    while True:
        try:
            print("\n----- NEW MATCH PREDICTION -----")
            print("Type 'q' or 'quit' at any prompt to exit.\n")
            
            fixture = input("Enter Matchup (e.g. Chelsea vs Arsenal) or press Enter to skip: ").strip()
            if fixture.lower() in ['q', 'quit', 'exit']: break
            
            # --- 1X2 MARKET ---
            print("\n[1] Match Winner Market (1X2)")
            odds_1x2 = get_float_list("Paste Home, Draw, Away Odds (e.g. '2.40 3.40 2.70'): ")
            if not odds_1x2:
                print("Skipping match...")
                continue
            if len(odds_1x2) != 3:
                print("[!] Error: You must enter exactly 3 odds for the 1X2 market.")
                continue
                
            h_odds, d_odds, a_odds = odds_1x2
            bias_1x2, probs_1x2 = calculate_true_probs(h_odds, d_odds, a_odds)
            
            hp, dp, ap = probs_1x2
            labels = ["HOME", "DRAW", "AWAY"]
            best_idx = probs_1x2.index(max(probs_1x2))
            pred_1x2 = labels[best_idx]
            
            # --- OVER/UNDER MARKET ---
            print("\n[2] Goal Count Market (Over/Under 2.5)")
            odds_ou = get_float_list("Paste Over, Under Odds (e.g. '2.30 1.55') or press Enter to skip: ")
            
            pred_ou = None
            if odds_ou and len(odds_ou) == 2:
                o_odds, u_odds = odds_ou
                bias_ou, probs_ou = calculate_true_probs(o_odds, u_odds)
                
                op, up = probs_ou
                pred_ou = "OVER 2.5" if op > up else "UNDER 2.5"
                prob_ou_val = max(op, up)
            elif odds_ou:
                print("[!] Warning: You must enter exactly 2 odds for Over/Under. Skipping O/U prediction.")

            # --- OUTPUT REPORT ---
            print("\n" + "="*50)
            if fixture: print(f" MATCH: {fixture}")
            print(f" BOOKMAKER BIAS (1X2): {bias_1x2:.4f} (Overround: {(1/bias_1x2 - 1)*100:.2f}%)")
            
            print("\n 🏆 MATCH WINNER PREDICTION:")
            print(f"    Home Win (1): {hp*100:05.2f}% (Raw: {h_odds})")
            print(f"    Draw     (X): {dp*100:05.2f}% (Raw: {d_odds})")
            print(f"    Away Win (2): {ap*100:05.2f}% (Raw: {a_odds})")
            
            confidence_note = "🔥 HIGH CONFIDENCE (>70%) 🔥" if max(probs_1x2) > 0.70 else "Regular Value"
            print(f"\n    >> PREDICTION: {pred_1x2}  [{confidence_note}]")
            
            if pred_ou:
                print(f"\n ⚽ GOAL COUNT (O/U 2.5) PREDICTION:")
                print(f"    Over  2.5: {op*100:05.2f}% (Raw: {o_odds})")
                print(f"    Under 2.5: {up*100:05.2f}% (Raw: {u_odds})")
                
                conf_ou = "🔥 HIGH CONFIDENCE (>60%) 🔥" if max(probs_ou) > 0.60 else "Regular Value"
                print(f"\n    >> PREDICTION: {pred_ou}  [{conf_ou}]")
                
            print("="*50)
            
        except KeyboardInterrupt:
            break
            
    print("\nExiting VFL Oracle. Good luck!")

if __name__ == "__main__":
    main()
