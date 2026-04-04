import json

d = json.load(open('master_rng_signatures.json'))

scoreboard = []
for k, v in d.items():
    if v['total'] < 3:
        continue
    c = v['counts']
    best_outcome = max(c, key=c.get)
    best_pct = c[best_outcome] / v['total']
    scoreboard.append((k, best_outcome, best_pct, v['total'], c))

scoreboard.sort(key=lambda x: (-x[2], -x[3]))

print('TOP 30 MOST PREDICTABLE SIGNATURES:')
print(f"{'Signature':<48} {'Pick':<6} {'Hit%':<7} {'N':<4} Counts")
print('-' * 95)
for sig, pick, pct, n, counts in scoreboard[:30]:
    parts = sig.split('|')
    label = f"{parts[0]} v {parts[1]} ({parts[2]}/{parts[3]}/{parts[4]})"
    print(f"{label:<48} {pick:<6} {pct*100:.0f}%    {n:<4} {counts}")

# Odds-bracket analysis
print("\n\n=== ODDS BRACKET ANALYSIS ===")
brackets = {}
for k, v in d.items():
    parts = k.split('|')
    oh, od, oa = float(parts[2]), float(parts[3]), float(parts[4])
    fav_odds = min(oh, oa)
    
    if fav_odds <= 1.5:
        bracket = "Heavy Fav (<=1.5)"
    elif fav_odds <= 2.0:
        bracket = "Moderate Fav (1.5-2.0)"
    elif fav_odds <= 2.5:
        bracket = "Slight Fav (2.0-2.5)"
    else:
        bracket = "Balanced (>2.5)"
    
    if bracket not in brackets:
        brackets[bracket] = {'HOME': 0, 'DRAW': 0, 'AWAY': 0, 'total': 0}
    c = v['counts']
    brackets[bracket]['HOME'] += c.get('HOME', 0)
    brackets[bracket]['DRAW'] += c.get('DRAW', 0)
    brackets[bracket]['AWAY'] += c.get('AWAY', 0)
    brackets[bracket]['total'] += v['total']

for bracket, stats in sorted(brackets.items()):
    t = stats['total']
    print(f"\n{bracket} ({t} matches):")
    print(f"  HOME: {stats['HOME']/t*100:.1f}%  DRAW: {stats['DRAW']/t*100:.1f}%  AWAY: {stats['AWAY']/t*100:.1f}%")
