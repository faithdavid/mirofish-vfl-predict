#!/usr/bin/env python3
"""
Axial Transformer Inference
============================
Fast inference using ONNX model with signature database ensemble.
"""

import numpy as np
import onnxruntime as ort
import json
import pickle
from pathlib import Path

MODEL_DIR = Path('/root/.openclaw/workspace/vfl-repo/data/models')
ONNX_MODEL = MODEL_DIR / 'axial_transformer_v1.onnx'
WEIGHTS_FILE = MODEL_DIR / 'axial_transformer_v1.pkl'
SIG_DB = MODEL_DIR.parent.parent / 'master_rng_signatures.json'


def load_model():
    """Load ONNX model for inference."""
    session = ort.InferenceSession(str(ONNX_MODEL), providers=['CPUExecutionProvider'])
    
    with open(WEIGHTS_FILE, 'rb') as f:
        weights_data = pickle.load(f)
    
    with open(SIG_DB, 'r') as f:
        sig_db = json.load(f)
    
    return session, weights_data, sig_db


def predict_onnx(session, weights_data, sig_db, fixture):
    """Predict fixture outcome using ONNX model."""
    home = fixture['home']
    away = fixture['away']
    oh = float(fixture['oh'])
    od = float(fixture['od'])
    oa = float(fixture['oa'])
    
    # Prepare features
    probs = np.array([1/oh, 1/od, 1/oa], dtype=np.float32)
    probs = probs / probs.sum()
    
    mean = weights_data['feature_mean']
    std = weights_data['feature_std']
    
    raw_features = np.concatenate([
        probs,
        [oh/10, od/10, oa/10, 0.5]  # day normalized
    ])
    
    features = (raw_features - mean) / std
    
    # Run ONNX inference
    input_name = session.get_inputs()[0].name
    output = session.run(None, {input_name: features.reshape(1, -1)})
    
    probs_out = output[0][0]
    pred = int(np.argmax(probs_out))
    
    pred_map = {0: 'H', 1: 'D', 2: 'A'}
    cert = int(50 + probs_out[pred] * 50)
    
    # Signature ensemble
    key = f"{home.upper()}|{away.upper()}|{oh:.1f}|{od:.1f}|{oa:.1f}"
    se = sig_db.get(key, {})
    
    if se.get('total', 0) >= 5:
        cnt = se['counts']
        sp = max(cnt, key=cnt.get)
        sr = cnt[sp] / se['total']
        if sp == pred_map[pred]:
            cert = int(cert * 0.7 + sr * 100 * 0.3)
    
    target_odds = oh if pred == 0 else (od if pred == 1 else oa)
    
    return {
        'home': home,
        'away': away,
        'prediction': pred_map[pred],
        'prediction_label': {0: 'HOME', 1: 'DRAW', 2: 'AWAY'}[pred],
        'certainty_score': cert,
        'tier': 'LOCK' if cert >= 85 else ('SIGNAL' if cert >= 70 else 'MODERATE'),
        'target_odds': target_odds,
        'h_win_prob': round(float(probs_out[0]), 3),
        'draw_prob': round(float(probs_out[1]), 3),
        'a_win_prob': round(float(probs_out[2]), 3),
    }


if __name__ == '__main__':
    import json
    
    session, weights, sig_db = load_model()
    
    # Test fixtures
    test_fixtures = [
        {'home': 'CHELSEA', 'away': 'WOLVERHAMPTON', 'oh': 1.4, 'od': 5.0, 'oa': 5.8},
        {'home': 'LIVERPOOL', 'away': 'MANCHESTER RED', 'oh': 2.35, 'od': 3.25, 'oa': 2.90},
        {'home': 'ARSENAL', 'away': 'CHELSEA', 'oh': 2.1, 'od': 3.4, 'oa': 3.0},
    ]
    
    results = []
    for f in test_fixtures:
        result = predict_onnx(session, weights, sig_db, f)
        results.append(result)
        print(json.dumps(result, indent=2))
        print()
    
    print(f"[Axial Transformer] Model ready at {ONNX_MODEL}")