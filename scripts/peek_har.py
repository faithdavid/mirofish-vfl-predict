import json
import re
import os

path = 'ANalysis/www.msport27.har'
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read(1000000)
    # Search for matchDay to see the surrounding context
    match = re.search(r'\"matchDay\"', content)
    if match:
        start = max(0, match.start() - 500)
        end = min(len(content), match.end() + 2000)
        print("--- HAR STRUCTURE SAMPLE ---")
        print(content[start:end])
    else:
        print("matchDay not found in the first 1MB.")
