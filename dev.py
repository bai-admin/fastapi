#!/usr/bin/env python3
import subprocess
import sys
import time
import signal
import requests
import atexit
from pathlib import Path

def check_subscriptions():
    """Check for existing subscriptions"""
    try:
        response = requests.get('http://localhost:8000/subscriptions/current')
        if response.status_code == 200:
            print("Found existing subscription:", response.json())
            return True
        return False
    except requests.exceptions.ConnectionError:
        return False

def cleanup_subscriptions():
    """Cleanup any existing subscriptions"""
    try:
        response = requests.delete('http://localhost:8000/subscriptions/delete')
        if response.status_code == 200:
            print("Successfully cleaned up subscriptions")
        else:
            print("No subscriptions to clean up")
    except requests.exceptions.ConnectionError:
        print("Server not running, no subscriptions to clean up")

def run_server():
    """Run the uvicorn development server"""
    # Register cleanup function
    atexit.register(cleanup_subscriptions)
    
    # Start the server
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "fastapi.main:app", "--reload", "--port", "8000"],
        cwd=Path(__file__).parent.parent
    )
    
    # Handle Ctrl+C gracefully
    def signal_handler(signum, frame):
        print("\nShutting down server...")
        cleanup_subscriptions()
        server_process.terminate()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Wait for server to start
    print("Starting development server...")
    max_retries = 30
    for i in range(max_retries):
        try:
            requests.get('http://localhost:8000/docs')
            print("Server is ready!")
            break
        except requests.exceptions.ConnectionError:
            if i == max_retries - 1:
                print("Server failed to start")
                sys.exit(1)
            time.sleep(1)
    
    try:
        server_process.wait()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        cleanup_subscriptions()
        server_process.terminate()
        sys.exit(0)

if __name__ == "__main__":
    run_server() 