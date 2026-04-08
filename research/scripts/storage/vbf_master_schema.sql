-- Sovereign VFL Unified PostgreSQL Schema
-- Run this in your Supabase SQL Editor

CREATE TABLE master_ledger (
    match_id TEXT PRIMARY KEY,
    season_id TEXT,
    match_day INTEGER,
    home_team TEXT,
    away_team TEXT,
    
    -- Odds
    odds_h REAL,
    odds_d REAL,
    odds_a REAL,
    
    -- Prediction
    prediction TEXT,
    certainty REAL,
    tier TEXT,
    stake REAL,
    label TEXT,
    
    -- Result
    full_time TEXT,
    actual_h INTEGER,
    actual_a INTEGER,
    outcome TEXT,
    p_l REAL,
    
    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    settled_at TIMESTAMP WITH TIME ZONE,
    status TEXT DEFAULT 'PENDING'
);

-- Real-time Subscriptions (Optional but good for Dashboard)
alter publication supabase_realtime add table master_ledger;

-- Create Indexes for faster querying
CREATE INDEX idx_ml_season_day ON master_ledger(season_id, match_day);
CREATE INDEX idx_ml_status ON master_ledger(status);
CREATE INDEX idx_ml_teams ON master_ledger(home_team, away_team);
