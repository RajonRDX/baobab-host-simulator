"""
rename_to_rajon.py  -  replace every BAOBAB / Baobab / baobab and Compass Plus name with your own.

Default is a DRY RUN: it only prints what it would change.

    python rename_to_rajon.py                      (dry run, production folder)
    python rename_to_rajon.py --apply              (really change files, rename files, migrate DB)
    python rename_to_rajon.py "E:\\HSM_V2\\thales-soft-hsm" --apply     (same for the Soft-HSM project)

Options:
    --name Rajon                     one word, letters/digits only (default Rajon)
    --new-backend-host HOST          after you rename the Render service, put its new host name here
                                     (e.g. rajon-backend.onrender.com) to update _redirects / netlify.toml

What it does
 1. Text in source, docs, config, scripts:
      Compass Plus TW / Compass Plus -> Rajon       BAOBAB-Inspired X -> Rajon X
      BAOBAB -> RAJON      Baobab -> Rajon      baobab -> rajon
    (UI titles, browser storage keys, logger names, parameter group BAOBAB_AUTH_RULES -> RAJON_AUTH_RULES,
     database file name baobab_host.db -> rajon_host.db, docs/BAOBAB_TO_HOST_MAPPING.md, ...)
 2. Renames files whose name contains baobab (the .db file and the mapping doc).
 3. Migrates SQLite database files found in the folder: host_parameters.parameter_group and display
    text in non-log tables (without this the authorization rules would not be found after the rename).
 4. NEVER touches URLs that contain baobab (your Render URL and GitHub repo): renaming those must be done
    in the Render / GitHub dashboards (see the checklist printed at the end).
Backups of every changed file go to _backups\\rename_<timestamp>\\ .
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
ap.add_argument("--check", action="store_true", help="only list remaining Baobab / Compass Plus text, change nothing")
ap.add_argument("--name", default="Rajon")
ap.add_argument("--new-backend-host", default="")
args = ap.parse_args()

if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", args.name):
    sys.exit("--name must be one word (letters and digits only), for example Rajon")

ROOT = Path(args.root)
if not ROOT.exists():
    sys.exit(f"[STOP] folder not found: {ROOT}")

NAME, UP, LOW = args.name, args.name.upper(), args.name.lower()
BACKUP = ROOT / "_backups" / f"rename_{datetime.now():%Y%m%d_%H%M%S}"
SELF = Path(__file__).resolve()

TEXT_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".html", ".css", ".toml", ".txt",
            ".yml", ".yaml", ".cfg", ".ini", ".sh", ".bat", ".ps1", ".csv", ".example"}
TEXT_NAMES = {"_redirects", ".gitignore", "Procfile", ".env.example"}
SKIP_DIRS = {".git", "node_modules", "_backups", "dist", "__pycache__", ".venv", "venv", "env", "release", ".idea", ".vscode"}
MAX_BYTES = 5 * 1024 * 1024

# (regex, replacement) applied in this order
RULES = [
    (re.compile(r"Compass Plus(?: TW)?"), NAME),
    (re.compile(r"BAOBAB[- ]?[Ii]nspired "), NAME + " "),
    (re.compile(r"BAOBAB"), UP),
    (re.compile(r"Baobab"), NAME),
    (re.compile(r"baobab"), LOW),
    (re.compile(r"baobab", re.I), NAME),                 # any odd spelling, e.g. BaoBab
    (re.compile(r"compass\s*plus(?:\s*tw)?", re.I), NAME),  # COMPASS PLUS, CompassPlus ...
]
# URLs / hosts containing baobab are protected (they must be renamed in Render / GitHub first)
PROTECT = [
    re.compile(r"https?://[^\s'\"<>)\]]*baobab[^\s'\"<>)\]]*", re.I),
    re.compile(r"\b[\w\-]*baobab[\w\-]*\.(?:onrender\.com|netlify\.app)\b", re.I),
    re.compile(r"\b[\w\-]+/[\w\-]*baobab[\w\-]*\.git\b", re.I),
    re.compile(r"\bRajonRDX/[\w\-]*baobab[\w\-]*", re.I),
]
BACKEND_HOST_RE = re.compile(r"\b[\w\-]*baobab[\w\-]*\.onrender\.com\b", re.I)


def transform(text):
    """returns (new_text, number_of_replacements)"""
    if args.new_backend_host:
        text = BACKEND_HOST_RE.sub(args.new_backend_host.strip().replace("https://", "").rstrip("/"), text)
    saved = []

    def stash(m):
        saved.append(m.group(0))
        return f"\u0000P{len(saved) - 1}\u0000"

    for p in PROTECT:
        text = p.sub(stash, text)
    total = 0
    for rx, rep in RULES:
        text, n = rx.subn(rep, text)
        total += n
    for i, s in enumerate(saved):
        text = text.replace(f"\u0000P{i}\u0000", s)
    return text, total


def want(path):
    if path.resolve() == SELF:
        return False
    if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts[:-1]):
        return False
    return (path.suffix.lower() in TEXT_EXT or path.name in TEXT_NAMES) and path.stat().st_size <= MAX_BYTES


def backup(path):
    dest = BACKUP / path.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


mode = "APPLY" if args.apply else ("CHECK" if args.check else "DRY RUN")
print("=" * 72)
print(f" Rename to '{NAME}'  [{mode}]   folder: {ROOT}")
print("=" * 72)

if args.check:
    args.apply = False
    # CHECK = list leftovers only (steps 1-3 below run as a harmless dry run)
# ------------------------------------------------------------ 1. text files
changed, total_repl, skipped = [], 0, []
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or not want(path):
        continue
    try:
        raw = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        skipped.append(str(path.relative_to(ROOT)))
        continue
    new, n = transform(raw)
    if n and new != raw:
        changed.append((path, new, n))
        total_repl += n

print(f"\n[1] Text replacements: {total_repl} in {len(changed)} files")
for path, _, n in changed:
    print(f"    {n:>4}  {path.relative_to(ROOT)}")
if skipped:
    print("    skipped (not UTF-8):", ", ".join(skipped))

if args.apply:
    for path, new, _ in changed:
        backup(path)
        path.write_bytes(new.encode("utf-8"))

# ------------------------------------------------------------ 2. file renames
renames = []
for path in sorted(ROOT.rglob("*")):
    if path.is_file() and re.search("baobab", path.name, re.I):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts[:-1]):
            continue
        new_name = path.name
        for rx, rep in RULES[2:]:
            new_name = rx.sub(rep, new_name)
        renames.append((path, path.with_name(new_name)))

print(f"\n[2] File renames: {len(renames)}")
for old, new in renames:
    status = ""
    if new.exists():
        status = "  (target exists - SKIPPED)"
    print(f"    {old.relative_to(ROOT)}  ->  {new.name}{status}")
    if args.apply and not new.exists():
        old.rename(new)

# ------------------------------------------------------------ 3. SQLite migration
LOG_WORDS = ("log", "audit", "hsm_operation", "journal")
db_files = []
for folder in (ROOT, ROOT / "backend"):
    for nm in (f"{LOW}_host.db", "baobab_host.db"):
        p = folder / nm
        if p.exists() and p not in db_files:
            db_files.append(p)

DB_RULES = [("Compass Plus TW", NAME), ("Compass Plus", NAME), ("BAOBAB-Inspired ", NAME + " "),
            ("BAOBAB-inspired ", NAME + " "), ("BAOBAB", UP), ("Baobab", NAME), ("baobab", LOW)]

print(f"\n[3] SQLite databases found: {len(db_files)}")
for dbp in db_files:
    print(f"    {dbp.relative_to(ROOT)}")
    if args.apply:
        backup(dbp)
    con = sqlite3.connect(str(dbp))
    cur = con.cursor()
    tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
    grand = 0
    for t in tables:
        if any(w in t.lower() for w in LOG_WORDS):
            continue
        cols = [c[1] for c in cur.execute(f'pragma table_info("{t}")')
                if re.search(r"CHAR|TEXT|CLOB|JSON", (c[2] or "").upper())]
        for c in cols:
            hits = 0
            for old, new in DB_RULES:
                hits += cur.execute(f'select count(*) from "{t}" where instr("{c}", ?) > 0', (old,)).fetchone()[0]
                if args.apply:
                    # UPDATE OR IGNORE keeps UNIQUE constraints safe
                    cur.execute(f'update or ignore "{t}" set "{c}" = replace("{c}", ?, ?) where instr("{c}", ?) > 0',
                                (old, new, old))
            if hits:
                grand += hits
                print(f"       {t}.{c}: {hits} value(s)")
    if args.apply:
        con.commit()
        ok = cur.execute("pragma integrity_check").fetchone()[0]
        print(f"       integrity_check: {ok}")
    elif grand == 0:
        print("       nothing to migrate")
    con.close()

# ------------------------------------------------------------ 4. what is still left
OLD = re.compile(r"baobab|compass\s*plus", re.I)


def remaining():
    hits = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or not want(path):
            continue
        try:
            lines = path.read_bytes().decode("utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(lines, 1):
            probe = line
            for p in PROTECT:
                probe = p.sub("", probe)
            if OLD.search(probe):
                hits.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:110]}")
    return hits


left = remaining() if (args.apply or args.check) else []
if args.apply or args.check:
    print(f"\n[4] Old names still in files (protected URLs ignored): {len(left)}")
    for h in left[:40]:
        print("    " + h)
    if not left:
        print("    CLEAN - the folder no longer contains Baobab / Compass Plus text.")

# ------------------------------------------------------------ summary
print("\n" + "=" * 72)
if not args.apply:
    print(" DRY RUN finished - nothing was changed. Re-run with --apply to make the changes.")
else:
    print(f" Done. Backups: {BACKUP}")
    print(" Next: git add -A && git commit -m \"Rename to " + NAME + "\" && git push")
print("""
 STILL TO DO BY HAND (these live outside the code):
   1. Render:  host backend service -> Settings -> Name  (changes the URL, then run this script again with
               --new-backend-host <new-host>.onrender.com so _redirects / netlify.toml follow).
               If DATABASE_URL is set in Render's environment and points to baobab_host.db, change it to rajon_host.db.
   2. GitHub:  repository Settings -> Rename (the old URL redirects; update `git remote set-url origin <new url>`).
   3. Netlify: Site configuration -> Change site name (optional).
   4. Postgres instead of SQLite?  run:
         UPDATE host_parameters SET parameter_group = REPLACE(parameter_group, 'BAOBAB', '%s')
         WHERE parameter_group LIKE '%%BAOBAB%%';
   5. Everyone logs in once more (browser storage keys were renamed).
   6. Run the same script on the Soft-HSM folder (E:\\HSM_V2\\thales-soft-hsm) so both projects match.
""" % UP)
print("=" * 72)
