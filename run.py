"""
Unified runner for the Ollama Beam:Cloud ChatBot & Tracking REST API.
Launches both the FastAPI REST API (port 8000) and the Streamlit Web UI (port 8501).
"""
import sys
import os
import subprocess
import time
import requests

def check_rest_api_ready(timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get("http://127.0.0.1:8000/api/health", timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def main():
    print("=" * 60)
    print("⚡ Starting Ollama Beam:Cloud ChatBot & AI Tracker")
    print("=" * 60)

    python_exe = sys.executable
    script_dir = os.path.dirname(os.path.abspath(__file__))

    print("[1/2] Launching Streamlit Web UI...")
    # Streamlit automatically starts the background FastAPI REST API on port 8000
    cmd = [python_exe, "-m", "streamlit", "run", os.path.join(script_dir, "app.py"), "--server.port=8501", "--server.headless=false"]

    try:
        proc = subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nStopping services...")

if __name__ == "__main__":
    main()

