#!/usr/bin/env python3
"""
INSTALLER: tools/install_step00_01.py
STEP 0 — Prerequisites & Installer Framework — Script 1 of 2
Creates tools/patcher.py, PROGRESS.md, and docs/CONTRACTS.md.
"""

import argparse
from datetime import datetime
from pathlib import Path
import py_compile
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()

PATCHER_CODE = r'''#!/usr/bin/env python3
"""
tools/patcher.py — Enterprise Installer & Anchored Patch Framework
BAOBAB Private Host Simulator | Windows CRLF & Idempotent Patch Engine
"""

import argparse
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from pathlib import Path
import py_compile
import shutil
import sys
from typing import Dict, List, Optional

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
BACKUP_ROOT = BASE_DIR / "_backups"
PROGRESS_FILE = BASE_DIR / "PROGRESS.md"
CONTRACTS_FILE = BASE_DIR / "docs" / "CONTRACTS.md"

PROTECTED_FILENAMES = {".env", "baobab_host.db", "baobab_host.db-journal", "baobab_host.db-wal"}
PROTECTED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}


@dataclass
class OperationRecord:
    action: str
    rel_path: str
    status: str
    details: str = ""


class PatcherError(Exception):
    """Raised when a path safety check or anchored patch fails."""


class PatcherSession:
    def __init__(self, step_id: str, title: str, dry_run: bool = False):
        self.step_id = step_id
        self.title = title
        self.dry_run = dry_run
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_dir = BACKUP_ROOT / f"{self.step_id}_{self.timestamp}"
        self.records: List[OperationRecord] = []
        self.failed: bool = False
        self.BackedUpPaths: set[Path] = set()

    def _ensure_safe_path(self, rel_path: str) -> Path:
        clean_rel = rel_path.replace("\\", "/").lstrip("/")
        target = (BASE_DIR / clean_rel).resolve()
        if not target.is_relative_to(BASE_DIR):
            raise PatcherError(f"Path escapes BASE_DIR ({BASE_DIR}): {rel_path}")
        if target.name in PROTECTED_FILENAMES or target.suffix.lower() in PROTECTED_EXTENSIONS:
            raise PatcherError(f"Refusing to modify protected database/env file: {rel_path}")
        return target

    @staticmethod
    def _normalize_crlf(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _backup_file(self, target: Path) -> Optional[Path]:
        if not target.exists() or target in self.BackedUpPaths:
            return None
        rel = target.relative_to(BASE_DIR)
        dest = self.backup_dir / rel
        if not self.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, dest)
        self.BackedUpPaths.add(target)
        return dest

    def _format_marker(self, target: Path, marker: str) -> str:
        ext = target.suffix.lower()
        if ext in {".py", ".toml", ".sh", ".yaml", ".yml", ".gitignore"} or target.name == ".gitignore":
            return f"# [PATCH {marker}]"
        if ext in {".ts", ".tsx", ".js", ".jsx", ".css"}:
            return f"// [PATCH {marker}]"
        if ext in {".html", ".md"}:
            return f"<!-- [PATCH {marker}] -->"
        return f"# [PATCH {marker}]"

    def write_file(self, rel_path: str, content: str) -> bool:
        try:
            target = self._ensure_safe_path(rel_path)
            normalized = self._normalize_crlf(content)

            if target.exists():
                existing_raw = target.read_text(encoding="utf-8", errors="replace")
                existing_norm = self._normalize_crlf(existing_raw)
                if self._sha256(existing_norm) == self._sha256(normalized):
                    self.records.append(OperationRecord("WRITE", rel_path, "SKIPPED_IDENTICAL", "File already up to date"))
                    print(f"  [SKIP] {rel_path} (identical content)")
                    return True

                self._backup_file(target)
                action_label = "OVERWRITE"
            else:
                action_label = "CREATE"

            if not self.dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", encoding="utf-8", newline="") as f:
                    f.write(normalized)
                if target.suffix.lower() == ".py":
                    py_compile.compile(str(target), doraise=True)

            status_label = f"DRY_RUN_{action_label}" if self.dry_run else action_label
            self.records.append(OperationRecord("WRITE", rel_path, status_label, f"{len(normalized.splitlines())} lines"))
            print(f"  [{status_label}] {rel_path} ({len(normalized.splitlines())} lines)")
            return True

        except Exception as exc:
            self.failed = True
            self.records.append(OperationRecord("WRITE", rel_path, "FAILED", str(exc)))
            print(f"  [ERROR] Failed writing {rel_path}: {exc}")
            return False

    def patch_file(self, rel_path: str, edits: List[Dict[str, str]]) -> bool:
        try:
            target = self._ensure_safe_path(rel_path)
            if not target.exists():
                raise PatcherError(f"Target file does not exist: {rel_path}")

            raw_text = target.read_text(encoding="utf-8", errors="replace")
            working = raw_text.replace("\r\n", "\n").replace("\r", "\n")
            original_working = working
            applied_count = 0

            for idx, edit in enumerate(edits, start=1):
                marker_id = edit.get("marker") or f"{self.step_id}:edit{idx}"
                marker_line = self._format_marker(target, marker_id)
                action = edit.get("action", "").strip().lower()
                anchor = edit.get("anchor", "")
                text = edit.get("text", "")

                anchor_lf = anchor.replace("\r\n", "\n").replace("\r", "\n")
                text_lf = text.replace("\r\n", "\n").replace("\r", "\n")

                if marker_line in working or f"[PATCH {marker_id}]" in working:
                    print(f"  [IDEMPOTENT] {rel_path} already contains marker [{marker_id}] — skipping edit.")
                    continue

                if action == "append":
                    sep = "" if working.endswith("\n") else "\n"
                    working = f"{working}{sep}\n{marker_line}\n{text_lf}\n"
                    applied_count += 1
                    continue

                if not anchor_lf:
                    raise PatcherError(f"Edit [{marker_id}] in {rel_path} is missing an 'anchor' string.")

                occurrences = working.count(anchor_lf)
                if occurrences == 0:
                    self._report_manual_patch_guidance(rel_path, marker_id, action, anchor_lf, text_lf, "MISSING ANCHOR")
                    raise PatcherError(f"Anchor not found for [{marker_id}] in {rel_path}")
                if occurrences > 1:
                    self._report_manual_patch_guidance(rel_path, marker_id, action, anchor_lf, text_lf, f"AMBIGUOUS ANCHOR ({occurrences} matches)")
                    raise PatcherError(f"Anchor matched {occurrences} times for [{marker_id}] in {rel_path}")

                if action == "insert_after":
                    replacement = f"{anchor_lf}\n{marker_line}\n{text_lf}"
                    working = working.replace(anchor_lf, replacement, 1)
                elif action == "insert_before":
                    replacement = f"{marker_line}\n{text_lf}\n{anchor_lf}"
                    working = working.replace(anchor_lf, replacement, 1)
                elif action == "replace":
                    replacement = f"{marker_line}\n{text_lf}"
                    working = working.replace(anchor_lf, replacement, 1)
                else:
                    raise PatcherError(f"Unsupported patch action '{action}' in [{marker_id}]")

                applied_count += 1

            if working == original_working:
                self.records.append(OperationRecord("PATCH", rel_path, "SKIPPED_IDEMPOTENT", "All markers already present"))
                return True

            self._backup_file(target)
            final_crlf = self._normalize_crlf(working)

            if not self.dry_run:
                with open(target, "w", encoding="utf-8", newline="") as f:
                    f.write(final_crlf)
                if target.suffix.lower() == ".py":
                    py_compile.compile(str(target), doraise=True)

            status_label = "DRY_RUN_PATCHED" if self.dry_run else "PATCHED"
            self.records.append(OperationRecord("PATCH", rel_path, status_label, f"{applied_count} edit(s) applied"))
            print(f"  [{status_label}] {rel_path} ({applied_count} edit(s) applied)")
            return True

        except Exception as exc:
            self.failed = True
            self.records.append(OperationRecord("PATCH", rel_path, "FAILED", str(exc)))
            print(f"  [ERROR] Patch failed for {rel_path}: {exc}")
            return False

    @staticmethod
    def _report_manual_patch_guidance(rel_path: str, marker_id: str, action: str, anchor: str, text: str, reason: str) -> None:
        print("\n" + "!" * 78)
        print(f"  MANUAL PATCH GUIDANCE REQUIRED — {reason}")
        print(f"  Target File : {rel_path}")
        print(f"  Patch Marker: [PATCH {marker_id}]")
        print(f"  Operation   : {action.upper()}")
        print("-" * 78)
        print("  EXPECTED ANCHOR:")
        for line in anchor.splitlines():
            print(f"    | {line}")
        print("-" * 78)
        print("  CODE TO APPLY:")
        for line in text.splitlines():
            print(f"    + {line}")
        print("!" * 78 + "\n")

    def record_progress(
        self,
        completed: List[str],
        remaining: List[str],
        modified_files: Optional[List[str]] = None,
        known_issues: Optional[List[str]] = None,
    ) -> None:
        if self.dry_run or self.failed:
            return
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        header_needed = not PROGRESS_FILE.exists()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines: List[str] = []
        if header_needed:
            lines.append("# BAOBAB PRIVATE HOST SIMULATOR — IMPLEMENTATION PROGRESS\n")
            lines.append("Authoritative execution log updated automatically by `tools/patcher.py`.\n")

        lines.append(f"## [{now_str}] `{self.step_id}` — {self.title}")
        if modified_files:
            lines.append("- **Touched Files**: " + ", ".join(f"`{m}`" for m in modified_files))
        for item in completed:
            lines.append(f"- [x] **Completed**: {item}")
        for rem in remaining:
            lines.append(f"- [ ] **Next / Remaining**: {rem}")
        if known_issues:
            for issue in known_issues:
                lines.append(f"- **Issue/Note**: {issue}")
        else:
            lines.append("- **Known Issues**: None")
        lines.append("")

        existing = PROGRESS_FILE.read_text(encoding="utf-8") if PROGRESS_FILE.exists() else ""
        marker_tag = f"<!-- PROGRESS:{self.step_id} -->"
        if marker_tag in existing:
            return
        lines.insert(1 if header_needed else 0, marker_tag)
        full_text = existing + ("\n" if existing and not existing.endswith("\n") else "") + "\n".join(lines) + "\n"
        with open(PROGRESS_FILE, "w", encoding="utf-8", newline="") as f:
            f.write(self._normalize_crlf(full_text))
        print(f"  [PROGRESS] Updated PROGRESS.md for {self.step_id}")

    def record_contracts(self, section_title: str, contract_items: List[str]) -> None:
        if self.dry_run or self.failed:
            return
        CONTRACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        header_needed = not CONTRACTS_FILE.exists()
        existing = CONTRACTS_FILE.read_text(encoding="utf-8") if CONTRACTS_FILE.exists() else ""
        marker_tag = f"<!-- CONTRACT:{self.step_id} -->"
        if marker_tag in existing:
            return

        lines: List[str] = []
        if header_needed:
            lines.append("# BAOBAB PRIVATE HOST SIMULATOR — PUBLIC CONTRACTS & INTERFACES\n")
            lines.append("Tracks database tables, columns, API routes, schemas, settings, and React routes.\n")
        lines.append(marker_tag)
        lines.append(f"## `{self.step_id}` — {section_title}")
        for item in contract_items:
            lines.append(f"- {item}")
        lines.append("")

        full_text = existing + ("\n" if existing and not existing.endswith("\n") else "") + "\n".join(lines) + "\n"
        with open(CONTRACTS_FILE, "w", encoding="utf-8", newline="") as f:
            f.write(self._normalize_crlf(full_text))
        print(f"  [CONTRACTS] Updated docs/CONTRACTS.md for {self.step_id}")

    def finish(self) -> int:
        print("\n" + "=" * 78)
        print(f"  SUMMARY: {self.step_id} — {self.title} {'(DRY-RUN)' if self.dry_run else ''}")
        print("=" * 78)
        for rec in self.records:
            print(f"  {rec.action:<7} | {rec.status:<18} | {rec.rel_path:<42} | {rec.details}")
        if self.BackedUpPaths and not self.dry_run:
            print(f"\n  Backups saved to: {self.backup_dir.relative_to(BASE_DIR)}")
        print("=" * 78)
        if self.failed:
            print("  [RESULT] FAILED — One or more operations did not complete cleanly.")
            return 1
        print("  [RESULT] SUCCESS — All operations verified.")
        return 0


# Top-level convenience wrappers for installer scripts
_default_session: Optional[PatcherSession] = None


def get_session(step_id: str = "step00", title: str = "Manual Patch Session", dry_run: bool = False) -> PatcherSession:
    global _default_session
    if _default_session is None:
        _default_session = PatcherSession(step_id=step_id, title=title, dry_run=dry_run)
    return _default_session


def write_file(rel_path: str, content: str, dry_run: bool = False) -> bool:
    sess = get_session(dry_run=dry_run)
    return sess.write_file(rel_path, content)


def patch_file(rel_path: str, edits: List[Dict[str, str]], dry_run: bool = False) -> bool:
    sess = get_session(dry_run=dry_run)
    return sess.patch_file(rel_path, edits)


def parse_installer_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--dry-run", action="store_true", help="Simulate all file creations and patches without modifying disk")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_installer_args("BAOBAB Shared Patcher Framework")
    print(f"[OK] BAOBAB Patcher Framework ready at {BASE_DIR} (dry_run={args.dry_run})")
'''

INITIAL_PROGRESS_MD = """# BAOBAB PRIVATE HOST SIMULATOR — IMPLEMENTATION PROGRESS

Authoritative execution log updated automatically by `tools/patcher.py`.

## Baseline Architecture Indexed
- **Backend**: FastAPI, SQLAlchemy 2.0, Pydantic v2, SQLite/PostgreSQL (`backend/app/`)
- **Core Engine**: `HostTransactionProcessor` (`backend/app/host_engine.py`)
- **Soft-HSM**: `SoftHsmCryptoCore` & `HSMAdapter` (`backend/app/hsm_adapter.py`)
- **Wire Codec**: Compass Plus TW TIC/TCI v2.164e (`backend/app/iso_tic.py`)
- **Frontend**: React 18, TypeScript, Tailwind CSS, 16 views (`frontend/src/`)
"""

INITIAL_CONTRACTS_MD = """# BAOBAB PRIVATE HOST SIMULATOR — PUBLIC CONTRACTS & INTERFACES

Tracks database tables, columns, API routes, schemas, settings, and React routes.

## Baseline Contracts (Pre-Step 0)
- **Database Tables (21)**: `customers`, `accounts`, `account_ledger`, `account_limits`, `card_profiles`, `cards`, `card_accounts`, `card_limits`, `pin_profiles`, `emv_profiles`, `transaction_codes`, `transaction_code_fields`, `host_parameters`, `response_codes`, `network_profiles`, `hsm_key_references`, `hsm_operations`, `hsm_audit_logs`, `transactions`, `transaction_checks`, `transaction_messages`, `transaction_reversals`, `system_logs`, `notifications`.
- **Core Settings**: `APP_NAME`, `APP_ENV`, `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `DATABASE_URL`, `HSM_MODE`, `HSM_REMOTE_URL`, `HSM_HEADER_LENGTH`, `CORS_ORIGINS`.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 00_01 Installer: Bootstrap tools/patcher.py")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing files")
    args = parser.parse_args()

    print("=" * 78)
    print("  BAOBAB INSTALLER: STEP 0 — SCRIPT 1 OF 2 (Bootstrap tools/patcher.py)")
    print("=" * 78)

    if not BASE_DIR.exists():
        print(f"[ERROR] Project root {BASE_DIR} does not exist.")
        return 1

    patcher_path = BASE_DIR / "tools" / "patcher.py"
    normalized_patcher = PATCHER_CODE.lstrip("\n").replace("\r\n", "\n").replace("\n", "\r\n")

    if args.dry_run:
        print(f"  [DRY-RUN] Would create/update: tools/patcher.py ({len(normalized_patcher.splitlines())} lines)")
        print("  [DRY-RUN] Would initialize: PROGRESS.md and docs/CONTRACTS.md")
        return 0

    patcher_path.parent.mkdir(parents=True, exist_ok=True)
    with open(patcher_path, "w", encoding="utf-8", newline="") as f:
        f.write(normalized_patcher)
    py_compile.compile(str(patcher_path), doraise=True)
    print(f"  [WRITE] tools/patcher.py ({len(normalized_patcher.splitlines())} lines)")

    sys.path.insert(0, str(BASE_DIR))
    from tools.patcher import PatcherSession

    session = PatcherSession(
        step_id="step00_01",
        title="Bootstrap Reusable Installer & Patcher Framework",
        dry_run=args.dry_run,
    )

    if not (BASE_DIR / "PROGRESS.md").exists():
        session.write_file("PROGRESS.md", INITIAL_PROGRESS_MD)
    if not (BASE_DIR / "docs" / "CONTRACTS.md").exists():
        session.write_file("docs/CONTRACTS.md", INITIAL_CONTRACTS_MD)

    session.record_progress(
        completed=[
            "Created reusable installer engine `tools/patcher.py` with PatcherSession, write_file, patch_file, dry-run, and automatic backup support.",
            "Initialized `PROGRESS.md` and `docs/CONTRACTS.md`.",
        ],
        remaining=[
            "Step 0 Script 2 of 2 (`tools/install_step00_02.py`): Add `_backups/` to `.gitignore`, add `LOG_RAW_DATA=True` in `config.py` and `security.py`, and add startup schema synchronization (`schema_sync.py`).",
        ],
        modified_files=["tools/patcher.py", "PROGRESS.md", "docs/CONTRACTS.md"],
    )

    session.record_contracts(
        section_title="Installer & Patcher Framework (`tools/patcher.py`)",
        contract_items=[
            "**Module**: `tools/patcher.py`",
            "**Constants**: `BASE_DIR = Path(r'E:\\HOST_VSCODE\\host-simulator')`, `BACKUP_ROOT`, `PROGRESS_FILE`, `CONTRACTS_FILE`",
            "**Classes/Functions**: `PatcherSession`, `write_file(rel_path, content, dry_run=False)`, `patch_file(rel_path, edits, dry_run=False)`, `parse_installer_args(description)`",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())