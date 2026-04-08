import re

def patch_server():
    server_path = "c:/Users/faith/OneDrive/Documents/GitHub/mirofish/scripts/server.py"
    with open(server_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Replace get_data
    # Use regex to find the block from @app.route('/api/data') down to the end of the function (which is the return jsonify block)
    data_pattern = r"@app\.route\('/api/data'\)\s*def get_data\(\):.*?return jsonify\(\{.*?\}\)"
    
    new_data = """@app.route('/api/data')
def get_data():
    \"\"\"Aggregates all state for the HUD from the unified master ledger.\"\"\"
    try:
        with sqlite3.connect(VBF_DB) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT MAX(match_day), season_id FROM master_ledger")
            row = cursor.fetchone()
            matchday     = row[0] if row[0] is not None else 0
            season       = row[1] if row[1] else "UNKNOWN"
            
            cursor.execute("SELECT * FROM master_ledger WHERE match_day = ? AND season_id = ?", (matchday, season))
            rows = cursor.fetchall()
            fixtures = [dict(r) for r in rows]

            for f in fixtures:
                f['prediction_label'] = f['label']
                if f['prediction'] == 'H': f['target_odds'] = f['odds_h']
                elif f['prediction'] == 'D': f['target_odds'] = f['odds_d']
                else: f['target_odds'] = f['odds_a']
                f['ev'] = 0.05 # Placeholder

            cursor.execute("SELECT SUM(p_l), COUNT(CASE WHEN p_l > 0 THEN 1 END), COUNT(CASE WHEN p_l < 0 THEN 1 END) FROM master_ledger WHERE status = 'SETTLED'")
            stats = cursor.fetchone()
            pnl = stats[0] if stats[0] else 0.0
            wins = stats[1] if stats[1] else 0
            losses = stats[2] if stats[2] else 0

        accounting = oracle.get_seasonal_accounting(df_global, season)
        target_d   = (int(matchday) / 30) * oracle.D_MEAN
        current_d  = accounting.get('D', 0)
        draw_pressure = round((target_d - current_d) / max(1, target_d) * 100, 1) if target_d > 0 else 0

        return jsonify({
            'status': 'success',
            'season':    season,
            'matchday':  matchday,
            'pnl':       round(pnl, 2),
            'wins':      wins,
            'losses':    losses,
            'mode':      'autonomous',
            'fixtures':  fixtures,
            'draw_alerts': [],
            'accounting': {
                'draws': current_d,
                'total': sum(accounting.values()),
                'draw_pressure': draw_pressure,
            },
            'force':       1.15 if current_d < target_d * 0.85 and int(matchday) >= 20 else 1.0,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500"""
        
    content = re.sub(data_pattern, new_data, content, flags=re.DOTALL)
    
    # 2. Delete BOTH get_history versions and insert a single unified query version
    # The first history is at 430, the second at 543. We can just replace both with nothing, then insert our new one at the end or before api/predict.
    history_pattern1 = r"# ════════════════════════════════════════════════════════════════════════════════\n# /api/history — Live ledger visualization.*?(?=# ════════════════════════════════════════════════════════════════════════════════)"
    history_pattern2 = r"# ════════════════════════════════════════════════════════════════════════════════\n# /api/history — Settled Bets Feed.*?(?=# ════════════════════════════════════════════════════════════════════════════════)"
    
    content = re.sub(history_pattern1, "", content, flags=re.DOTALL)
    content = re.sub(history_pattern2, "", content, flags=re.DOTALL)
    
    new_history = """\n# ════════════════════════════════════════════════════════════════════════════════
# /api/history — Master Ledger Feed
# ════════════════════════════════════════════════════════════════════════════════
@app.route('/api/history')
def get_history():
    try:
        with sqlite3.connect(VBF_DB) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM master_ledger WHERE status = 'SETTLED' ORDER BY settled_at DESC LIMIT 100")
            settled_rows = cursor.fetchall()
            
            cursor.execute("SELECT * FROM master_ledger WHERE status = 'PENDING' ORDER BY match_day DESC")
            pending_rows = cursor.fetchall()

        history = []
        for r in settled_rows:
            history.append({
                'fixture': f"{r['home_team']} vs {r['away_team']}",
                'matchday': r['match_day'],
                'prediction': r['prediction'],
                'outcome': r['outcome'],
                'odds': r['odds_h'] if r['prediction'] == 'H' else (r['odds_d'] if r['prediction'] == 'D' else r['odds_a']),
                'stake': r['stake'],
                'profit': r['p_l'],
                'tier': r['tier']
            })

        pending = []
        for r in pending_rows:
            pending.append({
                'fixture': f"{r['home_team']} vs {r['away_team']}",
                'matchday': r['match_day'],
                'prediction': r['prediction'],
                'odds': r['odds_h'] if r['prediction'] == 'H' else (r['odds_d'] if r['prediction'] == 'D' else r['odds_a']),
                'stake': r['stake']
            })

        pnl = sum([h['profit'] for h in history])
        wins = len([h for h in history if h['profit'] > 0])
        total = len(history)
        strike_rate = round((wins/total * 100) if total > 0 else 0, 1)

        return jsonify({
            'total_pnl': pnl,
            'wins': wins,
            'losses': total - wins,
            'total': total,
            'strike_rate': strike_rate,
            'history': history,
            'pending': pending
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500\n\n"""

    # Just insert new history before "if __name__ == '__main__':"
    if "if __name__ == '__main__':" in content:
        content = content.replace("if __name__ == '__main__':", new_history + "if __name__ == '__main__':")
    else:
        content += new_history
        
    with open(server_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("server.py updated successfully.")

if __name__ == "__main__":
    patch_server()
