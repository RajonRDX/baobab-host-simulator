#!/usr/bin/env python3
"""
tools/fix_maintenance_nav.py
Directly registers CustomerDataMaintenancePage in frontend/src/App.tsx
and adds the sidebar link in frontend/src/components/Layout.tsx.
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()


def fix_app_tsx():
    path = BASE_DIR / "frontend" / "src" / "App.tsx"
    text = path.read_text(encoding="utf-8")

    # 1. Add Component Import if missing
    if "CustomerDataMaintenancePage" not in text:
        import_stmt = "import { CustomerDataMaintenancePage } from './pages/CustomerDataMaintenancePage';\n"
        text = import_stmt + text

    # 2. Add Route inside Routes
    if 'path="/customer-maintenance"' not in text:
        route_entry = (
            '        <Route\n'
            '          path="/customer-maintenance"\n'
            '          element={\n'
            '            <ProtectedRoute>\n'
            '              <CustomerDataMaintenancePage />\n'
            '            </ProtectedRoute>\n'
            '          }\n'
            '        />\n'
        )
        anchor = '<Route path="/" element={<Navigate to="/dashboard" replace />} />'
        if anchor in text:
            text = text.replace(anchor, route_entry + "        " + anchor, 1)
        else:
            text = text.replace("</Routes>", route_entry + "      </Routes>", 1)

    normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_text(normalized, encoding="utf-8", newline="")
    print("  [FIXED] frontend/src/App.tsx (Route /customer-maintenance registered)")


def fix_layout_tsx():
    path = BASE_DIR / "frontend" / "src" / "components" / "Layout.tsx"
    text = path.read_text(encoding="utf-8")

    # 1. Ensure lucide-react icon is available
    if "UserCheck" not in text:
        text = text.replace("  Users,", "  Users,\n  UserCheck,", 1)

    # 2. Ensure navigation entry exists under CORE BANKING
    if "'/customer-maintenance'" not in text:
        nav_entry = "  { to: '/customer-maintenance', label: '2.5. Customer Maintenance 360', icon: UserCheck, group: 'CORE BANKING' },\n"
        anchor = "  { to: '/customers', label: '2. Customers (CIF)', icon: Users, group: 'CORE BANKING' },"
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + nav_entry, 1)
        else:
            # Fallback insertion before cards
            anchor_card = "  { to: '/cards', label: '3. Cards & Profiles', icon: CreditCard, group: 'CORE BANKING' },"
            if anchor_card in text:
                text = text.replace(anchor_card, nav_entry + anchor_card, 1)

    normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_text(normalized, encoding="utf-8", newline="")
    print("  [FIXED] frontend/src/components/Layout.tsx (Navigation item added under CORE BANKING)")


def main():
    print("=" * 70)
    print("  REGISTERING CUSTOMER DATA MAINTENANCE ROUTE & SIDEBAR LINK")
    print("=" * 70)
    fix_app_tsx()
    fix_layout_tsx()
    print("=" * 70)
    print("  Done.")
    print("=" * 70)


if __name__ == "__main__":
    main()