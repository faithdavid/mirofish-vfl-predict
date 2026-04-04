import csv, os

PENDING = 'pending_tests'
files = sorted([f for f in os.listdir(PENDING) if f.endswith('.csv') and not f.startswith('SCORED')])

grand_fixtures = 0
grand_high     = 0
all_days       = set()
summary        = []

for fname in files:
    path = os.path.join(PENDING, fname)
    rows = list(csv.DictReader(open(path, encoding='utf-8')))
    high = [r for r in rows if int(r.get('stars', 0)) >= 4]
    days = sorted(set(r['day'] for r in rows), key=lambda x: int(x) if x.isdigit() else 99)
    all_days.update(days)
    grand_fixtures += len(rows)
    grand_high     += len(high)
    src = fname.replace('2026-04-04_17-02_', '').replace('.csv', '')
    summary.append((src, len(rows), len(high), days))

all_sorted = sorted(all_days, key=lambda x: int(x) if x.isdigit() else 99)

print("=" * 90)
print("  SAVED BLIND TEST COVERAGE SUMMARY")
print("=" * 90)
print()
print(f"  Total HAR files with saved predictions : {len(files)}")
print(f"  Total fixtures predicted               : {grand_fixtures}")
print(f"  Total high-confidence picks (4+ stars) : {grand_high}")
print(f"  Unique match days covered              : MD {', '.join(all_sorted)}")
print(f"  Total distinct match days              : {len(all_sorted)}")
print()
print(f"  {'Source':<40} {'Fixtures':>8}  {'4+* Picks':>9}  Match Days")
print("  " + "-" * 85)
for src, total, high, days in summary:
    day_str = "MD " + ", ".join(days)
    print(f"  {src:<40} {total:>8}  {high:>9}  {day_str}")
print("=" * 90)
