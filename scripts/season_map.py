import sys

# The constant offset between MSport Web Seasons and VFL Internal IDs
OFFSET = 3069509

def convert_season(val):
    val = int(val)
    if val < 10000:
        # User entered a Web Season (e.g., 4491)
        res = val + OFFSET
        print(f"WEB SEASON {val}  ==>  INTERNAL ID: {res}")
    else:
        # User entered an Internal ID (e.g., 3074000)
        res = val - OFFSET
        print(f"INTERNAL ID {val}  ==>  WEB SEASON: {res}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        convert_season(sys.argv[1])
    else:
        print("Usage: python scripts/season_map.py <SeasonNumber>")
        print("Example: python scripts/season_map.py 4491")
