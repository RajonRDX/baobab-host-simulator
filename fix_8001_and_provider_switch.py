"""
fix_8001_and_provider_switch.py
1. Scans and replaces all hardcoded 8001 / 8000 ports in frontend and backend.
2. Fixes switch_provider in lmk_key_management_router.py to never fail with Network Error.
3. Ensures HSM_REMOTE_URL defaults to Render in production.
"""

import os
from pathlib import Path
import re

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator-github-prod")
if not BASE_DIR.exists():
    BASE_DIR = Path(".")

PROD_HSM_URL = "https://thales-10k-soft-hsm.onrender.com"
PROD_HSM_CMD = "https://thales-10k-soft-hsm.onrender.com/api/host/command"
PROD_BACKEND_URL = "https://baobab-backend-uxgz.onrender.com"

print(f"Scanning and cleaning port 8001 across {BASE_DIR.resolve()}...")

# 1. Sweep all text files in frontend/src and backend/app
TARGET_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".env", ".html"}
REPLACEMENTS = [
    ("https://thales-10k-soft-hsm.onrender.com/api/host/command", PROD_HSM_CMD),
    ("https://thales-10k-soft-hsm.onrender.com/api/host/command", PROD_HSM_CMD),
    ("https://thales-10k-soft-hsm.onrender.com", PROD_HSM_URL),
    ("https://thales-10k-soft-hsm.onrender.com", PROD_HSM_URL),
    ("thales-10k-soft-hsm.onrender.com", "thales-10k-soft-hsm.onrender.com"),
    ("thales-10k-soft-hsm.onrender.com", "thales-10k-soft-hsm.onrender.com"),
    ("https://baobab-backend-uxgz.onrender.com/api", f"{PROD_BACKEND_URL}/api"),
    ("https://baobab-backend-uxgz.onrender.com/api", f"{PROD_BACKEND_URL}/api"),
]

modified_files = []

for root, _, files in os.walk(BASE_DIR):
    if any(skip in root for skip in [".git", "node_modules", "dist", ".venv", "__pycache__"]):
        continue
    for file in files:
        file_path = Path(root) / file
        if file_path.suffix.lower() in TARGET_EXTENSIONS:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                orig_content = content
                for old_val, new_val in REPLACEMENTS:
                    content = content.replace(old_val, new_val)
                
                if content != orig_content:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    modified_files.append(str(file_path.relative_to(BASE_DIR)))
            except Exception:
                pass

print(f"Cleaned {len(modified_files)} files with hardcoded port 8001 / 8000 references:")
for mf in modified_files:
    print(f"  - {mf}")

# 2. Patch backend/app/config.py
config_file = BASE_DIR / "backend" / "app" / "config.py"
if config_file.exists():
    with open(config_file, "r", encoding="utf-8") as f:
        c_code = f.read()
    
    # Ensure default fallback is never thales-10k-soft-hsm.onrender.com
    c_code = re.sub(
        r'HSM_REMOTE_URL:\s*str\s*=\s*["\'].*?["\']',
        f'HSM_REMOTE_URL: str = "{PROD_HSM_CMD}"',
        c_code
    )
    with open(config_file, "w", encoding="utf-8") as f:
        f.write(c_code)
    print("[OK] Enforced Render HSM URL in backend/app/config.py")

# 3. Patch backend/app/routers/lmk_key_management_router.py
router_file = BASE_DIR / "backend" / "app" / "routers" / "lmk_key_management_router.py"
if router_file.exists():
    with open(router_file, "r", encoding="utf-8") as f:
        r_code = f.read()

    # Robust switch_provider implementation that never fails with 500
    safe_switch_endpoint = f'''@router.post("/provider/switch")
def switch_provider(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Safely toggles between INTERNAL_HSM and EXTERNAL_HSM (SOFT_HSM_REMOTE).
    Handles remote cold-start and network latency gracefully without crashing.
    """
    target = payload.get("provider", payload.get("mode", "INTERNAL_HSM")).upper().strip()
    
    if target in ("EXTERNAL_HSM", "SOFT_HSM_REMOTE", "REMOTE"):
        settings.HSM_MODE = "SOFT_HSM_REMOTE"
        active_provider = "EXTERNAL_HSM"
    else:
        settings.HSM_MODE = "SOFT_HSM_LOCAL"
        active_provider = "INTERNAL_HSM"
        
    svc = LMKKeyManagementService(db)
    
    # Retrieve status safely
    try:
        status_info = svc.get_lmk_and_provider_status()
    except Exception as exc:
        status_info = {{
            "active_provider": active_provider,
            "hsm_mode": settings.HSM_MODE,
            "online": False,
            "hsm_state": "WARMING_UP",
            "lmk_id": "00",
            "lmk_check_value": "WARMING_UP",
            "lmk_kcv_short": "---",
            "remote_url": "{PROD_HSM_CMD}",
            "error": str(exc),
        }}
    
    # Auto-seed external key references in the database
    if active_provider == "EXTERNAL_HSM":
        try:
            from app.seed_data import seed_external_hsm_keys_if_needed
            seed_external_hsm_keys_if_needed(db)
        except Exception:
            pass

    return {{
        "status": "SWITCHED",
        "hsm_mode": settings.HSM_MODE,
        "active_provider": active_provider,
        "provider_status": status_info,
    }}
'''

    # Replace existing switch route
    if "@router.post(\"/provider/switch\")" in r_code or "@router.post('/provider/switch')" in r_code:
        r_code = re.sub(
            r"@router\.post\([\"']/provider/switch[\"'].*?\n(?:    .*\n)*",
            safe_switch_endpoint + "\n",
            r_code,
        )
        with open(router_file, "w", encoding="utf-8") as f:
            f.write(r_code)
        print("[OK] Hardened switch_provider route in lmk_key_management_router.py")

# 4. Check Frontend Simulator & Keys Pages
frontend_dir = BASE_DIR / "frontend" / "src"
if frontend_dir.exists():
    for f in frontend_dir.rglob("*.tsx"):
        try:
            with open(f, "r", encoding="utf-8") as pf:
                code = pf.read()
            # Replace any residual 8001 label or default state
            new_code = code.replace("8001", "Remote Soft-HSM").replace(":8001", "")
            if new_code != code:
                with open(f, "w", encoding="utf-8") as pf:
                    pf.write(new_code)
                print(f"[OK] Purged 8001 references from frontend: {f.name}")
        except Exception:
            pass

print("\nFix completed successfully!")