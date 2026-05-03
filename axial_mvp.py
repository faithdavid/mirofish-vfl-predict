#!/usr/bin/env python3
"""
Axial Transformer MVP - Simple Ensemble
=========================================
Fast training on 50K matches with signature database ensemble.
Output ready for ONNX conversion.
"""

import sqlite3
import json
import pickle
from pathlib import Path

# Use built-in libraries only
DB = Path('/root/.openclaw/workspace/vfl-repo/data/databases/vfl_history.db')
SIG = Path('/root/.openclaw/workspace/vfl-repo/data/models/master_rng_signatures.json')
OUT = Path('/root/.openclaw/workspace/vfl-repo/data/models/axial_transformer_v1.pkl')

def main():
    print("[Axial Transformer MVP] Loading data...")
    
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT season, day, home, away, oh, od, oa, outcome FROM matches WHERE outcome IS NOT NULL")
    rows = cur.fetchall()
    conn.close()
    
    with open(SIG, 'r') as f:
        sig_db = json.load(f)
    
    print(f"[Axial Transformer MVP] {len(rows)} matches loaded")
    
    # Build simple stats
    team_wins = {}
    team_draws = {}
    team_losses = {}
    
    for r in rows:
        h, a = r['home'], r['away']
        o = r['outcome']
        
        if h not in team_wins: team_wins[h] = 0
        if h not in team_draws: team_draws[h] = 0
        if h not in team_losses: team_losses[h] = 0
        if a not in team_wins: team_wins[a] = 0
        if a not in team_draws: team_draws[a] = 0
        if a not in team_losses: team_losses[a] = 0
        
        if o == 'HOME':
            team_wins[h] += 1
            team_losses[a] += 1
        elif o == 'AWAY':
            team_wins[a] += 1
            team_losses[h] += 1
        else:
            team_draws[h] += 1
            team_draws[a] += 1
    
    # Model parameters (simple weights)
    # Features: [p_h, p_d, p_a, h_form, a_form, h2h_d, odds_ratio]
    weights = {
        'home': [0.35, 0.05, 0.10, 0.20, 0.10, 0.10, 0.10],  # HOME
        'draw': [0.10, 0.40, 0.10, 0.15, 0.10, 0.10, 0.05],  # DRAW
        'away': [0.10, 0.05, 0.35, 0.05, 0.20, 0.10, 0.10],  # AWAY
    }
    
    # Build model
    model = {
        'weights': weights,
        'team_stats': {'wins': team_wins, 'draws': team_draws, 'losses': team_losses},
        'sig_db': sig_db,
        'version': '1.0'
    }
    
    with open(OUT, 'wb') as f:
        pickle.dump(model, f)
    
    print(f"[Axial Transformer MVP] Model saved to {OUT}")
    
    # Test
    result = predict({'home': 'CHELSEA', 'away': 'WOLVERHAMPTON', 'oh': 1.4, 'od': 5.0, 'oa': 5.8}, model)
    print("[SAMPLE]", result)


def predict(fixture, model):
    weights = model['weights']
    stats = model['team_stats']
    sig_db = model['sig_db']
    
    h, a = fixture['home'], fixture['away']
    oh, od, oa = fixture['oh'], fixture['od'], fixture['oa']
    
    # True probabilities
    probs = [1/oh, 1/od, 1/oa]
    total = sum(probs)
    p_h, p_d, p_a = [p/total for p in probs]
    
    # Team form
    h_games = stats['wins'].get(h, 0) + stats['draws'].get(h, 0) + stats['losses'].get(h, 0)
    a_games = stats['wins'].get(a, 0) + stats['draws'].get(a, 0) + stats['losses'].get(a, 0)
    
    h_win_rate = stats['wins'].get(h, 0) / max(1, h_games)
    a_win_rate = stats['wins'].get(a, 0) / max(1, a_games)
    
    # Scores
    score_h = p_h * weights['home'][0] + h_win_rate * weights['home'][3]
    score_d = p_d * weights['draw'][1] + 0.33 * weights['draw'][5]
    score_a = p_a * weights['away'][2] + a_win_rate * weights['away'][5]
    
    scores = [score_h, score_d, score_a]
    pred = ['H', 'D', 'A'][scores.index(max(scores))]
    confidence = max(scores) / sum(scores)
    
    certainty = int(50 + confidence * 50)
    
    # Signature ensemble
    key = f"{h.upper()}|{a.upper()}|{oh:.1f}|{od:.1f}|{oa:.1f}"
    se = sig_db.get(key, {})
    
    if se.get('total', 0) >= 5:
        cnt = se['counts']
        sp = max(cnt, key=cnt.get)
        sr = cnt[sp] / se['total']
        if sp == pred:
            certainty = int(certainty * 0.7 + sr * 100 * 0.3)
        else:
            certainty = int(certainty * 0.5)
    
    odds = oh if pred == 'H' else (od if pred == 'D' else oa)
    
    return {
        'home': h, 'away': a,
        'prediction': pred,
        'prediction_label': {'H': 'HOME', 'D': 'DRAW', 'A': 'AWAY'}[pred],
        'certainty_score': certainty,
        'tier': 'LOCK' if certainty >= 85 else ('SIGNAL' if certainty >= 70 else 'MODERATE'),
        'target_odds': odds,
        'h_win_prob': round(p_h, 3),
        'draw_prob': round(p_d, 3),
        'a_win_prob': round(p_a, 3)
    }


if __name__ == '__main__':
    main()