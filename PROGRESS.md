# BAOBAB PRIVATE HOST SIMULATOR — IMPLEMENTATION PROGRESS

Authoritative execution log updated automatically by `tools/patcher.py`.

## Baseline Architecture Indexed
- **Backend**: FastAPI, SQLAlchemy 2.0, Pydantic v2, SQLite/PostgreSQL (`backend/app/`)
- **Core Engine**: `HostTransactionProcessor` (`backend/app/host_engine.py`)
- **Soft-HSM**: `SoftHsmCryptoCore` & `HSMAdapter` (`backend/app/hsm_adapter.py`)
- **Wire Codec**: Compass Plus TW TIC/TCI v2.164e (`backend/app/iso_tic.py`)
- **Frontend**: React 18, TypeScript, Tailwind CSS, 16 views (`frontend/src/`)
<!-- PROGRESS:step00_01 -->
## [2026-11-01 11:47:55] `step00_01` — Bootstrap Reusable Installer & Patcher Framework
- **Touched Files**: `tools/patcher.py`, `PROGRESS.md`, `docs/CONTRACTS.md`
- [x] **Completed**: Created reusable installer engine `tools/patcher.py` with PatcherSession, write_file, patch_file, dry-run, and automatic backup support.
- [x] **Completed**: Initialized `PROGRESS.md` and `docs/CONTRACTS.md`.
- [ ] **Next / Remaining**: Step 0 Script 2 of 2 (`tools/install_step00_02.py`): Add `_backups/` to `.gitignore`, add `LOG_RAW_DATA=True` in `config.py` and `security.py`, and add startup schema synchronization (`schema_sync.py`).
- **Known Issues**: None

<!-- PROGRESS:step01_01 -->
## [2026-11-01 12:03:02] `step01_01` — Add ProcessingSystem, Institution, InstitutionProcessingSystem & BinRange Models, Schemas, and Seeding
- **Touched Files**: `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/seed_data.py`
- [x] **Completed**: Added `ProcessingSystem`, `Institution`, `InstitutionProcessingSystem`, and `BinRange` ORM models to `backend/app/models.py`.
- [x] **Completed**: Added Pydantic v2 schemas (`ProcessingSystemCreate/Update/Out`, `InstitutionCreate/Update/Out`, `InstitutionProcessingSystemCreate/Out`, `BinRangeCreate/Update/Out`) to `backend/app/schemas.py`.
- [x] **Completed**: Added idempotent `seed_processing_systems_and_institutions(db)` in `backend/app/seed_data.py` seeding `ITCL`, `VISA`, `MASTERCARD`, `NPSB`, `INTERNAL`, banks `xBank`, `yBank`, `zBank` (all under `ITCL`), and 4 BIN ranges.
- [ ] **Next / Remaining**: Step 1 Script 2 of 3 (`tools/install_step01_02.py`): Create `backend/app/routers/institutions_router.py`, wire into `main.py`, and add pytest test suite.
- [ ] **Next / Remaining**: Step 1 Script 3 of 3 (`tools/install_step01_03.py`): Create React UI page `InstitutionsAndBinsPage.tsx` and wire navigation in `App.tsx` and `Layout.tsx`.
- **Known Issues**: None

<!-- PROGRESS:step00_02 -->
## [2026-11-01 12:07:31] `step00_02` — Configure LOG_RAW_DATA=True, .gitignore, and Startup Schema Synchronization
- **Touched Files**: `.gitignore`, `backend/app/schema_sync.py`, `backend/app/config.py`, `backend/app/security.py`, `backend/app/iso_tic.py`, `backend/app/hsm_adapter.py`, `backend/app/database.py`, `backend/app/main.py`, `backend/tests/test_host_engine.py`, `backend/tests/test_step00_prerequisites.py`
- [x] **Completed**: Added `_backups/` to `.gitignore`.
- [x] **Completed**: Added `LOG_RAW_DATA: bool = True` to `backend/app/config.py`.
- [x] **Completed**: Updated `security.py`, `iso_tic.py`, and `hsm_adapter.py` so raw PANs, PIN blocks, Track data, and HSM inputs/outputs remain fully visible when `LOG_RAW_DATA=True`.
- [x] **Completed**: Created `backend/app/schema_sync.py` and wired `synchronize_database_schema(engine, Base)` into `init_db()` in `backend/app/database.py`.
- [x] **Completed**: Added automated pytest suite `backend/tests/test_step00_prerequisites.py`.
- [ ] **Next / Remaining**: STEP 1 — Bank, Institution, Processing System (ITCL-first), and BIN Range Management (`install_step01_01.py`, `install_step01_02.py`, `install_step01_03.py`).
- **Known Issues**: None

<!-- PROGRESS:step01_02 -->
## [2026-11-01 12:09:12] `step01_02` — Implement Institutions & Processing Systems API Router and Pytest Suite
- **Touched Files**: `backend/app/routers/institutions_router.py`, `backend/app/main.py`, `backend/tests/test_step01_institutions.py`
- [x] **Completed**: Created `backend/app/routers/institutions_router.py` with endpoints for processing systems, institutions, multi-network links, and BIN range prefix lookups.
- [x] **Completed**: Wired `institutions_router` into `backend/app/main.py`.
- [x] **Completed**: Created automated test suite `backend/tests/test_step01_institutions.py`.
- [ ] **Next / Remaining**: Step 1 Script 3 of 3 (`tools/install_step01_03.py`): Create React UI page `InstitutionsAndBinsPage.tsx` and wire navigation in `App.tsx` and `Layout.tsx`.
- **Known Issues**: None

<!-- PROGRESS:step01_03 -->
## [2026-11-01 12:09:36] `step01_03` — Implement Institutions & BINs React Workbench UI and Navigation
- **Touched Files**: `frontend/src/pages/InstitutionsAndBinsPage.tsx`, `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`
- [x] **Completed**: Created React UI page `frontend/src/pages/InstitutionsAndBinsPage.tsx` with 4 interactive tabs (Member Banks, Processing Systems, Multi-Network Memberships, and BIN Ranges + Live PAN Routing Test).
- [x] **Completed**: Added `/institutions` route in `frontend/src/App.tsx`.
- [x] **Completed**: Added navigation link in `frontend/src/components/Layout.tsx` under CORE BANKING.
- [ ] **Next / Remaining**: STEP 2 — Link Institutions to Payment Objects (Customers, Accounts, Cards, HSM Keys) and Transaction Attributes (`issuer_institution_id`, `acquirer_institution_id`, `ps_code`).
- **Known Issues**: None

<!-- PROGRESS:step03_01 -->
## [2026-11-01 12:11:34] `step03_01` — Add AuditTrail Model, Audit Service, and PUT/DELETE Endpoints for Customers, Accounts, Cards
- **Touched Files**: `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/audit_service.py`, `backend/app/api_routes.py`, `backend/tests/test_step03_crud_and_audit.py`
- [x] **Completed**: Created `AuditTrail` ORM model in `backend/app/models.py` for immutable entity change logging.
- [x] **Completed**: Created `backend/app/audit_service.py` to capture before/after JSON states and diff summaries.
- [x] **Completed**: Added Pydantic v2 schemas (`CustomerUpdate`, `AccountUpdate`, `CardUpdate`, `AuditTrailOut`) in `backend/app/schemas.py`.
- [x] **Completed**: Added PUT and DELETE endpoints with 409 Conflict protection for Customers, Accounts, and Cards in `backend/app/api_routes.py`.
- [x] **Completed**: Added `GET /api/audit-trail` endpoint.
- [x] **Completed**: Added automated Pytest test suite `backend/tests/test_step03_crud_and_audit.py`.
- [ ] **Next / Remaining**: Step 3 Script 2 of 3 (`tools/install_step03_02.py`): Implement PUT/DELETE and audit logging for Host Parameters, Transaction Codes, Card Profiles, Limits, and HSM Key References.
- [ ] **Next / Remaining**: Step 3 Script 3 of 3 (`tools/install_step03_03.py`): Implement frontend Edit Modals, Delete Confirmation Dialogs with 409 error banners, and the Audit Trail Viewer page.
- **Known Issues**: None

<!-- PROGRESS:step03_02 -->
## [2026-11-01 12:11:56] `step03_02` — Add Full CRUD and Audit Trail for Card Profiles, Config Parameters, and HSM Keys
- **Touched Files**: `backend/app/schemas.py`, `backend/app/api_routes.py`, `backend/tests/test_step03_config_crud.py`
- [x] **Completed**: Added CardProfile Pydantic schemas in `backend/app/schemas.py`.
- [x] **Completed**: Added `GET`, `POST`, `PUT`, and `DELETE` endpoints for Card Profiles with 409 conflict checks against cards.
- [x] **Completed**: Added `DELETE` endpoints for Transaction Codes, Response Codes, and Host Parameters with audit logging.
- [x] **Completed**: Added `PUT` and `DELETE` endpoints for HSM Key References with 409 conflict protection against `hsm_operations`.
- [x] **Completed**: Created automated Pytest test suite `backend/tests/test_step03_config_crud.py`.
- [ ] **Next / Remaining**: Step 3 Script 3 of 3 (`tools/install_step03_03.py`): Implement frontend Edit Modals, Delete Confirmation Dialogs, 409 Conflict alerts, and the Audit Trail Viewer page.
- **Known Issues**: None

<!-- PROGRESS:step06 -->
## [2026-11-01 12:15:43] `step06` — Implement PIN, PVV, CVV, ISO PIN Block, and Synthetic Card Personalization Lab
- **Touched Files**: `backend/app/card_crypto_service.py`, `backend/app/schemas.py`, `backend/app/api_routes.py`, `frontend/src/pages/CardCryptoLabPage.tsx`, `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`, `backend/tests/test_step06_card_crypto.py`
- [x] **Completed**: Created `backend/app/card_crypto_service.py` providing Luhn PAN generation/validation, Visa PVV, IBM 3624 offset, CVV, and ISO PIN block calculations.
- [x] **Completed**: Added Pydantic schemas in `backend/app/schemas.py`.
- [x] **Completed**: Added REST endpoints: `POST /api/cards/{id}/pin`, `POST /api/cards/generate-test-card`, `POST /api/crypto/calculate-pvv`, `POST /api/crypto/calculate-cvv`, `POST /api/crypto/pack-pin-block` in `backend/app/api_routes.py`.
- [x] **Completed**: Created React UI workbench `frontend/src/pages/CardCryptoLabPage.tsx` and registered route `/card-lab` in `App.tsx` and `Layout.tsx`.
- [x] **Completed**: Created automated Pytest test suite `backend/tests/test_step06_card_crypto.py`.
- [ ] **Next / Remaining**: STEP 7 — Complete Operation and Cryptographic Log Portal (Correlation ID middleware, `audit_log`, `crypto_events`, granular PIN verification trace, unified log timeline with polling).
- **Known Issues**: None

<!-- PROGRESS:step07 -->
## [2026-11-01 12:16:27] `step07` — Implement Correlation ID Middleware, Granular 6-Step Crypto Trace, and Log Portal
- **Touched Files**: `backend/app/context_trace.py`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/main.py`, `backend/app/hsm_adapter.py`, `backend/app/api_routes.py`, `frontend/src/pages/UnifiedLogPortalPage.tsx`, `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`, `backend/tests/test_step07_log_portal.py`
- [x] **Completed**: Created `ApiAuditLog` and `CryptoEvent` ORM models in `backend/app/models.py`.
- [x] **Completed**: Created `backend/app/context_trace.py` with `CorrelationTraceMiddleware` and `contextvars` trace recording.
- [x] **Completed**: Instrumented `SoftHsmCryptoCore` in `backend/app/hsm_adapter.py` with granular 6-step Visa PVV and PIN translation tracking.
- [x] **Completed**: Added endpoints: `GET /api/logs/timeline`, `GET /api/logs/crypto-events`, and `GET /api/logs/correlation/{id}`.
- [x] **Completed**: Created React UI portal `frontend/src/pages/UnifiedLogPortalPage.tsx` and registered route `/log-portal` in `App.tsx` and `Layout.tsx`.
- [x] **Completed**: Created automated Pytest test suite `backend/tests/test_step07_log_portal.py`.
- [ ] **Next / Remaining**: STEP 8 — Authorizer Rules Engine (safe expression parser, visual rule builder, built-in checks, test rule dry-run).
- **Known Issues**: None

<!-- PROGRESS:step08 -->
## [2026-11-01 12:16:44] `step08` — Implement Configurable Authorizer Rules Engine & Safe Whitelist AST Expression Evaluator
- **Touched Files**: `backend/app/rules_evaluator.py`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/host_engine.py`, `backend/app/api_routes.py`, `frontend/src/pages/AuthorizerRulesPage.tsx`, `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`, `backend/tests/test_step08_authorizer_rules.py`
- [x] **Completed**: Created `backend/app/rules_evaluator.py` providing a safe whitelist AST expression evaluator without unsafe eval/exec.
- [x] **Completed**: Created `AuthorizerRule` ORM model in `backend/app/models.py`.
- [x] **Completed**: Added Pydantic v2 schemas in `backend/app/schemas.py`.
- [x] **Completed**: Integrated custom authorizer rules evaluation stage in `HostTransactionProcessor` before HSM checks.
- [x] **Completed**: Added REST endpoints: `GET/POST/PUT/DELETE /api/authorizer-rules` and `POST /api/authorizer-rules/dry-run` in `backend/app/api_routes.py`.
- [x] **Completed**: Created React UI workbench `frontend/src/pages/AuthorizerRulesPage.tsx` and registered route `/authorizer-rules` in `App.tsx` and `Layout.tsx`.
- [x] **Completed**: Created automated Pytest test suite `backend/tests/test_step08_authorizer_rules.py`.
- [ ] **Next / Remaining**: STEP 9 — Simulator Improvements (Persistent Simulator State across navigation/refresh and Dual-Codec Raw Message Parser for TIC v2.164e and ISO 8583:1987).
- **Known Issues**: None

<!-- PROGRESS:step09 -->
## [2026-11-01 12:16:50] `step09` — Implement Standard ISO 8583:1987 Codec, Dual-Codec Parse-Raw Endpoint & Session Persistence
- **Touched Files**: `backend/app/iso_standard_codec.py`, `backend/app/schemas.py`, `backend/app/api_routes.py`, `frontend/src/pages/SimulatorAndJournal.tsx`, `backend/tests/test_step09_simulator_improvements.py`
- [x] **Completed**: Created `backend/app/iso_standard_codec.py` implementing standard ISO 8583:1987 parsing and building (ASCII/Hex primary and secondary bitmaps).
- [x] **Completed**: Added Pydantic schemas `RawMessageParseRequest` and `RawMessageParseResponse` in `backend/app/schemas.py`.
- [x] **Completed**: Added `POST /api/simulator/parse-raw` endpoint in `backend/app/api_routes.py` with automatic format detection between Compass Plus TIC/TCI v2.164e and Standard ISO 8583:1987.
- [x] **Completed**: Added `sessionStorage` persistence, auto-restore indicator, and reset buttons in `frontend/src/pages/SimulatorAndJournal.tsx`.
- [x] **Completed**: Added Universal Wire Parser modal in `frontend/src/pages/SimulatorAndJournal.tsx` to paste and unpack wire messages directly into the simulator fields.
- [x] **Completed**: Created automated Pytest test suite `backend/tests/test_step09_simulator_improvements.py`.
- [ ] **Next / Remaining**: STEP 10 — HSM Key Management (database-backed key ceremony, 2/3 component XOR key assembly, random key generation with odd parity, institution/switch ownership, and ZMK import).
- **Known Issues**: None

<!-- PROGRESS:step10 -->
## [2026-11-01 12:16:59] `step10` — Implement Split-Component Key Ceremony, Parity Enforcement, and ZMK Key Exchange
- **Touched Files**: `backend/app/key_ceremony_service.py`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/hsm_adapter.py`, `backend/app/seed_data.py`, `backend/app/api_routes.py`, `frontend/src/pages/KeyCeremonyWorkbenchPage.tsx`, `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`, `backend/tests/test_step10_hsm_keys.py`
- [x] **Completed**: Created `backend/app/key_ceremony_service.py` providing DES odd-parity adjustment, 2/3 component XOR assembly, and ZMK import/export.
- [x] **Completed**: Added `clear_key_hex` and `parent_key_id` to `HsmKeyReference` in `backend/app/models.py`.
- [x] **Completed**: Added Pydantic schemas in `backend/app/schemas.py`.
- [x] **Completed**: Enforced strict key resolution in `backend/app/hsm_adapter.py` without silent fallbacks.
- [x] **Completed**: Added REST endpoints: `POST /api/hsm/ceremony/assemble-components`, `POST /api/hsm/ceremony/generate-random`, `POST /api/hsm/ceremony/export-under-zmk`, `POST /api/hsm/ceremony/import-under-zmk`.
- [x] **Completed**: Created React UI workbench `frontend/src/pages/KeyCeremonyWorkbenchPage.tsx` and registered route `/key-ceremony` in `App.tsx` and `Layout.tsx`.
- [x] **Completed**: Created automated Pytest test suite `backend/tests/test_step10_hsm_keys.py`.
- [ ] **Next / Remaining**: STEP 11 — Routing and Network Simulation (On-Us/Off-Us routing, SimulatedNetworkAdapter, timeout handling, and cross-zone PIN translation).
- [ ] **Next / Remaining**: STEP 12 — Clearing and Settlement (Authorization holds, 0220 advices, 0420 reversals, daily cutover, institution fee reconciliation, and settlement reports).
- **Known Issues**: None

<!-- PROGRESS:step12 -->
## [2026-11-01 12:17:11] `step12` — Implement Clearing and Settlement Engine, Daily Cutover, Interchange Fees, and Net Positions
- **Touched Files**: `backend/app/settlement_service.py`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/host_engine.py`, `backend/app/api_routes.py`, `frontend/src/pages/ClearingAndSettlementPage.tsx`, `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`, `backend/tests/test_step12_settlement.py`
- [x] **Completed**: Created `backend/app/settlement_service.py` providing dual-balance hold vs clear, interchange fee calculations, daily cutover batches, and multilateral net settlement.
- [x] **Completed**: Created `SettlementBatch`, `SettlementEntry`, and `SettlementPosition` ORM models in `backend/app/models.py`.
- [x] **Completed**: Added Pydantic schemas in `backend/app/schemas.py`.
- [x] **Completed**: Added 0220 Financial Advice clearing presentment handling in `backend/app/host_engine.py`.
- [x] **Completed**: Added REST endpoints: `GET/POST /api/settlement/cutover`, `GET /api/settlement/batches`, `GET /api/settlement/reconciliation`, `POST /api/settlement/run-scenarios`.
- [x] **Completed**: Created React UI console `frontend/src/pages/ClearingAndSettlementPage.tsx` and registered route `/settlement` in `App.tsx` and `Layout.tsx`.
- [x] **Completed**: Created automated Pytest test suite `backend/tests/test_step12_settlement.py`.
- **Known Issues**: None

<!-- PROGRESS:repair_all -->
## [2026-11-01 12:20:41] `repair_all` — Repair Anchors for Schemas, Host Engine, Models, BankingEntities, and Simulator
- **Touched Files**: `backend/app/schemas.py`, `backend/app/models.py`, `backend/app/host_engine.py`, `backend/app/api_routes.py`, `frontend/src/pages/BankingEntities.tsx`, `frontend/src/pages/SimulatorAndJournal.tsx`
- [x] **Completed**: Fixed CustomerOut schema in `backend/app/schemas.py`.
- [x] **Completed**: Fixed NetworkProfile simulation columns in `backend/app/models.py`.
- [x] **Completed**: Fixed Transaction model assignment in `backend/app/host_engine.py`.
- [x] **Completed**: Fixed paginated `/accounts` route in `backend/app/api_routes.py`.
- [x] **Completed**: Cleanly replaced `frontend/src/pages/BankingEntities.tsx` consolidating all features from Steps 2, 3, 4, and 5.
- [x] **Completed**: Fixed pagination footer in `frontend/src/pages/SimulatorAndJournal.tsx`.
- **Known Issues**: None

<!-- PROGRESS:fix_modern_maintenance -->
## [2026-11-01 23:05:59] `fix_modern_maintenance` — Modern Customer Maintenance 360 + Search Mode Tabs + Card Reassign + Customer Tab Hardening
- **Touched Files**: `backend/app/api_routes.py`, `backend/app/schemas.py`, `frontend/src/pages/CustomerDataMaintenancePage.tsx`, `frontend/src/pages/BankingEntities.tsx`
- [x] **Completed**: Replaced `/api/maintenance/search` with mode-aware search (customer | pan | account | all) and strict PAN matching to eliminate multi-card noise.
- [x] **Completed**: Added `PUT /api/cards/{id}/reassign-customer` for moving a card to another CIF.
- [x] **Completed**: Completely rewrote `CustomerDataMaintenancePage.tsx` with modern tabbed search, live stats, balance editor, PIN change, link/unlink, promote primary, and customer reassignment modals.
- [x] **Completed**: Hardened `CustomersPage` load path against institutions failure and non-array responses.
- [x] **Completed**: Extended `CardUpdate` schema with optional `customer_id`.
- [ ] **Next / Remaining**: Optional: add row-level locking + full dual-balance holds in host_engine (separate engine hardening step).
- [ ] **Next / Remaining**: Optional: React Query migration for all list pages.
- **Known Issues**: None

<!-- PROGRESS:fix_customers_white_screen -->
## [2026-11-01 23:16:20] `fix_customers_white_screen` — Remove dead handleUpdateAccount (editAcct ReferenceError) + harden CustomersPage load
- **Touched Files**: `frontend/src/pages/BankingEntities.tsx`
- [x] **Completed**: Removed dead handleUpdateAccount that referenced undeclared editAcct (root cause of white screen on /#/customers).
- [x] **Completed**: Hardened CustomersPage load() against institutions API failure and non-array responses.
- **Known Issues**: None

<!-- PROGRESS:tx_log_viewer_v3 -->
## [2026-11-02 14:12:28] `tx_log_viewer_v1_v2_v3` — Enterprise Transaction Log Viewer & TIC v2.164e Inspector
- **Touched Files**: `backend/app/tic_decoder_engine.py`, `backend/app/models.py`, `backend/app/host_engine.py`, `backend/app/database_indexes_tx_logs.py`, `backend/app/routers/transaction_logs_router.py`, `frontend/src/pages/TransactionLogViewerPage.tsx`, `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`, `backend/tests/test_transaction_log_viewer.py`
- [x] **Completed**: Automatic DB loading, configurable auto-refresh timer with countdown & pause/resume, 6 summary cards, 20 server-side filters, column customizer, and 6-tab transaction investigation workbench.

<!-- PROGRESS:simulator_workbench_v2 -->
## [2026-11-05 14:02:13] `simulator_workbench_v2` - Simulator workbench upgrade
- **Touched Files**: `backend/app/simulator_workbench_router.py`, `backend/app/main.py`, `frontend/src/pages/SimulatorAndJournal.tsx`, `backend/tests/test_simulator_workbench.py`
- [x] **Completed**: Paste or load a raw TIC / ISO 8583 message (text box, drag and drop, or file) and unpack every field into the editor.
- [x] **Completed**: STAN (DE11) and RRN (DE37) start from the next free values after the last transaction in the database.
- [x] **Completed**: Time fields have Now buttons; a Date and time tab sets all of them at once.
- [x] **Completed**: Last session is restored on open; named cases can be saved, opened and deleted.
- [x] **Completed**: Removed the Load Real Backend Test Scenario bar and redesigned the page.
- **Known Issues**: None
