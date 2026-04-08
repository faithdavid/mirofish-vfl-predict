import argparse
import json

def calculate_implied_probability(decimal_odds):
    """Convert decimal odds to implied probability."""
    if decimal_odds <= 0:
        return 0
    return 1 / decimal_odds

def apply_bias_correction(implied_prob, bias_factor=0.8):
    """
    Apply a bias correction to the implied probability.
    The theory is that the house injects a bias (margin) to lower the payout.
    """
    # Simple model: True Prob = Implied Prob * Bias Factor
    # If bias is 0.8, it means the 'Fair' probability is lower than what the odds suggest,
    # OR that the house has inflated the odds to hide a 20% edge.
    # User's mention: "bias that i calculated once to be around 0.8... injection in the odds"
    
    # If the bias is "injected in the odds" at 0.8, we might treat it as a multiplier
    # for the odds themselves or a divisor for the probability.
    
    true_prob = implied_prob * bias_factor
    return true_prob

def analyze_match(home_odds, draw_odds, away_odds, bias_factor=0.8):
    """Analyze a single match with three outcomes."""
    outcomes = ["Home", "Draw", "Away"]
    odds = [home_odds, draw_odds, away_odds]
    
    results = []
    total_implied = 0
    
    for label, od in zip(outcomes, odds):
        implied = calculate_implied_probability(od)
        total_implied += implied
        true_p = apply_bias_correction(implied, bias_factor)
        
        results.append({
            "outcome": label,
            "odds": od,
            "implied_prob": round(implied * 100, 2),
            "bias_adjusted_prob": round(true_p * 100, 2)
        })
    
    # The 'Overround' or 'Juice' is (Total Implied - 100%)
    overround = (total_implied - 1.0) * 100
    
    return {
        "outcomes": results,
        "market_overround_percent": round(overround, 2),
        "applied_bias_factor": bias_factor
    }

def main():
    parser = argparse.ArgumentParser(description="Analyze Virtual Sports RNG Bias")
    parser.add_argument("--home", type=float, help="Home win decimal odds")
    parser.add_argument("--draw", type=float, help="Draw decimal odds")
    parser.add_argument("--away", type=float, help="Away win decimal odds")
    parser.add_argument("--bias", type=float, default=0.8, help="Known bias factor (default 0.8)")
    
    args = parser.parse_args()
    
    if args.home and args.away:
        # If no draw odds provided (e.g. tennis), use 0 or handle accordingly
        draw = args.draw if args.draw else 0
        data = analyze_match(args.home, draw, args.away, args.bias)
        
        print("\n=== Virtual Sports Bias Analysis ===")
        print(f"Known Bias Factor: {data['applied_bias_factor']}")
        print(f"Market Overround: {data['market_overround_percent']}%\n")
        
        for res in data['outcomes']:
            if res['odds'] > 0:
                print(f"{res['outcome']}:")
                print(f"  Odds: {res['odds']}")
                print(f"  Market Prob: {res['implied_prob']}%")
                print(f"  Bias-Adjusted Prob: {res['bias_adjusted_prob']}%")
    else:
        print("Example Usage: python analyze_rng_bias.py --home 1.5 --draw 3.4 --away 6.5 --bias 0.8")

if __name__ == "__main__":
    main()
