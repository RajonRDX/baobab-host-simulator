#!/usr/bin/env python3
"""
tools/fix_customers_white_screen.py
====================================
Fixes the blank/white page at /#/customers.

Root cause:
  Inside CustomersPage (BankingEntities.tsx) a dead function leaked from an
  earlier merge/repair:

      const handleUpdateAccount = async (...) => {
        if (!editAcct) return;   // <-- editAcct is NEVER declared
        setEditAcct(null);       // <-- crashes React → white screen
      };

  ReferenceError on first render → entire route fails → white page + back button
  appears broken because the error boundary / router is stuck.

This script removes the dead block and hardens the load() function so the
Customers page works again.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Resolve project root (works whether run from tools/ or project root)
SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[1] if SCRIPT.parent.name == "tools" else SCRIPT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from tools.patcher import PatcherSession, parse_installer_args
except ImportError:
    # Minimal fallback if patcher not on path yet
    class PatcherSession:  # type: ignore
        def __init__(self, step_id, title, dry_run=False):
            self.step_id = step_id
            self.title = title
            self.dry_run = dry_run
            self.failed = False
            self.records = []

        def patch_file(self, rel, edits):
            target = ROOT / rel
            if not target.exists():
                print(f"  [ERROR] Missing {rel}")
                self.failed = True
                return False
            text = target.read_text(encoding="utf-8")
            original = text
            for ed in edits:
                marker = f"// [PATCH {ed['marker']}]"
                if marker in text or f"[PATCH {ed['marker']}]" in text:
                    print(f"  [IDEMPOTENT] {rel} already has {ed['marker']}")
                    continue
                anchor = ed.get("anchor", "")
                new = ed.get("text", "")
                action = ed.get("action", "replace")
                if action == "replace" and anchor and anchor in text:
                    text = text.replace(anchor, f"{marker}\n{new}", 1)
                    print(f"  [PATCHED] {rel} — {ed['marker']}")
                elif action == "replace" and anchor:
                    print(f"  [WARN] Anchor not found for {ed['marker']}")
                    # Try regex flexible whitespace
                    pat = re.escape(anchor)
                    pat = pat.replace(r"\ ", r"\s+").replace(r"\n", r"\s*\n\s*")
                    m = re.search(pat, text)
                    if m:
                        text = text[: m.start()] + f"{marker}\n{new}" + text[m.end() :]
                        print(f"  [PATCHED-FLEX] {rel} — {ed['marker']}")
                    else:
                        self.failed = True
                else:
                    self.failed = True
            if text != original and not self.dry_run:
                target.write_text(text, encoding="utf-8", newline="\n")
            return not self.failed

        def write_file(self, rel, content):
            target = ROOT / rel
            if not self.dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
            print(f"  [WRITE] {rel}")
            return True

        def record_progress(self, **kwargs):
            pass

        def record_contracts(self, **kwargs):
            pass

        def finish(self):
            print("=" * 60)
            print("  SUCCESS" if not self.failed else "  FAILED")
            print("=" * 60)
            return 0 if not self.failed else 1

    def parse_installer_args(desc):
        import argparse
        p = argparse.ArgumentParser(description=desc)
        p.add_argument("--dry-run", action="store_true")
        return p.parse_args()


DEAD_HANDLE_UPDATE_ACCOUNT = """  const handleUpdateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editAcct) return;
    await apiFetch(`/accounts/${editAcct.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        account_type: editAcct.account_type,
        available_balance: editAcct.available_balance,
        ledger_balance: editAcct.ledger_balance,
        overdraft_limit: editAcct.overdraft_limit,
        account_status: editAcct.account_status,
      }),
    });
    setEditAcct(null);
    load();
  };

"""

# Clean replacement: just delete the dead function (leave a short comment)
CLEAN_REPLACEMENT = """  // [removed dead handleUpdateAccount that referenced undeclared editAcct — caused white screen]

"""

ROBUST_LOAD = """  const load = async () => {
    try {
      setErrorBanner('');
      const q = searchTerm ? `&q=${encodeURIComponent(searchTerm)}` : '';
      const [cRes, iList] = await Promise.all([
        apiFetch(`/customers?page=${page}&page_size=15${q}`),
        apiFetch('/institutions').catch(() => []),
      ]);
      const items = Array.isArray(cRes) ? cRes : (cRes?.items || []);
      setCustomers(items);
      setTotalCount(cRes?.total ?? items.length);
      setTotalPages(cRes?.total_pages || 1);
      const inst = Array.isArray(iList) ? iList : [];
      setInstitutions(inst);
      if (!form.institution_id && inst.length > 0) {
        setForm((prev) => ({ ...prev, institution_id: inst[0].id }));
      }
    } catch (err: any) {
      console.error(err);
      setErrorBanner(err?.message || 'Failed to load customers');
      setCustomers([]);
    }
  };
"""

OLD_LOAD = """  const load = async () => {
    try {
      const q = searchTerm ? `&q=${encodeURIComponent(searchTerm)}` : '';
      const [cRes, iList] = await Promise.all([
        apiFetch(`/customers?page=${page}&page_size=15${q}`),
        apiFetch('/institutions'),
      ]);
      setCustomers(cRes.items || cRes);
      setTotalCount(cRes.total || (cRes.items ? cRes.items.length : cRes.length));
      setTotalPages(cRes.total_pages || 1);
      setInstitutions(iList);
      if (!form.institution_id && iList.length > 0) {
        setForm((prev) => ({ ...prev, institution_id: iList[0].id }));
      }
    } catch (err: any) {
      console.error(err);
    }
  };
"""


def main() -> int:
    args = parse_installer_args("Fix white screen on /#/customers (undeclared editAcct)")
    session = PatcherSession(
        step_id="fix_customers_white_screen",
        title="Remove dead handleUpdateAccount (editAcct ReferenceError) + harden CustomersPage load",
        dry_run=args.dry_run,
    )

    rel = "frontend/src/pages/BankingEntities.tsx"
    target = ROOT / rel

    if not target.exists():
        print(f"[ERROR] File not found: {target}")
        print("Run this script from your host-simulator project root.")
        return 1

    text = target.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # 1. Remove the crashing handleUpdateAccount block
    # ------------------------------------------------------------------
    if "if (!editAcct) return" in text and "handleUpdateAccount" in text:
        # Flexible removal (handles slight whitespace differences)
        pattern = re.compile(
            r"  const handleUpdateAccount = async \(e: React\.FormEvent\) => \{\s*"
            r"e\.preventDefault\(\);\s*"
            r"if \(!editAcct\) return;\s*"
            r"await apiFetch\(`/accounts/\$\{editAcct\.id\}`, \{[\s\S]*?"
            r"setEditAcct\(null\);\s*"
            r"load\(\);\s*"
            r"\};\s*",
            re.MULTILINE,
        )
        new_text, n = pattern.subn(
            "  // [PATCH fix_customers_white_screen:removed_dead_handleUpdateAccount]\n"
            "  // Removed dead handleUpdateAccount that referenced undeclared editAcct (caused white screen).\n\n",
            text,
            count=1,
        )
        if n == 0:
            # Fallback: exact string replace
            if DEAD_HANDLE_UPDATE_ACCOUNT in text:
                new_text = text.replace(
                    DEAD_HANDLE_UPDATE_ACCOUNT,
                    "  // [PATCH fix_customers_white_screen:removed_dead_handleUpdateAccount]\n"
                    + CLEAN_REPLACEMENT,
                    1,
                )
                n = 1
            else:
                print("  [WARN] Could not match handleUpdateAccount with regex — trying line-based strip")
                lines = text.splitlines(keepends=True)
                out = []
                skip = False
                depth = 0
                for line in lines:
                    if (not skip) and "const handleUpdateAccount" in line and "editAcct" not in "".join(out[-5:]):
                        skip = True
                        depth = line.count("{") - line.count("}")
                        out.append(
                            "  // [PATCH fix_customers_white_screen:removed_dead_handleUpdateAccount]\n"
                        )
                        out.append(
                            "  // Removed dead handleUpdateAccount (undeclared editAcct → white screen).\n"
                        )
                        continue
                    if skip:
                        depth += line.count("{") - line.count("}")
                        if depth <= 0:
                            skip = False
                        continue
                    out.append(line)
                new_text = "".join(out)
                n = 1 if new_text != text else 0

        if n:
            text = new_text
            print("  [FIXED] Removed dead handleUpdateAccount (editAcct ReferenceError)")
        else:
            print("  [ERROR] Failed to locate handleUpdateAccount block")
            session.failed = True
    else:
        print("  [OK] No crashing handleUpdateAccount / editAcct found (already fixed?)")

    # ------------------------------------------------------------------
    # 2. Harden load() so institutions failure does not blank the page
    # ------------------------------------------------------------------
    if OLD_LOAD in text:
        text = text.replace(
            OLD_LOAD,
            "  // [PATCH fix_customers_white_screen:robust_load]\n" + ROBUST_LOAD,
            1,
        )
        print("  [FIXED] Hardened CustomersPage load()")
    elif "apiFetch('/institutions').catch" in text or "setErrorBanner(err" in text:
        print("  [OK] load() already robust")
    else:
        # Flexible load replace
        load_pat = re.compile(
            r"  const load = async \(\) => \{\s*"
            r"try \{\s*"
            r"const q = searchTerm \? `&q=\$\{encodeURIComponent\(searchTerm\)\}` : '';\s*"
            r"const \[cRes, iList\] = await Promise\.all\(\[\s*"
            r"apiFetch\(`/customers\?page=\$\{page\}&page_size=15\$\{q\}`\),\s*"
            r"apiFetch\('/institutions'\),\s*"
            r"\]\);\s*"
            r"setCustomers\(cRes\.items \|\| cRes\);\s*"
            r"setTotalCount\(cRes\.total \|\| \(cRes\.items \? cRes\.items\.length : cRes\.length\)\);\s*"
            r"setTotalPages\(cRes\.total_pages \|\| 1\);\s*"
            r"setInstitutions\(iList\);\s*"
            r"if \(!form\.institution_id && iList\.length > 0\) \{\s*"
            r"setForm\(\(prev\) => \(\{ \.\.\.prev, institution_id: iList\[0\]\.id \}\)\);\s*"
            r"\}\s*"
            r"\} catch \(err: any\) \{\s*"
            r"console\.error\(err\);\s*"
            r"\}\s*"
            r"\};",
            re.MULTILINE,
        )
        text2, n2 = load_pat.subn(
            "  // [PATCH fix_customers_white_screen:robust_load]\n" + ROBUST_LOAD,
            text,
            count=1,
        )
        if n2:
            text = text2
            print("  [FIXED] Hardened CustomersPage load() (regex)")
        else:
            print("  [WARN] Could not patch load() — page should still work after removing editAcct")

    # ------------------------------------------------------------------
    # 3. Safety: ensure no remaining bare editAcct references inside CustomersPage
    # ------------------------------------------------------------------
    # Only check between CustomersPage and CardsPage
    c_start = text.find("export const CustomersPage")
    c_end = text.find("export const CardsPage")
    if c_start >= 0 and c_end > c_start:
        segment = text[c_start:c_end]
        if re.search(r"\beditAcct\b", segment):
            print("  [WARN] Still found 'editAcct' inside CustomersPage — manual check recommended")
            for i, line in enumerate(segment.splitlines()):
                if "editAcct" in line and "removed" not in line.lower():
                    print(f"    line-ish: {line.strip()[:100]}")
        else:
            print("  [OK] No remaining editAcct references in CustomersPage")

    if not args.dry_run and not session.failed:
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"  [WRITE] {rel}")
    elif args.dry_run:
        print("  [DRY-RUN] No files written")

    session.record_progress(
        completed=[
            "Removed dead handleUpdateAccount that referenced undeclared editAcct (root cause of white screen on /#/customers).",
            "Hardened CustomersPage load() against institutions API failure and non-array responses.",
        ],
        remaining=[],
        modified_files=[rel],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())
