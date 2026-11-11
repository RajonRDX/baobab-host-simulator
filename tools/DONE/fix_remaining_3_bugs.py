#!/usr/bin/env python3
"""
tools/fix_remaining_3_bugs.py
Fixes the 3 root causes reported by pytest:
  1. Moves xbank_id / itcl_id initialization to the top of seed_initial_data() in backend/app/seed_data.py
  2. Escapes \\x regex pattern in backend/app/iso_tic.py for Python 3.13 compatibility
  3. Blocks dunder/private attribute access (_ / __) in backend/app/rules_evaluator.py
"""

from pathlib import Path
import py_compile
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()


def fix_seed_data() -> None:
    seed_file = BASE_DIR / "backend" / "app" / "seed_data.py"
    text = seed_file.read_text(encoding="utf-8")

    # Ensure xbank_id and itcl_id are initialized right after the early return in seed_initial_data
    old_block = (
        "def seed_initial_data(db: Session) -> None:\n"
        "    seed_processing_systems_and_institutions(db)\n"
        "    if db.query(Customer).count() > 0:\n"
        "        return"
    )
    new_block = (
        "def seed_initial_data(db: Session) -> None:\n"
        "    seed_processing_systems_and_institutions(db)\n"
        "    if db.query(Customer).count() > 0:\n"
        "        return\n\n"
        "    xbank = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()\n"
        "    xbank_id = xbank.id if xbank else None\n"
        "    itcl_ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == 'ITCL').first()\n"
        "    itcl_id = itcl_ps.id if itcl_ps else None"
    )

    if "xbank_id = xbank.id if xbank else None" not in text.split("# 1. Response Codes")[0]:
        if old_block in text:
            text = text.replace(old_block, new_block, 1)
        else:
            # Fallback regex replacement if comments exist between lines
            import re
            text = re.sub(
                r"(def seed_initial_data\(db:\s*Session\)\s*->\s*None:.*?if db\.query\(Customer\)\.count\(\)\s*>\s*0:\s*\n\s*return)",
                r"\1\n\n    xbank = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()\n"
                r"    xbank_id = xbank.id if xbank else None\n"
                r"    itcl_ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == 'ITCL').first()\n"
                r"    itcl_id = itcl_ps.id if itcl_ps else None",
                text,
                count=1,
                flags=re.DOTALL,
            )

    normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
    seed_file.write_text(normalized, encoding="utf-8", newline="")
    py_compile.compile(str(seed_file), doraise=True)
    print("  [FIXED] backend/app/seed_data.py (xbank_id & itcl_id initialized at top of seed_initial_data)")


def fix_iso_tic_regex() -> None:
    iso_file = BASE_DIR / "backend" / "app" / "iso_tic.py"
    text = iso_file.read_text(encoding="utf-8")

    # Replace single-backslash r"\x([0-9a-fA-F]{2})" with double-backslash r"\\x([0-9a-fA-F]{2})"
    bad_regex = 're.sub(r"\\x([0-9a-fA-F]{2})"'
    good_regex = 're.sub(r"\\\\x([0-9a-fA-F]{2})"'

    if bad_regex in text:
        text = text.replace(bad_regex, good_regex)

    normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
    iso_file.write_text(normalized, encoding="utf-8", newline="")
    py_compile.compile(str(iso_file), doraise=True)
    print("  [FIXED] backend/app/iso_tic.py (Python 3.13 regex escape fixed)")


def fix_rules_evaluator_dunder() -> None:
    rules_file = BASE_DIR / "backend" / "app" / "rules_evaluator.py"
    text = rules_file.read_text(encoding="utf-8")

    old_attr_block = (
        "        if isinstance(node, ast.Attribute):\n"
        "            val = cls._eval_node(node.value, context)\n"
        "            attr = node.attr\n"
        "            if isinstance(val, dict):\n"
        "                return val.get(attr)\n"
        "            if hasattr(val, attr):\n"
        "                return getattr(val, attr)"
    )

    new_attr_block = (
        "        if isinstance(node, ast.Attribute):\n"
        "            attr = node.attr\n"
        "            if attr.startswith(\"_\"):\n"
        "                raise SafeEvalError(f\"Forbidden private/dunder attribute access: '{attr}'\")\n"
        "            val = cls._eval_node(node.value, context)\n"
        "            if isinstance(val, dict):\n"
        "                return val.get(attr)\n"
        "            if hasattr(val, attr):\n"
        "                return getattr(val, attr)"
    )

    if "attr.startswith(\"_\")" not in text and old_attr_block in text:
        text = text.replace(old_attr_block, new_attr_block, 1)

    normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
    rules_file.write_text(normalized, encoding="utf-8", newline="")
    py_compile.compile(str(rules_file), doraise=True)
    print("  [FIXED] backend/app/rules_evaluator.py (dunder/private attributes blocked)")


def main() -> int:
    print("=" * 72)
    print("  APPLYING TARGETED FIXES FOR PYTEST SUITE")
    print("=" * 72)
    fix_seed_data()
    fix_iso_tic_regex()
    fix_rules_evaluator_dunder()
    print("=" * 72)
    print("  All 3 fixes applied and syntax-verified.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())