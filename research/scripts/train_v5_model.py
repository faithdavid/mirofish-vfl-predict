import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import sqlite3
import joblib
import os

DB_PATH = 'vfl_history.db'
MODEL_PATH = 'vfl_xgboost_v5.model'

def train_v5_model():
    print("INITIALIZING XGBOOST TRAINING ENGINE...")
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM matches WHERE outcome IS NOT NULL", conn)
    conn.close()
    
    # ── FEATURE ENGINEERING ──────────────────────────────────────────
    # Convert outcomes to numeric
    df['target'] = df['outcome'].map({'HOME': 0, 'DRAW': 1, 'AWAY': 2})
    
    # Select Features: Odds and Stats
    features = ['oh', 'od', 'oa', 'o25', 'gg'] # Basic odds features
    X = df[features]
    y = df['target']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Task: XGBoost Pattern Recognition
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        objective='multi:softprob',
        num_class=3
    )
    
    print(f"Training on {len(X_train)} matches...")
    model.fit(X_train, y_train)
    
    # Evaluate
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print(f"\n[SUCCESS] XGBoost Statistical Accuracy: {acc:.1%}")
    
    # Save the model
    joblib.dump(model, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")
    return model

if __name__ == '__main__':
    train_v5_model()
