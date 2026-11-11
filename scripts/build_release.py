#!/usr/bin/env python3
"""
build_release.py — Final Validation, Syntax Checker, and Clean ZIP Release Builder
Run from project root: python scripts/build_release.py
"""

import os
import py_compile
import shutil
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

REQUIRED_SEVEN_MODULES = [
    "backend/app/database.py",
    "backend/app/models.py",
    "backend/app/schemas.py",
    "backend/app/api_routes.py",
    "backend/app/host_engine.py",
    "backend/app/hsm_adapter.py",
    "backend/app/iso_tic.py",
]

REQUIRED_OTHER_FILES = [
    "backend/app/main.py",
    "backend/app/config.py",
    "backend/app/security.py",
    "backend/app/logging_service.py",
    "backend/app/seed_data.py",
    "backend/requirements.txt",
    "frontend/package.json",
    "frontend/src/App.tsx",
    "frontend/src/pages/SimulatorAndJournal.tsx",
    "frontend/src/pages/HsmAndMonitorPages.tsx",
    "README.md",
]

EXCLUDE_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git", "release", "dist"}
EXCLUDE_FILES = {".env", "rajon_host.db"}


def main() -> int:
    print("=" * 72)
    print("  RAJON HOST SIMULATOR — RELEASE VALIDATOR & ZIP BUILDER")
    print("=" * 72)

    missing = []
    for rel in REQUIRED_SEVEN_MODULES + REQUIRED_OTHER_FILES:
        if not (ROOT_DIR / rel).exists():
            missing.append(rel)

    if missing:
        print("[ERROR] Missing required files:")
        for m in missing:
            print(f"  - {m}")
        return 1

    print("[OK] All 7 core Python modules and frontend files are present.")

    # Syntax check all Python files
    syntax_errors = []
    for py_file in (ROOT_DIR / "backend").rglob("*.py"):
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as exc:
            syntax_errors.append(str(exc))

    if syntax_errors:
        print("[ERROR] Python syntax errors detected:")
        for err in syntax_errors:
            print(err)
        return 1

    print("[OK] All Python backend files passed syntax verification.")

    release_dir = ROOT_DIR / "release" / "rajon-host-simulator"
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    for item in ROOT_DIR.rglob("*"):
        rel = item.relative_to(ROOT_DIR)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if item.name in EXCLUDE_FILES or item.suffix == ".zip":
            continue
        target = release_dir / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            copied_count += 1

    zip_path = ROOT_DIR / "rajon-host-simulator-release.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in release_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(release_dir.parent)
                zf.write(file_path, arcname)

    print(f"[OK] Copied {copied_count} clean source files into {release_dir}")
    print(f"[OK] Created deployable ZIP archive: {zip_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
