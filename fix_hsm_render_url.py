# E:\HSM_V2\thales-soft-hsm\fix_hsm_render_url.py
"""
Automated Production Patcher for Thales 10K Soft-HSM Frontend
Sets default production backend URL to https://thales-10k-soft-hsm.onrender.com
"""

import shutil
from datetime import datetime
from pathlib import Path

HSM_ROOT = Path(r"E:\HSM_V2\thales-soft-hsm")
if not HSM_ROOT.exists():
    HSM_ROOT = Path(__file__).resolve().parent

BACKUP_DIR = HSM_ROOT / "_backups" / f"render_url_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
RENDER_HSM_BASE = "https://thales-10k-soft-hsm.onrender.com"


def backup_file(path: Path) -> None:
    if path.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, BACKUP_DIR / path.name)
        print(f"[BACKUP] {path.name} -> {BACKUP_DIR / path.name}")


def main():
    print("=" * 75)
    print(f" Setting Default Render URL in Soft-HSM Frontend: {RENDER_HSM_BASE}")
    print("=" * 75)

    client_js = HSM_ROOT / "js" / "hsm_api_client.js"
    if client_js.exists():
        backup_file(client_js)
        text = client_js.read_text(encoding="utf-8")
        old_fn = '''        static getBaseUrl() {
            const saved = localStorage.getItem(STORAGE_KEY_API_URL);
            if (saved && saved.trim()) {
                return saved.trim().replace(/\\/+$/, "");
            }
            if (window.VITE_API_BASE_URL) {
                return window.VITE_API_BASE_URL.replace(/\\/+$/, "");
            }
            if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {
                return "http://127.0.0.1:8001";
            }
            return "";
        }'''

        new_fn = f'''        static getBaseUrl() {{
            const saved = localStorage.getItem(STORAGE_KEY_API_URL);
            if (saved && saved.trim() && !saved.includes("127.0.0.1") && !saved.includes("localhost")) {{
                return saved.trim().replace(/\\/+$/, "");
            }}
            if (window.VITE_API_BASE_URL) {{
                return window.VITE_API_BASE_URL.replace(/\\/+$/, "");
            }}
            if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {{
                return saved && saved.trim() ? saved.trim().replace(/\\/+$/, "") : "{RENDER_HSM_BASE}";
            }}
            return "{RENDER_HSM_BASE}";
        }}'''

        if "static getBaseUrl()" in text:
            # Replace getBaseUrl method cleanly
            start_idx = text.find("static getBaseUrl()")
            end_idx = text.find("static setBaseUrl(", start_idx)
            if start_idx != -1 and end_idx != -1:
                text = text[:start_idx] + new_fn.lstrip() + "\n\n        " + text[end_idx:]
                client_js.write_text(text, encoding="utf-8")
                print(f"[UPDATED] {client_js}")

    print("=" * 75)
    print(" SOFT-HSM FRONTEND PATCH COMPLETE!")
    print("=" * 75)


if __name__ == "__main__":
    main()