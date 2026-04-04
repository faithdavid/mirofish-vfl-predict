import sqlite3
DB_PATH = 'vfl_history.db'
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
# Find the absolute latest season and day where we have both odds and results
c.execute("SELECT season, MAX(day) FROM matches WHERE oh IS NOT NULL AND outcome IS NOT NULL GROUP BY season ORDER BY season DESC LIMIT 1")
row = c.fetchone()
if row:
    print(f"LATEST_GROUND_TRUTH: {row[0]}, Day {row[1]}")
else:
    print("LATEST_GROUND_TRUTH: NONE_FOUND")
conn.close()
