import json
import os
import sys
import pandas as pd
from datetime import datetime

# Add scripts to path
ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import vfl_oracle_v5 as oracle

def generate_dashboard():
    mds = [
        'extracted_odds/www.msport27_odds.txt',
        'extracted_results/7 results s4245www.msport_results.txt'
    ]
    
    # Load history
    df = oracle.load_vfl_history()
    profiles = oracle.get_team_profiles(df)
    
    all_cards = ""
    all_rows = ""
    upcoming_season = "Unknown"
    upcoming_day = "Unknown"
    
    for md_file in mds:
        if not os.path.exists(md_file): continue
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Simple extraction of last MD
        blocks = content.split('===== MATCH #')
        if len(blocks) < 2: continue
        last_block = blocks[-1]
        
        try:
            json_str = last_block[last_block.find('{'):last_block.rfind('}')+1]
            data = json.loads(json_str)
            md = data['data'].get('matchDay', 'Unknown')
            sst = data['data'].get('startTime', 'Unknown')
            season_id = data['data'].get('seasonId', '').replace('vf:season:', '')
            events = data['data'].get('events', [])
            
            if events:
                upcoming_season = season_id
                upcoming_day = md
                
                # V8.0 GLOBAL ACCOUNTING
                stats = oracle.get_seasonal_accounting(df, upcoming_season)
                rem_d = int(max(0, oracle.D_MEAN - stats['D']))
                rem_h = int(max(0, oracle.H_MEAN - stats['H']))
                rem_a = int(max(0, oracle.A_MEAN - stats['A']))
                
                all_cards += f"""
                <div class="quota-hud">
                    <h3>GLOBAL QUOTA HUD (Season {upcoming_season} | MD {upcoming_day})</h3>
                    <div class="quota-meters">
                        <div class="meter"><span>HOME: {stats['H']}/{int(oracle.H_MEAN)}</span><div class="bar"><div class="fill" style="width: {min(100, (stats['H']/oracle.H_MEAN)*100)}%"></div></div></div>
                        <div class="meter draw-surge"><span>DRAWS: {stats['D']}/{int(oracle.D_MEAN)}</span><div class="bar"><div class="fill" style="width: {min(100, (stats['D']/oracle.D_MEAN)*100)}%"></div></div></div>
                        <div class="meter"><span>AWAY: {stats['A']}/{int(oracle.A_MEAN)}</span><div class="bar"><div class="fill" style="width: {min(100, (stats['A']/oracle.A_MEAN)*100)}%"></div></div></div>
                    </div>
                    <div class="due-panel">
                        <p><b>DUE DRAWS:</b> <span class="badge">{rem_d}</span> | <b>DUE HOME:</b> {rem_h} | <b>DUE AWAY:</b> {rem_a}</p>
                        {"<p class='surge-alert'>!!! GLOBAL DRAW SURGE DETECTED !!!</p>" if rem_d > 10 and int(upcoming_day) > 20 else ""}
                    </div>
                </div>
                """
                
                for ev in events:
                    ht, at = ev['homeTeam'].upper(), ev['awayTeam'].upper()
                    m = ev['markets'][0]
                    oh = float(next(o['odds'] for o in m['outcomes'] if o['id']=='1'))
                    od = float(next(o['odds'] for o in m['outcomes'] if o['id']=='2'))
                    oa = float(next(o['odds'] for o in m['outcomes'] if o['id']=='3'))
                    
                    pred = oracle.predict_fixture({
                        'home': ht, 'away': at, 'oh': oh, 'od': od, 'oa': oa,
                        'day': int(md), 'season': upcoming_season, 'sst': sst
                    }, df, profiles)
                    
                    all_rows += f"""
                    <tr>
                        <td class="fixture">{ht} vs {at}</td>
                        <td class="pred">{pred['prediction']}</td>
                        <td>{pred['label']}</td>
                        <td>{pred['confidence']:.1%}</td>
                    </tr>
                    """
        except: continue

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>VFL ORACLE V8.0 - SOVEREIGN RESOLVED</title>
        <style>
            body {{ background: #0b111a; color: #e1e8ed; font-family: sans-serif; padding: 40px; }}
            .quota-hud {{ background: #1a1d23; padding: 20px; border-radius: 12px; border-left: 5px solid #3498db; margin-bottom: 30px; }}
            .bar {{ background: #333; height: 10px; border-radius: 5px; margin: 5px 0; }}
            .fill {{ background: #3498db; height: 100%; border-radius: 5px; }}
            .draw-surge .fill {{ background: #f1c40f; }}
            .surge-alert {{ color: #e74c3c; font-weight: bold; animation: blink 1s infinite; }}
            @keyframes blink {{ 0%{{opacity: 1}} 50%{{opacity: 0.3}} 100%{{opacity: 1}} }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 15px; border-bottom: 1px solid #2c3e50; text-align: left; }}
            .pred {{ font-weight: bold; color: #3498db; font-size: 1.2em; }}
            .badge {{ background: #f1c40f; color: #000; padding: 2px 8px; border-radius: 4px; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>VFL ORACLE V8.0 - SOVEREIGN COMMAND CENTER</h1>
        {all_cards}
        <table>
            <thead><tr><th>Fixture</th><th>Result</th><th>Oracle Signal</th><th>Resolution</th></tr></thead>
            <tbody>{all_rows}</tbody>
        </table>
    </body>
    </html>
    """
    
    with open('vfl_dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    print("V8.0 DASHBOARD DEPLOYED: vfl_dashboard.html")

if __name__ == '__main__':
    generate_dashboard()
