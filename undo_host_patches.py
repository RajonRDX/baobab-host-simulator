"""
Restore the RAJON Host Simulator files changed by:
  - fix_host_render_url.py
  - fix_production_host.py

Target:
  E:\HOST_VSCODE\host-simulator

IMPORTANT:
  1. Run without arguments first to preview the restore plan.
  2. Run with --apply only after checking the preview.
  3. This script restores the EARLIEST matching backup for each file in
     _backups\render_url_* and _backups\prod_fix_*.
     That is normally the pre-patch version, because each patcher backs up
     the current file before changing it.

The current versions are copied to _backups\_rollback_safety_* before restore.
No files are deleted.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

HOST_ROOT = Path(r"E:\HOST_VSCODE\host-simulator")
BACKUP_ROOT = HOST_ROOT / "_backups"
BACKUP_PREFIXES = ("render_url_", "prod_fix_")
SAFETY_PREFIX = "_rollback_safety_"

# The original patchers saved only path.name, not the original relative path.
# These mappings restore known backend files to their correct locations.
TARGETS = {
    "config.py": Path("backend/app/config.py"),
    "lmk_key_management_service.py": Path("backend/app/lmk_key_management_service.py"),
    "lmk_key_management_router.py": Path("backend/app/routers/lmk_key_management_router.py"),
    "seed_data.py": Path("backend/app/seed_data.py"),
}


def backup_directories():
    if not BACKUP_ROOT.is_dir():
        raise FileNotFoundError(f"Backup directory not found: {BACKUP_ROOT}")

    dirs = [
        p for p in BACKUP_ROOT.iterdir()
        if p.is_dir() and p.name.startswith(BACKUP_PREFIXES)
    ]
    return sorted(dirs, key=lambda p: p.name)


def build_restore_plan():
    """
    Backup scripts store files by basename (not relative path).
    Select the oldest backup occurrence per filename, which should be
    the state before the first patch run.
    """
    candidates = {}
    for backup_dir in backup_directories():
        for backup_file in backup_dir.iterdir():
            if not backup_file.is_file():
                continue
            candidates.setdefault(backup_file.name, []).append(
                (backup_dir.name, backup_file)
            )

    plan = []
    for filename, entries in sorted(candidates.items()):
        entries.sort(key=lambda item: item[0])
        source_dir, source = entries[0]
        if filename in TARGETS:
            destination = HOST_ROOT / TARGETS[filename]
        elif filename == ".env":
            # The patcher could have backed up either root .env or backend .env.
            # Since it flattened the path, the correct destination cannot be known.
            print(
                "[WARNING] .env backup found, but its original location is ambiguous "
                "(root or backend). It will NOT be restored automatically."
            )
            continue
        else:
            print(f"[WARNING] Unknown backup file skipped: {filename}")
            continue

        plan.append({
            "filename": filename,
            "source": source,
            "source_dir": source_dir,
            "destination": destination,
            "versions": len(entries),
        })
    return plan


def main():
    parser = argparse.ArgumentParser(
        description="Preview or restore RAJON Host Simulator patch backups."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually restore files. Without this flag, only preview.",
    )
    args = parser.parse_args()

    print("=" * 78)
    print(" RAJON HOST SIMULATOR - PATCH ROLLBACK")
    print("=" * 78)
    print(f"Target folder : {HOST_ROOT}")
    print(f"Backup folder : {BACKUP_ROOT}")
    print(f"Mode          : {'RESTORE' if args.apply else 'PREVIEW ONLY'}")
    print()

    if not HOST_ROOT.is_dir():
        raise FileNotFoundError(f"Host folder not found: {HOST_ROOT}")

    plan = build_restore_plan()
    if not plan:
        print("[STOP] No backup files found in render_url_* or prod_fix_* folders.")
        return

    print("Restore plan (oldest matching backup per filename):")
    for item in plan:
        status = "OK" if item["destination"].exists() else "DESTINATION MISSING"
        print(
            f"  [{status}] {item['filename']}\n"
            f"      FROM: {item['source']}\n"
            f"        TO: {item['destination']}\n"
            f"      Backup versions found: {item['versions']}"
        )

    if not args.apply:
        print("\n[PREVIEW COMPLETE] No files were changed.")
        print("If the plan is correct, run:")
        print('  python undo_host_patches.py --apply')
        return

    print("\nThis will overwrite the listed files with their selected backups.")
    confirmation = input('Type RESTORE to continue: ').strip()
    if confirmation != "RESTORE":
        print("[CANCELLED] No files were changed.")
        return

    safety_dir = BACKUP_ROOT / (
        SAFETY_PREFIX + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    safety_dir.mkdir(parents=True, exist_ok=False)

    restored = 0
    for item in plan:
        destination = item["destination"]
        source = item["source"]

        if not source.is_file():
            print(f"[SKIP] Backup disappeared: {source}")
            continue

        # Preserve the current file before overwriting it.
        if destination.exists():
            shutil.copy2(destination, safety_dir / destination.name)

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        restored += 1
        print(f"[RESTORED] {destination}")

    print()
    print(f"[COMPLETE] Restored {restored} file(s).")
    print(f"[SAFETY BACKUP] Previous current files saved in: {safety_dir}")
    print("Review the application locally before committing or pushing anything.")


if __name__ == "__main__":
    main()
