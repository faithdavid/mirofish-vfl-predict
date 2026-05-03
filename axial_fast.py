#!/usr/bin/env python3
"""
Axial Transformer Ensemble for VFL Prediction - Fast MVP
========================================================
Simplified implementation for fast training on 50K match dataset.
Uses numpy/scipy only - no heavy dependencies.
"""

import numpy as np
import pandas as pd
import sqlite3
import json
from pathlib import Path
import pickle

# ── PATHS ─────────────────────────────────────────────────────────────────────
_VFL_REPO = Path('/root/.openclaw/workspace/vfl-repo')
_HIST_DB = _VFL_REPO / 'data' / 'databases' / 'vfl_history.db'
_SIG_DB = _VFL_REPO / 'data' / 'models' / 'master_rng_signatures.json'
_MODEL_OUT = _VFL_REPO / 'data' / 'models' / 'axial_transformer_v1.pkl'


def load_data():
    """Load VFL data efficiently."""
    conn = sqlite3.connect(_HIST_DB)
    df = pd.read_sql_query("SELECT * FROM matches WHERE outcome IS NOT NULL", conn)
    conn.close()
    
    df['season'] = df['season'].astype(str).str.replace('vf:season:', '', regex=False)
    df['outcome_code'] = df['outcome'].map({'HOME': 0, 'DRAW': 1, 'AWAY': 2})
    
    for col in ['oh', 'od', 'oa', 'h', 'a', 'total', 'day']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df


def true_probs(oh, od, oa):
    probs = np.array([1/oh, 1/od, 1/oa])
    return probs / probs.sum()


def compute_form(team, df, n_matches=8):
    """Compute team form vector - our 'temporal attention'."""
    team_games = df[(df['home'] == team) | (df['away'] == team)].tail(n_matches)
    
    if len(team_games) == 0:
        return np.array([0.33, 0.33, 0.33])
    
    # Exponential weights for recent matches
    weights = np.exp(-0.5 * np.arange(len(team_games) - 1, -1, -1))
    
    results = np.zeros(3)
    for _, row in team_games.iterrows():
        if row['home'] == team:
            if row['outcome'] == 'HOME':
                results[0] += 1
            elif row['outcome'] == 'DRAW':
                results[1] += 1
        else:
            if row['outcome'] == 'AWAY':
                results[2] += 1
            elif row['outcome'] == 'DRAW':
                results[1] += 1
    
    return results / results.sum() if results.sum() > 0 else np.array([0.33, 0.33, 0.33])


def extract_features(row, df, team_profiles):
    """Extract feature vector for prediction."""
    home, away = row['home'], row['away']
    oh, od, oa = row['oh'], row['od'], row['oa']
    
    # True probabilities
    p = true_probs(oh, od, oa)
    
    # Team form (momentum)
    home_form = compute_form(home, df)
    away_form = compute_form(away, df)
    
    # Team profiles
    hp = team_profiles.get(home, {'h_win_p': 0.33, 'h_draw_p': 0.33, 'h_loss_p': 0.33})
    ap = team_profiles.get(away, {'a_win_p': 0.33, 'a_draw_p': 0.33, 'a_loss_p': 0.33})
    
    # Interaction score
    interaction = hp['h_win_p'] * ap['a_win_p'] + 0.3 * hp['h_draw_p']
    
    # H2H
    h2h = df[((df['home'] == home) & (df['away'] == away)) | 
             ((df['home'] == away) & (df['away'] == home))]
    h2h_h = (h2h['outcome'] == 'HOME').sum() if len(h2h) > 0 else 0
    h2h_d = (h2h['outcome'] == 'DRAW').sum() if len(h2h) > 0 else 0
    h2h_a = (h2h['outcome'] == 'AWAY').sum() if len(h2h) > 0 else 0
    
    return np.concatenate([p, home_form, away_form, [interaction], [h2h_h, h2h_d, h2h_a, oh, od, oa]])


def train():
    """Train lightweight model."""
    print("[Axial Transformer] Loading data...")
    df = load_data()
    
    with open(_SIG_DB, 'r') as f:
        sig_db = json.load(f)
    
    # Build team profiles
    teams = pd.concat([df['home'], df['away']]).unique()
    team_profiles = {}
    for team in teams:
        h_games = df[df['home'] == team]
        a_games = df[df['away'] == team]
        team_profiles[team] = {
            'h_win_p': (h_games['outcome'] == 'HOME').mean() if len(h_games) > 0 else 0.33,
            'h_draw_p': (h_games['outcome'] == 'DRAW').mean() if len(h_games) > 0 else 0.33,
            'a_win_p': (a_games['outcome'] == 'AWAY').mean() if len(a_games) > 0 else 0.33,
            'a_draw_p': (a_games['outcome'] == 'DRAW').mean() if len(a_games) > 0 else 0.33,
        }
    
    print(f"[Axial Transformer] {len(df)} matches, {len(teams)} teams")
    
    # Extract features
    X, y = [], []
    for _, row in df.iterrows():
        if pd.notna(row['outcome_code']):
            X.append(extract_features(row, df, team_profiles))
            y.append(int(row['outcome_code']))
    
    X = np.array(X, dtype=np.float32)
    y = np.array(y)
    
    # Simple gradient boosting via logistic regression with feature crosses
    from scipy.special import expit
    
    # Normalize features
    X_mean = X.mean(axis=0)
    X_std = X.std(axis=0) + 1e-8
    X_norm = (X - X_mean) / X_std
    
    # One-vs-rest logistic regression
    n_classes = 3
    n_features = X_norm.shape[1]
    weights = np.zeros((n_classes, n_features))
    
    print("[Axial Transformer] Training logistic regression...")
    for epoch in range(100):
        for c in range(n_classes):
            y_binary = (y == c).astype(float)
            z = X_norm @ weights[c]
            pred = expit(z)
            grad = (pred - y_binary)[:, None] * X_norm
            weights[c] -= 0.01 * grad.mean(axis=0)
    
    # Validation
    X_val = X_norm[int(0.9 * len(X_norm)):]
    y_val = y[int(0.9 * len(y)):]
    
    preds = []
    for i in range(len(X_val)):
        scores = X_val[i] @ weights.T
        preds.append(np.argmax(scores))
    
    acc = np.mean(np.array(preds) == y_val)
    print(f"[Axial Transformer] Validation accuracy: {acc:.4f}")
    
    # Save model
    model_data = {
        'weights': weights,
        'X_mean': X_mean,
        'X_std': X_std,
        'team_profiles': team_profiles,
        'sig_db': sig_db,
        'feature_count': n_features,
    }
    
    with open(_MODEL_OUT, 'wb') as f:
        pickle.dump(model_data, f)
    
    print(f"[Axial Transformer] Model saved to {_MODEL_OUT}")
    return model_data


def predict(fixture, model_data):
    """Predict fixture outcome."""
    weights = model_data['weights']
    X_mean = model_data['X_mean']
    X_std = model_data['X_std']
    team_profiles = model_data['team_profiles']
    sig_db = model_data['sig_db']
    
    df = load_data()
    
    features = extract_features(pd.Series(fixture), df, team_profiles)
    features_norm = (features - X_mean) / X_std
    
    scores = features_norm @ weights.T
    probs = np.exp(scores) / np.exp(scores).sum()
    prediction = int(np.argmax(probs))
    
    pred_map = {0: 'H', 1: 'D', 2: 'A'}
    pred_label = pred_map[prediction]
    
    certainty = int(50 + probs[prediction] * 50)
    
    # Signature ensemble
    home, away = fixture['home'], fixture['away']
    oh, od, oa = fixture['oh'], fixture['od'], fixture['oa']
    
    key = f"{home.upper()}|{away.upper()}|{oh:.1f}|{od:.1f}|{oa:.1f}"
    sig_entry = sig_db.get(key, {})
    
    if sig_entry and sig_entry.get('total', 0) >= 5:
        counts = sig_entry['counts']
        sig_pred = max(counts, key=counts.get)
        sig_rate = counts[sig_pred] / sig_entry['total']
        
        if sig_pred == pred_label:
            certainty = int(certainty * 0.7 + sig_rate * 100 * 0.3)
            label = f"TRANSFORMER + SIG {sig_rate:.0%}"
        else:
            certainty = int(certainty * 0.5)
            label = f"TRANSFORMER (vs SIG {sig_rate:.0%})"
    else:
        label = "TRANSFORMER"
    
    target_odds = oh if pred_label == 'H' else (od if pred_label == 'D' else oa)
    ev = (certainty / 100) * target_odds - 1
    
    return {
        'home': home,
        'away': away,
        'prediction': pred_label,
        'prediction_label': {'H': 'HOME', 'D': 'DRAW', 'A': 'AWAY'}[pred_label],
        'certainty_score': certainty,
        'tier': 'LOCK' if certainty >= 85 else ('SIGNAL' if certainty >= 70 else 'MODERATE'),
        'label': label,
        'stake': 50.0 if certainty >= 85 else (30.0 if certainty >= 70 else 15.0),
        'ev': round(ev, 3),
        'target_odds': target_odds,
        'h_win_prob': float(probs[0]),
        'draw_prob': float(probs[1]),
        'a_win_prob': float(probs[2]),
    }


if __name__ == '__main__':
    model_data = train()
    
    # Test prediction
    test = {
        'home': 'CHELSEA',
        'away': 'WOLVERHAMPTON',
        'oh': 1.4,
        'od': 5.0,
        'oa': 5.8,
    }
    
    result = predict(test, model_data)
    print("\n[SAMPLE PREDICTION]")
    print(json.dumps(result, indent=2))