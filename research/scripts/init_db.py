import sqlite3
import os

DB_PATH = 'vfl_history.db'

def setup_db():
    print(f"Initializing VFL SQL Database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Matches Table (Detailed)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season TEXT,
            day TEXT,
            home TEXT,
            away TEXT,
            oh REAL,
            od REAL,
            oa REAL,
            o_o25 REAL,
            o_u25 REAL,
            o_gg REAL,
            o_ng REAL,
            outcome TEXT,
            h INTEGER,
            a INTEGER,
            total INTEGER,
            gg INTEGER,
            o25 INTEGER,
            -- Metadata Fields for V5 Determinism
            start_time TEXT,
            match_id TEXT,
            season_start_time TEXT,
            source_har TEXT,
            UNIQUE(season, day, home, away)
        )
    ''')

    # 2. MatchDay Blocks Index (for sequence mirroring)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocks (
            block_hash TEXT PRIMARY KEY,
            outcome_sequence TEXT,
            score_sequence TEXT,
            occurrence_count INTEGER
        )
    ''')

    # Indices for speed
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_odds ON matches (home, away, oh, od, oa)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_season_day ON matches (season, day)')
    
    conn.commit()
    conn.close()
    print("Database structure ready.")

if __name__ == '__main__':
    setup_db()
