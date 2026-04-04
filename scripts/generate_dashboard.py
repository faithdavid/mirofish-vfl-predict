import json
import os
import sys
import sqlite3

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import vfl_oracle_v5 as oracle

def generate_dashboard():
    # 1. Load latest data points
    mds = ['upcoming_md11_fixed.json', 'upcoming_md22_fixed.json', 'upcoming_s3074000_md11.json']
    
    conn = sqlite3.connect('vfl_history.db')
    df = oracle.load_vfl_history()
    profiles = oracle.get_team_profiles(df)
    
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>VFL ORACLE V5.2 - COMMAND CENTER</title>
        <style>
            body { font-family: 'Inter', system-ui, sans-serif; background: #0b0f19; color: #f8fafc; padding: 40px; margin: 0; }
            .container { max-width: 1000px; margin: 0 auto; }
            h1 { color: #38bdf8; border-bottom: 2px solid #1e293b; padding-bottom: 15px; margin-bottom: 30px; letter-spacing: -0.02em; }
            .card { background: #111827; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4); border: 1px solid #1f2937; }
            h2 { font-size: 1.1rem; margin-top: 0; color: #94a3b8; font-weight: 500; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th { text-align: left; color: #4b5563; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 12px 16px; border-bottom: 1px solid #1f2937; }
            td { padding: 16px; border-bottom: 1px solid #111827; }
            .lock { background: #ea580c; color: white; padding: 4px 8px; border-radius: 6px; font-weight: 800; font-size: 0.7rem; display: inline-block; animation: pulse 2s infinite; }
            @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.05); } 100% { transform: scale(1); } }
            .hit { color: #10b981; font-weight: 800; background: rgba(16, 185, 129, 0.1); padding: 4px 8px; border-radius: 4px; }
            .miss { color: #ef4444; font-weight: 700; background: rgba(239, 68, 68, 0.1); padding: 4px 8px; border-radius: 4px; }
            .fixture { font-weight: 600; font-size: 1rem; color: #f1f5f9; }
            .pred { font-weight: 800; font-size: 1.1rem; color: #38bdf8; }
            .badge { padding: 4px 10px; border-radius: 6px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; }
            .badge-high { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 1); }
            .badge-quota { background: #ea580c; color: white; border: 1px solid #ff4500; }
            .badge-wall { background: #ef4444; color: white; border: 1px solid white; animation: pulse 1s infinite; }
            .win-count { font-weight: 800; color: #facc15; font-size: 0.9rem; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>VFL ORACLE V5.2 - QUOTA RESOLUTION DASHBOARD</h1>
    """
    
    for md_file in mds:
        if not os.path.exists(md_file): continue
        with open(md_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        md = data['data'].get('matchDay', '?')
        sst = data['data'].get('seasonStartTime', '0')
        season_id = data['data'].get('seasonId', '').replace('vf:season:', '')
        events = data['data'].get('events', [])
        
        html_content += f'<div class="card"><h2>MatchDay {md} (Season: {season_id} | Seed: {sst})</h2><table>'
        html_content += '<thead><tr><th>Fixture</th><th>Wins</th><th>Pred</th><th>Conf</th><th>Oracle Signal</th><th>Audit Status</th></tr></thead><tbody>'
        
        for ev in events:
            ht, at = ev['homeTeam'].upper(), ev['awayTeam'].upper()
            m1x2 = next((m for m in ev['markets'] if m['id'] == 1), None)
            if not m1x2: continue
            outs = m1x2['outcomes']
            oh = float(next(o['odds'] for o in outs if o['id'] == '1'))
            od = float(next(o['odds'] for o in outs if o['id'] == '2'))
            oa = float(next(o['odds'] for o in outs if o['id'] == '3'))
            
            fixture = {
                'home': ht, 'away': at, 'oh': oh, 'od': od, 'oa': oa, 
                'sst': sst, 'day': md, 'season': season_id
            }
            res = oracle.predict_fixture(fixture, df, profiles)
            
            # Audit Check
            actual_res = conn.execute("SELECT outcome, h, a FROM matches WHERE home=? AND away=? AND season=? AND day=? AND outcome IS NOT NULL", 
                                    (ev['homeTeam'], ev['awayTeam'], season_id, md)).fetchone()
            
            status_html = ""
            if actual_res:
                outcome_code = actual_res[0][0]
                is_hit = res['prediction'] == outcome_code
                status_class = "hit" if is_hit else "miss"
                status_html = f'<span class="{status_class}">{"HIT" if is_hit else "MISS"} ({actual_res[1]}:{actual_res[2]})</span>'
            else:
                status_html = '<span style="color: #4b5563">Pending...</span>'

            signal_html = ""
            if res['is_mirror']: signal_html = '<span class="lock">MIRROR LOCK</span>'
            elif "WALL" in res['label']: signal_html = '<span class="badge badge-wall">WIN WALL WARNING</span>'
            elif "QUOTA" in res['label']: signal_html = '<span class="badge badge-quota">QUOTA DRAW ALERT</span>'
            elif res['confidence'] >= 0.65: signal_html = '<span class="badge badge-high">STRONG HIGH</span>'
            else: signal_html = '<span style="color: #4b5563">Low Edge</span>'
            
            wins = res.get('h_wins', '?')
            
            html_content += f"""
            <tr>
                <td class="fixture">{ht} vs {at}</td>
                <td class="win-count">W: {wins}</td>
                <td class="pred">{res['prediction']}</td>
                <td><div style="font-weight: 500;">{res['confidence']:.1%}</div></td>
                <td>{signal_html}</td>
                <td>{status_html}</td>
            </tr>
            """
        html_content += "</tbody></table></div>"
        
    html_content += """
        </div>
    </body>
    </html>
    """
    conn.close()
    dashboard_path = os.path.join(ROOT, 'vfl_dashboard.html')
    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"DASHBOARD_V52_AUDIT_CREATED: {dashboard_path}")

if __name__ == '__main__':
    generate_dashboard()
