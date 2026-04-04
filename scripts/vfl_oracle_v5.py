import pandas as pd
import numpy as np
import sqlite3
import os
import joblib
import xgboost as xgb

# Core Oracle Config
DB_PATH = 'vfl_history.db'
MODEL_PATH = 'vfl_xgboost_v5.model'
model = None

def get_model():
    global model
    if model is None and os.path.exists(MODEL_PATH):
        model = joblib.load(MODEL_PATH)
    return model

def load_vfl_history():
    """Loads and cleans the 50,000 match dataset for V5 analysis."""
    if not os.path.exists(DB_PATH): return None
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM matches WHERE outcome IS NOT NULL", conn)
    conn.close()
    df['season'] = df['season'].str.replace('vf:season:', '')
    numeric_cols = ['oh', 'od', 'oa', 'h', 'a', 'total', 'gg', 'o25', 'day']
    for col in numeric_cols: df[col] = pd.to_numeric(df[col], errors='coerce')
    df['outcome_code'] = df['outcome'].map({'HOME': 'H', 'DRAW': 'D', 'AWAY': 'A'})
    return df

def get_team_profiles(df):
    """Task 2: Build team profiles (Home/Away Stats)."""
    teams = pd.concat([df['home'], df['away']]).unique()
    profiles = {}
    for team in teams:
        h_games = df[df['home'] == team]; a_games = df[df['away'] == team]
        profiles[team] = {
            'h_win_p': (h_games['outcome_code'] == 'H').mean() if len(h_games) > 0 else 0,
            'h_draw_p': (h_games['outcome_code'] == 'D').mean() if len(h_games) > 0 else 0,
            'h_gpg': h_games['h'].mean() if len(h_games) > 0 else 0,
            'h_cpg': h_games['a'].mean() if len(h_games) > 0 else 0,
            'a_win_p': (a_games['outcome_code'] == 'A').mean() if len(a_games) > 0 else 0,
            'a_draw_p': (a_games['outcome_code'] == 'D').mean() if len(a_games) > 0 else 0,
            'a_gpg': a_games['a'].mean() if len(a_games) > 0 else 0,
            'a_cpg': a_games['h'].mean() if len(a_games) > 0 else 0,
            'total_games': len(h_games) + len(a_games)
        }
    return profiles

def get_h2h_stats(df, home_team, away_team):
    """Task 3: Build H2H Tables."""
    h2h = df[((df['home'] == home_team) & (df['away'] == away_team)) |
             ((df['home'] == away_team) & (df['away'] == home_team))]
    if len(h2h) == 0: return None
    return {
        'h_win_p': (h2h[h2h['home'] == home_team]['outcome_code'] == 'H').mean() if len(h2h[h2h['home'] == home_team]) > 0 else 0,
        'd_p': (h2h['outcome_code'] == 'D').mean(),
        'a_win_p': (h2h[h2h['home'] == home_team]['outcome_code'] == 'A').mean() if len(h2h[h2h['home'] == home_team]) > 0 else 0,
        'o25_p': h2h['o25'].mean()
    }

def get_true_probabilities(oh, od, oa):
    """Step 4: Remove bookmaker margin."""
    probs = [1/oh, 1/od, 1/oa]
    margin = sum(probs)
    return [p/margin for p in probs]

def predict_fixture(fixture, df, profiles):
    """V5.1 HYBRID ORACLE: DETERMINISTIC MIRROR + XGBOOST ANALYST."""
    ht, at = fixture['home'].upper(), fixture['away'].upper()
    oh, od, oa = fixture['oh'], fixture['od'], fixture['oa']
    sst = fixture.get('sst', '0')
    
    # ── LAYER 1: DETERMINISTIC MIRROR (100% LOCK) ──────────────────
    # Check if this exact combination has ever appeared before
    # (season_start_time is the absolute RNG seed)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT outcome, h, a, COUNT(*) 
        FROM matches 
        WHERE home=? AND away=? AND oh=? AND od=? AND oa=? AND season_start_time=?
        GROUP BY outcome, h, a
    ''', (ht, at, oh, od, oa, sst))
    mirror = c.fetchone()
    conn.close()

    if mirror:
        return {
            'prediction': mirror[0][0], # 'H', 'D', 'A' logic handle
            'score': f"{mirror[1]}:{mirror[2]}",
            'confidence': 1.00,
            'is_strong': True,
            'is_mirror': True,
            'label': 'DETERMINISTIC LOCK (100%)'
        }

    # ── LAYER 2: XGBOOST STATISTICAL BLEND (40/35/25) ────────────────
    xgb_model = get_model()
    if xgb_model:
        # Features for XGBoost: oh, od, oa, o25, gg
        # (Assuming o25/gg defaults if not in upcoming file)
        features = pd.DataFrame([{
            'oh': oh, 'od': od, 'oa': oa, 
            'o25': fixture.get('o_o25', 1.8), 'gg': fixture.get('o_gg', 1.8)
        }])
        probs = xgb_model.predict_proba(features)[0]
        # XGB mapping: 0=H, 1=D, 2=A
        p_h_xgb, p_d_xgb, p_a_xgb = probs[0], probs[1], probs[2]
    else:
        p_h_xgb, p_d_xgb, p_a_xgb = get_true_probabilities(oh, od, oa)
        
    # ── LAYER 3: THE 3-SIGNAL AGREEMENT FILTER ──────────────────────
    h2h = get_h2h_stats(df, ht, at)
    
    # Statistical Signals (25% Weight)
    # Using Home Team's Home Stats and Away Team's Away Stats
    p_h_stats = profiles.get(ht, {}).get('h_win_p', 0)
    p_d_stats = (profiles.get(ht, {}).get('h_draw_p', 0) + profiles.get(at, {}).get('a_draw_p', 0)) / 2
    p_a_stats = profiles.get(at, {}).get('a_win_p', 0)
    
    # Final Blended Score
    # (Using XGBoost as the 40% Odds layer as it's better calibrated)
    # We follow the user's specific weights: 40% Odds/Model, 35% H2H, 25% Stats
    w_odds, w_h2h, w_stats = 0.40, 0.35, 0.25
    if not h2h:
        w_odds, w_h2h, w_stats = 0.55, 0.00, 0.45
        p_h_h2h = p_d_h2h = p_a_h2h = 0
    else:
        p_h_h2h, p_d_h2h, p_a_h2h = h2h['h_win_p'], h2h['d_p'], h2h['a_win_p']

    final_h = (p_h_xgb * w_odds) + (p_h_h2h * w_h2h) + (p_h_stats * w_stats)
    final_d = (p_d_xgb * w_odds) + (p_d_h2h * w_h2h) + (p_d_stats * w_stats)
    final_a = (p_a_xgb * w_odds) + (p_a_h2h * w_h2h) + (p_a_stats * w_stats)
    
    outcomes = {'H': final_h, 'D': final_d, 'A': final_a}
    best_out = max(outcomes, key=outcomes.get)
    conf = outcomes[best_out]
    
    # Task 6: FLAG STRONG CALLS
    # Agreement: Odds Signal + H2H Signal + Team Form Signal
    is_strong = False
    if h2h:
        fav_odds = 'H' if p_h_xgb > p_a_xgb and p_h_xgb > p_d_xgb else 'A'
        fav_h2h = 'H' if p_h_h2h > p_a_h2h else 'A'
        fav_stats = 'H' if p_h_stats > p_a_stats else 'A'
        if fav_odds == fav_h2h == fav_stats == best_out:
            is_strong = True

    return {
        'prediction': best_out,
        'confidence': conf,
        'is_strong': is_strong,
        'is_mirror': False,
        'label': 'HIGH' if conf >= 0.60 else ('MODERATE' if conf >= 0.45 else 'LOW')
    }
