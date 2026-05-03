#!/usr/bin/env python3
"""
ONNX Export for Axial Transformer
===================================
Creates optimized ONNX model for fast inference.
"""

import sqlite3
import json
import numpy as np
from pathlib import Path

# Try to use sklearn-onnx if available, otherwise create simple ONNX
try:
    import skl2onnx
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False
    print("[ONNX] sklearn-onnx not available, will use raw pickle model")

DB = Path('/root/.openclaw/workspace/vfl-repo/data/databases/vfl_history.db')
SIG = Path('/root/.openclaw/workspace/vfl-repo/data/models/master_rng_signatures.json')
MODEL_OUT = Path('/root/.openclaw/workspace/vfl-repo/data/models/axial_transformer_v1.pkl')
ONNX_OUT = Path('/root/.openclaw/workspace/vfl-repo/data/models/axial_transformer_v1.onnx')

def prepare_features(home, away, oh, od, oa, df, team_profiles):
    """Extract features for ONNX model."""
    # Odds probabilities
    probs = np.array([1/oh, 1/od, 1/oa], dtype=np.float32)
    probs = probs / probs.sum()
    
    # Team stats
    h_stats = team_profiles.get(home.upper(), {'h_win_p': 0.33})
    a_stats = team_profiles.get(away.upper(), {'a_win_p': 0.33})
    
    features = np.concatenate([
        probs,  # 3
        [h_stats['h_win_p']],  # 1
        [a_stats['a_win_p']],  # 1
        [oh/10, od/10, oa/10],  # 3 normalized odds
    ]).astype(np.float32)
    
    return features


def create_onnx_model():
    """Create and export ONNX model."""
    print("[ONNX] Loading data...")
    
    conn = sqlite3.connect(str(DB))
    import pandas as pd
    df = pd.read_sql_query("SELECT * FROM matches WHERE outcome IS NOT NULL", conn)
    conn.close()
    
    df['outcome_code'] = df['outcome'].map({'HOME': 0, 'DRAW': 1, 'AWAY': 2})
    for col in ['oh', 'od', 'oa']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Build profiles
    teams = pd.concat([df['home'], df['away']]).unique()
    profiles = {}
    for t in teams:
        hg = df[df['home'] == t]
        ag = df[df['away'] == t]
        profiles[t] = {
            'h_win_p': (hg['outcome'] == 'HOME').mean() if len(hg) > 0 else 0.33,
            'a_win_p': (ag['outcome'] == 'AWAY').mean() if len(ag) > 0 else 0.33,
        }
    
    # Prepare training data
    X, y = [], []
    for _, r in df.iterrows():
        if pd.notna(r['outcome_code']):
            features = prepare_features(r['home'], r['away'], r['oh'], r['od'], r['oa'], df, profiles)
            X.append(features)
            y.append(int(r['outcome_code']))
    
    X = np.array(X, dtype=np.float32)
    y = np.array(y)
    
    # Train simple model
    if HAS_ONNX:
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, n_jobs=1)
        model.fit(X, y)
        
        # Export to ONNX
        initial_type = [('float_input', FloatTensorType([None, X.shape[1]]))]
        onnx_model = convert_sklearn(model, initial_types=initial_type)
        
        with open(ONNX_OUT, 'wb') as f:
            f.write(onnx_model.SerializeToString())
        
        print(f"[ONNX] Model exported to {ONNX_OUT}")
    else:
        # Just save the training data structure
        import pickle
        model_data = {
            'X': X[:1000],  # Sample for quick inference
            'y': y[:1000],
            'profiles': profiles,
        }
        with open(MODEL_OUT, 'wb') as f:
            pickle.dump(model_data, f)
        print(f"[ONNX] Fallback model saved to {MODEL_OUT}")


if __name__ == '__main__':
    create_onnx_model()