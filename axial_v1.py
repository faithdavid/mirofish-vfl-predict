#!/usr/bin/env python3
"""
Axial Transformer Ensemble - NumPy Only
=========================================
Fast training without scipy dependency issues.
"""

import numpy as np
import pandas as pd
import sqlite3
import json
from pathlib import Path
import pickle

_VFL_REPO = Path('/root/.openclaw/workspace/vfl-repo')
_HIST_DB = _VFL_REPO / 'data' / 'databases' / 'vfl_history.db'
_SIG_DB = _VFL_REPO / 'data' / 'models' / 'master_rng_signatures.json'
_MODEL_OUT = _VFL_REPO / 'data' / 'models' / 'axial_transformer_v1.pkl'


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -500, 500)))


def load_data():
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


def compute_form(team, df, n=8):
    games = df[(df['home'] == team) | (df['away'] == team)].tail(n)
    if len(games) == 0:
        return np.array([0.33, 0.33, 0.33])
    
    results = np.zeros(3)
    for _, r in games.iterrows():
        if r['home'] == team:
            if r['outcome'] == 'HOME': results[0] += 1
            elif r['outcome'] == 'DRAW': results[1] += 1
        else:
            if r['outcome'] == 'AWAY': results[2] += 1
            elif r['outcome'] == 'DRAW': results[1] += 1
    
    return results / results.sum() if results.sum() > 0 else np.array([0.33, 0.33, 0.33])


def extract_features(row, df, profiles):
    p = true_probs(row['oh'], row['od'], row['oa'])
    hf = compute_form(row['home'], df)
    af = compute_form(row['away'], df)
    
    hp = profiles.get(row['home'], {'h_win_p': 0.33, 'h_draw_p': 0.33})
    ap = profiles.get(row['away'], {'a_win_p': 0.33, 'a_draw_p': 0.33})
    
    interaction = hp['h_win_p'] * ap['a_win_p'] + 0.3 * hp['h_draw_p']
    
    h2h = df[((df['home'] == row['home']) & (df['away'] == row['away'])) | 
             ((df['home'] == row['away']) & (df['away'] == row['home']))]
    h2h_h = (h2h['outcome'] == 'HOME').sum() if len(h2h) > 0 else 0
    h2h_d = (h2h['outcome'] == 'DRAW').sum() if len(h2h) > 0 else 0
    h2h_a = (h2h['outcome'] == 'AWAY').sum() if len(h2h) > 0 else 0
    
    return np.concatenate([p, hf, af, [interaction], [h2h_h, h2h_d, h2h_a, row['oh'], row['od'], row['oa']]])


def train():
    print("[Axial] Loading data...")
    df = load_data()
    
    with open(_SIG_DB, 'r') as f:
        sig_db = json.load(f)
    
    teams = pd.concat([df['home'], df['away']]).unique()
    profiles = {}
    for t in teams:
        hg = df[df['home'] == t]
        ag = df[df['away'] == t]
        profiles[t] = {
            'h_win_p': (hg['outcome'] == 'HOME').mean() if len(hg) > 0 else 0.33,
            'h_draw_p': (hg['outcome'] == 'DRAW').mean() if len(hg) > 0 else 0.33,
            'a_win_p': (ag['outcome'] == 'AWAY').mean() if len(ag) > 0 else 0.33,
            'a_draw_p': (ag['outcome'] == 'DRAW').mean() if len(ag) > 0 else 0.33,
        }
    
    print(f"[Axial] {len(df)} matches")
    
    X, y = [], []
    for _, r in df.iterrows():
        if pd.notna(r['outcome_code']):
            X.append(extract_features(r, df, profiles))
            y.append(int(r['outcome_code']))
    
    X = np.array(X, dtype=np.float32)
    y = np.array(y)
    
    # Normalize
    X_mean = X.mean(axis=0)
    X_std = X.std(axis=0) + 1e-8
    Xn = (X - X_mean) / X_std
    
    # Train - one vs rest logistic regression
    W = np.zeros((3, Xn.shape[1]))
    
    print("[Axial] Training (100 epochs)...")
    for epoch in range(100):
        for c in range(3):
            yb = (y == c).astype(float)
            z = Xn @ W[c]
            pred = sigmoid(z)
            grad = ((pred - yb)[:, None] * Xn).mean(axis=0)
            W[c] -= 0.05 * grad
    
    # Validate
    Xv = Xn[int(0.9 * len(Xn)):]
    yv = y[int(0.9 * len(y)):]
    preds = []
    for i in range(len(Xv)):
        scores = Xv[i] @ W.T
        preds.append(np.argmax(scores))
    acc = np.mean(np.array(preds) == yv)
    print(f"[Axial] Validation: {acc:.4f}")
    
    model = {'W': W, 'X_mean': X_mean, 'X_std': X_std, 'profiles': profiles, 'sig_db': sig_db}
    
    with open(_MODEL_OUT, 'wb') as f:
        pickle.dump(model, f)
    
    print(f"[Axial] Saved to {_MODEL_OUT}")
    return model


def predict(fixture, model):
    W = model['W']
    X_mean, X_std = model['X_mean'], model['X_std']
    profiles, sig_db = model['profiles'], model['sig_db']
    df = load_data()
    
    fvec = extract_features(pd.Series(fixture), df, profiles)
    fn = (fvec - X_mean) / X_std
    scores = fn @ W.T
    probs = np.exp(scores) / np.exp(scores).sum()
    
    pred = int(np.argmax(probs))
    plabel = {0: 'H', 1: 'D', 2: 'A'}[pred]
    certainty = int(50 + probs[pred] * 50)
    
    # Signature ensemble
    key = f"{fixture['home'].upper()}|{fixture['away'].upper()}|{fixture['oh']:.1f}|{fixture['od']:.1f}|{fixture['oa']:.1f}"
    se = sig_db.get(key, {})
    
    if se.get('total', 0) >= 5:
        cnt = se['counts']
        sp = max(cnt, key=cnt.get)
        sr = cnt[sp] / se['total']
        if sp == plabel:
            certainty = int(certainty * 0.7 + sr * 100 * 0.3)
            label = f"TRANS + SIG {sr:.0%}"
        else:
            certainty = int(certainty * 0.5)
            label = f"TRANS (vs SIG {sr:.0%})"
    else:
        label = "TRANSFORMER"
    
    odds = fixture['oh'] if plabel == 'H' else (fixture['od'] if plabel == 'D' else fixture['oa'])
    ev = (certainty / 100) * odds - 1
    
    return {'home': fixture['home'], 'away': fixture['away'], 'prediction': plabel,
            'prediction_label': {'H': 'HOME', 'D': 'DRAW', 'A': 'AWAY'}[plabel],
            'certainty_score': certainty, 'tier': 'LOCK' if certainty >= 85 else ('SIGNAL' if certainty >= 70 else 'MODERATE'),
            'label': label, 'stake': 50 if certainty >= 85 else (30 if certainty >= 70 else 15),
            'ev': round(ev, 3), 'target_odds': odds,
            'h_win_prob': float(probs[0]), 'draw_prob': float(probs[1]), 'a_win_prob': float(probs[2])}


if __name__ == '__main__':
    m = train()
    print("\n[TEST]", predict({'home': 'CHELSEA', 'away': 'WOLVERHAMPTON', 'oh': 1.4, 'od': 5.0, 'oa': 5.8}, m))