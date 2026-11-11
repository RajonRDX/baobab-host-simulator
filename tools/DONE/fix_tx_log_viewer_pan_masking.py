#!/usr/bin/env python3
"""
fix_tx_log_viewer_pan_masking.py
Enforces strict default PAN masking (first 6 + '*' + last 4) in Transaction Log Viewer
even when settings.LOG_RAW_DATA=True, and makes the pytest suite repeatable across runs.
"""

import subprocess
import sys
from pathlib import Path


def detect_root() -> Path:
    root = Path(__file__).resolve().parent
    if not (root / "backend").exists() and (root.parent / "backend").exists():
        root = root.parent
    return root


STRICT_MASK_HELPER = '''
def strict_mask_pan(pan: Optional[str]) -> str:
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


def patch_tic_decoder_engine(root: Path) -> None:
    path = root / "backend" / "app" / "tic_decoder_engine.py"
    text = path.read_text(encoding="utf-8")

    if "def strict_mask_pan" not in text:
        text = text.replace(
            "from app.security import mask_pan\n",
            "from app.security import mask_pan\n" + STRICT_MASK_HELPER + "\n",
            1,
        )
    # Replace mask_pan(...) calls inside tic_decoder_engine with strict_mask_pan(...)
    text = text.replace("mask_pan(", "strict_mask_pan(")
    path.write_text(text, encoding="utf-8", newline="\n")
    print("  [M] Enforced strict_mask_pan in backend/app/tic_decoder_engine.py")


def patch_transaction_logs_router(root: Path) -> None:
    path = root / "backend" / "app" / "routers" / "transaction_logs_router.py"
    text = path.read_text(encoding="utf-8")

    if "strict_mask_pan" not in text:
        text = text.replace(
            "from app.tic_decoder_engine import (\n",
            "from app.tic_decoder_engine import (\n    strict_mask_pan,\n",
            1,
        )

    # Mask PAN in list row serialization
    text = text.replace(
        '"masked_pan": tx.masked_pan or "****",',
        '"masked_pan": strict_mask_pan(tx.masked_pan),',
    )

    # Mask PAN by default in General tab unless reveal_pan=True
    old_gen_pan = '    pan_display = (card.test_pan_reference if (allow_full and card) else tx.masked_pan) or "****"'
    new_gen_pan = (
        '    raw_pan_val = (card.test_pan_reference if card else tx.masked_pan) or ""\n'
        '    pan_display = raw_pan_val if allow_full else strict_mask_pan(raw_pan_val)'
    )
    if old_gen_pan in text:
        text = text.replace(old_gen_pan, new_gen_pan)

    text = text.replace(
        '"masked_pan": tx.masked_pan,',
        '"masked_pan": strict_mask_pan(raw_pan_val),',
    )

    # Mask PAN in switch trace header
    text = text.replace(
        'f"Masked PAN     : {tx.masked_pan}",',
        'f"Masked PAN     : {strict_mask_pan(tx.masked_pan)}",',
    )

    path.write_text(text, encoding="utf-8", newline="\n")
    print("  [M] Enforced default PAN masking in backend/app/routers/transaction_logs_router.py")


def patch_pytest_file(root: Path) -> None:
    path = root / "backend" / "tests" / "test_transaction_log_viewer.py"
    text = path.read_text(encoding="utf-8")

    # Use dynamic STAN & RRN so repeated pytest executions never collide with RC 94 Duplicate
    if "import uuid" not in text:
        text = "import uuid\n" + text

    old_block = '''    # 1. Submit an Approved transaction & a Declined transaction + a Reversal
    r1 = client.post(
        "/api/simulator/submit",
        headers=headers,
        json={
            "transaction_code": "10",
            "mti": "0200",
            "test_clear_pin_helper": "1234",
            "fields": {
                "2": "4567890123450001",
                "3": "0100000",
                "4": "000000150000",
                "7": "1101120000",
                "11": "880101",
                "12": "120000",
                "13": "1101",
                "14": "2812",
                "18": "6011",
                "22": "051",
                "25": "000",
                "32": "123456",
                "37": "000088010101",
                "41": "ATM00001",
                "49": "BDT",
            },
        },
    )'''

    new_block = '''    # 1. Submit an Approved transaction with unique STAN/RRN
    unique_num = str(uuid.uuid4().int)[:6]
    stan_val = unique_num
    rrn_val = f"000088{unique_num}"
    r1 = client.post(
        "/api/simulator/submit",
        headers=headers,
        json={
            "transaction_code": "10",
            "mti": "0200",
            "test_clear_pin_helper": "1234",
            "fields": {
                "2": "4567890123450001",
                "3": "0100000",
                "4": "000000010000",
                "7": "1101120000",
                "11": stan_val,
                "12": "120000",
                "13": "1101",
                "14": "2812",
                "18": "6011",
                "22": "051",
                "25": "000",
                "32": "123456",
                "37": rrn_val,
                "41": "ATM00001",
                "49": "BDT",
            },
        },
    )'''

    if old_block in text:
        text = text.replace(old_block, new_block)
        text = text.replace(
            'client.get("/api/transaction-logs?rrn=000088010101&stan=880101", headers=headers)',
            'client.get(f"/api/transaction-logs?rrn={rrn_val}&stan={stan_val}", headers=headers)',
        )
        text = text.replace(
            'assert gen["network_reference_info"]["rrn"] == "000088010101"',
            'assert gen["network_reference_info"]["rrn"] == rrn_val\n'
            '    # Also verify explicit simulator reveal_pan=true works\n'
            '    gen_rev = client.get(f"/api/transaction-logs/{tx1_id}?reveal_pan=true", headers=headers).json()\n'
            '    assert gen_rev["card_info"]["pan"] == "4567890123450001"',
        )
        text = text.replace('"37": "000088010101",', '"37": rrn_val,')
        text = text.replace('"4": "000000150000",', '"4": "000000010000",')

    path.write_text(text, encoding="utf-8", newline="\n")
    print("  [M] Updated backend/tests/test_transaction_log_viewer.py with repeatable STAN/RRN & reveal_pan test")


def main():
    root = detect_root()
    print(f"=== Applying PAN Masking & Test Repeatability Fix in {root} ===")
    patch_tic_decoder_engine(root)
    patch_transaction_logs_router(root)
    patch_pytest_file(root)

    res = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/test_transaction_log_viewer.py", "-v"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr)
        sys.exit(res.returncode)


if __name__ == "__main__":
    main()