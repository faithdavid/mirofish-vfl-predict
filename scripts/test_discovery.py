import requests
import json
import os

def test_discovery():
    auth_path = r'c:\Users\faith\OneDrive\Documents\GitHub\mirofish\msport_auth.json'
    if not os.path.exists(auth_path):
        auth_path = 'msport_auth.json'
        if not os.path.exists(auth_path):
            print("Auth file missing")
            return
            
    with open(auth_path, 'r') as f:
        auth = json.load(f)
        
    base_url = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual"
    url = f"{base_url}/current/match/day/info"
    
    headers = auth.get('headers', {})
    cookies = auth.get('cookies', {})
    
    if 'User-Agent' not in headers:
        headers['User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

    print(f"Calling: {url}")
    try:
        response = requests.get(url, headers=headers, cookies=cookies, timeout=15)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("Response Data (Success):")
            print(json.dumps(data, indent=2))
        else:
            print("Response Text (Error):")
            print(response.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_discovery()
