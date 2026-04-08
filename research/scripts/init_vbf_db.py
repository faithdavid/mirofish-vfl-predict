import sqlite3
import os

DB_PATH = 'sovereign_vbf.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Master Ledger: One table to rule them all
    # Stores fixture data, prediction data, and settlement data in one row.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS master_ledger (
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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            settled_at DATETIME,
            status TEXT DEFAULT 'PENDING' -- PENDING, SETTLED, VOID
        )
    ''')
    
    # Indexes for fast lookup
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_season_day ON master_ledger(season_id, match_day)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_status ON master_ledger(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_teams ON master_ledger(home_team, away_team)')

    conn.commit()
    conn.close()
    print(f"[DB] Initialized {DB_PATH}")

if __name__ == "__main__":
    init_db()
