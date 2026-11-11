import os
import itertools
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.host_engine import HostTransactionProcessor
from app.models import Account, Card, Customer, Transaction, Institution, CardProfile, HostParameter
from app.models_local_host import LocalHostPolicy, HostAlgo, HostAlgoLog, HostAlgoVersion
from app.local_host_engine import (
    validate_python, validate_sql, field_catalog, ALGO_TEMPLATES, effective_policy, build_test_context, LocalHostEngine,
    run_python_algo,
)
from app.seed_data import seed_initial_data
from app.security import create_access_token
from app.config import settings

PAN = "4567890123450001"
_seq = itertools.count(1)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    # other test modules (e.g. the LMK provider switch test) leave settings.HSM_MODE on EXTERNAL: pin it for these tests
    previous_mode = settings.HSM_MODE
    settings.HSM_MODE = "SOFT_HSM_LOCAL"
    session = SessionLocal()
    seed_initial_data(session)
    yield session
    session.close()
    settings.HSM_MODE = previous_mode
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    with TestClient(app) as c:
        token = create_access_token(subject=settings.ADMIN_USERNAME)
        c.headers = {"Authorization": f"Bearer {token}"}
        yield c


def tx(db, amount=2500, terminal="ATM01", tcode="10", mcc=None, country=None, hour=None, pan=PAN, **extra):
    n = next(_seq)
    fields = {"2": pan, "3": f"{int(tcode):03d}0000", "4": f"{int(amount * 100):012d}", "11": f"{n:06d}",
              "37": f"{900000000000 + n}", "41": terminal, "49": "050"}
    if mcc:
        fields["18"] = mcc
    if country:
        fields["19"] = country
    if hour is not None:
        fields["12"] = f"{hour:02d}0000"
    fields.update(extra)
    return HostTransactionProcessor(db).process_transaction(
        {"transaction_code": tcode, "mti": "0200", "test_clear_pin_helper": "1234", "fields": fields}
    )


def card_of(db):
    return db.query(Card).filter(Card.test_pan_reference == PAN).first()


def set_policy(db, config, scope="GLOBAL", inst=None, enabled=True):
    db.add(LocalHostPolicy(scope_type=scope, institution_id=inst, name="t", enabled=enabled, config_json=config))
    db.commit()


def add_algo(db, code="T_ALGO", language="PYTHON", src="", **kw):
    a = HostAlgo(algo_code=code, name=code, language=language, code=src, **kw)
    db.add(a)
    db.commit()
    return a


def check_names(res):
    return [c["check_name"] for c in res["checks"]]


# ============================================================================ baseline
def test_default_policy_does_not_change_existing_behaviour(db_session):
    res = tx(db_session)
    assert res["response_code"] == "00"
    assert any(n == "Local Host Policy" for n in check_names(res))


# ============================================================================ policy engine
def test_host_status_maintenance_declines_bank(db_session):
    bank = card_of(db_session).institution
    set_policy(db_session, {"general": {"host_status": "MAINTENANCE", "status_response_code": "91", "status_message": "Down for upgrade"}},
               scope="BANK", inst=bank.id)
    res = tx(db_session)
    assert res["response_code"] == "91"
    failed = [c for c in res["checks"] if c["check_status"] == "FAILED"][0]
    assert "Down for upgrade" in failed["message"]


def test_channel_disabled_and_amount_caps(db_session):
    set_policy(db_session, {"channels": {"ATM": {"enabled": False}}})
    assert tx(db_session)["response_code"] == "57"
    db_session.query(LocalHostPolicy).delete(); db_session.commit()
    set_policy(db_session, {"channels": {"ATM": {"enabled": True, "max_amount": 1000}}})
    assert tx(db_session, amount=2500)["response_code"] == "61"
    assert tx(db_session, amount=500)["response_code"] == "00"


def test_transaction_matrix_blocks_code_on_channel(db_session):
    set_policy(db_session, {"transactions": {"10": {"enabled": True, "channels": ["POS"]}}})
    res = tx(db_session)  # cash withdrawal on ATM terminal
    assert res["response_code"] == "57"
    set_policy_row = db_session.query(LocalHostPolicy).first()
    set_policy_row.config_json = {"transactions": {"10": {"enabled": False}}}
    db_session.commit()
    assert tx(db_session)["response_code"] == "57"


def test_source_control_on_us_and_unknown_source(db_session):
    set_policy(db_session, {"sources": {"ON_US": {"enabled": False}}})
    assert tx(db_session)["response_code"] == "57"  # seeded terminal belongs to the card's own bank -> ON_US


def test_mcc_currency_country_and_acquirer_filters(db_session):
    set_policy(db_session, {"mcc": {"blocked": ["7995"]}})
    assert tx(db_session, mcc="7995")["response_code"] == "57"
    assert tx(db_session, mcc="5411")["response_code"] == "00"
    cfg = db_session.query(LocalHostPolicy).first()
    cfg.config_json = {"cross_border": {"enabled": False}}
    db_session.commit()
    assert tx(db_session, country="840")["response_code"] == "57"
    cfg.config_json = {"general": {"allowed_currencies": ["USD"]}}
    db_session.commit()
    assert tx(db_session)["response_code"] == "57"
    card = card_of(db_session)
    cfg.config_json = {"acquirers": {"blocked": [card.institution.institution_code], "response_code": "58"}}
    db_session.commit()
    assert tx(db_session)["response_code"] == "58"          # terminal owner = the card's own bank here
    cfg.config_json = {"acquirers": {"allowed": ["SOME_OTHER_BANK"], "response_code": "58"}}
    db_session.commit()
    assert tx(db_session)["response_code"] == "58"
    cfg.config_json = {"acquirers": {"allowed": [card.institution.institution_code]}}
    db_session.commit()
    assert tx(db_session)["response_code"] == "00"


def test_business_hours_wrap_and_velocity(db_session):
    set_policy(db_session, {"general": {"business_hours": {"enabled": True, "start": "09:00", "end": "17:00"}}})
    assert tx(db_session, hour=3)["response_code"] == "57"
    assert tx(db_session, hour=10)["response_code"] == "00"
    cfg = db_session.query(LocalHostPolicy).first()
    cfg.config_json = {"velocity": {"enabled": True, "max_tx_per_minute": 2, "response_code": "65"}}
    db_session.commit()
    # earlier approved transaction(s) in this test already count; use clear numbers
    before = db_session.query(Transaction).count()
    res = None
    for _ in range(4):
        res = tx(db_session, amount=10)
        if res["response_code"] == "65":
            break
    assert res["response_code"] == "65"


def test_policy_inheritance_bank_overrides_only_its_sections(db_session):
    bank = card_of(db_session).institution
    set_policy(db_session, {"channels": {"ATM": {"enabled": False}}, "mcc": {"blocked": ["7995"]}})
    set_policy(db_session, {"channels": {"ATM": {"enabled": True}}}, scope="BANK", inst=bank.id)
    eff = effective_policy(db_session, bank.id)
    assert eff["config"]["channels"]["ATM"]["enabled"] is True            # bank override wins
    assert eff["config"]["mcc"]["blocked"] == ["7995"]                    # inherited from GLOBAL
    assert eff["sources"]["channels"] == "BANK" and eff["sources"]["mcc"] == "GLOBAL" and eff["sources"]["velocity"] == "DEFAULT"
    assert tx(db_session)["response_code"] == "00"


def test_policy_api_roundtrip_and_simulator(client, db_session):
    bank = card_of(db_session).institution
    r = client.put("/api/local-host/policies", json={"scope_type": "GLOBAL", "config": {"channels": {"ATM": {"enabled": False, "max_amount": "oops"}}, "bogus": {"x": 1}}})
    assert r.status_code == 200 and r.json()["sections"] == ["channels"]
    r = client.put("/api/local-host/policies", json={"scope_type": "BANK", "institution_id": bank.id, "config": {"mcc": {"blocked": "7995, 6012"}}})
    assert r.status_code == 200
    assert client.put("/api/local-host/policies", json={"scope_type": "BANK", "config": {}}).status_code == 400
    lst = client.get("/api/local-host/policies").json()
    assert lst[0]["scope_type"] == "GLOBAL" and any(p["bank_code"] == bank.institution_code and p["exists"] for p in lst)
    eff = client.get("/api/local-host/policies/effective", params={"institution_id": bank.id}).json()
    assert eff["config"]["mcc"]["blocked"] == ["7995", "6012"] and eff["config"]["channels"]["ATM"]["max_amount"] == 0
    sim = client.post("/api/local-host/policies/simulate", json={"institution_id": bank.id, "overrides": {"channel": "ATM", "amount": 500}}).json()
    assert sim["allowed"] is False and sim["failed_control"] == "Channel Control" and sim["response_code"] == "57"
    sim2 = client.post("/api/local-host/policies/simulate", json={"institution_id": bank.id, "overrides": {"channel": "POS", "mcc": "7995"}}).json()
    assert sim2["failed_control"] == "MCC Control"
    sim3 = client.post("/api/local-host/policies/simulate", json={"institution_id": bank.id, "overrides": {"channel": "POS", "mcc": "5411"}}).json()
    assert sim3["allowed"] is True and sim3["checks"]
    assert client.delete(f"/api/local-host/policies/bank/{bank.id}").status_code == 200
    assert client.delete(f"/api/local-host/policies/bank/{bank.id}").status_code == 404
    meta = client.get("/api/local-host/meta").json()
    assert meta["banks"] and meta["transaction_codes"] and meta["processing_systems"] and "ATM" in meta["channels"]


# ============================================================================ python sandbox
@pytest.mark.parametrize("code", [
    "import os",
    "x = ().__class__",
    "open('/etc/passwd')",
    "while True:\n    pass",
    "eval('1+1')",
    "x = tx.amount ** 9",
    "getattr(tx, 'amount')",
    "'{0.__class__}'.format(tx)",
    "def f():\n    return (i for i in []).gi_frame\nf()",
    "class A: pass",
    "try:\n    pass\nexcept:\n    pass",
    "with open('x') as f:\n    pass",
    "x = 1 << 99",
])
def test_sandbox_rejects_dangerous_code(code):
    errors, _ = validate_python(code)
    assert errors, f"should be rejected: {code!r}"


def test_sandbox_accepts_normal_code_and_blocks_memory_bombs(db_session):
    assert validate_python("if tx.amount > 5000 and tx.hour < 5:\n    decline('57', 'x')\n")[0] == []
    card = card_of(db_session)
    ctx = build_test_context(db_session, card, {"amount": 100})
    res = run_python_algo(db_session, "x = 'a' * 10**3 * 10**3\nreturn True", ctx)
    # ** is rejected at validation; plain repetition beyond the cap is blocked at run time
    assert res.error
    res = run_python_algo(db_session, "x = 'a' * 100000\nreturn True", ctx)
    assert res.error and "too large" in res.error
    res = run_python_algo(db_session, "x = 0\nfor i in range(100000):\n    x = x + i\nreturn True", ctx)
    assert res.error and "range()" in res.error
    res = run_python_algo(db_session, "tx.amount > 50", ctx)         # last expression is the result
    assert res.matched and res.action is None and not res.error
    res = run_python_algo(db_session, "decline('Night time')", ctx)  # message only
    assert res.action == "DECLINE" and res.message == "Night time" and res.rc is None
    res = run_python_algo(db_session, "decline('61', 'Too much')", ctx)
    assert res.rc == "61" and res.message == "Too much"
    res = run_python_algo(db_session, "block_card('stolen', '62')", ctx)
    assert res.action == "BLOCK_CARD" and res.rc == "62" and res.message == "stolen"
    res = run_python_algo(db_session, "block_card('only message')", ctx)
    assert res.rc is None and res.message == "only message"
    res = run_python_algo(db_session, "y = card.nothing", ctx)
    assert res.error and "AttributeError" in res.error
    res = run_python_algo(db_session, "try:\n    decline('57','in try')\nexcept Exception:\n    pass", ctx)
    assert res.action == "DECLINE"  # a script cannot swallow its own decision


# ============================================================================ python algos in the pipeline
def test_python_algo_declines_in_pipeline_and_logs(db_session):
    add_algo(db_session, "NIGHT", src="if tx.channel == 'ATM' and tx.amount > 1000 and tx.hour < 5:\n    decline('57', 'night cash')\n",
             default_action="DECLINE")
    res = tx(db_session, amount=2000, hour=2)
    assert res["response_code"] == "57"
    failed = [c for c in res["checks"] if c["check_status"] == "FAILED"][0]
    assert failed["check_name"] == "Algo NIGHT" and "night cash" in failed["message"]
    assert tx(db_session, amount=2000, hour=14)["response_code"] == "00"
    algo = db_session.query(HostAlgo).first()
    db_session.refresh(algo)
    assert algo.eval_count == 2 and algo.hit_count == 1
    logs = db_session.query(HostAlgoLog).all()
    assert len(logs) == 1 and logs[0].matched and logs[0].action_applied and logs[0].response_code == "57"
    assert "4567890123450001" not in str(logs[0].context_json)


def test_monitor_mode_never_declines_or_blocks(db_session):
    add_algo(db_session, "MON", src="return True", default_action="BLOCK_CARD", mode="MONITOR")
    res = tx(db_session)
    assert res["response_code"] == "00"
    assert any("[MONITOR] would BLOCK_CARD" in c["message"] for c in res["checks"])
    assert card_of(db_session).card_status == "ACTIVE"
    log = db_session.query(HostAlgoLog).first()
    assert log.matched and not log.action_applied


def test_block_card_blocks_for_real_and_next_tx_is_declined(db_session):
    add_algo(db_session, "BLK", src="if tx.amount > 5000:\n    block_card('suspicious', '62')\n", default_action="BLOCK_CARD", default_response_code="62")
    res = tx(db_session, amount=6000)
    assert res["response_code"] == "62"
    assert card_of(db_session).card_status == "BLOCKED"
    assert tx(db_session, amount=100)["response_code"] == "05"      # card status check now declines


def test_block_customer_blocks_customer(db_session):
    add_algo(db_session, "BLKC", src="block_customer('fraud ring')", default_action="BLOCK_CUSTOMER", default_response_code="62")
    res = tx(db_session)
    assert res["response_code"] == "62"
    cust = card_of(db_session).customer
    assert cust.customer_status == "BLOCKED"
    assert tx(db_session)["response_code"] == "05"


def test_approve_allow_list_skips_later_algos_but_not_balance(db_session):
    add_algo(db_session, "A_ALLOW", src="if tx.amount < 5000:\n    approve('allow small')", default_action="APPROVE", priority=10)
    add_algo(db_session, "B_DENY", src="return True", default_action="DECLINE", priority=20)
    assert tx(db_session, amount=100)["response_code"] == "00"
    assert tx(db_session, amount=9000)["response_code"] == "57"      # allow-list did not match -> next algo declines
    # approve() does not bypass balance checks
    acct = db_session.query(Account).filter(Account.account_number == "1001000001").first()
    acct.available_balance = Decimal("50.00"); db_session.commit()
    assert tx(db_session, amount=100)["response_code"] == "51"


def test_flag_continues_and_error_policies(db_session):
    add_algo(db_session, "FLG", src="flag('watch this card')", default_action="FLAG", priority=10)
    res = tx(db_session)
    assert res["response_code"] == "00" and any("FLAG: watch this card" in c["message"] for c in res["checks"])
    db_session.query(HostAlgo).delete(); db_session.commit()
    add_algo(db_session, "BUGSKIP", src="return 1 / 0", on_error="SKIP")
    res = tx(db_session)
    assert res["response_code"] == "00" and any(c["check_status"] == "SKIPPED" for c in res["checks"])
    assert db_session.query(HostAlgo).first().error_count >= 1
    db_session.query(HostAlgo).delete(); db_session.commit()
    add_algo(db_session, "BUGCLOSED", src="return 1 / 0", on_error="DECLINE", default_response_code="05")
    assert tx(db_session)["response_code"] == "05"


def test_scopes_and_filters(db_session):
    card = card_of(db_session)
    other = db_session.query(Institution).filter(Institution.id != card.institution_id).first()
    add_algo(db_session, "OTHERBANK", src="return True", scope_type="BANK", institution_id=other.id)
    assert tx(db_session)["response_code"] == "00"                     # other bank's algo does not apply
    add_algo(db_session, "MYBANK", src="return True", scope_type="BANK", institution_id=card.institution_id)
    assert tx(db_session)["response_code"] == "57"
    db_session.query(HostAlgo).delete(); db_session.commit()
    prof = db_session.query(CardProfile).filter(CardProfile.id != card.card_profile_id).first()
    add_algo(db_session, "OTHERPROF", src="return True", scope_type="CARD_PROFILE", card_profile_id=prof.id)
    assert tx(db_session)["response_code"] == "00"
    add_algo(db_session, "MYPROF", src="return True", scope_type="CARD_PROFILE", card_profile_id=card.card_profile_id)
    assert tx(db_session)["response_code"] == "57"
    db_session.query(HostAlgo).delete(); db_session.commit()
    add_algo(db_session, "ONLYPOS", src="return True", channels_json=["POS"])
    add_algo(db_session, "ONLYCODE00", src="return True", tx_codes_json=["00"])
    assert tx(db_session)["response_code"] == "00"                     # ATM cash (code 10): filtered out
    add_algo(db_session, "DISABLED", src="return True", enabled=False)
    assert tx(db_session)["response_code"] == "00"


def test_history_helper_velocity_and_block_after_declines(db_session):
    add_algo(db_session, "DECL3", src="if history.declines('10m', 'card') >= 2:\n    block_card('2 declines', '62')\n",
             default_action="BLOCK_CARD", default_response_code="62")
    acct = db_session.query(Account).filter(Account.account_number == "1001000001").first()
    acct.available_balance = Decimal("10.00"); db_session.commit()
    assert tx(db_session, amount=500)["response_code"] == "51"
    assert tx(db_session, amount=500)["response_code"] == "51"
    res = tx(db_session, amount=500)                                   # 2 earlier declines -> blocked
    assert res["response_code"] == "62" and card_of(db_session).card_status == "BLOCKED"


def test_post_auth_stage_sees_balance_after(db_session):
    add_algo(db_session, "POST", src="if account.balance_after < 150000:\n    decline('57', 'would leave too little')\n", stage="POST_AUTH")
    acct = db_session.query(Account).filter(Account.account_number == "1001000001").first()
    start = float(acct.available_balance)
    assert start >= 150000
    res = tx(db_session, amount=2000)                       # balance after = start - 2000 < 150000 only if start < 152000
    expected = "57" if start - 2000 < 150000 else "00"
    assert res["response_code"] == expected
    acct.available_balance = Decimal("151000.00"); db_session.commit()
    res = tx(db_session, amount=2000)                       # 149,000 left -> POST_AUTH algo declines before posting
    assert res["response_code"] == "57"
    db_session.refresh(acct)
    assert acct.available_balance == Decimal("151000.00")   # nothing was posted


# ============================================================================ SQL algos
@pytest.mark.parametrize("sql", [
    "DELETE FROM transactions",
    "SELECT 1; DROP TABLE cards",
    "UPDATE cards SET card_status='X'",
    "SELECT :not_a_field",
    "PRAGMA table_info(cards)",
    "SELECT * INTO x FROM cards",
    "INSERT INTO cards VALUES (1)",
])
def test_sql_validation_rejects_unsafe(sql):
    assert validate_sql(sql)[0], sql


def test_sql_algo_condition_and_custom_action(db_session):
    add_algo(db_session, "SQL1", language="SQL",
             src="SELECT COUNT(*) >= 2 FROM transactions WHERE card_id = :card_id AND authorization_status = 'APPROVED' AND transaction_datetime >= :since_1h",
             default_action="DECLINE", default_response_code="65")
    assert tx(db_session, amount=10)["response_code"] == "00"
    assert tx(db_session, amount=10)["response_code"] == "00"
    assert tx(db_session, amount=10)["response_code"] == "65"          # two approved earlier -> SQL matches
    db_session.query(HostAlgo).delete(); db_session.commit()
    add_algo(db_session, "SQL2", language="SQL",
             src="SELECT 'BLOCK_CARD' AS action, '62' AS response_code, 'sql says block' AS message WHERE :tx_amount > 7000")
    assert tx(db_session, amount=100)["response_code"] == "00"
    res = tx(db_session, amount=8000)
    assert res["response_code"] == "62" and card_of(db_session).card_status == "BLOCKED"
    failed = [c for c in res["checks"] if c["check_status"] == "FAILED"][0]
    assert "sql says block" in failed["message"]


# ============================================================================ algo API
def _body(**kw):
    b = {"algo_code": "api algo 1", "name": "API Algo", "language": "PYTHON", "code": "if tx.amount > 100:\n    decline('57','big')\n",
         "scope_type": "GLOBAL", "stage": "PRE_AUTH", "priority": 50, "mode": "ENFORCE", "default_action": "DECLINE",
         "default_response_code": "57", "default_message": "msg", "on_error": "SKIP", "stop_on_match": True,
         "tx_codes": [], "channels": [], "enabled": True}
    b.update(kw)
    return b


def test_algo_crud_versions_rollback_toggle_logs(client, db_session):
    r = client.post("/api/local-host/algos", json=_body())
    assert r.status_code == 200, r.text
    algo = r.json()
    assert algo["algo_code"] == "API_ALGO_1" and algo["version"] == 1
    assert client.post("/api/local-host/algos", json=_body()).status_code == 409
    assert client.post("/api/local-host/algos", json=_body(algo_code="bad code", code="import os")).status_code == 400
    assert client.post("/api/local-host/algos", json=_body(algo_code="no bank", scope_type="BANK")).status_code == 400
    assert client.post("/api/local-host/algos", json=_body(algo_code="bad sql", language="SQL", code="DELETE FROM cards")).status_code == 400
    lst = client.get("/api/local-host/algos").json()
    assert len(lst) == 1 and "code" not in lst[0]
    aid = algo["id"]
    upd = client.put(f"/api/local-host/algos/{aid}", json=_body(code="return False", change_note="no-op")).json()
    assert upd["version"] == 2 and upd["code"] == "return False"
    vers = client.get(f"/api/local-host/algos/{aid}/versions").json()
    assert [v["version"] for v in vers] == [2, 1]
    rb = client.post(f"/api/local-host/algos/{aid}/rollback", json={"version": 1}).json()
    assert rb["version"] == 3
    assert "decline" in client.get(f"/api/local-host/algos/{aid}").json()["code"]
    assert client.post(f"/api/local-host/algos/{aid}/toggle", json={"enabled": False}).json()["enabled"] is False
    assert client.post(f"/api/local-host/algos/{aid}/toggle", json={"mode": "MONITOR", "enabled": True}).json()["mode"] == "MONITOR"
    assert client.post(f"/api/local-host/algos/{aid}/toggle", json={"mode": "NOPE"}).status_code == 400
    # run a real transaction through it and read the logs / overview
    client.post(f"/api/local-host/algos/{aid}/toggle", json={"mode": "ENFORCE"})
    assert tx(db_session, amount=500)["response_code"] == "57"
    logs = client.get("/api/local-host/algos/logs", params={"algo_id": aid, "matched_only": True}).json()
    assert len(logs) == 1 and logs[0]["action"] == "DECLINE"
    ov = client.get("/api/local-host/overview").json()
    assert ov["algos_total"] == 1 and ov["matches_24h"] == 1 and ov["top_algos"][0]["algo_code"] == "API_ALGO_1"
    assert client.delete(f"/api/local-host/algos/{aid}").status_code == 200
    assert client.get(f"/api/local-host/algos/{aid}").status_code == 404


def test_algo_test_endpoint_is_side_effect_free(client, db_session):
    card = card_of(db_session)
    draft = _body(code="block_card('test block', '62')", default_action="BLOCK_CARD")
    r = client.post("/api/local-host/algos/test", json={"draft": draft, "card_id": card.id, "overrides": {"amount": 9999, "channel": "ATM", "hour": 3}}).json()
    assert r["ok"] and r["result"]["matched"] and r["result"]["action"] == "BLOCK_CARD" and r["result"]["would_block_card"]
    assert r["context"]["tx"]["amount"] == 9999 and r["context"]["tx"]["channel"] == "ATM" and r["context"]["tx"]["hour"] == 3
    assert r["context"]["card"]["pan"].startswith("456789******")   # never exposes the full PAN
    db_session.expire_all()
    assert card_of(db_session).card_status == "ACTIVE" and db_session.query(HostAlgoLog).count() == 0
    bad = client.post("/api/local-host/algos/test", json={"draft": _body(code="import os"), "card_id": card.id}).json()
    assert bad["ok"] is False and bad["errors"]
    sqlr = client.post("/api/local-host/algos/test", json={"draft": _body(language="SQL", code="SELECT 1 AS x WHERE :tx_amount > 5"), "pan": PAN, "overrides": {"amount": 50}}).json()
    assert sqlr["ok"] and sqlr["result"]["matched"] is True and sqlr["result"]["rows"] == [{"x": 1}]
    v = client.post("/api/local-host/algos/validate", json={"language": "PYTHON", "code": "while True: pass"}).json()
    assert v["valid"] is False
    assert client.post("/api/local-host/algos/validate", json={"language": "SQL", "code": "SELECT 1"}).json()["valid"] is True


def test_catalog_templates_and_schema(client, db_session):
    cat = client.get("/api/local-host/algos/fields").json()
    keys = {f["python"] for g in cat["groups"] for f in g["fields"]}
    for must in ("tx.amount", "tx.hour", "tx.channel", "bank.name", "terminal.owner", "profile.auth_name", "customer.risk",
                 "card.status", "account.balance", "limits.card_daily_used"):
        assert must in keys, must
    assert all(f["sql"].startswith(":") for g in cat["groups"] for f in g["fields"])
    assert cat["actions"] and cat["history"] and cat["time_params"]
    tpls = client.get("/api/local-host/algos/templates").json()
    assert len(tpls) == len(ALGO_TEMPLATES) >= 8
    card = card_of(db_session)
    for t in tpls:                                                      # every template is valid and runs
        v = client.post("/api/local-host/algos/validate", json={"language": t["language"], "code": t["code"]}).json()
        assert v["valid"], (t["key"], v)
        r = client.post("/api/local-host/algos/test", json={"draft": {**t, "algo_code": t["key"]}, "card_id": card.id,
                                                            "overrides": {"amount": 30000, "channel": "ATM", "hour": 2}}).json()
        assert r["ok"], (t["key"], r)
        assert not r["result"]["error"], (t["key"], r["result"]["error"])
    schema = client.get("/api/local-host/algos/schema").json()
    assert any(t["table"] == "transactions" for t in schema)
    # every SQL param in the catalog really exists in the live context
    ctx = build_test_context(db_session, card, {})
    for g in cat["groups"]:
        for f in g["fields"]:
            assert f["sql"][1:] in ctx.params


# ============================================================================ Rules & Checks tab + friendly errors
def test_algo_save_errors_are_readable_not_422(client, db_session):
    r = client.post("/api/local-host/algos", json=_body(algo_code="", name=""))
    assert r.status_code == 400
    msg = r.json()["detail"]
    assert "Algo code is required" in msg and "Name is required" in msg
    assert client.post("/api/local-host/algos", json=_body(algo_code="AB")).status_code == 400
    assert "Priority" in client.post("/api/local-host/algos", json=_body(algo_code="PRIO_X", priority=0)).json()["detail"]
    assert "Response code" in client.post("/api/local-host/algos", json=_body(algo_code="RC_X", default_response_code="5")).json()["detail"]
    ok = client.post("/api/local-host/algos", json=_body(algo_code="fine one", name="Fine"))
    assert ok.status_code == 200 and ok.json()["algo_code"] == "FINE_ONE"
    long_msg = client.post("/api/local-host/algos", json=_body(algo_code="LONGMSG", default_message="x" * 500))
    assert long_msg.status_code == 200 and len(long_msg.json()["default_message"]) == 200


def test_builtin_checks_list_toggle_and_really_switch_off(client, db_session):
    checks = client.get("/api/local-host/checks").json()
    live = [c for c in checks if c["affects_host"]]
    assert [c["name"] for c in live] == ["CHECKCARDLIMITS", "CHECKACCT2CARDLIMITS", "AUTHORIZEACCTBALANCESTRANS"]
    assert all(c["enabled"] and c["title"] and c["what"] and c["decline_rc"] for c in live)
    assert [c["name"] for c in checks if not c["affects_host"]] == ["DEFAULTREQUESTFUNCTION", "DEFAULTRESPONSEFUNCTION", "POSRESPONSECONTROLFUNCTION"]

    acct = db_session.query(Account).filter(Account.account_number == "1001000001").first()
    acct.available_balance = Decimal("10.00"); db_session.commit()
    bal = next(c for c in live if c["name"] == "AUTHORIZEACCTBALANCESTRANS")
    assert tx(db_session, amount=500)["response_code"] == "51"
    assert client.post(f"/api/local-host/checks/{bal['id']}/toggle", json={"enabled": False}).status_code == 200
    assert next(c for c in client.get("/api/local-host/checks").json() if c["id"] == bal["id"])["enabled"] is False
    assert tx(db_session, amount=500)["response_code"] == "00"          # really OFF now
    client.post(f"/api/local-host/checks/{bal['id']}/toggle", json={"enabled": True})
    assert tx(db_session, amount=500)["response_code"] == "51"          # and ON again

    # what the OLD page saved (active = false) also switches the check off now
    p = db_session.query(HostParameter).filter(HostParameter.parameter_name == "AUTHORIZEACCTBALANCESTRANS").first()
    p.active = False
    p.parameter_value = {**p.parameter_value, "enabled": False}
    db_session.commit()
    assert tx(db_session, amount=500)["response_code"] == "00"

    # parameters the engine does not know are listed as reference only
    db_session.add(HostParameter(parameter_group="MY_GROUP", parameter_name="MY_SWITCH", parameter_value={"enabled": True}, description="mine"))
    db_session.commit()
    mine = next(c for c in client.get("/api/local-host/checks").json() if c["name"] == "MY_SWITCH")
    assert mine["affects_host"] is False and mine["known"] is False and mine["title"] == "MY_SWITCH"
    assert client.post("/api/local-host/checks/nope/toggle", json={"enabled": True}).status_code == 404


def test_simple_rules_builder_roundtrip_validation_and_engine(client, db_session):
    fields = client.get("/api/local-host/rules/fields").json()
    names = {f["name"] for f in fields}
    assert {"amount", "trancode", "hour", "mcc", "institution.code", "is_foreign", "card_status", "account_balance"} <= names
    bad = client.post("/api/local-host/rules/validate", json={"expression": "ammount > 5"}).json()
    assert bad["valid"] is False and "ammount" in bad["error"]
    assert client.post("/api/local-host/rules/validate", json={"expression": "  "}).json()["valid"] is False
    for expr in ["amount > 50000", "(trancode == '10' or trancode == '11')", "not is_foreign", "institution.code == 'XBANK'",
                 "hour < 5 and amount >= 20000", "(mcc != '5411' and mcc != '5812')", "is_foreign"]:
        assert client.post("/api/local-host/rules/validate", json={"expression": expr}).json()["valid"] is True, expr

    cj = {"logic": "AND", "conditions": [{"field": "amount", "op": ">", "value": "1000"}]}
    r = client.post("/api/authorizer-rules", json={"rule_code": "BIG_CASH", "name": "Big cash", "rule_mode": "BUILDER", "conditions_json": cj,
                    "expression": "amount > 1000", "action": "DECLINE", "response_code": "61", "message": "too big", "priority": 10,
                    "stop_on_match": True, "enabled": True})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert tx(db_session, amount=2000)["response_code"] == "61"
    assert tx(db_session, amount=500)["response_code"] == "00"

    cj2 = {"logic": "AND", "conditions": [{"field": "amount", "op": ">", "value": "5000"}]}
    u = client.put(f"/api/authorizer-rules/{rid}", json={"expression": "amount > 5000", "conditions_json": cj2, "rule_mode": "BUILDER"})
    assert u.status_code == 200 and u.json()["conditions_json"] == cj2 and u.json()["rule_mode"] == "BUILDER"
    assert tx(db_session, amount=2000)["response_code"] == "00"
    assert tx(db_session, amount=6000)["response_code"] == "61"
    assert client.put(f"/api/authorizer-rules/{rid}", json={"enabled": False}).status_code == 200
    assert tx(db_session, amount=6000)["response_code"] == "00"

    t = client.post("/api/local-host/rules/test", json={"expression": "amount > 1000 and hour < 5", "pan": PAN, "overrides": {"amount": 5000, "hour": 2}}).json()
    assert t["valid"] and t["matched"] and t["context"]["amount"] == 5000 and t["context"]["hour"] == 2
    t2 = client.post("/api/local-host/rules/test", json={"expression": "amount > 1000 and hour < 5", "pan": PAN, "overrides": {"amount": 5000, "hour": 14}}).json()
    assert t2["valid"] and t2["matched"] is False
    t3 = client.post("/api/local-host/rules/test", json={"expression": "nope > 1", "pan": PAN}).json()
    assert t3["valid"] is False and "nope" in t3["error"]
    assert client.post("/api/local-host/rules/test", json={"expression": "amount > 1", "pan": "0000000000000000"}).status_code == 404


def test_every_field_in_the_reference_is_usable_in_a_real_transaction(client, db_session):
    cat = client.get("/api/local-host/algos/fields").json()
    paths = [f["python"] for g in cat["groups"] for f in g["fields"]]
    params = [f["sql"] for g in cat["groups"] for f in g["fields"]]
    assert len(paths) >= 90 and "tx.currency" in paths and "tx.tran_code" in paths and "tx.is_financial" in paths

    # PYTHON: read every single field, then check that the values are the real ones of this transaction
    code = "seen = [\n" + ",\n".join(f"    {p}" for p in paths) + "\n]\n"
    code += ("if tx.currency != '050' or tx.tran_code != '10' or tx.channel != 'ATM' or tx.amount != 2500 or tx.mti != '0200':\n"
             "    decline('99', 'tx fields do not match')\n"
             "if card.status != 'ACTIVE' or card.last4 != '0001' or not bank.code or customer.status != 'ACTIVE':\n"
             "    decline('98', 'card/bank/customer fields do not match')\n"
             "if profile.auth_code == '' and profile.card_code == '':\n"
             "    decline('97', 'profile fields are empty')\n"
             "log(len(seen))\nreturn False\n")
    add_algo(db_session, "ALL_PY", src=code)
    res = tx(db_session, amount=2500)
    chk = [c for c in res["checks"] if c["check_name"] == "Algo ALL_PY"][0]
    assert chk["check_status"] == "PASSED" and chk["message"] == "Condition not met", chk
    assert res["response_code"] == "00"

    # SQL: every :parameter is bound to a value
    db_session.query(HostAlgo).delete(); db_session.commit()
    sql = "SELECT 1 WHERE " + " AND ".join(f"({p} IS NOT NULL)" for p in params)
    add_algo(db_session, "ALL_SQL", language="SQL", src=sql, mode="MONITOR")
    res = tx(db_session, amount=2500)
    chk = [c for c in res["checks"] if c["check_name"] == "Algo ALL_SQL"][0]
    assert "[MONITOR] would DECLINE" in chk["message"], chk
