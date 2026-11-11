#!/usr/bin/env python3
"""
Fixes `sqlite3.IntegrityError: FOREIGN KEY constraint failed` on `limit_transaction_consumptions`
Works whether saved in `E:\\HOST_VSCODE\\host-simulator\\` or `E:\\HOST_VSCODE\\host-simulator\\tools\\`.
"""

from datetime import datetime
from pathlib import Path
import shutil
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if (SCRIPT_DIR / "backend" / "app" / "host_engine.py").exists():
    PROJECT_ROOT = SCRIPT_DIR
elif (SCRIPT_DIR.parent / "backend" / "app" / "host_engine.py").exists():
    PROJECT_ROOT = SCRIPT_DIR.parent
elif (Path.cwd() / "backend" / "app" / "host_engine.py").exists():
    PROJECT_ROOT = Path.cwd()
else:
    raise FileNotFoundError(
        "Could not locate backend/app/host_engine.py. Please run from E:\\HOST_VSCODE\\host-simulator"
    )

BACKUP_ROOT = PROJECT_ROOT / "_backups" / f"step13_07_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def backup_file(rel_path: str) -> None:
    src = PROJECT_ROOT / rel_path
    if src.exists():
        dst = BACKUP_ROOT / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def patch_host_engine() -> None:
    rel_path = "backend/app/host_engine.py"
    target = PROJECT_ROOT / rel_path
    if not target.exists():
        raise FileNotFoundError(f"Cannot find {target}")

    text = target.read_text(encoding="utf-8")
    backup_file(rel_path)

    # 1. Ensure self.pending_limit_consumptions is initialized in __init__
    if "self.pending_limit_consumptions" not in text:
        text = text.replace(
            "self.limit_eval_results: List[Dict[str, Any]] = []",
            "self.limit_eval_results: List[Dict[str, Any]] = []\n        self.pending_limit_consumptions: List[Any] = []",
            1,
        )

    # 2. Replace premature commit_approved_usage call before _finalize_transaction
    premature_block = (
        '        # Commit pending LimitCalculationEngine usage now that authorization is APPROVED\n'
        '        if limit_eval_report and limit_eval_report.pending_consumptions:\n'
        '            self.limit_engine.commit_approved_usage(tx_id, limit_eval_report.pending_consumptions)'
    )
    deferred_block = (
        '        # Queue pending LimitCalculationEngine usage to be flushed right after Transaction row is inserted\n'
        '        if limit_eval_report and limit_eval_report.pending_consumptions:\n'
        '            self.pending_limit_consumptions = list(limit_eval_report.pending_consumptions)'
    )
    if premature_block in text:
        text = text.replace(premature_block, deferred_block, 1)

    # 3. Inside _finalize_transaction, right after `self.db.add(tx)` and `self.db.flush()`,
    #    flush `self.pending_limit_consumptions` now that `tx.id` exists in `transactions` table!
    tx_flush_anchor = "        self.db.add(tx)\n        self.db.flush()"
    tx_flush_replacement = (
        "        self.db.add(tx)\n"
        "        self.db.flush()\n\n"
        "        # [PATCH step13_07:commit_limit_usage_after_tx_flush]\n"
        "        if approved and getattr(self, 'pending_limit_consumptions', None):\n"
        "            self.limit_engine.commit_approved_usage(tx.id, self.pending_limit_consumptions)\n"
        "            self.pending_limit_consumptions = []"
    )
    if "# [PATCH step13_07:commit_limit_usage_after_tx_flush]" not in text:
        if tx_flush_anchor not in text:
            raise RuntimeError("Could not find `self.db.add(tx)\\n        self.db.flush()` in host_engine.py")
        text = text.replace(tx_flush_anchor, tx_flush_replacement, 1)

    target.write_text(text, encoding="utf-8")
    print(f"[PATCH] {target} updated so limit_transaction_consumptions flushes AFTER Transaction row insert.")


def main() -> int:
    print("=" * 76)
    print("STEP 13_07 INSTALLER: Fix Foreign Key Flush Order in HostTransactionProcessor")
    print(f"Detected Project Root: {PROJECT_ROOT}")
    print("=" * 76)

    patch_host_engine()

    print("-" * 76)
    print("[OK] Foreign key ordering fixed!")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())