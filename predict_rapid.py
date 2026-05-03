#!/usr/bin/env python3
"""
Rapid VFL Prediction for Season 3075072, Matchday 22
Uses Oracle V6 engine with signature database and statistical approach
"""
import json
import sqlite3
from pathlib import Path

# Constants
D_MEAN = 57.3  # draws per season

# Paths
ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "databases" / "vfl_history.db"
SIG_PATH = ROOT / "data" / "models" / "master_rng_signatures.json"

# Load signature database
with open(SIG_PATH, 'r', encoding='utf-8') as f:
    SIG_DB = json.load(f)

# Load history database
def load_history():
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT season, day, home, away, oh, od, oa, h, a, outcome 
        FROM matches 
        WHERE oh IS NOT NULL AND od IS NOT NULL AND oa IS NOT NULL
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

# Build team profiles and seasonal accounting
def build_data(history):
    profiles = {}
    season_counts = {}
    
    for season, day, home, away, oh, od, oa, h, a, outcome in history:
        home = home.upper()
        away = away.upper()
        season = str(season)
        
        if home not in profiles:
            profiles[home] = {'h_games': 0, 'h_wins': 0, 'h_draws': 0}
        profiles[home]['h_games'] += 1
        if outcome == 'HOME':
            profiles[home]['h_wins'] += 1
        elif outcome == 'DRAW':
            profiles[home]['h_draws'] += 1
        
        if away not in profiles:
            profiles[away] = {'a_games': 0, 'a_wins': 0, 'a_draws': 0}
        profiles[away]['a_games'] += 1
        if outcome == 'AWAY':
            profiles[away]['a_wins'] += 1
        elif outcome == 'DRAW':
            profiles[away]['a_draws'] += 1
        
        # Track season outcomes
        if outcome:
            if season not in season_counts:
                season_counts[season] = {'H': 0, 'D': 0, 'A': 0}
            season_counts[season][outcome[0]] += 1
    
    return profiles, season_counts

# True probabilities
def true_probs(oh, od, oa):
    probs = [1/oh, 1/od, 1/oa]
    margin = sum(probs)
    return [p / margin for p in probs]

# Signature lookup
def sig_lookup(home, away, oh, od, oa):
    home, away = home.upper(), away.upper()
    key = f"{home}|{away}|{oh:.1f}|{od:.1f}|{oa:.1f}"
    entry = SIG_DB.get(key)
    
    if entry and entry['total'] >= 5:
        counts = entry['counts']
        best = max(counts, key=counts.get)
        rate = counts[best] / entry['total']
        if rate >= 0.70:
            certainty = int(90 + (rate - 0.90) * 100) if rate >= 0.90 else int(70 + (rate - 0.70) * 100)
            return best, min(100, max(70, certainty)), entry['total'], rate
    
    return None

# Quota analysis - detects draw pressure and win caps
def quota_analysis(home, away, oh, od, oa, day, profiles, season, season_counts):
    home, away = home.upper(), away.upper()
    
    # Check seasonal draw deficit (use day 22 as estimate)
    target_d = (22 / 30) * D_MEAN
    current_d = season_counts.get(season, {}).get('D', 0) if season in season_counts else 0
    
    draw_deficit = max(0, target_d - current_d)
    
    # Draw detection signals
    draw_score = 0
    
    # Signal 1: Draw odds in balanced zone
    if 2.8 <= od <= 3.8:
        draw_score += 25
    
    # Signal 2: Seasonal draw deficit
    if draw_deficit > 5:
        draw_score += min(30, int(draw_deficit * 5))
    
    # Signal 3: Low draw odds relative to others
    if od < oh and od < oa:
        draw_score += 15
    
    if draw_score >= 50:
        return 'D', min(75, 55 + draw_score // 3), f"DRAW PRESSURE ({draw_score} pts)", 'DRAW_PRESSURE'
    
    return None

# Predict fixture
def predict_fixture(home, away, oh, od, oa, day, season, profiles, season_counts):
    # 1. Signature check
    sig = sig_lookup(home, away, oh, od, oa)
    if sig:
        pred, certainty, n, rate = sig
        return {
            'home': home.upper(),
            'away': away.upper(),
            'oh': oh, 'od': od, 'oa': oa,
            'prediction': pred,
            'prediction_label': {'H': 'HOME', 'D': 'DRAW', 'A': 'AWAY'}[pred],
            'certainty_score': certainty,
            'tier': 'LOCK' if certainty >= 85 else 'SIGNAL',
            'label': f'SIG {rate:.0%} ({n} samples)',
            'stake': 50.0 if certainty >= 85 else 30.0,
        }
    
    # 2. Quota analysis
    quota = quota_analysis(home, away, oh, od, oa, day, profiles, season, season_counts)
    if quota:
        pred, certainty, label, tier = quota
        return {
            'home': home.upper(),
            'away': away.upper(),
            'oh': oh, 'od': od, 'oa': oa,
            'prediction': pred,
            'prediction_label': {'H': 'HOME', 'D': 'DRAW', 'A': 'AWAY'}[pred],
            'certainty_score': certainty,
            'tier': tier,
            'label': label,
            'stake': 30.0 if certainty >= 70 else 15.0,
        }
    
    # 3. Statistical blend
    p_h, p_d, p_a = true_probs(oh, od, oa)
    hp = profiles.get(home.upper(), {'h_wins': 0, 'h_draws': 0, 'h_games': 0})
    ap = profiles.get(away.upper(), {'a_wins': 0, 'a_draws': 0, 'a_games': 0})
    
    h_win_p = hp['h_wins'] / max(1, hp.get('h_games', 0))
    h_draw_p = hp['h_draws'] / max(1, hp.get('h_games', 0))
    a_win_p = ap.get('a_wins', 0) / max(1, ap.get('a_games', 0))
    
    final_h = (p_h * 0.40) + (h_win_p * 0.35) + (0.33 * 0.25)
    final_d = (p_d * 0.40) + (h_draw_p * 0.35) + (0.33 * 0.25)
    final_a = (p_a * 0.40) + (a_win_p * 0.35) + (0.33 * 0.25)
    
    outcomes = {'H': final_h, 'D': final_d, 'A': final_a}
    best = max(outcomes, key=outcomes.get)
    total = sum(outcomes.values())
    conf = outcomes[best] / total if total > 0 else 0.33
    certainty = int(40 + (conf - 0.33) / 0.67 * 25)
    certainty = max(40, min(65, certainty))
    
    return {
        'home': home.upper(),
        'away': away.upper(),
        'oh': oh, 'od': od, 'oa': oa,
        'prediction': best,
        'prediction_label': {'H': 'HOME', 'D': 'DRAW', 'A': 'AWAY'}[best],
        'certainty_score': certainty,
        'tier': 'MODERATE' if certainty >= 55 else 'WEAK',
        'label': f'BLEND H{final_h:.0%}/D{final_d:.0%}/A{final_a:.0%}',
        'stake': 15.0 if certainty >= 55 else 0.0,
    }

# Main
if __name__ == '__main__':
    fixtures = [
        {"home": "NEWCASTLE", "away": "LONDON GUNS", "oh": 3.0, "od": 2.5, "oa": 2.0},
        {"home": "WOLVERHAMPTON", "away": "BOURNEMOUTH", "oh": 1.5, "od": 2.5, "oa": 4.95},
        {"home": "MANCHESTER BLUE", "away": "EVERTON", "oh": 1.45, "od": 2.5, "oa": 6.25},
        {"home": "CHELSEA", "away": "LEEDS", "oh": 1.4, "od": 2.5, "oa": 9.0},
        {"home": "CRYSTAL PALACE", "away": "FULHAM", "oh": 2.1, "od": 2.5, "oa": 3.35},
        {"home": "WEST HAM", "away": "TOTTENHAM", "oh": 2.9, "od": 2.5, "oa": 2.2},
        {"home": "MANCHESTER RED", "away": "ASTON VILLA", "oh": 1.85, "od": 2.5, "oa": 3.8},
        {"home": "BRIGHTON", "away": "LIVERPOOL", "oh": 3.7, "od": 2.5, "oa": 1.85},
    ]
    
    history = load_history()
    profiles, season_counts = build_data(history)
    
    predictions = []
    for f in fixtures:
        result = predict_fixture(
            f['home'], f['away'], f['oh'], f['od'], f['oa'],
            22, 'vf:season:3075072', profiles, season_counts
        )
        predictions.append(result)
    
    output = {
        "season_id": "vf:season:3075072",
        "match_day": 22,
        "generated_at": "2026-05-03T07:51:30Z",
        "predictions": predictions
    }
    
    print(json.dumps(output, indent=2))