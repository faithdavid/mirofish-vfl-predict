#!/usr/bin/env python3
"""
Axial Transformer VFL - Final Fast MVP
======================================
"""

import numpy as np
import sqlite3
import json
import pickle
from pathlib import Path

DB = Path('/root/.openclaw/workspace/vfl-repo/data/databases/vfl_history.db')
SIG = Path('/root/.openclaw/workspace/vfl-repo/data/models/master_rng_signatures.json')
MODEL_OUT = Path('/root/.openclaw/workspace/vfl-repo/data/models/axial_transformer_v1.pkl')
ONNX_OUT = Path('/root/.openclaw/workspace/vfl-repo/data/models/axial_transformer_v1.onnx')


def train():
    print("[Axial] Loading...")
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    cur.execute("SELECT home, away, oh, od, oa, outcome FROM matches WHERE outcome IS NOT NULL AND oh IS NOT NULL AND od IS NOT NULL AND oa IS NOT NULL LIMIT 30000")
    rows = cur.fetchall()
    conn.close()
    
    with open(SIG, 'r') as f:
        sig_db = json.load(f)
    
    print(f"[Axial] {len(rows)} samples")
    
    # Team stats
    w, d, l = {}, {}, {}
    for h, a, _, _, _, o in rows:
        for t in (h, a):
            if t not in w: w[t] = d[t] = l[t] = 0
        if o == 'HOME': w[h] += 1; l[a] += 1
        elif o == 'AWAY': w[a] += 1; l[h] += 1
        else: d[h] += 1; d[a] += 1
    
    X, y = [], []
    for h, a, oh, od, oa, o in rows:
        if not all(isinstance(x, (int, float)) and x for x in [oh, od, oa]):
            continue
            
        p = np.array([1/float(oh), 1/float(od), 1/float(oa)]); p = p / p.sum()
        
        tw = w.get(h, 0) / max(1, w.get(h, 0) + d.get(h, 0) + l.get(h, 0))
        td = d.get(h, 0) / max(1, w.get(h, 0) + d.get(h, 0) + l.get(h, 0))
        aw = w.get(a, 0) / max(1, w.get(a, 0) + d.get(a, 0) + l.get(a, 0))
        ad = d.get(a, 0) / max(1, w.get(a, 0) + d.get(a, 0) + l.get(a, 0))
        
        X.append(np.concatenate([p, [tw, td, aw, ad, float(oh)/10, float(od)/10, float(oa)/10]]))
        y.append(0 if o == 'HOME' else (1 if o == 'DRAW' else 2))
    
    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.int32)
    
    X_mean = X.mean(axis=0)
    X_std = X.std(axis=0) + 1e-8
    Xn = (X - X_mean) / X_std
    
    np.random.seed(42)
    W = np.random.randn(X.shape[1], 3).astype(np.float32) * 0.1
    b = np.zeros(3)
    
    print("[Axial] Training...")
    for _ in range(30):
        for c in range(3):
            z = Xn @ W[:, c] + b[c]
            pr = 1 / (1 + np.exp(-np.clip(z, -10, 10)))
            W[:, c] -= 0.1 * (Xn.T * (pr - (y == c))).mean(axis=1)
            b[c] -= 0.1 * (pr - (y == c)).mean()
    
    split = int(0.9 * len(Xn))
    acc = (np.argmax(Xn[split:] @ W + b, axis=1) == y[split:]).mean()
    print(f"[Axial] Accuracy: {acc:.3f}")
    
    model = {'W': W, 'b': b, 'mean': X_mean, 'std': X_std, 'sig_db': sig_db}
    with open(MODEL_OUT, 'wb') as f:
        pickle.dump(model, f)
    print(f"[Axial] Saved to {MODEL_OUT}")
    
    # ONNX
    try:
        import onnx
        from onnx import helper, TensorProto, numpy_helper
        
        W_onnx = W.T.astype(np.float32)
        b_onnx = b.astype(np.float32)
        
        model = helper.make_model(
            helper.make_graph(
                [helper.make_node('MatMul', ['X', 'W'], ['Y']),
                 helper.make_node('Add', ['Y', 'b'], ['Z']),
                 helper.make_node('Softmax', ['Z'], ['Out'], axis=1)],
                'axial',
                [helper.make_tensor_value_info('X', TensorProto.FLOAT, [None, W.shape[0]])],
                [helper.make_tensor_value_info('Out', TensorProto.FLOAT, [None, 3])],
                [numpy_helper.from_array(W_onnx, 'W'), numpy_helper.from_array(b_onnx, 'b')]
            ),
            opset_imports=[helper.make_opsetid('', 17)]
        )
        onnx.checker.check_model(model)
        onnx.save(model, str(ONNX_OUT))
        print(f"[Axial] ONNX saved to {ONNX_OUT}")
    except Exception as e:
        print(f"[Axial] ONNX: {e}")
    
    return model


if __name__ == '__main__':
    train()