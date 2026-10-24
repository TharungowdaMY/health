"""Used by the Docker HEALTHCHECK: exit 0 if /health returns 200, else exit 1."""
import os
import sys
import urllib.request

port = os.environ.get("PORT", "8000")
try:
    urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3)
except Exception:
    sys.exit(1)
