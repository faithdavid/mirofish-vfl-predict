import os
import json
import base64
import argparse
import re
from urllib.parse import urlparse

# Target endpoints from the original Node.js tools
RESULT_BASE = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/result"
ODDS_BASE = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/match/day/event/list"

def extract_via_regex(path, target_base):
    """Fallback: Scans the file for patterns if JSON parsing fails."""
    matches = []
    print(f"    [Fallback] Attempting regex extraction for {os.path.basename(path)}...")
    
    # Read the file with errors replaced to avoid decoding crashes
    try:
        # We'll try latin-1 as it accepts all byte patterns
        with open(path, 'r', encoding='latin-1', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print(f"      !!! Fatal Read Error: {e}")
        return []

    # Search for occurrences of target_base
    # Pattern: "url"\s*:\s*"target_base" ... "text"\s*:\s*"(.*?)"
    # We use a broad search since HAR structure can vary (spacing, order)
    
    search_pattern = re.escape(target_base)
    # Find all indices of target_base
    indices = [m.start() for m in re.finditer(search_pattern, content)]
    
    for idx in indices:
        # Search backward for the start of the entry or forward for the text block
        # Usually, the "text" block is after the "url" in a standard HAR entry
        # We'll look for the next "text":"(.*?)" pattern
        # This regex is memory-intensive on huge files, so we'll slice a window
        window = content[idx:idx + 100000] # Increase window to 100KB
        
        # More robust regex for the text value (handles escaped quotes better)
        text_match = re.search(r'"text"\s*:\s*"(\{.*?\})(?<!\\)"', window)
        if text_match:
            raw_text = text_match.group(1)
            # Unescape JSON characters (like \")
            body = raw_text.replace('\\"', '"').replace('\\\\', '\\')
            
            # Check for base64 (usually "encoding":"base64" is nearby)
            is_base64 = '"encoding":"base64"' in window
            if is_base64:
                try:
                    body = base64.b64decode(body).decode('utf-8', errors='replace')
                except Exception:
                    pass
            
            # Try to pretty-print
            try:
                body_json = json.loads(body)
                body = json.dumps(body_json, indent=2, ensure_ascii=False)
            except Exception:
                pass

            block = (
                f"===== MATCH #{len(matches) + 1} [REGEX FALLBACK] =====\n"
                f"BASE: {target_base}\n"
                f"SRC: {os.path.basename(path)}\n\n"
                f"{body}\n\n"
            )
            matches.append(block)
            
    return matches

def get_base_url(url):
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    except Exception:
        return ""

def extract_from_har(har_path, target_base):
    """Extracts response bodies from a HAR file matching a target base URL."""
    if not os.path.exists(har_path):
        return []

    har_data = None
    # Try common encodings to handle various browser export formats
    for enc in ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1']:
        try:
            with open(har_path, 'r', encoding=enc, errors='replace') as f:
                # If the file is very large, json.load might be slow, but it's the safest way to get the entries
                har_data = json.load(f)
                break
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue

    if not har_data:
        # Fallback: Try regex extraction if JSON parsing fails
        return extract_via_regex(har_path, target_base)

    entries = har_data.get('log', {}).get('entries', [])
    matches = []

    for i, entry in enumerate(entries):
        url = entry.get('request', {}).get('url', '')
        if get_base_url(url) == target_base:
            response = entry.get('response', {})
            content = response.get('content', {})
            text = content.get('text', '')
            encoding = content.get('encoding', '')
            mime = content.get('mimeType', 'unknown')
            status = response.get('status', 'unknown')
            timestamp = entry.get('startedDateTime', 'unknown')

            if encoding == 'base64' and text:
                try:
                    text = base64.b64decode(text).decode('utf-8')
                except Exception:
                    pass

            # Try to pretty-print JSON
            try:
                text_json = json.loads(text)
                body = json.dumps(text_json, indent=2, ensure_ascii=False)
            except Exception:
                body = text

            block = (
                f"===== MATCH #{len(matches) + 1} =====\n"
                f"BASE: {target_base}\n"
                f"FULL URL: {url}\n"
                f"STATUS: {status}\n"
                f"MIME: {mime}\n"
                f"TIMESTAMP: {timestamp}\n\n"
                f"{body}\n\n"
            )
            matches.append(block)

    return matches

def main():
    parser = argparse.ArgumentParser(description="Batch HAR Extractor for MSport")
    parser.add_argument("source_dir", help="Directory containing .har files")
    parser.add_argument("--odds_dir", default="extracted_odds", help="Output directory for odds")
    parser.add_argument("--results_dir", default="extracted_results", help="Output directory for results")
    
    args = parser.parse_args()

    os.makedirs(args.odds_dir, exist_ok=True)
    os.makedirs(args.results_dir, exist_ok=True)

    har_files = [f for f in os.listdir(args.source_dir) if f.lower().endswith('.har')]
    
    if not har_files:
        print(f"No HAR files found in {args.source_dir}")
        return

    print(f"Processing {len(har_files)} files...")

    for filename in har_files:
        path = os.path.join(args.source_dir, filename)
        base_name = os.path.splitext(filename)[0]
        
        print(f"  Extracting: {filename}")

        # Extract Odds
        odds_blocks = extract_from_har(path, ODDS_BASE)
        if odds_blocks:
            out_path = os.path.join(args.odds_dir, f"{base_name}_odds.txt")
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write("".join(odds_blocks))
            print(f"    -> Saved {len(odds_blocks)} odds blocks to {out_path}")

        # Extract Results
        result_blocks = extract_from_har(path, RESULT_BASE)
        if result_blocks:
            out_path = os.path.join(args.results_dir, f"{base_name}_results.txt")
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write("".join(result_blocks))
            print(f"    -> Saved {len(result_blocks)} result blocks to {out_path}")

    print("\nBatch extraction complete!")

if __name__ == "__main__":
    main()
