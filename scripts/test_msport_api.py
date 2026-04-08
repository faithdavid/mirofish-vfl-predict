import requests
import json

# Configuration from USER headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-NG,en-US;q=0.9,en-GB;q=0.8,en;q=0.7",
    "apilevel": "2",
    "clientid": "WEB",
    "deviceid": "f7aa2d97-a435-4375-ad21-9d45e12c0524",
    "operid": "2",
    "platform": "WEB",
    "referer": "https://www.msport.com/ng/web/virtual",
    "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin"
}

COOKIES = {
    "device-id": "b473b5f1-7758-4f49-bad0-b1942b35b1bb",
    "deviceId": "b473b5f1-7758-4f49-bad0-b1942b35b1bb",
    "__zlcmid": "1WOoKpCZD6bfRap",
    "__cf_bm": "1oI3kJ72tsNRAPl2EdmZ5P0.h0xdCLlUN6eWRNS._Ww-1775513650.3767786-1.0.1.1-VzQUN.AoQ7H_MzS58z.PI8CaDLLBXJa35P60u6APH0eNJYSb83kPwu0IbMGiaeVZ03IH6.zeU8ydd2apHQnX.1R.Jcbq4uDxcMte7RFOojEMZ7Uiwt7dMXvMIjoPtgOj"
}

def test_odds():
    print("Testing Odds API...")
    url = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/match/day/event/list"
    params = {
        "seasonId": "vf:season:3074782",
        "matchDay": "19"
    }
    try:
        response = requests.get(url, headers=HEADERS, cookies=COOKIES, params=params, timeout=10)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("Odds API Response keys:", data.keys())
            if 'data' in data and data['data']:
                matches = data['data'].get('matches', [])
                if not matches:
                    print(f"Warning: No matches found in 'data'. Full data keys: {data['data'].keys()}")
                print(f"Success! Found {len(matches)} matches.")
            else:
                print(f"Error: 'data' key missing or null. Full response: {data}")
            return True
        else:
            print(f"Failed: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
    return False

def test_results():
    print("\nTesting Results API...")
    url = "https://www.msport.com/api/ng/facts-center/query/frontend/virtual/result"
    params = {
        "seasonId": "vf:season:3074782",
        "matchDay": "19"
    }
    try:
        response = requests.get(url, headers=HEADERS, cookies=COOKIES, params=params, timeout=10)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if 'data' in data:
                meta = {k: v for k, v in data['data'].items() if k != 'results'}
                print(f"Results Metadata: {meta}")
            print(f"Success! Found {len(data.get('data', {}).get('results', []))} results.")
            return True
        else:
            print(f"Failed: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
    return False

if __name__ == "__main__":
    odds_ok = test_odds()
    results_ok = test_results()
    
    if odds_ok and results_ok:
        print("\nAll systems GO. Scavenger V1.0 is viable.")
    else:
        print("\nVerification FAILED. Check headers/cookies.")
