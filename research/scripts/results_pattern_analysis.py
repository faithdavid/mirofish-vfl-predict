import os
import json
import re
from collections import defaultdict

def parse_results_blocks(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'===== MATCH #\d+', content)
    events = []
    
    for b in blocks:
        m = re.search(r'\{[\s\S]*\}', b)
        if m:
            try:
                data = json.loads(m.group())
                
                # Extract results from nested structure
                extracted_events = []
                if "data" in data:
                    if "results" in data["data"]: extracted_events = data["data"]["results"]
                    elif "events" in data["data"]: extracted_events = data["data"]["events"]
                elif "results" in data: extracted_events = data["results"]
                
                if extracted_events:
                    for e in extracted_events:
                        events.append(e)
            except: pass
    return events

def analyze_patterns(events):
    print(f"\n--- VIRTUAL SPORTS PATTERN ANALYSIS ---")
    print(f"Total Matches Analyzed: {len(events)}")
    
    if not events:
        print("No valid matches found.")
        return

    # Basic tallies
    home_wins = 0
    away_wins = 0
    draws = 0
    score_freq = defaultdict(int)
    team_stats = defaultdict(lambda: {'wins': 0, 'draws': 0, 'losses': 0, 'goals_for': 0, 'goals_against': 0})
    
    for e in events:
        h_team = e.get('homeTeam')
        a_team = e.get('awayTeam')
        ft_score = e.get('fullTime', e.get('score')) # '1:2' or similar
        
        if not h_team or not a_team or not ft_score:
            continue
            
        score_freq[ft_score] += 1
        
        try:
            h_score, a_score = map(int, ft_score.split(':'))
            
            team_stats[h_team]['goals_for'] += h_score
            team_stats[h_team]['goals_against'] += a_score
            team_stats[a_team]['goals_for'] += a_score
            team_stats[a_team]['goals_against'] += h_score

            if h_score > a_score:
                home_wins += 1
                team_stats[h_team]['wins'] += 1
                team_stats[a_team]['losses'] += 1
            elif a_score > h_score:
                away_wins += 1
                team_stats[a_team]['wins'] += 1
                team_stats[h_team]['losses'] += 1
            else:
                draws += 1
                team_stats[h_team]['draws'] += 1
                team_stats[a_team]['draws'] += 1
        except:
            pass # Invalid score format

    total_valid = home_wins + away_wins + draws
    if total_valid == 0: return
    
    print("\n[Behavioral Patterns: Outcome Distribution]")
    print(f"Home Wins: {home_wins} ({home_wins/total_valid:.1%})")
    print(f"Away Wins: {away_wins} ({away_wins/total_valid:.1%})")
    print(f"Draws:     {draws} ({draws/total_valid:.1%})")
    
    print("\n[Behavioral Patterns: Most Common Final Scores]")
    sorted_scores = sorted(score_freq.items(), key=lambda x: x[1], reverse=True)
    for score, count in sorted_scores[:5]:
        print(f"Score {score}: {count} occurrences ({count/total_valid:.1%})")
        
    print("\n[Systemic Oddities: High Scoring / Reset Benchmarks]")
    high_scoring = [s for s, c in sorted_scores if sum(map(int, s.split(':'))) > 4]
    print(f"Matches with 5+ goals (potential system resets): {sum(score_freq[s] for s in high_scoring)}")
    
    print("\n[Team Anomalies: Top 5 Winning Streaks/Biases]")
    sorted_teams = sorted(team_stats.items(), key=lambda x: x[1]['wins'], reverse=True)
    for team, stats in sorted_teams[:5]:
        print(f"{team:<20} | Wins: {stats['wins']:<3} | GD: {stats['goals_for'] - stats['goals_against']:+3}")

def main():
    results_dir = "extracted_results"
    all_events = []
    
    if not os.path.exists(results_dir):
        print(f"Directory {results_dir} not found.")
        return
        
    for f in os.listdir(results_dir):
        if not f.endswith('.txt'): continue
        path = os.path.join(results_dir, f)
        events = parse_results_blocks(path)
        all_events.extend(events)
        
    analyze_patterns(all_events)

if __name__ == "__main__":
    main()
