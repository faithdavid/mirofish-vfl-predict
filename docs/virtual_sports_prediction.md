# MiroFish: Virtual Sports Prediction Guide

Welcome to the **MiroFish Virtual Sports Prediction** workflow. This system combines cold mathematical probability with LLM "Swarm Intelligence" to analyze and predict Virtual Football League (VFL) matches (like MSport).

This guide will explain what to do with your generated Prediction Reports and how to use the MiroFish UI effectively.

---

## 1. Using the Master Prediction Report

You have just generated the `vfl_predictions_master.md` file using your harvested HAR data. This file serves as your **Mathematical Baseline**. 

### What it means:
The system calculated the exact *Bookmaker Margin* (Overround) for every single match and stripped it away to reveal the **True Probability**. It then identified the "Best Value Prediction" (HOME, DRAW, or AWAY).

### What to do with it:
1. **Backtesting**: If you have the actual match results for those seasons, you can compare them against the predictions in this report to determine the strike rate of the raw mathematical bias model.
2. **Match Selection**: Do not bet blindly! Scroll through the report and find fixtures with a **True Probability > 60%** for a specific outcome. These are your "high confidence" targets. 
3. **Swarm Analysis**: Once you find a high-confidence Match Day, you will feed it to the MiroFish Swarm Intelligence for a second opinion.

---

## 2. Generating a Match Day "Reality Seed"

MiroFish does not read the entire massive master report. Instead, you feed it a single **Match Day** (or fixture) as a "Reality Seed".

If you want the Swarm to analyze an upcoming match or a specific day from your data, you can use the built-in script:

```bash
python scripts/generate_daily_seed.py
```

When you run this script, it will ask you to paste the raw odds for that match day. It will instantly format the data, inject the mathematically calculated true probabilities, and save a Markdown file (e.g., `match_day_seed.md`).

---

## 3. Triggering the Swarm in MiroFish

Now it's time to bring in the AI Swarm! 

1. Ensure your MiroFish frontend and backend are running (`npm run dev` in the project root).
2. Open your web browser to `http://localhost:3000`.
3. Start a new simulation.
4. **Context Upload**: Copy the entire contents of your generated `match_day_seed.md` (or a specific match from the master report) and paste it into the MiroFish **Reality Seed** input.
5. **System Prompt**: Use the following prompt to guide the Swarm:

> "You are an Expert Virtual Sports Analyst Swarm. I have provided the raw odds and the mathematically derived True Probabilities for this VFL Match Day. Review the systemic bias and overround. Based purely on value betting principles and your expert personas (Risk Management, Statistical Arbitrage, Behavior Analysis), debate and finalize the single BEST bet for this match day. Ignore team names and focus only on the mathematical value."

6. **Start Simulation**: The MiroFish backend will read the Reality Seed, analyze the data using the Bias Detection Ontology, and spawn distinct AI Personas (e.g., "Odds Analyst", "Risk Appraiser") to debate the fixture over multiple cycles.
7. **The Verdict**: After the "Wisdom of the Crowd" cycles complete, MiroFish will output a final synthesized verdict on which match to bet on.

---

### Disclaimer
Virtual Football Leagues (VFL) are controlled by pure RNG (Random Number Generators). This system identifies bookmaker mathematical exploitation, but no prediction system guarantees profit against an RNG algorithm. Always bet responsibly!
