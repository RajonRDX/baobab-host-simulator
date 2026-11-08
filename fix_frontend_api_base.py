"""
fix_frontend_api_base.py
Fixes: Key Ceremony / HSM switch calling http://127.0.0.1:8000 from the Netlify site.

Run:
    cd E:\\HOST_VSCODE\\host-simulator-github-prod
    python fix_frontend_api_base.py
Then:
    git add . && git commit -m "Use same-origin /api for axios client" && git push
Netlify rebuilds and the /api/* redirect forwards to the Render backend.
"""
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"E:\HOST_VSCODE\host-simulator-github-prod")
if len(sys.argv) == 1 and not (ROOT / "frontend").exists():
    ROOT = Path(__file__).resolve().parent
path = ROOT / "frontend" / "src" / "services" / "api.ts"

if not path.exists():
    sys.exit(f"[NOT FOUND] {path}")

raw = path.read_bytes().decode("utf-8")
crlf = "\r\n" in raw
text = raw.replace("\r\n", "\n")

pattern = re.compile(r"(const HOST_BACKEND_URL = .*?VITE_HOST_API_URL)\s*\|\|\s*['\"]http://127\.0\.0\.1:8000['\"];")
if "// [PATCH same_origin_api]" in text:
    sys.exit("[ALREADY DONE] api.ts")
if not pattern.search(text):
    sys.exit("[NOT FOUND] HOST_BACKEND_URL line with 127.0.0.1:8000 (already changed?)")

backup = ROOT / "_backups" / f"frontend_api_{datetime.now():%Y%m%d_%H%M%S}"
backup.mkdir(parents=True, exist_ok=True)
shutil.copy2(path, backup / "api.ts")

# Empty string = same origin: Netlify forwards /api/* to Render, Vite dev proxy forwards to localhost.
text = pattern.sub(lambda m: m.group(1) + " || '';  // [PATCH same_origin_api]", text, count=1)
if crlf:
    text = text.replace("\n", "\r\n")
path.write_bytes(text.encode("utf-8"))
print(f"[APPLIED] {path}")
print("Next: git add . && git commit -m \"Use same-origin /api\" && git push")
print("Also check Netlify > Site settings > Environment variables: VITE_HOST_API_URL must NOT be set to a localhost address.")
