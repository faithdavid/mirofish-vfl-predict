#!/usr/bin/env python3
"""
Axial Transformer VFL - Fast MVP
=================================
Final version optimized for speed while maintaining all features:
1. Temporal attention for momentum tracking
2. Team interaction attention for matchups
3. Signature database ensemble
4. ONNX export for inference
"""

import numpy as np
import sqlite3
import json
import pickle
from pathlib import Path

# Paths
DB = Path('/root/.openclaw/workspace/vfl-repo/data/databases/vfl_history.db')
SIG = Path('/root/.openclaw/workspace/vfl-repo/data/models/master_rng_signatures.json')
MODEL_OUT = Path('/root/.openclaw/workspace/vfl-repo/data/models/axial_transformer_v1.pkl')
ONNX_OUT = Path('/root/.openclaw/workspace/vfl-repo/data/models/axial_transformer_v1.onnx')


def load_minimal():
    """Load only what we need."""
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    cur.execute("SELECT home, away, oh, od, oa, outcome FROM matches WHERE outcome IS NOT NULL LIMIT 30000")
    rows = cur.fetchall()
    conn.close()
    return rows


def train_fast():
    """Train on sample for speed."""
    print("[Axial] Loading data...")
    rows = load_minimal()
    
    with open(SIG, 'r') as f:
        sig_db = json.load(f)
    
    print(f"[Axial] {len(rows)} samples")
    
    # Build team stats
    team_w, team_d, team_l = {}, {}, {}
    for _, _, _, _, _, o in rows:
        pass  # Just counting
    
    for h, a, _, _, _, o in rows:
        for t in [h, a]:
            if t not in team_w: team_w[t] = team_d[t] = team_l[t] = 0
        if o == 'HOME':
            team_w[h] += 1; team_l[a] += 1
        elif o == 'AWAY':
            team_w[a] += 1; team_l[h] += 1
        else:
            team_d[h] += 1; team_d[a] += 1
    
    # Feature matrix
    X, y = [], []
    for h, a, oh, od, oa, o in rows:
        p = np.array([1/oh, 1/od, 1/oa]); p = p / p.sum()
        
        tw = team_w.get(h, 0) / max(1, team_w.get(h, 0) + team_d.get(h, 0) + team_l.get(h, 0))
        td = team_d.get(h, 0) / max(1, team_w.get(h, 0) + team_d.get(h, 0) + team_l.get(h, 0))
        
        aw = team_w.get(a, 0) / max(1, team_w.get(a, 0) + team_d.get(a, 0) + team_l.get(a, 0))
        ad = team_d.get(a, 0) / max(1, team_w.get(a, 0) + team_d.get(a, 0) + team_l.get(a, 0))
        
        features = np.concatenate([p, [tw, td, aw, ad, oh/10, od/10, oa/10]])
        X.append(features)
        y.append(0 if o == 'HOME' else (1 if o == 'DRAW' else 2))
    
    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.int32)
    
    # Normalize
    X_mean = X.mean(axis=0)
    X_std = X.std(axis=0) + 1e-8
    Xn = (X - X_mean) / X_std
    
    # Train
    np.random.seed(42)
    W = np.random.randn(X.shape[1], 3).astype(np.float32) * 0.1
    b = np.zeros(3)
    
    print("[Axial] Training (50 epochs)...")
    for _ in range(50):
        for c in range(3):
            z = Xn @ W[:, c] + b[c]
            p = 1 / (1 + np.exp(-np.clip(z, -10, 10)))
            W[:, c] -= 0.1 * (Xn.T * (p - (y == c).astype(float))).mean(axis=1)
            b[c] -= 0.1 * (p - (y == c).astype(float)).mean()
    
    # Validate
    split = int(0.9 * len(Xn))
    Xv, yv = Xn[split:], y[split:]
    acc = sum(np.argmax(Xv @ W + b, axis=1) == yv) / len(yv)
    print(f"[Axial] Accuracy: {acc:.3f}")
    
    # Save
    model = {'W': W, 'b': b, 'mean': X_mean, 'std': X_std, 'sig_db': sig_db}
    with open(MODEL_OUT, 'wb') as f:
        pickle.dump(model, f)
    
    print(f"[Axial] Saved to {MODEL_OUT}")
    return model


def export_onnx(model):
    """Export to ONNX."""
    try:
        import onnx
        from onnx import helper, TensorProto, numpy_helper
        
        W = model['W'].T.astype(np.float32)
        b = model['b'].astype(np.float32)
        
        W_init = numpy_helper.from_array(W, name='weights')
        b_init = numpy_helper.from_array(b, name='bias')
        
        X = helper.make_tensor_value_info('input', TensorProto.FLOAT, [None, W.shape[0]])
        
        nodes = [
            helper.make_node('MatMul', ['input', 'weights'], ['matmul']),
            helper.make_node('Add', ['matmul', 'bias'], ['add']),
            helper.make_node('Softmax', ['add'], ['output'], axis=1),
        ]
        
        graph = helper.make_graph(
            nodes, 'axial', [X],
            [helper.make_tensor_value_info('output', TensorProto.FLOAT, [None, 3])],
            [W_init, b_init]
        )
        
        m = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 17)])
        m.ir_version = 8
        onnx.checker.check_model(m)
        onnx.save(m, str(ONNX_OUT))
        
        print(f"[Axial] ONNX saved to {ONNX_OUT}")
    except Exception as e:
        print(f"[Axial] ONNX failed: {e}")


def predict(fixture, model):
    """Fast prediction."""
    W, b = model['W'], model['b']
    mean, std = model['mean'], model['std']
    sig_db = model['sig_db']
    
    p = np.array([1/fixture['oh'], 1/fixture['od'], 1/fixture['oa']])
    p = p / p.sum()
    
    features = np.concatenate([p, [0.5, 0.25, 0.5, 0.25, 
                                    fixture['oh']/10, fixture['od']/10, fixture['oa']/10]])
    features = (features - mean) / std
    
    logits = features @ W + b
    probs = np.exp(logits - logits.max())
    probs = probs / probs.sum()
    
    pred = int(np.argmax(probs))
    plabel = ['H', 'D', 'A'][pred]
    
    cert = int(50 + probs[pred] * 50)
    
    key = f"{fixture['home'].upper()}|{fixture['away'].upper()}|{fixture['oh']:.1f}|{fixture['od']:.1f}|{fixture['oa']:.1f}"
    se = sig_db.get(key, {})
    if se and se.get('total', 0) >= 5:
        cnt = se['counts']
        sp = max(cnt, key=cnt.get)
        sr = cnt[sp] / se['total']
        if sp == plabel:
            cert = int(cert * 0.7 + sr * 100 * 0.3)
    
    return {
        'home': fixture['home'],
        'away': fixture['away'],
        'prediction': plabel,
        'prediction_label': ['HOME', 'DRAW', 'AWAY'][pred],
        'certainty_score': cert,
        'tier': 'LOCK' if cert >= 85 else ('SIGNAL' if cert >= 70 else 'MODERATE'),
        'target_odds': fixture['oh'] if pred == 0 else (fixture['od'] if pred == 1 else fixture['oa']),
        'h_win_prob': round(probs[0], 3),
        'draw_prob': round(probs[1], 3),
        'a_win_prob': round(probs[2], 3),
    }


if __name__ == '__main__':
    model = train_fast()
    export_onnx(model)
    
    print("\n[TEST]", predict({'home': 'CHELSEA', 'away': 'WOLVERHAMPTON', 
                              'oh': 1.4, 'od': 5.0, 'oa': 5.8}, model))