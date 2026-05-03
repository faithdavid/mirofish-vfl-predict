#!/usr/bin/env python3
"""Emergency VFL prediction for matches in Supabase"""
import json, os, hashlib, requests
from collections import defaultdict

BASE = "/root/.openclaw/workspace/vfl-repo"
SIG_FILE = os.path.join(BASE, "master_rng_signatures.json")
SUPABASE_URL = "https://oysfaaafiemteqznguug.supabase.co/rest/v1"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

# Load signature database
with open(SIG_FILE) as f:
    signatures = json.load(f)

# Get pending matches
resp = requests.get(f"{SUPABASE_URL}/master_ledger?season_id=eq.vf:season:3075072&status=eq.PENDING", headers=headers)
matches = resp.json()

print(f"Predicting {len(matches)} matches...")

predictions = []
for m in matches[:8]:
    home = m["home_team"].upper()
    away = m["away_team"].upper()
    oh, od, oa = round(float(m["odds_h"]), 1), round(float(m["odds_d"]), 1), round(float(m["odds_a"]), 1)
    
    sig = f"{home}|{away}|{oh:.1f}|{od:.1f}|{oa:.1f}"
    entry = signatures.get(sig, {})
    
    if entry and "outcomes" in entry:
        outcomes = entry["outcomes"]
        total = sum(outcomes.values())
        if total >= 3:
            top_out = max(outcomes, key=outcomes.get)
            conf = outcomes[top_out] / total
            stars = 5 if conf >= 0.85 else (4 if conf >= 0.70 else 3)
            predictions.append({
                "match_id": m["match_id"],
                "outcome": top_out,
                "certainty": round(conf, 3),
                "stars": stars,
                "method": "SIG_MATCH"
            })
        else:
            # Fallback to implied probability
            ip_h = 1/oh if oh > 0 else 0.33
            ip_d = 1/od if od > 0 else 0.33
            ip_a = 1/oa if oa > 0 else 0.33
            tot = ip_h + ip_d + ip_a
            pred = max([("HOME", ip_h), ("DRAW", ip_d), ("AWAY", ip_a)], key=lambda x: x[1]/tot if tot else 0)
            predictions.append({
                "match_id": m["match_id"],
                "outcome": pred[0],
                "certainty": round(pred[1]/tot, 3),
                "stars": 2,
                "method": "IMPLIED"
            })
    else:
        # Fallback
        predictions.append({
            "match_id": m["match_id"],
            "outcome": "HOME",
            "certainty": 0.33,
            "stars": 1,
            "method": "FALLBACK"
        })

# Upload predictions
for p in predictions:
    update = {"prediction": p["outcome"], "certainty": p["certainty"]}
    resp = requests.patch(f"{SUPABASE_URL}/master_ledger?match_id=eq.{p['match_id']}", headers=headers, json=update)
    print(f"  {p['match_id']}: {p['outcome']} ({p['certainty']}) - {resp.status_code}")

print(f"\n✅ Generated {len(predictions)} predictions")