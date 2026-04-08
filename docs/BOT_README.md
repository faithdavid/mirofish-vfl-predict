# MiroFish VFL Sovereign Trading Bot

This is your autonomous "Quant" system for MSport VFL. It moves from simple predictions to **Expected Value (EV)** trading using the **V8.0 Global Balancer.**

## CORE COMPONENTS

1.  **`scripts/bot.py`**: The "Execution Brain." It scans fixtures, checks the **Sovereign Oracle**, and calculates **Fractional Kelly Stakes.**
2.  **`scripts/vfl_backtester.py`**: The "Stress-Tester." Run this to see how your current settings would have performed over the last 50,000 matches.
3.  **`scripts/update_results.py`**: The "Feedback Loop." After a matchday resolves, run this to update your P&L and recalibrate the **RNG Bias** model.

## HOW TO OPERATE

### 1. Stress-Test Before Risking Funds
Run the backtester to verify that your **5% Edge** threshold is statistically sound.
```bash
python scripts/vfl_backtester.py
```

### 2. Enter "Shadow Mode"
Run the bot in dry-run mode for 3 MatchDays to verify the actual results align with the Oracle's probabilities.
```bash
python scripts/bot.py --mode dry-run
```

### 3. Resolve and Recalibrate
After the MatchDay ends, enter the results. This is critical—it feeds the results back into `vfl_history.db` so the **Global Balancer** knows exactly how many Draws are left in the quota.
```bash
python scripts/update_results.py
```

## KEY CONFIGURATION (`scripts/bot.py`)

- **`BANKROLL`**: Your current NGN balance.
- **`KELLY_FRACTION` (0.25)**: We use **Quarter-Kelly** to ensure you don't go bust during a losing streak.
- **`MIN_EDGE` (0.05)**: The minimum advantage (5%) you require before the bot will fire a bet.

## THE MINDSET
You no longer care if a single bet wins or loses. You only care that you are betting when the **Expected Value (EV)** is positive. Over 100 bets, the **Law of Large Numbers** ensures the RNG Bias becomes your profit.

**Sovereign Status: ACTIVE.**
