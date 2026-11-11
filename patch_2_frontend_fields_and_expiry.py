"""
patch_2_frontend_fields_and_expiry.py
Run in the project folder:   python patch_2_frontend_fields_and_expiry.py
Customers page: father, mother, DOB, NID, passport, address ... (create + edit).
Cards & Profiles page and PIN & Card Lab: a real Expiry (MM / YYYY) input instead of the fixed 12/2028.
Idempotent. Backups go to _backups/.
"""

PATCH_NAME = "patch2_frontend"

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- locate the project
def find_root():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        return Path(sys.argv[1])
    cwd = Path.cwd()
    if (cwd / "backend" / "app").exists():
        return cwd
    here = Path(__file__).resolve().parent
    if (here / "backend" / "app").exists():
        return here
    return Path(r"E:\HOST_VSCODE\host-simulator-github-prod")


ROOT = find_root()
BACKUP = ROOT / "_backups" / f"{PATCH_NAME}_{datetime.now():%Y%m%d_%H%M%S}"
problems = []


def load(path):
    raw = path.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), ("\r\n" in raw)


def save(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def backup(path):
    if not path.exists():
        return
    dest = BACKUP / path.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def check_syntax(path, text):
    if path.suffix == ".py":
        try:
            compile(text, str(path), "exec")
        except SyntaxError as exc:
            return f"syntax error: {exc}"
    return None


def edit(rel, label, marker, old, new, count=1):
    """Replace `old` by `new` in file `rel` (exactly `count` occurrences). Idempotent via `marker`."""
    path = ROOT / rel
    if not path.exists():
        print(f"[NOT FOUND] {rel} (file missing)  - {label}")
        problems.append(label)
        return
    text, crlf = load(path)
    if (marker and marker in text) or (old not in text and new in text):
        print(f"[ALREADY DONE] {label}")
        return
    found = text.count(old)
    if found != count:
        print(f"[NOT FOUND] {label}  ({rel}: expected {count} match, found {found})")
        problems.append(label)
        return
    new_text = text.replace(old, new)
    err = check_syntax(path, new_text)
    if err:
        print(f"[FAILED] {label}: {err}; file NOT changed")
        problems.append(label)
        return
    backup(path)
    save(path, new_text, crlf)
    print(f"[APPLIED] {label}")


def write_new(rel, label, marker, content):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing, _ = load(path)
        if marker in existing:
            if existing.strip() == content.strip():
                print(f"[ALREADY DONE] {label}")
                return
        backup(path)
    err = check_syntax(path, content)
    if err:
        print(f"[FAILED] {label}: {err}")
        problems.append(label)
        return
    path.write_bytes(content.encode("utf-8"))
    print(f"[APPLIED] {label}")


def banner(title):
    print("=" * 72)
    print(f" {title}")
    print(f" Project folder: {ROOT}")
    print("=" * 72)
    if not (ROOT / "backend" / "app").exists():
        print("[STOP] backend/app not found here. Run from the project folder or pass the folder as argument.")
        sys.exit(2)


def finish(next_steps):
    print("=" * 72)
    if problems:
        print(f" FINISHED WITH {len(problems)} PROBLEM(S): " + "; ".join(problems))
        print(" Nothing else was touched for the failed edits. Send me this output if you need help.")
        sys.exit(1)
    print(f" Done. Backups: {BACKUP}")
    for s in next_steps:
        print(" " + s)
    print("=" * 72)


banner("PATCH 2/3  Frontend: more customer fields + free card expiry date")

BE = "frontend/src/pages/BankingEntities.tsx"
LAB = "frontend/src/pages/CardCryptoLabPage.tsx"

# ================================================================ Customers page
edit(BE, "Customers: shared field list + payload helper", "// [PATCH customer_360:fields]",
'''import { apiFetch } from '../api';
''',
'''import { apiFetch } from '../api';

// [PATCH customer_360:fields]
// Extra customer identity fields: [key, label, input type]
const CUSTOMER_EXTRA_INPUTS: [string, string, string][] = [
  ['father_name', "Father's name", 'text'],
  ['mother_name', "Mother's name", 'text'],
  ['spouse_name', 'Spouse name', 'text'],
  ['date_of_birth', 'Date of birth', 'date'],
  ['gender', 'Gender (MALE/FEMALE/OTHER)', 'text'],
  ['marital_status', 'Marital status', 'text'],
  ['nationality', 'Nationality', 'text'],
  ['place_of_birth', 'Place of birth', 'text'],
  ['nid_number', 'NID number', 'text'],
  ['passport_number', 'Passport number', 'text'],
  ['passport_expiry_date', 'Passport expiry', 'date'],
  ['driving_license_number', 'Driving licence no.', 'text'],
  ['tin_number', 'TIN', 'text'],
  ['occupation', 'Occupation', 'text'],
  ['employer_name', 'Employer', 'text'],
  ['alternate_mobile', 'Alternate mobile', 'text'],
  ['address', 'Present address', 'text'],
  ['permanent_address', 'Permanent address', 'text'],
  ['city', 'City', 'text'],
  ['postal_code', 'Postal code', 'text'],
  ['country', 'Country', 'text'],
  ['kyc_status', 'KYC status (PENDING/VERIFIED)', 'text'],
];
const CUSTOMER_DATE_KEYS = ['date_of_birth', 'passport_expiry_date'];
// Create: drop empty values so optional fields stay empty
const cleanCustomerCreate = (f: Record<string, any>) => {
  const out: Record<string, any> = {};
  Object.keys(f).forEach((k) => {
    const v = f[k];
    if (v === '' || v === null || v === undefined) return;
    out[k] = v;
  });
  return out;
};
''')

edit(BE, "Customers: create form state has the new fields", "father_name: '',\n    mother_name: '',",
'''    risk_category: 'NORMAL',
    institution_id: '',
  });

  const load = async () => {
    try {
      setErrorBanner('');
      const q = searchTerm''',
'''    risk_category: 'NORMAL',
    institution_id: '',
    father_name: '',
    mother_name: '',
    spouse_name: '',
    date_of_birth: '',
    gender: '',
    marital_status: '',
    nationality: '',
    place_of_birth: '',
    nid_number: '',
    passport_number: '',
    passport_expiry_date: '',
    driving_license_number: '',
    tin_number: '',
    occupation: '',
    employer_name: '',
    alternate_mobile: '',
    permanent_address: '',
    city: '',
    postal_code: '',
    country: '',
    kyc_status: '',
  });

  const load = async () => {
    try {
      setErrorBanner('');
      const q = searchTerm''')

edit(BE, "Customers: create sends the cleaned payload and clears the new fields", "body: JSON.stringify(cleanCustomerCreate(form))",
'''      await apiFetch('/customers', { method: 'POST', body: JSON.stringify(form) });
      setForm({
        ...form,
        customer_number: `CUST-${Math.floor(1006 + Math.random() * 9000)}`,
        first_name: '',
        last_name: '',
      });''',
'''      await apiFetch('/customers', { method: 'POST', body: JSON.stringify(cleanCustomerCreate(form)) });
      setForm({
        ...form,
        customer_number: `CUST-${Math.floor(1006 + Math.random() * 9000)}`,
        first_name: '',
        last_name: '',
        father_name: '',
        mother_name: '',
        spouse_name: '',
        date_of_birth: '',
        nid_number: '',
        passport_number: '',
        passport_expiry_date: '',
        driving_license_number: '',
        tin_number: '',
      });''')

edit(BE, "Customers: edit saves the new fields", "...Object.fromEntries(CUSTOMER_EXTRA_INPUTS",
'''          customer_status: editCust.customer_status,
        }),
      });
      setEditCust(null);''',
'''          customer_status: editCust.customer_status,
          ...Object.fromEntries(
            CUSTOMER_EXTRA_INPUTS.map(([k]) => {
              const v = editCust[k];
              return [k, v === '' || v === undefined ? null : v];
            })
          ),
        }),
      });
      setEditCust(null);''')

edit(BE, "Customers: edit window is wider and scrolls", "max-w-2xl w-full space-y-4 shadow-2xl max-h-[90vh] overflow-y-auto",
'''            onSubmit={handleUpdateCustomer}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl"''',
'''            onSubmit={handleUpdateCustomer}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-2xl w-full space-y-4 shadow-2xl max-h-[90vh] overflow-y-auto"''')

edit(BE, "Customers: edit window shows the new fields", "{/* [PATCH customer_360:edit_extra] */}",
'''                  <option value="HIGH">HIGH</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditCust(null)} className="px-3 py-1.5 rounded text-xs">''',
'''                  <option value="HIGH">HIGH</option>
                </select>
              </div>
            </div>
            {/* [PATCH customer_360:edit_extra] */}
            <div className="text-[11px] font-bold uppercase tracking-wider text-emerald-500 pt-1">More details</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
              {CUSTOMER_EXTRA_INPUTS.map(([key, label, type]) => (
                <div key={key}>
                  <label className="block text-slate-400 mb-1">{label}</label>
                  <input
                    type={type}
                    value={editCust[key] || ''}
                    onChange={(e) => setEditCust({ ...editCust, [key]: e.target.value })}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditCust(null)} className="px-3 py-1.5 rounded text-xs">''')

edit(BE, "Customers: create form has a 'More details' section", "{/* [PATCH customer_360:create_extra] */}",
'''          + Create Customer
        </button>
      </form>''',
'''          + Create Customer
        </button>
        {/* [PATCH customer_360:create_extra] */}
        <details className="md:col-span-7 group">
          <summary className="cursor-pointer text-xs font-semibold text-emerald-500 select-none">
            More details (father, mother, date of birth, NID, passport, address ...)
          </summary>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 mt-3">
            {CUSTOMER_EXTRA_INPUTS.map(([key, label, type]) => (
              <div key={key}>
                <label className="block text-[11px] text-slate-400 font-mono mb-1">{label}</label>
                <input
                  type={type}
                  value={(form as any)[key] || ''}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs"
                />
              </div>
            ))}
          </div>
        </details>
      </form>''')

# ================================================================ Cards & Profiles page: expiry
edit(BE, "Cards: default expiry is no longer fixed to 12/2028", "expiry_year: new Date().getFullYear() + 3,",
'''    expiry_month: 12,
    expiry_year: 2028,
''',
'''    expiry_month: new Date().getMonth() + 1,
    expiry_year: new Date().getFullYear() + 3,
''')

edit(BE, "Cards: issue form has an Expiry (MM / YYYY) input", "{/* [PATCH customer_360:card_expiry] */}",
'''      <form onSubmit={handleIssue} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-7 gap-3">''',
'''      <form onSubmit={handleIssue} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-8 gap-3">''')

edit(BE, "Cards: expiry month / year fields", "Expiry (MM / YYYY)",
'''        <div>
          <label className="block text-[11px] text-slate-400 font-mono mb-1">PIN (Auto-Derives PVV)</label>''',
'''        {/* [PATCH customer_360:card_expiry] */}
        <div>
          <label className="block text-[11px] text-slate-400 font-mono mb-1">Expiry (MM / YYYY)</label>
          <div className="flex gap-1.5">
            <select
              value={form.expiry_month}
              onChange={(e) => setForm({ ...form, expiry_month: Number(e.target.value) })}
              className="w-16 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-1.5 py-2 text-xs font-mono"
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <option key={m} value={m}>{String(m).padStart(2, '0')}</option>
              ))}
            </select>
            <input
              type="number"
              min={2000}
              max={2099}
              value={form.expiry_year}
              onChange={(e) => setForm({ ...form, expiry_year: e.target.value as any })}
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-2.5 py-2 text-xs font-mono"
              required
            />
          </div>
        </div>
        <div>
          <label className="block text-[11px] text-slate-400 font-mono mb-1">PIN (Auto-Derives PVV)</label>''')

# ================================================================ PIN & Card Lab: expiry for generated cards
edit(LAB, "Card Lab: expiry state", "const [expMonth, setExpMonth]",
     "  const [initialPin, setInitialPin] = useState('1234');\n",
     "  const [initialPin, setInitialPin] = useState('1234');\n"
     "  const [expMonth, setExpMonth] = useState<number>(new Date().getMonth() + 1);\n"
     "  const [expYear, setExpYear] = useState<string>(String(new Date().getFullYear() + 3));\n")

edit(LAB, "Card Lab: send the expiry", "expiry_month: expMonth,",
'''          initial_pin: initialPin,
        }),''',
'''          initial_pin: initialPin,
          expiry_month: expMonth,
          expiry_year: Number(expYear) || undefined,
        }),''')

edit(LAB, "Card Lab: expiry inputs", "Expiry (MM / YYYY)",
'''                    maxLength={4}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                  />
                </div>
              </div>''',
'''                    maxLength={4}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-slate-400 mb-1">Expiry (MM / YYYY)</label>
                  <div className="flex gap-2">
                    <select
                      value={expMonth}
                      onChange={(e) => setExpMonth(Number(e.target.value))}
                      className="w-24 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                    >
                      {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                        <option key={m} value={m}>{String(m).padStart(2, '0')}</option>
                      ))}
                    </select>
                    <input
                      type="number"
                      min={2000}
                      max={2099}
                      value={expYear}
                      onChange={(e) => setExpYear(e.target.value)}
                      className="flex-1 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                    />
                  </div>
                </div>
              </div>''')

finish([
    "Next: run PATCH 3/3 (new Customer Maintenance 360 page), then rebuild/restart the frontend.",
])
