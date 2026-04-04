import json
import os
import sqlite3

DB_PATH = 'vfl_history.db'
ODDS_DIR = 'extracted_odds'
RESULTS_DIR = 'extracted_results'

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Lossless reset: we want exactly what is in the text files
    c.execute('DROP TABLE IF EXISTS matches')
    c.execute('''
        CREATE TABLE matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season TEXT,
            day INTEGER,
            home TEXT, away TEXT,
            oh REAL, od REAL, oa REAL,
            o_o25 REAL, o_u25 REAL, o_gg REAL, o_ng REAL,
            outcome TEXT, h INTEGER, a INTEGER,
            total INTEGER, gg INTEGER, o25 INTEGER,
            half_time TEXT, first_goal TEXT,
            season_start_time TEXT,
            har_timestamp TEXT,
            source_file TEXT,
            UNIQUE(season, day, home, away)
        )
    ''')
    conn.commit()
    return conn

def extract_json_balanced(content, start_pos):
    opener = content.find('{', start_pos)
    if opener == -1: return None, -1
    bracket_count = 0
    in_str = False
    escape = False
    for i in range(opener, len(content)):
        char = content[i]
        if not escape:
            if char == '"': in_str = not in_str
            if not in_str:
                if char == '{': bracket_count += 1
                elif char == '}':
                    bracket_count -= 1
                    if bracket_count == 0: return content[opener:i+1], i+1
        if char == '\\': escape = not escape
        else: escape = False
    return None, -1

def process_data(cursor, data, ts, fname):
    d = data.get('data', {})
    if not d: return
    
    # ── ODDS DATA ──────────────────────────────────────────────
    if 'events' in d:
        day    = int(d.get('matchDay', 0))
        season = str(d.get('seasonId', ''))
        sst    = str(d.get('seasonStartTime', '0'))
        for ev in d.get('events', []):
            ht, at = ev.get('homeTeam', '').upper(), ev.get('awayTeam', '').upper()
            mkts = ev.get('markets', [])
            m1x2 = next((m for m in mkts if m.get('id') == 1), None)
            if not m1x2: continue
            try:
                outs = m1x2.get('outcomes', [])
                oh = float(next(o['odds'] for o in outs if o['id'] == '1'))
                od = float(next(o['odds'] for o in outs if o['id'] == '2'))
                oa = float(next(o['odds'] for o in outs if o['id'] == '3'))
                cursor.execute('''INSERT OR IGNORE INTO matches (season, day, home, away, oh, od, oa, season_start_time, har_timestamp, source_file)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (season, day, ht, at, oh, od, oa, sst, ts, fname))
                cursor.execute('UPDATE matches SET oh=?, od=?, oa=?, season_start_time=?, har_timestamp=? WHERE season=? AND day=? AND home=? AND away=?',
                               (oh, od, oa, sst, ts, season, day, ht, at))
            except: continue
            
    # ── RESULTS DATA ───────────────────────────────────────────
    elif 'results' in d:
        current = d.get('current', {}) or {}
        day    = int(current.get('matchDay', 0))
        season = str(current.get('seasonId', ''))
        sst    = str(current.get('seasonStartTime', '0'))
        for r in d.get('results', []):
            ht, at = r.get('homeTeam', '').upper(), r.get('awayTeam', '').upper()
            ft = r.get('fullTime', '0:0')
            try: h, a = map(int, ft.split(':'))
            except: h, a = 0, 0
            outcome = 'HOME' if h > a else ('AWAY' if a > h else 'DRAW')
            cursor.execute('''INSERT OR IGNORE INTO matches (season, day, home, away, h, a, outcome, total, gg, o25, half_time, first_goal, season_start_time, har_timestamp, source_file)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                              (season, day, ht, at, h, a, outcome, h+a, 1 if h>0 and a>0 else 0, 1 if h+a>2 else 0, r.get('halfTime'), r.get('firstGoal'), sst, ts, fname))
            cursor.execute('''UPDATE matches SET h=?, a=?, outcome=?, total=?, gg=?, o25=?, half_time=?, first_goal=?, season_start_time=?, har_timestamp=? 
                              WHERE season=? AND day=? AND home=? AND away=?''', 
                              (h, a, outcome, h+a, 1 if h>0 and a>0 else 0, 1 if h+a>2 else 0, r.get('halfTime'), r.get('firstGoal'), sst, ts, season, day, ht, at))

def migrate_from_directory(conn, directory, label):
    cursor = conn.cursor()
    print(f"PRECISION-BORING {label} FROM {directory}...")
    files = [f for f in os.listdir(directory) if f.endswith('.txt')]
    for fname in files:
        path = os.path.join(directory, fname)
        print(f"  Boring {fname}...")
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                pos = 0
                while True:
                    idx = content.find('bizCode": 10000', pos)
                    if idx == -1: break
                    obj_start = content.rfind('{', 0, idx)
                    raw_json, next_pos = extract_json_balanced(content, obj_start)
                    if raw_json:
                        try:
                            # Also pick up the closest timestamp if we are in results folders
                            ts = "0"
                            if label == "RESULTS":
                                ts_idx = content.rfind("TIMESTAMP:", 0, obj_start)
                                if ts_idx != -1 and (obj_start - ts_idx) < 500:
                                    ts = content[ts_idx+10:content.find("\n", ts_idx)].strip()
                            data = json.loads(raw_json)
                            process_data(cursor, data, ts, fname)
                        except: pass
                        pos = next_pos
                    else: pos = idx + 1
            conn.commit()
        except Exception as e: print(f"    [Error] {fname}: {e}")

if __name__ == '__main__':
    conn = setup_db()
    migrate_from_directory(conn, ODDS_DIR, "ODDS")
    migrate_from_directory(conn, RESULTS_DIR, "RESULTS")
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM matches')
    rows = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM matches WHERE oh IS NOT NULL AND h IS NOT NULL')
    joined = cursor.fetchone()[0]
    print(f"\nFinal Migration Complete. Total Matches: {rows} (Joined: {joined})")
    conn.close()
