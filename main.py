import threading
import time
import sys
from pathlib import Path

# Add root to path
ROOT = Path(__file__).parent
sys.path.append(str(ROOT))

from web.server import app
from core.scavenger import run_scavenger

def start_backend():
    print("[SYSTEM] Starting Sovereign API Server...")
    # Run Flask in the main thread or a separate one
    # Running in a thread so we can manage both
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

def start_scavenger():
    print("[SYSTEM] Starting Scavenger Background Service...")
    # Wait for server to be ready
    time.sleep(5) 
    run_scavenger()

if __name__ == "__main__":
    print("""
    =============================================
      MIROFISH SOVEREIGN — Unified Engine V1
    =============================================
    """)
    
    # Start Scavenger in background thread
    scav_thread = threading.Thread(target=start_scavenger, daemon=True)
    scav_thread.start()
    
    # Start Web Server in main thread
    start_backend()
