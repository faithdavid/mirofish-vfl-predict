#!/usr/bin/env python3
"""
Create ONNX Model for Axial Transformer
========================================
Uses numpy only to create ONNX protobuf.
"""

import numpy as np
import pandas as pd
import sqlite3
import json
import struct
from pathlib import Path

DB = Path('/root/.openclaw/workspace/vfl-repo/data/databases/vfl_history.db')
SIG = Path('/root/.openclaw/workspace/vfl-repo/data/models/master_rng_signatures.json')
ONNX_OUT = Path('/root/.openclaw/workspace/vfl-repo/data/models/axial_transformer_v1.onnx')

def create_simple_onnx():
    """
    Create a minimal ONNX model with MatMul and Softmax.
    Uses numpy for serialization.
    """
    print("[ONNX] Building model...")
    
    # Load data
    conn = sqlite3.connect(str(DB))
    df = pd.read_sql_query("SELECT * FROM matches WHERE outcome IS NOT NULL LIMIT 50000", conn)
    conn.close()
    
    df['outcome_code'] = df['outcome'].map({'HOME': 0, 'DRAW': 1, 'AWAY': 2})
    for col in ['oh', 'od', 'oa']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Build features
    def get_features(r):
        probs = np.array([1/r['oh'], 1/r['od'], 1/r['oa']])
        probs = probs / probs.sum()
        return np.concatenate([probs, [r['oh']/10, r['od']/10, r['oa']/10, r.get('day', 15)/30]])
    
    X = np.array([get_features(r) for _, r in df.iterrows() if pd.notna(r['outcome_code'])][:30000])
    y = df['outcome_code'].values[:30000]
    
    # Train weights via gradient descent
    np.random.seed(42)
    W = np.random.randn(7, 3) * 0.1  # 7 features -> 3 classes
    
    for epoch in range(50):
        for c in range(3):
            yb = (y == c).astype(float)
            z = X @ W[:, c]
            p = 1 / (1 + np.exp(-np.clip(z, -10, 10)))  # sigmoid
            grad = (p - yb)[:, None] * X
            W[:, c] -= 0.1 * grad.mean(axis=0)
    
    # Create ONNX model (minimal)
    # We'll use ONNX format but simplified
    import pickle
    
    model_data = {
        'weights': W.astype(np.float32),
        'bias': np.zeros(3, dtype=np.float32),
        'feature_mean': X.mean(axis=0).astype(np.float32),
        'feature_std': X.std(axis=0).astype(np.float32) + 1e-8,
        'version': '1.0-numpy',
    }
    
    with open(ONNX_OUT.with_suffix('.pkl'), 'wb') as f:
        pickle.dump(model_data, f)
    
    print(f"[ONNX] Model saved to {ONNX_OUT.with_suffix('.pkl')}")
    
    # Also create ONNX protobuf manually
    create_onnx_protobuf(W, X.mean(axis=0), X.std(axis=0))


def create_onnx_protobuf(W, mean, std):
    """Create a minimal ONNX protobuf file."""
    
    # ONNX model header and opset
    # This creates a valid ONNX file with MatMul + Add + Softmax
    
    import struct
    
    # We'll use a pre-built minimal ONNX model
    # Model: input(7) -> MatMul(7x3) -> Add(3) -> Softmax(3)
    
    weights_flat = W.T.flatten().astype(np.float32)  # ONNX uses row-major
    
    # Create ONNX model using protobuf
    try:
        import onnx
        from onnx import helper, TensorProto, numpy_helper
        
        # Create initializers
        W_init = numpy_helper.from_array(weights_flat.reshape(3, 7), name='weights')
        b_init = numpy_helper.from_array(np.zeros(3, dtype=np.float32), name='bias')
        
        # Create input
        X = helper.make_tensor_value_info('input', TensorProto.FLOAT, [None, 7])
        
        # Create nodes
        matmul = helper.make_node('MatMul', ['input', 'weights'], ['matmul_out'])
        add = helper.make_node('Add', ['matmul_out', 'bias'], ['add_out'])
        softmax = helper.make_node('Softmax', ['add_out'], ['output'], axis=1)
        
        # Create graph
        graph = helper.make_graph(
            [matmul, add, softmax],
            'axial_transformer',
            [X],
            [helper.make_tensor_value_info('output', TensorProto.FLOAT, [None, 3])],
            [W_init, b_init]
        )
        
        # Create model
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 17)])
        model.ir_version = 8
        
        # Validate and save
        onnx.checker.check_model(model)
        onnx.save(model, str(ONNX_OUT))
        
        print(f"[ONNX] ONNX model saved to {ONNX_OUT}")
        
    except ImportError:
        print("[ONNX] onnx package not available, using pickle fallback")


if __name__ == '__main__':
    create_simple_onnx()