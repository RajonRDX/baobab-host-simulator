import uuid
"""
test_transaction_log_viewer.py — Automated Pytest Verification for Transaction Log Viewer
"""

from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)


def _auth_headers():
    resp = client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_transaction_log_viewer_end_to_end():
    headers = _auth_headers()

    # 1. Submit an Approved transaction with unique STAN/RRN
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
    )
    assert r1.status_code == 200
    tx1_id = r1.json()["transaction_id"]

    # 2. Automatic initial list loading & summary verification
    list_resp = client.get("/api/transaction-logs?page=1&page_size=25", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert "summary" in list_data
    assert list_data["summary"]["total_transactions"] >= 1
    assert list_data["items"][0]["id"] == tx1_id

    # 3. Filtering by RRN & STAN
    filt_resp = client.get(f"/api/transaction-logs?rrn={rrn_val}&stan={stan_val}", headers=headers)
    assert filt_resp.status_code == 200
    assert filt_resp.json()["total"] >= 1

    # 4. General Detail Tab (PAN masked by default)
    gen_resp = client.get(f"/api/transaction-logs/{tx1_id}", headers=headers)
    assert gen_resp.status_code == 200
    gen = gen_resp.json()
    assert "*" in gen["card_info"]["pan"]
    assert gen["network_reference_info"]["rrn"] == rrn_val
    # Also verify explicit simulator reveal_pan=true works
    gen_rev = client.get(f"/api/transaction-logs/{tx1_id}?reveal_pan=true", headers=headers).json()
    assert gen_rev["card_info"]["pan"] == "4567890123450001"

    # 5. Authorizer Response Tab
    auth_resp = client.get(f"/api/transaction-logs/{tx1_id}/authorization", headers=headers)
    assert auth_resp.status_code == 200
    assert auth_resp.json()["response_code"] == "00"
    assert len(auth_resp.json()["checks"]) >= 5

    # 6. ISO Details Tab with tic_decoder.py integration & Request/Response comparison
    iso_resp = client.get(f"/api/transaction-logs/{tx1_id}/messages", headers=headers)
    assert iso_resp.status_code == 200
    iso_data = iso_resp.json()
    assert len(iso_data["messages"]) == 2
    req_decoded = iso_data["messages"][0]["decoded"]
    assert req_decoded["valid"] is True
    fnums = [f["field_number"] for f in req_decoded["parsed_fields"]]
    assert fnums == sorted(fnums)
    assert 1 not in fnums
    # Verify PIN block F52 is strictly masked
    f52_entry = next((f for f in req_decoded["parsed_fields"] if f["field_number"] == 52), None)
    if f52_entry:
        assert "MASKED" in f52_entry["display_value"]
    assert len(iso_data["comparison"]) >= 5

    # 7. Keys & Crypto Tab (no clear keys or PIN blocks exposed)
    crypto_resp = client.get(f"/api/transaction-logs/{tx1_id}/crypto", headers=headers)
    assert crypto_resp.status_code == 200
    crypto_data = crypto_resp.json()
    assert crypto_data["operations_count"] >= 1
    raw_crypto_str = str(crypto_data)
    assert "5566778899AABBCC5566778899AABBCC" not in raw_crypto_str

    # 8. Processing Trace Tab (Generate/Load without re-executing transaction)
    bal_before_trace = client.get(f"/api/transaction-logs/{tx1_id}/authorization", headers=headers).json()["balance_snapshot"]["balance_after"]
    trace_resp = client.post(f"/api/transaction-logs/{tx1_id}/trace/generate", headers=headers)
    assert trace_resp.status_code == 200
    trace_data = trace_resp.json()
    assert "TRANSACTION PROCESSING TRACE" in trace_data["formatted_trace"]
    assert len(trace_data["events"]) >= 5
    bal_after_trace = client.get(f"/api/transaction-logs/{tx1_id}/authorization", headers=headers).json()["balance_snapshot"]["balance_after"]
    assert bal_before_trace == bal_after_trace

    # 9. Reversal & Related Transactions Tab
    rev_submit = client.post(
        "/api/simulator/submit",
        headers=headers,
        json={
            "transaction_code": "10",
            "mti": "0400",
            "fields": {
                "2": "4567890123450001",
                "3": "0100000",
                "4": "000000010000",
                "7": "1101120500",
                "11": "880102",
                "37": rrn_val,
                "41": "ATM00001",
                "49": "BDT",
            },
        },
    )
    assert rev_submit.status_code == 200
    rel_resp = client.get(f"/api/transaction-logs/{tx1_id}/related", headers=headers)
    assert rel_resp.status_code == 200
    assert rel_resp.json()["related_count"] >= 1


def test_column_preferences_and_exports():
    headers = _auth_headers()
    # Column preference GET & PUT
    g_resp = client.get("/api/transaction-logs/preferences/columns", headers=headers)
    assert g_resp.status_code == 200
    assert "columns" in g_resp.json()

    custom_cols = ["transaction_reference", "date", "time", "mti", "masked_pan", "amount", "rrn", "stan", "status"]
    p_resp = client.put(
        "/api/transaction-logs/preferences/columns",
        headers=headers,
        json={"columns": custom_cols},
    )
    assert p_resp.status_code == 200
    assert p_resp.json()["columns"] == custom_cols

    # CSV export
    csv_resp = client.get("/api/transaction-logs/export", headers=headers)
    assert csv_resp.status_code == 200
    assert "Txn Reference" in csv_resp.text
