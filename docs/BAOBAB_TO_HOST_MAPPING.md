# BAOBAB-to-Python Host Simulator Mapping

This mapping tracks how BAOBAB Oracle packages/configurations map to the modular Python services in `backend/app/`.
When you supply `BAOBAB SCHEMA.txt`, the verified package body rules will be populated here.

| BAOBAB Source Object / Parameter | Confidence | Python Module & Service | Notes |
|---|---|---|---|
| `AUTHORIZEACCTBALANCESTRANS` | CONFIGURATION-BASED | `host_engine.py` -> `HostTransactionProcessor` | Controls Step 21 available balance + overdraft check; configurable in **Host Configuration** UI |
| `CHECKCARDLIMITS` (`ATH_CARDLIMIT`) | CONFIGURATION-BASED | `host_engine.py` -> `HostTransactionProcessor` | Controls Step 19 card per-tx, daily, weekly, monthly limits |
| `CHECKACCT2CARDLIMITS` | CONFIGURATION-BASED | `host_engine.py` -> `HostTransactionProcessor` | Controls Step 20 account limit evaluation |
| `DEFAULTREQUESTFUNCTION` | CONFIGURATION-BASED | `host_engine.py` -> `HostTransactionProcessor.process_transaction` | Central entry point for all TIC/ISO requests |
| `DEFAULTRESPONSEFUNCTION` | CONFIGURATION-BASED | `iso_tic.py` -> `build_tic_message` | Formats outgoing Compass Plus TW v2.164e response |
| `POSRESPONSECONTROLFUNCTION` | CONFIGURATION-BASED | `host_engine.py` -> `_finalize_transaction` | Populates `F39` (5-char TIC response) and `F105` (balance data) |
| `BAOBAB.ACC_1058` .. `ACC_1395` | UNKNOWN (Awaiting `BAOBAB SCHEMA.txt`) | `host_engine.py` | Package bodies not yet uploaded; ready for reverse-engineering |
