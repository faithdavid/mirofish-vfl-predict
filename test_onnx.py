#!/usr/bin/env python3
"""
Verify ONNX inference works
"""

import numpy as np
import onnxruntime as ort
import json
import pickle
from pathlib import Path

BASE = Path('/root/.openclaw/workspace/vfl-repo')
model = pickle.load(open(BASE / 'data/models/axial_transformer_v1.pkl', 'rb'))
sig_db = json.load(open(BASE / 'data/models/master_rng_signatures.json'))

# ONNX session
sess = ort.InferenceSession(str(BASE / 'data/models/axial_transformer_v1.onnx'))

def predict_onnx(fixture):
    oh, od, oa = float(fixture['oh']), float(fixture['od']), float(fixture['oa'])
    p = np.array([1/oh, 1/od, 1/oa]); p = p / p.sum()
    
    features = np.concatenate([p, [0.33, 0.33, 0.33, 0.33, oh/10, od/10, oa/10]], dtype=np.float32)
    features = (features - model['mean']) / model['std']
    
    probs = sess.run(None, {'X': features.reshape(1, -1)})[0][0]
    pred = int(np.argmax(probs))
    plabel = ['H', 'D', 'A'][pred]
    
    cert = int(50 + probs[pred] * 50)
    key = f"{fixture['home'].upper()}|{fixture['away'].upper()}|{oh:.1f}|{od:.1f}|{oa:.1f}"
    se = sig_db.get(key, {})
    if se and se.get('total', 0) >= 5:
        cnt = se['counts']
        sp = max(cnt, key=cnt.get)
        sr = cnt[sp] / se['total']
        if sp == plabel:
            cert = int(cert * 0.7 + sr * 100 * 0.3)
    
    return {'prediction': plabel, 'certainty': cert, 'probs': probs.tolist()}

# Test
f = {'home': 'CHELSEA', 'away': 'WOLVERHAMPTON', 'oh': 1.4, 'od': 5.0, 'oa': 5.8}
print("ONNX prediction:", predict_onnx(f))