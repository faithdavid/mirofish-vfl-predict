import sys
import os
import sqlite3
import pandas as pd

# Add current scripts to path
ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import vfl_oracle_v5 as oracle

def resolve_4494():
    df = oracle.load_vfl_history()
    profiles = oracle.get_team_profiles(df)
    
    # Fixtures from your JSON
    fixtures = [
        {'home': 'Bournemouth', 'away': 'Manchester Red', 'oh': 6.75, 'od': 3.65, 'oa': 1.50},
        {'home': 'Crystal Palace', 'away': 'Everton', 'oh': 2.80, 'od': 3.25, 'oa': 2.40},
        {'home': 'Aston Villa', 'away': 'Tottenham', 'oh': 2.15, 'od': 3.10, 'oa': 3.45},
        {'home': 'London Guns', 'away': 'Chelsea', 'oh': 2.20, 'od': 3.65, 'oa': 2.80},
        {'home': 'Wolverhampton', 'away': 'Liverpool', 'oh': 3.95, 'od': 4.40, 'oa': 1.65},
        {'home': 'West Ham', 'away': 'Manchester Blue', 'oh': 3.80, 'od': 3.85, 'oa': 1.80},
        {'home': 'Newcastle', 'away': 'Fulham', 'oh': 1.85, 'od': 3.50, 'oa': 3.85},
        {'home': 'Brighton', 'away': 'Leeds', 'oh': 1.85, 'od': 3.20, 'oa': 4.40}
    ]
    
    # Meta
    season_id = '3074091' # Season 4494
    day = 26
    sst = 1775341790000
    
    print(f"--- V8.0 SOVEREIGN RESOLUTION: SEASON 4494 (MatchDay {day}) ---")
    print("-" * 105)
    print(f"{'FIXTURE':<35} | {'PRED':<4} | {'CONF':<7} | {'ORACLE SIGNAL'}")
    print("-" * 105)
    
    for f in fixtures:
        f.update({'day': day, 'season': season_id, 'sst': sst})
        res = oracle.predict_fixture(f, df, profiles)
        print(f"{f['home']} vs {f['away']:<20} | {res['prediction']:<4} | {res['confidence']:.1%} | {res['label']}")

if __name__ == '__main__':
    resolve_4494()
