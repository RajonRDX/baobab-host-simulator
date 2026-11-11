"""
restore_db.py - restore the correct SQLite database after a bad undo_db_rename.py run.

Safe by default:
    python restore_db.py                 (dry run - shows what it WOULD do)
    python restore_db.py --apply         (do it)

What it does
 1. Finds every *.db file in the project + _backups\\undo_db_*\\ and _backups\\rename_*\\
    and scores each one by how much migrated data it contains
    (counts rows, checks for RAJON_AUTH_RULES / BAOBAB_AUTH_RULES in host_parameters.parameter_group).
 2. Picks the BEST candidate = the file with the most rows AND the migrated parameter_group.
 3. Copies that file to baobab_host.db (keeping the current one in _backups\\restore_<ts>\\ first).
 4. Rewrites text references rajon_host.db -> baobab_host.db in code/config/docs.
 5. Removes (moves to _backups) stray rajon_host.db files so the app can't open them by mistake.
 6. Prints a verification summary of what is now in baobab_host.db.

Nothing is deleted - everything moved goes to _backups\\restore_<timestamp>\\ .
"""
import argparse
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("root", nargs="?", default=r"E:\HOST_VSCODE\host-simulator")
ap.add_argument("--apply", action="store_true")
ap.add_argument("--target", default="baobab_host.db",
                help="final database filename (default baobab_host.db)")
ap.add_argument("--force", default="",
                help="force using this exact .db file instead of auto-picking")
args = ap.parse_args()

ROOT = Path(args.root).resolve()
if not ROOT.exists():
    sys.exit(f"[STOP] folder not found: {ROOT}")

TARGET_NAME = args.target
BACKUP = ROOT / "_backups" / f"restore_{datetime.now():%Y%m%d_%H%M%S}"
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".venv", "venv", "env", "release", ".idea", ".vscode"}
TEXT_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".html", ".css", ".toml", ".txt",
            ".yml", ".yaml", ".cfg", ".ini", ".sh", ".bat", ".ps1", ".example"}
TEXT_NAMES = {"_redirects", ".gitignore", "Procfile", ".env", ".env.example"}
SELF = Path(__file__).resolve()
MODE = "APPLY" if args.apply else "DRY RUN"

print("=" * 74)
print(f" Restore database   [{MODE}]")
print(f" Project: {ROOT}")
print(f" Target : {TARGET_NAME}")
print("=" * 74)


def skip(path: Path) -> bool:
    try:
        parts = path.relative_to(ROOT).parts[:-1]
    except ValueError:
        return True
    return any(p in SKIP_DIRS for p in parts)


def backup_file(path: Path):
    dest = BACKUP / path.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest


# ---------------------------------------------------------------- inspect a DB
def inspect(db_path: Path) -> dict:
    info = {"path": db_path, "ok": False, "size": db_path.stat().st_size if db_path.exists() else 0,
            "rows": 0, "param_groups": [], "auth_migrated": False, "auth_old": False,
            "users": 0, "error": ""}
    if not db_path.is_file() or info["size"] == 0:
        info["error"] = "missing or empty"
        return info
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = con.cursor()
        tables = [r[0] for r in cur.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
        info["tables"] = tables
        total = 0
        for t in tables:
            try:
                total += cur.execute(f'select count(*) from "{t}"').fetchone()[0]
            except sqlite3.DatabaseError:
                pass
        info["rows"] = total
        # parameter groups
        if "host_parameters" in tables:
            try:
                groups = [r[0] for r in cur.execute(
                    "select distinct parameter_group from host_parameters "
                    "where parameter_group is not null")]
                info["param_groups"] = sorted(g for g in groups if g)
                info["auth_migrated"] = any("RAJON" in g.upper() for g in info["param_groups"])
                info["auth_old"] = any("BAOBAB" in g.upper() for g in info["param_groups"])
            except sqlite3.DatabaseError as e:
                info["error"] = f"host_parameters: {e}"
        # users table (loose heuristic)
        for name in ("users", "user", "accounts", "hsm_users"):
            if name in tables:
                try:
                    info["users"] = cur.execute(f'select count(*) from "{name}"').fetchone()[0]
                except sqlite3.DatabaseError:
                    pass
                break
        info["ok"] = True
        con.close()
    except sqlite3.DatabaseError as e:
        info["error"] = str(e)
    return info


# ---------------------------------------------------------------- find candidates
def find_dbs() -> list[Path]:
    seen, out = set(), []
    for p in ROOT.rglob("*.db"):
        if not p.is_file():
            continue
        rp = p.resolve()
        if rp in seen:
            continue
        # skip obvious junk
        if any(x in rp.parts for x in SKIP_DIRS):
            continue
        seen.add(rp)
        out.append(p)
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


candidates = find_dbs()

if args.force:
    forced = Path(args.force) if Path(args.force).is_absolute() else (ROOT / args.force)
    if not forced.exists():
        sys.exit(f"[STOP] --force file not found: {forced}")
    candidates = [forced] + [c for c in candidates if c.resolve() != forced.resolve()]

print(f"\n[1] Found {len(candidates)} .db file(s). Inspecting…\n")
infos = [inspect(p) for p in candidates]

hdr = f"{'file':55} {'size':>10} {'rows':>7} {'users':>6} {'RAJON?':>7} {'BAOBAB?':>8}"
print(hdr)
print("-" * len(hdr))
for i in infos:
    try:
        rel = str(i["path"].relative_to(ROOT))
    except ValueError:
        rel = str(i["path"])
    print(f"{rel[:55]:55} {i['size']:>10} {i['rows']:>7} {i['users']:>6} "
          f"{'yes' if i['auth_migrated'] else '-':>7} {'yes' if i['auth_old'] else '-':>8}")

# ---------------------------------------------------------------- pick best
def score(i: dict) -> tuple:
    # prefer: OK > many rows > RAJON-migrated > more users > newer
    if not i["ok"]:
        return (-1, 0, 0, 0)
    return (1, i["rows"], 1 if i["auth_migrated"] else 0, i["users"])


best = None
if args.force:
    best = next((i for i in infos if str(i["path"]).endswith(str(Path(args.force).name))), None)
if best is None:
    valid = [i for i in infos if i["ok"] and i["rows"] > 0]
    if not valid:
        sys.exit("\n[STOP] no non-empty SQLite database found in the project or _backups.\n"
                 "        Check that _backups\\undo_db_*\\ still exists.")
    best = max(valid, key=lambda i: (score(i), i["path"].stat().st_mtime))

target = ROOT / TARGET_NAME
try:
    best_rel = best["path"].relative_to(ROOT)
except ValueError:
    best_rel = best["path"]

print(f"\n[2] BEST candidate: {best_rel}")
print(f"    size={best['size']}  rows={best['rows']}  users={best['users']}  "
      f"RAJON_AUTH_RULES={'yes' if best['auth_migrated'] else 'no'}  "
      f"BAOBAB_AUTH_RULES={'yes' if best['auth_old'] else 'no'}")

if best["auth_old"] and not best["auth_migrated"]:
    print("    ! WARNING: chosen DB still has BAOBAB_AUTH_RULES - the migration script will be")
    print("      needed afterwards:  python rename_to_rajon.py --apply")

print(f"\n[3] Will copy it to: {TARGET_NAME}")
if target.exists():
    same = target.resolve() == best["path"].resolve()
    print(f"    existing {TARGET_NAME} will be backed up to _backups\\restore_...\\ "
          f"{'(identical file - skipped)' if same else ''}")

if args.apply:
    target = ROOT / TARGET_NAME
    if target.exists() and target.resolve() != best["path"].resolve():
        backup_file(target)
    if target.resolve() != best["path"].resolve():
        shutil.copy2(best["path"], target)
    # remove stray rajon_host.db so the app can't open it
    for stray in ROOT.rglob("rajon_host.db"):
        if stray.resolve() == target.resolve():
            continue
        dest = BACKUP / "stray" / stray.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stray), str(dest))
        print(f"    moved stray file: {stray.relative_to(ROOT)} -> _backups\\restore_...\\stray\\")
    # also remove stray inside backend\
    for stray in (ROOT / "backend").glob("rajon_host.db"):
        if stray.resolve() == target.resolve():
            continue
        dest = BACKUP / "stray" / stray.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stray), str(dest))
        print(f"    moved stray file: {stray.relative_to(ROOT)} -> _backups\\restore_...\\stray\\")

# ---------------------------------------------------------------- rewrite text refs
OLD_NAME = "rajon_host.db"
print(f"\n[4] Rewriting text references {OLD_NAME} -> {TARGET_NAME}")
hits = []
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or path.resolve() == SELF or skip(path):
        continue
    if not (path.suffix.lower() in TEXT_EXT or path.name in TEXT_NAMES):
        continue
    if path.stat().st_size > 5_000_000:
        continue
    try:
        raw = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        continue
    if OLD_NAME in raw:
        hits.append((path, raw, raw.count(OLD_NAME)))

if not hits:
    print("    nothing to rewrite")
for path, raw, n in hits:
    print(f"    {n:>3}  {path.relative_to(ROOT)}")
    if args.apply:
        backup_file(path)
        path.write_bytes(raw.replace(OLD_NAME, TARGET_NAME).encode("utf-8"))

# ---------------------------------------------------------------- verify
print(f"\n[5] Verification of {TARGET_NAME}")
final = inspect(ROOT / TARGET_NAME)
print(f"    exists      : {(ROOT / TARGET_NAME).exists()}")
print(f"    size        : {final['size']}")
print(f"    tables      : {len(final.get('tables', []))}")
print(f"    rows        : {final['rows']}")
print(f"    users       : {final['users']}")
print(f"    param groups: {', '.join(final['param_groups'][:8]) if final['param_groups'] else '(none)'}")
if final["auth_migrated"]:
    print("    auth rules  : RAJON_AUTH_RULES present  [OK]")
elif final["auth_old"]:
    print("    auth rules  : BAOBAB_AUTH_RULES present  [needs migration]")
    print("                  run:  python rename_to_rajon.py --apply")
else:
    print("    auth rules  : (no AUTH parameter_group found)")

print("\n" + "=" * 74)
if not args.apply:
    print(" DRY RUN finished - nothing was changed. Re-run with --apply to restore.")
    print(" If the picked candidate above is wrong, override with:")
    print(f'   python restore_db.py --apply --force "path\\to\\specific.db"')
else:
    print(f" DONE. Backups: {BACKUP}")
    print(" Next steps:")
    print("   1. Check backend\\.env / config.py / DATABASE_URL still say baobab_host.db")
    print("   2. Render Dashboard -> Environment -> DATABASE_URL -> .../baobab_host.db")
    print("   3. git add -A && git commit -m \"Restore baobab_host.db\" && git push")
    print("   4. If auth rules show BAOBAB_*, run: python rename_to_rajon.py --apply")
print("=" * 74)