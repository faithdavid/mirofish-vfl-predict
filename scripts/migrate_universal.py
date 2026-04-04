import json
import os
import sqlite3
import base64
from urllib.parse import urlparse

DB_PATH = 'vfl_history.db'
HAR_DIR = 'ANalysis'
ODDS_BASE = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/match/day/event/list"
RESULT_BASE = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/result"

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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
            source_har TEXT,
            UNIQUE(season, day, home, away)
        )
    ''')
    conn.commit()
    return conn

def get_base_url(url):
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    except: return ""

def process_data(cursor, data, har_ts, fname):
    d = data.get('data', {})
    if not d: return

    # ODDS DATA
    if 'events' in d:
        day    = int(d.get('matchDay', 0))
        season = d.get('seasonId', '')
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
                cursor.execute('''INSERT OR IGNORE INTO matches (season, day, home, away, oh, od, oa, season_start_time, har_timestamp, source_har)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (season, day, ht, at, oh, od, oa, sst, har_ts, fname))
                cursor.execute('UPDATE matches SET oh=?, od=?, oa=?, season_start_time=?, har_timestamp=? WHERE season=? AND day=? AND home=? AND away=?',
                               (oh, od, oa, sst, har_ts, season, day, ht, at))
            except: continue

    # RESULTS DATA
    elif 'results' in d:
        current = d.get('current', {}) or {}
        day    = int(current.get('matchDay', 0))
        season = current.get('seasonId', '')
        sst    = str(current.get('seasonStartTime', '0'))
        for r in d.get('results', []):
            ht, at = r.get('homeTeam', '').upper(), r.get('awayTeam', '').upper()
            ft = r.get('fullTime', '0:0')
            try: h, a = map(int, ft.split(':'))
            except: h, a = 0, 0
            outcome = 'HOME' if h > a else ('AWAY' if a > h else 'DRAW')
            cursor.execute('''INSERT OR IGNORE INTO matches (season, day, home, away, h, a, outcome, total, gg, o25, half_time, first_goal, season_start_time, har_timestamp, source_har)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                              (season, day, ht, at, h, a, outcome, h+a, 1 if h>0 and a>0 else 0, 1 if h+a>2 else 0, r.get('halfTime'), r.get('firstGoal'), sst, har_ts, fname))
            cursor.execute('''UPDATE matches SET h=?, a=?, outcome=?, total=?, gg=?, o25=?, half_time=?, first_goal=?, season_start_time=?, har_timestamp=? 
                              WHERE season=? AND day=? AND home=? AND away=?''', 
                              (h, a, outcome, h+a, 1 if h>0 and a>0 else 0, 1 if h+a>2 else 0, r.get('halfTime'), r.get('firstGoal'), sst, har_ts, season, day, ht, at))

def parse_all_hars(conn):
    cursor = conn.cursor()
    print(f"STARTING GOLD STANDARD MIGRATION...")
    
    for fname in os.listdir(HAR_DIR):
        if not fname.endswith('.har'): continue
        path = os.path.join(HAR_DIR, fname)
        print(f"  Processing {fname}...")
        
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                har_data = json.load(f)
                entries = har_data.get('log', {}).get('entries', [])
                
                for entry in entries:
                    url = entry.get('request', {}).get('url', '')
                    base = get_base_url(url)
                    if base in [ODDS_BASE, RESULT_BASE]:
                        ts = entry.get('startedDateTime', '0')
                        content = entry.get('response', {}).get('content', {})
                        text = content.get('text', '')
                        if content.get('encoding') == 'base64' and text:
                            try: text = base64.b64decode(text).decode('utf-8')
                            except: continue
                        
                        if text:
                            try:
                                data = json.loads(text)
                                if data.get('bizCode') == 10000:
                                    process_data(cursor, data, ts, fname)
                            except: pass
                conn.commit()
        except Exception as e:
            print(f"    [Error] Skipping {fname}: {e}")

    cursor.execute('SELECT COUNT(*) FROM matches')
    rows = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM matches WHERE oh IS NOT NULL AND h IS NOT NULL')
    joined = cursor.fetchone()[0]
    print(f"\nMigration Complete. Total Matches: {rows} (Joined: {joined})")

if __name__ == '__main__':
    conn = setup_db()
    parse_all_hars(conn)
    conn.close()
