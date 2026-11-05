"""
test_lmk_centric_key_management.py — Automated Verification for LMK-Centric Key Management
"""

from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models import HsmKeyReference

client = TestClient(app)


def _auth_headers() -> dict:
    resp = client.post("/api/auth/login", json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _mock_soft_hsm_execute(raw_command: str, header_length: int = 4, synthetic_mode: bool = False, source_host: str = "TEST"):
    assert synthetic_mode is False, "External key management must never request synthetic_mode=True (clear keys)"
    cmd = raw_command[header_length:header_length + 2].upper()
    body = raw_command[header_length + 2:]

    if cmd == "NC":
        return {
            "status_code": "00",
            "raw_request": raw_command,
            "raw_response": "0000ND00D3B82A00000000001347-0900",
            "parsed_response": [
                {"tag": "LMK Check Value", "value": "D3B82A0000000000"},
                {"tag": "Firmware Version", "value": "1347-0900"},
            ],
        }
    if cmd == "A0":
        mode = body[0]
        scheme = body[4]
        lmk_tok = f"{scheme}A1B2C3D4E5F60718293A4B5C6D7E8F90" if scheme != "S" else "S1006472TN0000A1B2C3D4E5F60718293A4B5C6D7E8F9012345678"
        kcv = "8F4E2A"
        zmk_tok = "U99887766554433221100FFEEDDCCBBAA" if mode == "1" else ""
        parsed = [{"tag": "Key under LMK", "value": lmk_tok}]
        if zmk_tok:
            parsed.append({"tag": "Key under ZMK/TMK", "value": zmk_tok})
        return {
            "status_code": "00",
            "raw_request": raw_command,
            "raw_response": f"0000A100{lmk_tok}{zmk_tok}{kcv}",
            "parsed_response": parsed,
        }
    if cmd == "A8":
        return {
            "status_code": "00",
            "raw_request": raw_command,
            "raw_response": "0000A900U99887766554433221100FFEEDDCCBBAA8F4E2A",
            "parsed_response": [{"tag": "Key under ZMK", "value": "U99887766554433221100FFEEDDCCBBAA"}],
        }
    if cmd == "A6":
        return {
            "status_code": "00",
            "raw_request": raw_command,
            "raw_response": "0000A700UA1B2C3D4E5F60718293A4B5C6D7E8F908F4E2A",
            "parsed_response": [{"tag": "Key under LMK", "value": "UA1B2C3D4E5F60718293A4B5C6D7E8F90"}],
        }
    if cmd == "BU":
        return {
            "status_code": "00",
            "raw_request": raw_command,
            "raw_response": "0000BV008F4E2A0000000000",
            "parsed_response": [{"tag": "Key Check Value", "value": "8F4E2A0000000000"}],
        }
    return {"status_code": "68", "raw_response": "0000ER68"}


def test_part_g_audit_deliverable_and_lmk_lifecycle():
    headers = _auth_headers()

    with patch("app.lmk_key_management_service.ExternalSoftHSMBridge.execute_command", side_effect=_mock_soft_hsm_execute), \
         patch("app.lmk_key_management_service.ExternalSoftHSMBridge.fetch_status", return_value={
             "status": "ONLINE",
             "hsm_state": "AUTHORIZED_ONLINE",
             "version": "3.5.0",
             "firmware": "1347-0900",
             "lmk_check_value": "D3B82A0000000000",
             "storage": {"mode": "EPHEMERAL_MEMORY", "persistent_cloud_db": False},
         }):

        sw = client.post("/api/hsm/lmk-key-management/provider", json={"provider_mode": "EXTERNAL_HSM"}, headers=headers)
        assert sw.status_code == 200
        assert sw.json()["active_provider"] == "EXTERNAL_HSM"
        assert sw.json()["lmk_check_value"] == "D3B82A0000000000"

        aud = client.get("/api/hsm/lmk-key-management/audit-report", headers=headers)
        assert aud.status_code == 200
        body = aud.json()
        assert "1_lmk_generation_mechanism" in body
        assert "12_lmk_compatibility_and_persistence_limitations" in body

        gen_zmk = client.post("/api/hsm/lmk-key-management/generate", json={
            "key_identifier": "ZMK_EXT_TEST_01",
            "key_name": "External Test ZMK",
            "key_type": "ZMK",
            "key_scheme": "U",
            "mode": "0",
        }, headers=headers)
        assert gen_zmk.status_code == 200
        zmk_data = gen_zmk.json()["key"]
        assert zmk_data["provider_type"] == "EXTERNAL_HSM"
        assert zmk_data["lmk_check_value"] == "D3B82A0000000000"
        assert zmk_data["encrypted_key_block"].startswith("U")

        db = SessionLocal()
        try:
            db_rec = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == "ZMK_EXT_TEST_01").first()
            assert db_rec is not None
            assert db_rec.clear_key_hex is None
        finally:
            db.close()

        gen_zpk = client.post("/api/hsm/lmk-key-management/generate", json={
            "key_identifier": "ZPK_EXT_TEST_01",
            "key_name": "External Test ZPK",
            "key_type": "ZPK",
            "key_scheme": "U",
            "mode": "1",
            "export_zmk_key_identifier": "ZMK_EXT_TEST_01",
        }, headers=headers)
        assert gen_zpk.status_code == 200
        assert gen_zpk.json()["exported_key_under_zmk"] == "U99887766554433221100FFEEDDCCBBAA"

        exp_res = client.post("/api/hsm/lmk-key-management/export", json={
            "key_identifier": "ZPK_EXT_TEST_01",
            "zmk_key_identifier": "ZMK_EXT_TEST_01",
            "export_scheme": "U",
        }, headers=headers)
        assert exp_res.status_code == 200
        assert exp_res.json()["command_executed"] == "A8"

        imp_res = client.post("/api/hsm/lmk-key-management/import", json={
            "key_identifier": "ZPK_EXT_IMPORTED_01",
            "key_name": "Imported Partner ZPK",
            "key_type": "ZPK",
            "zmk_key_identifier": "ZMK_EXT_TEST_01",
            "encrypted_key_under_zmk": exp_res.json()["key_under_zmk"],
            "key_scheme_lmk": "U",
        }, headers=headers)
        assert imp_res.status_code == 200
        assert imp_res.json()["command_executed"] == "A6"

        bu_res = client.post("/api/hsm/lmk-key-management/verify-kcv/ZPK_EXT_TEST_01", headers=headers)
        assert bu_res.status_code == 200
        assert bu_res.json()["kcv_matched"] is True

        rot_res = client.post("/api/hsm/lmk-key-management/rotate", json={
            "key_identifier": "ZPK_EXT_TEST_01",
        }, headers=headers)
        assert rot_res.status_code == 200
        assert rot_res.json()["new_version"] == 2

        client.post("/api/hsm/lmk-key-management/provider", json={"provider_mode": "INTERNAL_HSM"}, headers=headers)
