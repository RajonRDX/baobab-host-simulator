#!/usr/bin/env python3
"""
run_local.py — Convenience launcher to start the FastAPI Backend on http://127.0.0.1:8000
Run from project root: python scripts/run_local.py
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"

if __name__ == "__main__":
    os.chdir(BACKEND_DIR)
    print("Starting RAJON Private Host Simulator Backend on http://127.0.0.1:8000 ...")
    subprocess.run([sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"])
