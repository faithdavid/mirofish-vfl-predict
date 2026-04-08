import sqlite3
DB_PATH = 'vfl_history.db'
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
# Search for any match in season 3073974 that has a valid timestamp
c.execute("SELECT DISTINCT season_start_time FROM matches WHERE season LIKE '%3073974%' AND season_start_time != '0' LIMIT 1")
row = c.fetchone()
if row:
    print(f"RECOVERED_SST: {row[0]}")
else:
    print("RECOVERED_SST: NOT_FOUND")
conn.close()
