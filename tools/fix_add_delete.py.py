#!/usr/bin/env python3
"""tools/fix_final_bugs.py - final bug fixes. Run from project root. Supports --dry-run."""
import datetime, shutil, sys
from pathlib import Path

ROOT = Path(r"E:\HOST_VSCODE\host-simulator")
DRY = "--dry-run" in sys.argv
BACKUP = ROOT / "_backups" / ("final_fix_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
failed = []


def load(rel):
    p = ROOT / rel
    raw = p.read_bytes().decode("utf-8-sig")
    return p, raw.replace("\r\n", "\n"), ("\r\n" if "\r\n" in raw else "\n")


def store(rel, p, text, eol):
    if DRY:
        return
    dest = BACKUP / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, dest)
    p.write_bytes(text.replace("\n", eol).encode("utf-8"))


def fix(rel, old, new, many=False):
    p, text, eol = load(rel)
    if old not in text:
        if new in text:
            print("[SKIP] already applied:", rel)
        else:
            print("[FAIL] anchor not found:", rel, "|", old[:60].replace("\n", " "))
            failed.append(rel)
        return
    if not many and text.count(old) != 1:
        print("[FAIL] anchor not unique:", rel)
        failed.append(rel)
        return
    store(rel, p, text.replace(old, new), eol)
    print(("[DRY] " if DRY else "[OK]  ") + rel)


# ---------------- BACKEND ----------------
S = "backend/app/seed_data.py"
fix(S, "    Account,\n    AccountLimit,\n    Card,\n",
       "    Account,\n    AccountLimit,\n    BinRange,\n    Card,\n")
fix(S, "    HsmKeyReference,\n    NetworkProfile,\n    PinProfile,\n",
       "    HsmKeyReference,\n    Institution,\n    InstitutionProcessingSystem,\n    NetworkProfile,\n    PinProfile,\n    ProcessingSystem,\n")

SC = "backend/app/schemas.py"
fix(SC, '    customer_status: str = "ACTIVE"\n    risk_category: str = "NORMAL"\n\n\n# [PATCH step02_01:schema_customer_out_inst_fixed]',
        '    customer_status: str = "ACTIVE"\n    risk_category: str = "NORMAL"\n    institution_id: Optional[str] = None\n\n\n# [PATCH step02_01:schema_customer_out_inst_fixed]')
fix(SC, '    account_status: str = "ACTIVE"\n    branch_code: str = "0001"\n\n\nclass AccountOut(AccountCreate):',
        '    account_status: str = "ACTIVE"\n    branch_code: str = "0001"\n    institution_id: Optional[str] = None\n\n\nclass AccountOut(AccountCreate):')
fix(SC, '    pvv_or_offset: str = "7821"\n    cvv_value: str = "011"\n\n\nclass CardOut(BaseModel):',
        '    pvv_or_offset: str = "7821"\n    cvv_value: str = "011"\n    institution_id: Optional[str] = None\n\n\nclass CardOut(BaseModel):')
fix(SC, '    card_profile_id: Optional[str]\n    created_at: datetime\n    model_config = ConfigDict(from_attributes=True)\n\n\nclass CardLimitUpdate',
        '    card_profile_id: Optional[str]\n    institution_id: Optional[str] = None\n    institution_code: Optional[str] = None\n    institution_name: Optional[str] = None\n    created_at: datetime\n    model_config = ConfigDict(from_attributes=True)\n\n\nclass CardLimitUpdate')

A = "backend/app/api_routes.py"
fix(A, '            } if lim else None,\n        })\n    return out\n\n\n@router.post("/cards", response_model=CardOut)',
       '            } if lim else None,\n        })\n    total_pages = max(1, (total + page_size - 1) // page_size)\n    return {"items": out, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}\n\n\n@router.post("/cards", response_model=CardOut)')
fix(A, '    db.commit()\n    db.refresh(card)\n    return card\n\n\n@router.patch("/cards/{card_id}/status")',
       '    db.commit()\n    db.refresh(card)\n    card.institution_code = card.institution.institution_code if card.institution else None\n    card.institution_name = card.institution.name if card.institution else None\n    return card\n\n\n@router.patch("/cards/{card_id}/status")')

# remove dead leftover function in api_routes.py
p, text, eol = load(A)
a = text.find("def _unused_old_list_accounts():")
b = text.find('@router.post("/accounts", response_model=AccountOut)')
if a == -1:
    print("[SKIP] dead function already removed")
elif b == -1 or b < a:
    print("[FAIL] could not locate end of dead function"); failed.append(A)
else:
    store(A, p, text[:a] + "\n\n" + text[b:], eol)
    print(("[DRY] " if DRY else "[OK]  ") + A + " (dead function removed)")

fix("backend/app/audit_service.py",
    '        if hasattr(val, "isoformat"):\n            out[col.name] = val.isoformat()\n        elif hasattr(val, "__float__"):',
    '        if isinstance(val, bool):\n            out[col.name] = val\n        elif hasattr(val, "isoformat"):\n            out[col.name] = val.isoformat()\n        elif hasattr(val, "__float__"):')

fix("backend/app/database.py",
    """engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)""",
    """engine_kwargs = {}
if settings.DATABASE_URL.startswith("sqlite") and ":memory:" in settings.DATABASE_URL:
    # in-memory SQLite is per-connection; share one connection across threads (tests)
    from sqlalchemy.pool import StaticPool
    engine_kwargs["poolclass"] = StaticPool

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
    **engine_kwargs,
)""")

# ---------------- TESTS ----------------
for t in ["test_host_engine", "test_step02_institution_links", "test_step04_multi_account",
          "test_step05_search_and_pagination", "test_step07_log_portal",
          "test_step08_authorizer_rules", "test_step12_settlement"]:
    fix("backend/tests/%s.py" % t, '"49": "BDT"', '"49": "050"', many=True)

fix("backend/tests/test_step11_routing.py",
    '''    db_session.add(
        NetworkProfile(
            network_name="VISA_SCHEME",
            network_type="CARD_SCHEME",
            enabled=True,
            simulation_mode="ALWAYS_APPROVE",
            simulated_response_code="00",
        )
    )
''',
    '''    if not db_session.query(NetworkProfile).filter(NetworkProfile.network_name == "VISA_SCHEME").first():
        db_session.add(
            NetworkProfile(
                network_name="VISA_SCHEME",
                network_type="CARD_SCHEME",
                enabled=True,
                simulation_mode="ALWAYS_APPROVE",
                simulated_response_code="00",
            )
        )
''')

# ---------------- FRONTEND ----------------
fix("frontend/src/pages/CardCryptoLabPage.tsx",
    "{pvvResult.3des_cipher_hex}", "{pvvResult['3des_cipher_hex']}")
fix("frontend/src/components/Layout.tsx",
    "  Moon,\n  Sun,\n} from 'lucide-react';",
    "  Moon,\n  Sun,\n  Network,\n  Layers,\n} from 'lucide-react';")

J = "frontend/src/pages/SimulatorAndJournal.tsx"
fix(J, r"""  const [status, setStatus] = useState('');

  const load = async () => {
    const params = new URLSearchParams();
    if (stan) params.set('stan', stan);
    if (rrn) params.set('rrn', rrn);
    if (status) params.set('status', status);
    setTxs(await apiFetch(`/transactions?${params.toString()}`));
  };

  useEffect(() => {
    load();
  }, []);
""", r"""  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalTxs, setTotalTxs] = useState(0);

  const load = async (p: number = page) => {
    const params = new URLSearchParams({ page: String(p), page_size: '25' });
    if (stan) params.set('stan', stan);
    if (rrn) params.set('rrn', rrn);
    if (status) params.set('status', status);
    const res = await apiFetch(`/transactions?${params.toString()}`);
    const items = Array.isArray(res) ? res : (res.items || []);
    setTxs(items);
    setTotalTxs(Array.isArray(res) ? items.length : (res.total ?? items.length));
    setTotalPages(Array.isArray(res) ? 1 : (res.total_pages || 1));
  };

  useEffect(() => {
    load(page);
  }, [page]);
""")
fix(J, '            onClick={load}\n            className="flex items-center gap-1 bg-emerald-600',
       '            onClick={() => { setPage(1); load(1); }}\n            className="flex items-center gap-1 bg-emerald-600')

d = ROOT / "frontend/src/vite-env.d.ts"
if not d.exists() and not DRY:
    d.write_bytes(b'/// <reference types="vite/client" />\r\n')
    print("[OK]  frontend/src/vite-env.d.ts created")

print("\nFAILED: %d" % len(failed))
for f in failed:
    print("   ", f)
sys.exit(1 if failed else 0)