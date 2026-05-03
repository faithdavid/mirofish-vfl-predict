"""
Axial Transformer Ensemble for VFL Prediction
==============================================
Simplified implementation using scikit-learn + numpy for fast inference.
Mimics transformer attention concepts without PyTorch dependency.

Features:
1. Temporal momentum tracking via exponential decay weighting
2. Team interaction similarity via embedding lookups
3. Signature database ensemble
4. ONNX export for fast inference
"""

import numpy as np
import pandas as pd
import sqlite3
import json
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import pickle
import os

# ── PATHS ─────────────────────────────────────────────────────────────────────
_VFL_REPO = Path('/root/.openclaw/workspace/vfl-repo')
_HIST_DB = _VFL_REPO / 'data' / 'databases' / 'vfl_history.db'
_SIG_DB = _VFL_REPO / 'data' / 'models' / 'master_rng_signatures.json'
_MODEL_OUT = _VFL_REPO / 'data' / 'models' / 'axial_transformer_v1.onnx'
_MODEL_PT = _VFL_REPO / 'data' / 'models' / 'axial_transformer_v1.pkl'


# ── AXIAL ATTENTION IMPLEMENTATION ───────────────────────────────────────────

def temporal_attention_weights(day: int, decay_factor: float = 0.95) -> np.ndarray:
    """
    Generate attention weights that decay exponentially for older matches.
    Simulates temporal attention for momentum tracking.
    """
    weights = np.array([decay_factor ** (day - d) for d in range(1, day + 1)])
    return weights / weights.sum()


def team_interaction_score(home: str, away: str, team_profiles: dict) -> float:
    """
    Compute interaction score between two teams based on historical patterns.
    Higher score = more competitive/uncertain matchup.
    """
    hp = team_profiles.get(home.upper(), {'h_win_p': 0.33, 'h_draw_p': 0.33})
    ap = team_profiles.get(away.upper(), {'a_win_p': 0.33, 'a_draw_p': 0.33})
    
    # Interaction = product of win probabilities + draw base rate
    interaction = hp['h_win_p'] * ap['a_win_p'] + 0.33 * hp['h_draw_p']
    return float(interaction)


def compute_team_form(team: str, df: pd.DataFrame, max_matches: int = 10) -> dict:
    """
    Compute team form coefficients using exponential moving average.
    This is our simplified 'temporal attention' for momentum.
    """
    team_games = df[(df['home'] == team) | (df['away'] == team)].sort_values('day', ascending=False)
    
    if len(team_games) == 0:
        return {'form_h': 0.5, 'form_a': 0.5, 'momentum': 0.5}
    
    # Exponential weighting for recent matches
    alphas = [0.35, 0.25, 0.18, 0.12, 0.08, 0.05, 0.03, 0.02, 0.01, 0.01]
    
    form_h = 0.33
    form_a = 0.33
    weight_sum = 0
    
    for i, (_, row) in enumerate(team_games.head(max_matches).iterrows()):
        alpha = alphas[i] if i < len(alphas) else 0.01
        
        if row['home'] == team:
            outcome = 1 if row['outcome'] == 'HOME' else (0.5 if row['outcome'] == 'DRAW' else 0)
            form_h = form_h * (1 - alpha) + outcome * alpha
            weight_sum += alpha
        else:
            outcome = 1 if row['outcome'] == 'AWAY' else (0.5 if row['outcome'] == 'DRAW' else 0)
            form_a = form_a * (1 - alpha) + outcome * alpha
            weight_sum += alpha
    
    momentum = (form_h + form_a) / 2
    return {'form_h': form_h, 'form_a': form_a, 'momentum': momentum}


# ── DATA PREPARATION ─────────────────────────────────────────────────────────

def load_vfl_data() -> pd.DataFrame:
    """Load VFL match history."""
    conn = sqlite3.connect(_HIST_DB)
    df = pd.read_sql_query("SELECT * FROM matches WHERE outcome IS NOT NULL", conn)
    conn.close()
    
    df['season'] = df['season'].astype(str).str.replace('vf:season:', '', regex=False)
    df['outcome_code'] = df['outcome'].map({'HOME': 0, 'DRAW': 1, 'AWAY': 2})
    
    for col in ['oh', 'od', 'oa', 'h', 'a', 'total', 'day']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df


def load_signature_db() -> dict:
    """Load RNG signature database."""
    if _SIG_DB.exists():
        with open(_SIG_DB, 'r') as f:
            return json.load(f)
    return {}


def build_team_profiles(df: pd.DataFrame) -> dict:
    """Build team performance profiles."""
    teams = pd.concat([df['home'], df['away']]).unique()
    profiles = {}
    
    for team in teams:
        h_games = df[df['home'] == team]
        a_games = df[df['away'] == team]
        
        profiles[team] = {
            'h_win_p': (h_games['outcome'] == 'HOME').mean() if len(h_games) > 0 else 0.33,
            'h_draw_p': (h_games['outcome'] == 'DRAW').mean() if len(h_games) > 0 else 0.33,
            'a_win_p': (a_games['outcome'] == 'AWAY').mean() if len(a_games) > 0 else 0.33,
            'a_draw_p': (a_games['outcome'] == 'DRAW').mean() if len(a_games) > 0 else 0.33,
        }
    return profiles


def true_probs(oh: float, od: float, oa: float) -> tuple:
    """Remove bookmaker margin."""
    probs = [1/oh, 1/od, 1/oa]
    margin = sum(probs)
    return [p / margin for p in probs]


def extract_features(row: pd.Series, team_profiles: dict, df: pd.DataFrame) -> np.ndarray:
    """Extract feature vector for a match."""
    home, away = row['home'], row['away']
    oh, od, oa = row['oh'], row['od'], row['oa']
    day = int(row.get('day', 15))
    
    # Odds features
    p_h, p_d, p_a = true_probs(oh, od, oa)
    
    # Team profiles
    hp = team_profiles.get(home.upper(), {'h_win_p': 0.33, 'h_draw_p': 0.33})
    ap = team_profiles.get(away.upper(), {'a_win_p': 0.33, 'a_draw_p': 0.33})
    
    # Form/momentum
    home_form = compute_team_form(home, df)
    away_form = compute_team_form(away, df)
    
    # Interaction score
    interaction = team_interaction_score(home, away, team_profiles)
    
    # H2H record
    h2h_games = df[((df['home'] == home) & (df['away'] == away)) | 
                   ((df['home'] == away) & (df['away'] == home))]
    h2h_h = (h2h_games['outcome'] == 'HOME').sum() if len(h2h_games) > 0 else 0
    h2h_d = (h2h_games['outcome'] == 'DRAW').sum() if len(h2h_games) > 0 else 0
    h2h_a = (h2h_games['outcome'] == 'AWAY').sum() if len(h2h_games) > 0 else 0
    
    features = [
        # Odds-implied probabilities
        p_h, p_d, p_a,
        # Team profile probabilities  
        hp['h_win_p'], hp['h_draw_p'],
        ap['a_win_p'], ap['a_draw_p'],
        # Momentum/form
        home_form['form_h'], home_form['form_a'], home_form['momentum'],
        away_form['form_h'], away_form['form_a'], away_form['momentum'],
        # Interaction
        interaction,
        # H2H counts
        h2h_h, h2h_d, h2h_a,
        # Derived
        oh, od, oa,  # Raw odds
        day / 30.0,  # Normalized day
    ]
    
    return np.array(features, dtype=np.float32)


# ── MODEL TRAINING ────────────────────────────────────────────────────────────

def train_model():
    """Train the Axial Transformer ensemble model."""
    print("[Axial Transformer] Loading data...")
    df = load_vfl_data()
    sig_db = load_signature_db()
    team_profiles = build_team_profiles(df)
    
    print(f"[Axial Transformer] {len(df)} matches, {len(team_profiles)} teams")
    
    # Extract features
    X, y = [], []
    for _, row in df.iterrows():
        if pd.notna(row['outcome_code']):
            X.append(extract_features(row, team_profiles, df))
            y.append(int(row['outcome_code']))
    
    X = np.array(X)
    y = np.array(y)
    
    # Split
    n = len(X)
    n_train = int(n * 0.9)
    indices = np.random.permutation(n)
    train_idx, val_idx = indices[:n_train], indices[n_train:]
    
    X_train, X_val = X[train_idx], X[val_idx]
    y_train, y_val = y[train_idx], y[val_idx]
    
    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    
    # Train Random Forest (fast, no PyTorch needed)
    print("[Axial Transformer] Training Random Forest...")
    model = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
    model.fit(X_train_scaled, y_train)
    
    # Validation accuracy
    val_acc = model.score(X_val_scaled, y_val)
    print(f"[Axial Transformer] Validation accuracy: {val_acc:.4f}")
    
    # Feature importance
    feature_names = [
        'p_h', 'p_d', 'p_a',
        'h_win_p', 'h_draw_p', 'a_win_p', 'a_draw_p',
        'home_form_h', 'home_form_a', 'home_momentum',
        'away_form_h', 'away_form_a', 'away_momentum',
        'interaction',
        'h2h_h', 'h2h_d', 'h2h_a',
        'oh', 'od', 'oa', 'day_norm'
    ]
    
    importance = list(zip(feature_names, model.feature_importances_))
    importance.sort(key=lambda x: -x[1])
    print("[Axial Transformer] Top features:")
    for name, imp in importance[:5]:
        print(f"  {name}: {imp:.3f}")
    
    # Save model
    model_data = {
        'model': model,
        'scaler': scaler,
        'team_profiles': team_profiles,
        'sig_db': sig_db,
        'feature_names': feature_names,
    }
    
    with open(_MODEL_PT, 'wb') as f:
        pickle.dump(model_data, f)
    
    print(f"[Axial Transformer] Model saved to {_MODEL_PT}")
    return model_data


# ── INFERENCE ────────────────────────────────────────────────────────────────

def predict_fixture(fixture: dict, model_data: dict) -> dict:
    """Predict a single fixture."""
    model = model_data['model']
    scaler = model_data['scaler']
    team_profiles = model_data['team_profiles']
    sig_db = model_data['sig_db']
    
    # Create row-like object
    row = pd.Series(fixture)
    features = extract_features(row, team_profiles, pd.DataFrame()).reshape(1, -1)
    features_scaled = scaler.transform(features)
    
    # Model prediction
    probs = model.predict_proba(features_scaled)[0]
    prediction = int(np.argmax(probs))
    confidence = max(probs)
    
    # Map prediction
    pred_map = {0: 'H', 1: 'D', 2: 'A'}
    pred_label = pred_map[prediction]
    
    # Certainity score (0-100)
    certainty = int(50 + confidence * 50)
    
    # Signature ensemble
    home, away = fixture['home'], fixture['away']
    oh, od, oa = fixture['oh'], fixture['od'], fixture['oa']
    
    key = f"{home.upper()}|{away.upper()}|{oh:.1f}|{od:.1f}|{oa:.1f}"
    sig_entry = sig_db.get(key, {})
    
    if sig_entry and sig_entry.get('total', 0) >= 5:
        counts = sig_entry['counts']
        sig_best = max(counts, key=counts.get)
        sig_rate = counts[sig_best] / sig_entry['total']
        
        # Adjust certainty based on signature
        if sig_best == pred_label:
            certainty = int(certainty * (1 - 0.3) + sig_rate * 100 * 0.3)
            label = f"TRANSFORMER + SIG {sig_rate:.0%}"
        else:
            certainty = int(certainty * 0.7 + sig_rate * 100 * 0.3)
            label = f"TRANSFORMER (vs SIG {sig_rate:.0%})"
    else:
        label = "TRANSFORMER"
    
    # EV calculation
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


# ── ONNX EXPORT (via sklearn-onnx) ────────────────────────────────────────────

def export_onnx(model_data: dict):
    """Export model to ONNX format."""
    try:
        import skl2onnx
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType
        
        model = model_data['model']
        feature_count = len(model_data['feature_names'])
        
        initial_type = [('float_input', FloatTensorType([None, feature_count]))]
        onnx_model = convert_sklearn(model, initial_types=initial_type)
        
        with open(_MODEL_OUT, 'wb') as f:
            f.write(onnx_model.SerializeToString())
        
        print(f"[Axial Transformer] ONNX model saved to {_MODEL_OUT}")
        return True
    except ImportError:
        print("[Axial Transformer] sklearn-onnx not available, skipping ONNX export")
        return False


# ── MAIN ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    model_data = train_model()
    export_onnx(model_data)
    
    # Test prediction
    test_fixture = {
        'home': 'CHELSEA',
        'away': 'WOLVERHAMPTON', 
        'oh': 1.4,
        'od': 5.0,
        'oa': 5.8,
        'day': 22,
        'season': 'vf:season:3075072'
    }
    
    result = predict_fixture(test_fixture, model_data)
    print("\n[SAMPLE PREDICTION]")
    print(json.dumps(result, indent=2))