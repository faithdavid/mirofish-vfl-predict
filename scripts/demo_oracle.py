import json
import re
from vfl_oracle import calculate_true_probs, print_header

def test_oracle():
    content = open('extracted_odds/www.msport10_odds.txt', encoding='utf-8').read()
    blocks = re.split(r'===== MATCH #\d+', content)
    for b in blocks:
        m = re.search(r'\{[\s\S]*\}', b)
        if m:
            try:
                data = json.loads(m.group())
                e = data['data']['events'][0]
                break
            except: pass

    fixture = f"{e['homeTeam']} vs {e['awayTeam']}"

    m_1x2 = next((m for m in e['markets'] if m['id'] == 1), None)
    o1 = float(next(o['odds'] for o in m_1x2['outcomes'] if o['id'] == '1'))
    o2 = float(next(o['odds'] for o in m_1x2['outcomes'] if o['id'] == '2'))
    o3 = float(next(o['odds'] for o in m_1x2['outcomes'] if o['id'] == '3'))

    m_ou = next((m for m in e['markets'] if m['id'] == 18 and 'total=2.5' in m['specifiers']), None)
    ou_over = float(next(o['odds'] for o in m_ou['outcomes'] if o['id'] == '12'))
    ou_under = float(next(o['odds'] for o in m_ou['outcomes'] if o['id'] == '13'))

    print_header()
    print(f'\n MATCH: {fixture}')

    bias_1x2, p1x2 = calculate_true_probs(o1, o2, o3)
    labels = ['HOME', 'DRAW', 'AWAY']
    best_1x2 = labels[p1x2.index(max(p1x2))]

    print(f'\n BOOKMAKER BIAS (1X2): {bias_1x2:.4f}')
    print(f' 🏆 MATCH WINNER PREDICTION:')
    print(f'    Home Win: {p1x2[0]*100:05.2f}% (Raw: {o1})')
    print(f'    Draw:     {p1x2[1]*100:05.2f}% (Raw: {o2})')
    print(f'    Away Win: {p1x2[2]*100:05.2f}% (Raw: {o3})')
    print(f'    >> PREDICTION: {best_1x2}')

    bias_ou, pou = calculate_true_probs(ou_over, ou_under)
    best_ou = 'OVER 2.5' if pou[0] > pou[1] else 'UNDER 2.5'

    print(f'\n ⚽ GOAL COUNT (O/U 2.5) PREDICTION:')
    print(f'    Over  2.5: {pou[0]*100:05.2f}% (Raw: {ou_over})')
    print(f'    Under 2.5: {pou[1]*100:05.2f}% (Raw: {ou_under})')
    print(f'    >> PREDICTION: {best_ou}')

if __name__ == '__main__':
    test_oracle()
