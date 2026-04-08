import json
import os

# Load H2H data
h2h_path = 'h2h_model.json'
if not os.path.exists(h2h_path):
    print(f"Error: {h2h_path} not found.")
    exit(1)

with open(h2h_path, 'r', encoding='utf-8') as f:
    h2h_db = json.load(f)

# Input data from user JSON
events = [
    {'home': 'Fulham', 'away': 'Liverpool', 'odds': {'h': 5.25, 'd': 3.75, 'a': 1.60}},
    {'home': 'London Guns', 'away': 'Crystal Palace', 'odds': {'h': 1.45, 'd': 4.55, 'a': 6.25}},
    {'home': 'Chelsea', 'away': 'Manchester Red', 'odds': {'h': 2.55, 'd': 3.85, 'a': 2.35}},
    {'home': 'Leeds', 'away': 'West Ham', 'odds': {'h': 2.95, 'd': 3.25, 'a': 2.35}},
    {'home': 'Aston Villa', 'away': 'Bournemouth', 'odds': {'h': 1.40, 'd': 4.35, 'a': 7.75}},
    {'home': 'Manchester Blue', 'away': 'Tottenham', 'odds': {'h': 1.70, 'd': 4.15, 'a': 3.95}},
    {'home': 'Everton', 'away': 'Newcastle', 'odds': {'h': 1.70, 'd': 3.40, 'a': 5.00}},
    {'home': 'Wolverhampton', 'away': 'Brighton', 'odds': {'h': 2.10, 'd': 3.60, 'a': 3.10}}
]

results = []

for e in events:
    h_name = e['home'].upper()
    a_name = e['away'].upper()
    
    # Try forward key
    key = f"{h_name} VS {a_name}"
    stats = h2h_db.get(key)
    reversed = False
    
    if not stats:
        # Try reversed key
        key = f"{a_name} VS {h_name}"
        stats = h2h_db.get(key)
        reversed = True
        
    if stats:
        h_rate = stats.get('HOME_RATE', stats.get('HOME_WIN', 0)/stats.get('TOTAL', 1))
        d_rate = stats.get('DRAW_RATE', stats.get('DRAW', 0)/stats.get('TOTAL', 1))
        a_rate = stats.get('AWAY_RATE', stats.get('AWAY_WIN', 0)/stats.get('TOTAL', 1))
        
        if reversed:
            h_rate, a_rate = a_rate, h_rate
            
        # Calculate EV
        # Implied = 1/odds
        implied_h = 1.0 / e['odds']['h']
        implied_d = 1.0 / e['odds']['d']
        implied_a = 1.0 / e['odds']['a']
        
        results.append({
            'fixture': f"{h_name} vs {a_name}",
            'odds': e['odds'],
            'h2h': {'h': h_rate, 'd': d_rate, 'a': a_rate, 'total': stats['TOTAL']},
            'ev': {
                'h': h_rate / implied_h - 1,
                'd': d_rate / implied_d - 1,
                'a': a_rate / implied_a - 1
            }
        })
    else:
        results.append({
            'fixture': f"{h_name} vs {a_name}",
            'error': 'H2H stats not found'
        })

print(json.dumps(results, indent=2))
