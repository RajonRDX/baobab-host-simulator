#!/usr/bin/env python3
"""
fix_tic_decoder.py
Safely appends strict_mask_pan to backend/app/tic_decoder_engine.py
"""

from pathlib import Path

def main():
    root = Path(__file__).resolve().parent
    if not (root / "backend").exists() and (root.parent / "backend").exists():
        root = root.parent
    
    target_path = root / "backend" / "app" / "tic_decoder_engine.py"
    if not target_path.exists():
        print(f"Error: Could not find {target_path}")
        return

    print(f"Found target file: {target_path}")
    text = target_path.read_text(encoding="utf-8")

    if "def strict_mask_pan" in text:
        print("✅ strict_mask_pan already exists in tic_decoder_engine.py")
        return

    helper_code = '''

def strict_mask_pan(pan) -> str:
    """Always masks PAN as 123456******1234 by default, even when LOG_RAW_DATA=True."""
    if not pan:
        return "****"
    clean = "".join(ch for ch in str(pan) if ch.isdigit())
    if len(clean) >= 10:
        return f"{clean[:6]}{'*' * (len(clean) - 10)}{clean[-4:]}"
    if "*" in str(pan):
        return str(pan)
    return "****"
'''

    target_path.write_text(text + helper_code, encoding="utf-8", newline="\n")
    print("✨ Successfully added strict_mask_pan to tic_decoder_engine.py!")

if __name__ == "__main__":
    main()