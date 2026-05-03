"""
Axial Transformer for VFL Prediction
===================================
Mimics the transformer architecture with:
1. Temporal attention layer for momentum tracking
2. Team interaction attention for matchups
3. Ensemble with signature database
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import pandas as pd
import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import math

# ── CONFIG ─────────────────────────────────────────────────────────────────────
_VFL_REPO = Path('/root/.openclaw/workspace/vfl-repo')
_HIST_DB = _VFL_REPO / 'data' / 'databases' / 'vfl_history.db'
_SIG_DB = _VFL_REPO / 'data' / 'models' / 'master_rng_signatures.json'
_TEAMS_FILE = _VFL_REPO / 'data' / 'models' / 'teams.json'
_MODEL_OUT = _VFL_REPO / 'data' / 'models' / 'axial_transformer_v1.onnx'

# Model hyperparameters
D_MODEL = 128
N_HEADS = 8
N_LAYERS = 4
MAX_SEQ_LEN = 64
DROPOUT = 0.1
TEAM_EMB_DIM = 64
ODDS_DIM = 8


# ── DATA PREPARATION ────────────────────────────────────────────────────────────

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


def load_signature_db() -> Dict:
    """Load RNG signature database."""
    if _SIG_DB.exists():
        with open(_SIG_DB, 'r') as f:
            return json.load(f)
    return {}


def get_team_mapping(df: pd.DataFrame) -> Dict[str, int]:
    """Create team to index mapping."""
    teams = sorted(set(df['home'].tolist() + df['away'].tolist()))
    return {team: idx for idx, team in enumerate(teams)}


def encode_odds(oh: float, od: float, oa: float) -> np.ndarray:
    """Encode odds into feature vector."""
    # Normalize odds (typical range 1.2 - 10.0)
    odds = np.array([oh, od, oa], dtype=np.float32)
    odds = np.clip(odds / 5.0, 0.24, 2.0)
    
    # Add derived features
    probs = 1.0 / odds
    margin = probs.sum()
    probs = probs / margin  # Normalize to true probabilities
    
    # Concat features
    features = np.concatenate([odds, probs, [margin]])
    return features.astype(np.float32)


def prepare_sequence(team: str, team_map: Dict[str, int], df: pd.DataFrame, 
                     max_len: int = MAX_SEQ_LEN) -> np.ndarray:
    """Prepare temporal sequence for a team (recent results)."""
    team_games = df[(df['home'] == team) | (df['away'] == team)].sort_values('day', ascending=False)
    
    seq = np.zeros((max_len, TEAM_EMB_DIM), dtype=np.float32)
    
    for i, (_, row) in enumerate(team_games.head(max_len).iterrows()):
        # Encode result
        if row['outcome'] == 'HOME':
            result = [1, 0, 0]
        elif row['outcome'] == 'DRAW':
            result = [0, 1, 0]
        else:
            result = [0, 0, 1]
        
        # Encode goal difference
        gd = 0
        if row['home'] == team:
            gd = row['h'] - row['a']
        else:
            gd = row['a'] - row['h']
        gd_enc = [min(max(gd, -5), 5) / 5.0]
        
        # Encode position (home/away)
        pos = [1.0] if row['home'] == team else [0.0]
        
        # Build embedding
        emb = np.concatenate([result, gd_enc, pos])
        seq[i] = np.pad(emb, (0, TEAM_EMB_DIM - len(emb)))
    
    return seq


# ── AXIAL TRANSFORMER MODEL ───────────────────────────────────────────────────

class TemporalAttention(nn.Module):
    """Attention over temporal sequence for momentum tracking."""
    
    def __init__(self, d_model: int, n_heads: int):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        
        self.q_proj = nn.Linear(d_model, d_model)
        self.k_proj = nn.Linear(d_model, d_model)
        self.v_proj = nn.Linear(d_model, d_model)
        self.out_proj = nn.Linear(d_model, d_model)
        
        self.layernorm = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(DROPOUT)
    
    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        """
        x: (batch, seq_len, d_model)
        """
        B, S, D = x.shape
        
        Q = self.q_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        K = self.k_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        V = self.v_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        
        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.head_dim)
        
        # Causal mask for temporal attention
        causal_mask = torch.triu(torch.ones(S, S, device=x.device), diagonal=1).bool()
        scores = scores.masked_fill(causal_mask.unsqueeze(0).unsqueeze(0), float('-inf'))
        
        attn = F.softmax(scores, dim=-1)
        attn = self.dropout(attn)
        
        out = torch.matmul(attn, V)
        out = out.transpose(1, 2).contiguous().view(B, S, D)
        out = self.out_proj(out)
        
        return self.layernorm(x + self.dropout(out))


class TeamInteractionAttention(nn.Module):
    """Cross-attention between home and away team representations."""
    
    def __init__(self, d_model: int, n_heads: int):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        
        self.q_proj = nn.Linear(d_model, d_model)
        self.k_proj = nn.Linear(d_model, d_model)
        self.v_proj = nn.Linear(d_model, d_model)
        self.out_proj = nn.Linear(d_model, d_model)
        
        self.layernorm = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(DROPOUT)
    
    def forward(self, home_repr: torch.Tensor, away_repr: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        home_repr, away_repr: (batch, d_model)
        """
        # Cross attention: home -> away
        Q = self.q_proj(home_repr).view(-1, self.n_heads, self.head_dim)
        K = self.k_proj(away_repr).view(-1, self.n_heads, self.head_dim)
        V = self.v_proj(away_repr).view(-1, self.n_heads, self.head_dim)
        
        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.head_dim)
        attn = F.softmax(scores, dim=-1)
        
        home_updated = home_repr + self.out_proj(
            torch.matmul(attn, V).view(-1, self.d_model)
        )
        
        # Cross attention: away -> home
        Q = self.q_proj(away_repr).view(-1, self.n_heads, self.head_dim)
        K = self.k_proj(home_repr).view(-1, self.n_heads, self.head_dim)
        V = self.v_proj(home_repr).view(-1, self.n_heads, self.head_dim)
        
        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.head_dim)
        attn = F.softmax(scores, dim=-1)
        
        away_updated = away_repr + self.out_proj(
            torch.matmul(attn, V).view(-1, self.d_model)
        )
        
        return self.layernorm(home_updated), self.layernorm(away_updated)


class AxialTransformer(nn.Module):
    """
    Axial Transformer for VFL prediction.
    
    Architecture:
    - Team embeddings for home/away
    - Temporal attention over each team's history
    - Team interaction attention between teams
    - Signature ensemble layer
    """
    
    def __init__(self, n_teams: int, d_model: int = D_MODEL, n_heads: int = N_HEADS):
        super().__init__()
        
        self.d_model = d_model
        
        # Team embeddings
        self.home_emb = nn.Embedding(n_teams, TEAM_EMB_DIM)
        self.away_emb = nn.Embedding(n_teams, TEAM_EMB_DIM)
        
        # Temporal encoder
        self.temporal_conv = nn.Conv1d(TEAM_EMB_DIM, d_model, kernel_size=1)
        self.temporal_attn = TemporalAttention(d_model, n_heads)
        
        # Team interaction
        self.team_interaction = TeamInteractionAttention(d_model, n_heads)
        
        # Prediction head
        self.prediction_head = nn.Sequential(
            nn.Linear(d_model * 2 + ODDS_DIM, d_model),
            nn.ReLU(),
            nn.Dropout(DROPOUT),
            nn.Linear(d_model, d_model // 2),
            nn.ReLU(),
            nn.Dropout(DROPOUT),
            nn.Linear(d_model // 2, 3)  # H, D, A
        )
        
        self.certainty_head = nn.Sequential(
            nn.Linear(d_model * 2, d_model // 2),
            nn.ReLU(),
            nn.Linear(d_model // 2, 1),
            nn.Sigmoid()
        )
    
    def forward(self, home_ids: torch.Tensor, away_ids: torch.Tensor,
                home_seq: torch.Tensor, away_seq: torch.Tensor,
                odds: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        home_ids, away_ids: (batch,) team indices
        home_seq, away_seq: (batch, seq_len, emb_dim) temporal sequences
        odds: (batch, 8) encoded odds
        """
        B = home_ids.shape[0]
        
        # Team embeddings
        home_base = self.home_emb(home_ids)  # (B, TEAM_EMB_DIM)
        away_base = self.away_emb(away_ids)
        
        # Temporal encoding
        home_seq = self.temporal_conv(home_seq.transpose(1, 2)).transpose(1, 2)
        away_seq = self.temporal_conv(away_seq.transpose(1, 2)).transpose(1, 2)
        
        home_temp = self.temporal_attn(home_seq).mean(dim=1)  # (B, d_model)
        away_temp = self.temporal_attn(away_seq).mean(dim=1)
        
        # Team interaction
        home_final, away_final = self.team_interaction(home_temp, away_temp)
        
        # Combine representations
        repr_combined = torch.cat([home_final, away_final, odds], dim=-1)
        
        # Predictions
        logits = self.prediction_head(repr_combined)
        certainty = self.certainty_head(torch.cat([home_final, away_final], dim=-1))
        
        return logits, certainty.squeeze(-1)


# ── SIGNATURE ENSEMBLE ─────────────────────────────────────────────────────────

def get_sig_prediction(home: str, away: str, oh: float, od: float, oa: float,
                       sig_db: Dict) -> Optional[Tuple[str, float]]:
    """Get prediction from signature database."""
    key = f"{home.upper()}|{away.upper()}|{oh:.1f}|{od:.1f}|{oa:.1f}"
    entry = sig_db.get(key)
    
    if entry and entry['total'] >= 5:
        counts = entry['counts']
        best = max(counts, key=counts.get)
        rate = counts[best] / entry['total']
        return best, rate * entry['total'] / 20  # Scale certainty
    
    return None


def ensemble_with_signatures(model_out: Tuple[torch.Tensor, torch.Tensor],
                             sig_pred: Optional[Tuple[str, float]] = None,
                             weight: float = 0.3) -> Tuple[torch.Tensor, float]:
    """Ensemble model prediction with signature database."""
    logits, certainty = model_out
    
    if sig_pred is not None:
        sig_label, sig_conf = sig_pred
        sig_onehot = torch.zeros_like(logits)
        sig_onehot[0, {'HOME': 0, 'DRAW': 1, 'AWAY': 2}[sig_label]] = 1.0
        
        # Weighted ensemble
        alpha = min(weight, sig_conf)
        probs = F.softmax(logits, dim=-1)
        ensemble_probs = (1 - alpha) * probs + alpha * sig_onehot
        
        # Adjust certainty based on agreement
        ensemble_certainty = float(certainty) * (1 - alpha) + sig_conf * alpha
        
        return torch.log(ensemble_probs + 1e-8), ensemble_certainty
    
    return logits, float(certainty)


# ── TRAINING ────────────────────────────────────────────────────────────────────

def create_dataset(df: pd.DataFrame, team_map: Dict[str, int], 
                   sig_db: Dict) -> Tuple[List, List, List, List, List]:
    """Create training dataset."""
    X_home, X_away, X_home_seq, X_away_seq, X_odds = [], [], [], [], []
    y_label, y_certainty = [], []
    
    for _, row in df.iterrows():
        home, away = row['home'], row['away']
        if home not in team_map or away not in team_map:
            continue
        
        # Get temporal sequences
        home_seq = prepare_sequence(home, team_map, df)
        away_seq = prepare_sequence(away, team_map, df)
        
        # Encode odds
        odds = encode_odds(row['oh'], row['od'], row['oa'])
        
        X_home.append(team_map[home])
        X_away.append(team_map[away])
        X_home_seq.append(home_seq[:, :TEAM_EMB_DIM])
        X_away_seq.append(away_seq[:, :TEAM_EMB_DIM])
        X_odds.append(odds)
        y_label.append(row['outcome_code'])
        
        # Certainty from signature db
        sig_pred = get_sig_prediction(home, away, row['oh'], row['od'], row['oa'], sig_db)
        y_certainty.append(sig_pred[1] if sig_pred else 0.5)
    
    return X_home, X_away, X_home_seq, X_away_seq, X_odds, y_label, y_certainty


def train_model():
    """Train the Axial Transformer model."""
    print("[Axial Transformer] Loading data...")
    df = load_vfl_data()
    sig_db = load_signature_db()
    team_map = get_team_mapping(df)
    
    print(f"[Axial Transformer] {len(df)} matches, {len(team_map)} teams")
    
    # Create dataset
    X_home, X_away, X_home_seq, X_away_seq, X_odds, y_label, y_certainty = create_dataset(df, team_map, sig_db)
    
    # Convert to tensors
    X_home = torch.tensor(X_home, dtype=torch.long)
    X_away = torch.tensor(X_away, dtype=torch.long)
    X_home_seq = torch.tensor(X_home_seq, dtype=torch.float32)
    X_away_seq = torch.tensor(X_away_seq, dtype=torch.float32)
    X_odds = torch.tensor(X_odds, dtype=torch.float32)
    y_label = torch.tensor(y_label, dtype=torch.long)
    y_certainty = torch.tensor(y_certainty, dtype=torch.float32)
    
    # Train/val split
    n = len(X_home)
    n_train = int(n * 0.9)
    indices = torch.randperm(n)
    
    train_idx, val_idx = indices[:n_train], indices[n_train:]
    
    # Initialize model
    model = AxialTransformer(n_teams=len(team_map))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)
    
    # Training loop
    print("[Axial Transformer] Training...")
    model.train()
    
    for epoch in range(50):
        optimizer.zero_grad()
        
        logits, certainty = model(
            X_home[train_idx], X_away[train_idx],
            X_home_seq[train_idx], X_away_seq[train_idx],
            X_odds[train_idx]
        )
        
        loss_cls = F.cross_entropy(logits, y_label[train_idx])
        loss_cert = F.mse_loss(certainty, y_certainty[train_idx])
        loss = loss_cls + 0.5 * loss_cert
        
        loss.backward()
        optimizer.step()
        
        if epoch % 10 == 0:
            print(f"  Epoch {epoch}: loss={loss.item():.4f}")
    
    # Validation
    model.eval()
    with torch.no_grad():
        logits, certainty = model(
            X_home[val_idx], X_away[val_idx],
            X_home_seq[val_idx], X_away_seq[val_idx],
            X_odds[val_idx]
        )
        acc = (logits.argmax(dim=-1) == y_label[val_idx]).float().mean()
        print(f"[Axial Transformer] Validation accuracy: {acc.item():.4f}")
    
    # Save model
    print(f"[Axial Transformer] Saving model to {_MODEL_OUT}")
    torch.save({
        'model_state_dict': model.state_dict(),
        'team_map': team_map,
        'config': {'d_model': D_MODEL, 'n_heads': N_HEADS, 'n_teams': len(team_map)}
    }, _MODEL_OUT.with_suffix('.pt'))
    
    return model, team_map


# ── ONNX EXPORT ───────────────────────────────────────────────────────────────

def export_onnx(model: AxialTransformer, team_map: Dict[str, int]):
    """Export model to ONNX for fast inference."""
    model.eval()
    
    dummy_home = torch.zeros(1, dtype=torch.long)
    dummy_away = torch.zeros(1, dtype=torch.long)
    dummy_home_seq = torch.zeros(1, MAX_SEQ_LEN, TEAM_EMB_DIM)
    dummy_away_seq = torch.zeros(1, MAX_SEQ_LEN, TEAM_EMB_DIM)
    dummy_odds = torch.zeros(1, ODDS_DIM)
    
    torch.onnx.export(
        model,
        (dummy_home, dummy_away, dummy_home_seq, dummy_away_seq, dummy_odds),
        _MODEL_OUT,
        input_names=['home_id', 'away_id', 'home_seq', 'away_seq', 'odds'],
        output_names=['logits', 'certainty'],
        dynamic_axes={
            'home_seq': {0: 'batch', 1: 'seq_len'},
            'away_seq': {0: 'batch', 1: 'seq_len'},
        },
        opset_version=17
    )
    print(f"[Axial Transformer] ONNX model saved to {_MODEL_OUT}")


if __name__ == '__main__':
    model, team_map = train_model()
    export_onnx(model, team_map)
    print("[Axial Transformer] Done!")