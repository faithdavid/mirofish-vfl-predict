import json
import os

# Load H2H data
h2h_path = 'h2h_model.json'
with open(h2h_path, 'r', encoding='utf-8') as f:
    h2h_db = json.load(f)

# Input data for MD13
events = [
    {'home': 'Leeds', 'away': 'Tottenham', 'odds': {'h': 4.00, 'd': 3.55, 'a': 1.80}},
    {'home': 'Aston Villa', 'away': 'Everton', 'odds': {'h': 1.95, 'd': 2.85, 'a': 4.65}},
    {'home': 'Manchester Red', 'away': 'Manchester Blue', 'odds': {'h': 2.20, 'd': 3.65, 'a': 2.85}},
    {'home': 'Brighton', 'away': 'Wolverhampton', 'odds': {'h': 1.95, 'd': 3.60, 'a': 3.50}},
    {'home': 'London Guns', 'away': 'Bournemouth', 'odds': {'h': 1.35, 'd': 4.65, 'a': 7.75}},
    {'home': 'Crystal Palace', 'away': 'Fulham', 'odds': {'h': 2.10, 'd': 3.35, 'a': 3.30}},
    {'home': 'West Ham', 'away': 'Newcastle', 'odds': {'h': 1.60, 'd': 4.65, 'a': 4.00}},
    {'home': 'Liverpool', 'away': 'Chelsea', 'odds': {'h': 2.05, 'd': 4.10, 'a': 2.85}}
]

results = []

for e in events:
    h_name = e['home'].upper()
    a_name = e['away'].upper()
    key = f"{h_name} VS {a_name}"
    stats = h2h_db.get(key)
    reversed = False
    if not stats:
        key = f"{a_name} VS {h_name}"
        stats = h2h_db.get(key)
        reversed = True
        
    if stats:
        h_rate = stats.get('HOME_RATE', stats.get('HOME_WIN', 0)/stats.get('TOTAL', 1))
        d_rate = stats.get('DRAW_RATE', stats.get('DRAW', 0)/stats.get('TOTAL', 1))
        a_rate = stats.get('AWAY_RATE', stats.get('AWAY_WIN', 0)/stats.get('TOTAL', 1))
        if reversed: h_rate, a_rate = a_rate, h_rate
        
        results.append({
            'fixture': f"{h_name} vs {a_name}",
            'odds': e['odds'],
            'h2h': {'h': h_rate, 'd': d_rate, 'a': a_rate, 'total': stats['TOTAL']},
            'ev': {'h': h_rate / (1/e['odds']['h']) - 1, 'd': d_rate / (1/e['odds']['d']) - 1, 'a': a_rate / (1/e['odds']['a']) - 1}
        })

print(json.dumps(results, indent=2))
