from vfl_oracle import calculate_true_probs

matches = [
    ('Liverpool vs Crystal Palace', [1.22, 5.75, 11.0], [1.65, 2.05], '2.5'),
    ('Chelsea vs Wolverhampton', [1.45, 4.9, 5.75], [2.15, 1.65], '3.5'),
    ('Brighton vs London Guns', [3.15, 3.6, 2.05], [1.75, 1.95], '2.5'),
    ('Newcastle vs Bournemouth', [1.9, 3.6, 3.65], [2.05, 1.7], '2.5'),
    ('Everton vs Tottenham', [2.75, 3.15, 2.5], [1.5, 2.4], '1.5'),
    ('Manchester Blue vs Leeds', [1.3, 5.0, 8.25], [1.7, 2.05], '2.5'),
    ('Manchester Red vs Fulham', [1.3, 4.45, 10.25], [2.1, 1.65], '2.5'),
    ('West Ham vs Aston Villa', [2.85, 3.6, 2.2], [2.05, 1.65], '2.5')
]

output_lines = []
output_lines.append('============================================================')
output_lines.append('          LIVE MATCH DAY 12 PREDICTIONS')
output_lines.append('============================================================')

for fix, odds_1x2, odds_ou, outype in matches:
    output_lines.append(f'\n MATCH: {fix}')
    
    b1, p1x2 = calculate_true_probs(*odds_1x2)
    labels = ['HOME (1)', 'DRAW (X)', 'AWAY (2)']
    b1_idx = p1x2.index(max(p1x2))
    pred_1x2 = labels[b1_idx]
    conf_1x2 = '🔥 HIGH CONFIDENCE 🔥' if max(p1x2) > 0.70 else ''
    
    output_lines.append(f' Bookmaker Bias: {b1:.4f}')
    output_lines.append(f'   Home: {p1x2[0]*100:05.2f}% | Draw: {p1x2[1]*100:05.2f}% | Away: {p1x2[2]*100:05.2f}%')
    output_lines.append(f'   >> PREDICTION: {pred_1x2}  {conf_1x2}')
    
    b2, pou = calculate_true_probs(*odds_ou)
    ou_labels = [f'OVER {outype}', f'UNDER {outype}']
    b2_idx = pou.index(max(pou))
    pred_ou = ou_labels[b2_idx]
    conf_ou = '🔥 HIGH CONFIDENCE 🔥' if max(pou) > 0.60 else ''
    
    output_lines.append(f'   Over {outype}: {pou[0]*100:05.2f}% | Under {outype}: {pou[1]*100:05.2f}%')
    output_lines.append(f'   >> GOALS PRED: {pred_ou}  {conf_ou}')

with open('live_preds.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output_lines))
