#!/usr/bin/env python3
"""
tools/fix_seed_imports.py
Ensures Institution and ProcessingSystem are imported at the top of backend/app/seed_data.py.
"""

from pathlib import Path
import py_compile
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()


def main() -> int:
    seed_file = BASE_DIR / "backend" / "app" / "seed_data.py"
    text = seed_file.read_text(encoding="utf-8")

    # Add Institution and ProcessingSystem to the models import block if missing
    if "Institution," not in text or "ProcessingSystem," not in text:
        old_import = "from app.models import ("
        new_import = (
            "from app.models import (\n"
            "    Institution,\n"
            "    ProcessingSystem,"
        )
        if old_import in text:
            text = text.replace(old_import, new_import, 1)

    normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
    seed_file.write_text(normalized, encoding="utf-8", newline="")
    py_compile.compile(str(seed_file), doraise=True)
    print("  [FIXED] backend/app/seed_data.py (Added Institution & ProcessingSystem imports)")
    return 0


if __name__ == "__main__":
    sys.exit(main())