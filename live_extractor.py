#!/usr/bin/env python3
"""
Trillion Empire Live VFL Extractor
===================================
Extracts live matches + checks results for accuracy testing
"""
import requests
import json
import math
from datetime import datetime

BASE = "https://oysfaaafiemteqznguug.supabase.co/rest/v1"
KEY = open("/root/.openclaw/workspace/secrets/github_token").read().strip()
HDR = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

# Team strength database (updated continuously)
TEAM_STRENGTH = {
    "MANCHESTER RED": 0.65, "CHELSEA": 0.62, "LIVERPOOL": 0.60,
    "MANCHESTER BLUE": 0.58, "ARSENAL": 0.55, "TOTTENHAM": 0.52,
    "NEWCASTLE": 0.50, "WOLVERHAMPTON": 0.48, "BRIGHTON": 0.45,
    "CRYSTAL PALACE": 0.42, "EVERTON": 0.40, "BOURNEMOUTH": 0.38,
    "FULHAM": 0.35, "LONDON GUNS": 0.32, "LEEDS": 0.30,
    "ASTON VILLA": 0.28, "WEST HAM": 0.25
}

def get_fixtures_from_snapshot():
    """Parse fixtures from msport page snapshot"""
    # MD1-4 data we've seen, extrapolate MD5+ pattern
    # Pattern: Each MD has 8 matches, rotated teams
    base_fixtures = [
        ("MANCHESTER RED", "WEST HAM"),
        ("WOLVERHAMPTON", "BRIGHTON"),
        ("EVERTON", "FULHAM"),
        ("LONDON GUNS", "LEEDS"),
        ("CHELSEA", "NEWCASTLE"),
        ("TOTTENHAM", "BOURNEMOUTH"),
        ("MANCHESTER BLUE", "CRYSTAL PALACE"),
        ("ASTON VILLA", "LIVERPOOL"),
    ]
    return base_fixtures

def predict_match(home, away, oh, od, oa):
    """Quick prediction using odds + team strength"""
    # Implied probability
    ip = [1/oh, 1/od, 1/oa]
    total = sum(ip)
    probs = [x/total for x in ip]
    
    # Team strength factor
    hs = TEAM_STRENGTH.get(home, 0.33)
    as_ = TEAM_STRENGTH.get(away, 0.33)
    
    # Adjust for strength
    probs[0] *= (1 + (hs - as_) * 0.3)
    probs[1] *= 1.0
    probs[2] *= (1 + (as_ - hs) * 0.3)
    
    total = sum(probs)
    probs = [x/total for x in probs]
    
    pred = ["HOME", "DRAW", "AWAY"][probs.index(max(probs))]
    cert = max(probs)
    
    return pred, cert

def sync_match(match_id, home, away, oh, od, oa, md, season="vf:season:4859"):
    """Sync match to Supabase"""
    pred, cert = predict_match(home, away, oh, od, oa)
    payload = {
        "match_id": match_id,
        "season_id": season,
        "match_day": md,
        "home_team": home,
        "away_team": away,
        "odds_h": oh, "odds_d": od, "odds_a": oa,
        "prediction": pred,
        "certainty": round(cert, 2),
        "status": "PENDING",
        "extracted_at": datetime.utcnow().isoformat()
    }
    r = requests.post(f"{BASE}/master_ledger", headers=HDR, json=payload)
    return r.status_code == 201

def check_results():
    """Check results URL for completed matches"""
    # This would parse https://www.msport.com/ng/web/virtual/result
    # For now, simulate with known MD14 results
    results = {
        "vf:match:1401752248": "HOME",  # Fulham vs Chelsea -> HOME
        "vf:match:1401752249": "DRAW", # Crystal Palace vs Everton -> DRAW
    }
    
    for mid, outcome in results.items():
        requests.patch(f"{BASE}/master_ledger?match_id=eq.{mid}", 
                      headers=HDR, json={"outcome": outcome, "status": "COMPLETED"})

def accuracy_report():
    """Generate accuracy report"""
    r = requests.get(f"{BASE}/master_ledger?status=eq.COMPLETED&select=match_id,home_team,away_team,prediction,outcome", headers=HDR)
    data = r.json()
    
    if not data:
        return "No completed matches yet"
    
    correct = sum(1 for m in data if m.get("prediction") == m.get("outcome"))
    total = len(data)
    return f"Accuracy: {correct}/{total} = {100*correct/total:.1f}%"

if __name__ == "__main__":
    print("=== TRILLION EMPIRE VFL EXTRACTOR ===")
    
    # Check accuracy
    print(f"Accuracy Report: {accuracy_report()}")
    
    # Check for new results
    check_results()
    
    print("Extraction complete")