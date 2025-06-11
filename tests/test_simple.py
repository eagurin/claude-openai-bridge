"""Simple health check test to verify server functionality."""

import requests
import subprocess
import time
import signal
import os
from contextlib import contextmanager


@contextmanager
def run_server():
    """Context manager to start/stop server for testing."""
    # Start server
    proc = subprocess.Popen(
        ["python", "src/server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to start
    time.sleep(3)
    
    try:
        yield proc
    finally:
        # Stop server
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_health_endpoint():
    """Test that health endpoint returns expected response."""
    with run_server():
        response = requests.get("http://localhost:8000/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        print("✅ Health check passed")


def test_models_endpoint():
    """Test that models endpoint returns valid data."""
    with run_server():
        response = requests.get("http://localhost:8000/v1/models")
        assert response.status_code == 200
        
        data = response.json()
        assert data["object"] == "list"
        assert "data" in data
        assert len(data["data"]) > 0
        print("✅ Models endpoint passed")


def test_root_endpoint():
    """Test that root endpoint returns server info."""
    with run_server():
        response = requests.get("http://localhost:8000/")
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == "Claude OpenAI Server"
        assert "version" in data
        print("✅ Root endpoint passed")


if __name__ == "__main__":
    print("Running simple integration tests...")
    test_health_endpoint()
    test_models_endpoint() 
    test_root_endpoint()
    print("🎉 All tests passed!")