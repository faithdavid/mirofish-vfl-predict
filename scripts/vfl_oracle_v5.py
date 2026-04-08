import pandas as pd
import numpy as np
import sqlite3
import os
import joblib

# Core Oracle Config
DB_PATH = 'vfl_history.db'

# Constant Quotas (from 184 full season audit)
D_MEAN = 57.3
H_MEAN = 101.7
A_MEAN = 71.2

def get_seasonal_accounting(df, season_id):
    """Calculates the current league-wide H/D/A tally for the season"""
    if season_id == 'SOVEREIGN': return {'H': 0, 'D': 0, 'A': 0}
    s_df = df[df['season'] == season_id].copy()
    if s_df.empty: return {'H': 0, 'D': 0, 'A': 0}
    
    s_df['o'] = s_df['outcome'].apply(lambda x: str(x)[0] if x else None)
    counts = s_df['o'].value_counts()
    return {
        'H': int(counts.get('H', 0)),
        'D': int(counts.get('D', 0)),
        'A': int(counts.get('A', 0))
    }

def apply_global_balancing(pred, stats, day):
    """Applies the 240-match Zero-Sum weighting to the prediction"""
    # Pro-rated Draw Target
    target_d = (day / 30) * D_MEAN
    
    if day >= 20:
        if stats['D'] < target_d * 0.85: # If more than 15% behind pro-rated target
            pred['draw_surge'] = True
            if pred['prediction'] == 'D':
                pred['confidence'] += 0.15
                pred['label'] = f"[GLOBAL DRAW SURGE] {pred['label']}"
            elif pred['prediction'] == 'H' and pred['confidence'] < 0.60:
                # If H prediction is weak and Draws are due, flag as high risk
                pred['label'] = f"[QUOTA RISK] {pred['label']}"
                
    if day >= 25 and stats['D'] < 40:
        # ABSOLUTE RUPTURE POINT
        pred['label'] = f"[MATHEMATICAL DRAW FORCE] {pred['label']}"
        if pred['prediction'] == 'D':
            pred['confidence'] = max(pred['confidence'], 0.85)

    return pred

def load_vfl_history():
    """Loads and cleans the 50,000 match dataset for V5 analysis."""
    if not os.path.exists(DB_PATH): return None
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM matches WHERE outcome IS NOT NULL", conn)
    conn.close()
    
    # Internal cleanup
    df['season'] = df['season'].astype(str).str.replace('vf:season:', '')
    numeric_cols = ['oh', 'od', 'oa', 'h', 'a', 'total', 'day']
    for col in numeric_cols: df[col] = pd.to_numeric(df[col], errors='coerce')
    df['outcome_code'] = df['outcome'].map({'HOME': 'H', 'DRAW': 'D', 'AWAY': 'A'})
    return df

def get_team_profiles(df):
    """Build team profiles for the 25% Form Factor."""
    teams = pd.concat([df['home'], df['away']]).unique()
    profiles = {}
    for team in teams:
        h_games = df[df['home'] == team]
        a_games = df[df['away'] == team]
        profiles[team] = {
            'h_win_p': (h_games['outcome_code'] == 'H').mean() if len(h_games) > 0 else 0.33,
            'h_draw_p': (h_games['outcome_code'] == 'D').mean() if len(h_games) > 0 else 0.33,
            'a_win_p': (a_games['outcome_code'] == 'A').mean() if len(a_games) > 0 else 0.33,
            'a_draw_p': (a_games['outcome_code'] == 'D').mean() if len(a_games) > 0 else 0.33
        }
    return profiles

def get_true_probabilities(oh, od, oa):
    """Remove bookmaker margin for 40% Odds Layer."""
    probs = [1/oh, 1/od, 1/oa]
    margin = sum(probs)
    return [p/margin for p in probs]

def get_seasonal_stats(team, season_id, current_day, df):
    """Calculates Wins for a team in the current active season."""
    s_id = str(season_id).replace('vf:season:', '')
    played = df[(df['season'] == s_id) & (df['day'] < current_day)]
    wins = len(played[(played['home'] == team) & (played['outcome'] == 'HOME')]) + \
           len(played[(played['away'] == team) & (played['outcome'] == 'AWAY')])
    return {'wins': wins}

def predict_fixture(fixture, df, profiles):
    """Hybrid V5.2 Engine: Mirror Check (100%) + Quota Awareness + Stat Blend."""
    h, a = fixture['home'].upper(), fixture['away'].upper()
    oh, od, oa = fixture['oh'], fixture['od'], fixture['oa']
    sst = str(fixture.get('sst', '0'))
    day = fixture.get('day', 15)
    season_id = fixture.get('season', '')

    # 1. Deterministic Mirror Check (100% Accuracy Layer)
    mirror = df[(df['home'] == h) & (df['away'] == a) & (df['oh'] == oh) & 
                (df['od'] == od) & (df['oa'] == oa) & (df['season_start_time'] == sst)]
    
    if not mirror.empty:
        actual = mirror.iloc[0]['outcome_code']
        return {'prediction': actual, 'confidence': 1.0, 'label': 'DETERMINISTIC LOCK (100%)', 'is_mirror': True, 'is_strong': True, 'h_wins': '?' }

    # 2. Seasonal Win-Cap Layer (The Insighter Strategy)
    h_win_count = get_seasonal_stats(h, season_id, day, df)['wins']
    
    # Quota Draw Logic: Trigger if team hits absolute cap (18+) or relative spike (75% WR)
    is_quota_draw = False
    quota_penalty = 0.0
    relative_threshold = max(8, int(day * 0.75)) # At least 8 wins, or 75% of games
    
    if h_win_count >= 21:
        # ABSOLUTE WIN WALL: Algorithm usually forces a loss or draw here
        quota_penalty = 0.45
        label_prefix = "QUOTA WIN WALL"
        is_quota_draw = True
    elif h_win_count >= 18 or (day > 5 and h_win_count >= relative_threshold):
        # High likelihood of forced draw to balance seasonal limits
        quota_penalty = 0.22 
        label_prefix = "QUOTA DRAW ALERT"
        if od <= 3.95: is_quota_draw = True
    else:
        label_prefix = ""

    # 3. Statistical Blend (40/35/25)
    p_h_odds, p_d_odds, p_a_odds = get_true_probabilities(oh, od, oa)
    hp = profiles.get(h, {'h_win_p': 0.33, 'h_draw_p': 0.33})
    ap = profiles.get(a, {'a_win_p': 0.33, 'a_draw_p': 0.33})
    
    final_h = (p_h_odds * 0.40) + (hp['h_win_p'] * 0.35) + (0.33 * 0.25)
    final_d = (p_d_odds * 0.40) + (hp['h_draw_p'] * 0.35) + (0.33 * 0.25)
    final_a = (p_a_odds * 0.40) + (ap['a_win_p'] * 0.35) + (0.33 * 0.25)
    
    if quota_penalty > 0: 
        final_h -= quota_penalty
        final_d += quota_penalty
    
    outcomes = {'H': final_h, 'D': final_d, 'A': final_a}
    best = max(outcomes, key=outcomes.get)
    conf = outcomes[best] / sum(outcomes.values())
    
    label = 'HIGH' if conf > 0.60 else 'MODERATE'
    is_strong = (conf > 0.65) or (is_quota_draw and best == 'D')
    
    if label_prefix:
        label = label_prefix
        if is_strong and best == 'D': label = f"DETERMINISTIC {label_prefix}"

    return {
        'prediction': best,
        'confidence': conf,
        'label': label,
        'is_mirror': False,
        'is_strong': is_strong,
        'h_wins': h_win_count
    }
