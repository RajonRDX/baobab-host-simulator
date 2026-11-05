# BAOBAB PRIVATE HOST SIMULATOR — PUBLIC CONTRACTS & INTERFACES

Tracks database tables, columns, API routes, schemas, settings, and React routes.

## Baseline Contracts (Pre-Step 0)
- **Database Tables (21)**: `customers`, `accounts`, `account_ledger`, `account_limits`, `card_profiles`, `cards`, `card_accounts`, `card_limits`, `pin_profiles`, `emv_profiles`, `transaction_codes`, `transaction_code_fields`, `host_parameters`, `response_codes`, `network_profiles`, `hsm_key_references`, `hsm_operations`, `hsm_audit_logs`, `transactions`, `transaction_checks`, `transaction_messages`, `transaction_reversals`, `system_logs`, `notifications`.
- **Core Settings**: `APP_NAME`, `APP_ENV`, `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `DATABASE_URL`, `HSM_MODE`, `HSM_REMOTE_URL`, `HSM_HEADER_LENGTH`, `CORS_ORIGINS`.
<!-- CONTRACT:step00_01 -->
## `step00_01` — Installer & Patcher Framework (`tools/patcher.py`)
- **Module**: `tools/patcher.py`
- **Constants**: `BASE_DIR = Path(r'E:\HOST_VSCODE\host-simulator')`, `BACKUP_ROOT`, `PROGRESS_FILE`, `CONTRACTS_FILE`
- **Classes/Functions**: `PatcherSession`, `write_file(rel_path, content, dry_run=False)`, `patch_file(rel_path, edits, dry_run=False)`, `parse_installer_args(description)`

<!-- CONTRACT:step01_01 -->
## `step01_01` — Step 1.1 — Processing Systems, Institutions & BIN Ranges (Database & Schemas)
- **Table `processing_systems`**: `id`, `ps_code` (`ITCL`, `VISA`, `MASTERCARD`, `NPSB`, `INTERNAL`), `name`, `system_type`, `message_format`, `enabled`, `is_default`, `configuration`, `created_at`, `updated_at`.
- **Table `institutions`**: `id`, `institution_code` (`XBANK`, `YBANK`, `ZBANK`, `IFIC`, ...), `name`, `short_name`, `acquirer_id` (`DE32`), `forwarding_id` (`DE33`), `role` (`ISSUER`/`ACQUIRER`/`BOTH`), `processing_system_id` (FK -> `ITCL` by default), `country_code`, `currency`, `settlement_account_number`, `status`, `configuration`, `created_at`, `updated_at`.
- **Table `institution_processing_systems`**: `id`, `institution_id`, `processing_system_id`, `member_id`, `acquirer_id`, `network_identifier`, `issuer_enabled`, `acquirer_enabled`, `message_format`, `routing_configuration`, `status`, `effective_from`, `effective_to`, `created_at`, `updated_at`.
- **Table `bin_ranges`**: `id`, `bin_prefix`, `bin_low`, `bin_high`, `pan_length`, `institution_id`, `processing_system_id`, `card_type`, `card_product`, `scheme`, `country_code`, `currency`, `is_on_us`, `status`, `created_at`, `updated_at`.

<!-- CONTRACT:step00_02 -->
## `step00_02` — Raw Data Configuration & Non-Destructive Schema Sync
- **Setting**: `settings.LOG_RAW_DATA: bool = True` in `backend/app/config.py`
- **Function**: `synchronize_database_schema(engine, Base) -> Dict[str, List[str]]` in `backend/app/schema_sync.py`
- **Endpoint**: `GET /health` returns `{'status': 'ONLINE', 'application': ..., 'hsm_mode': ..., 'log_raw_data': True}`
- **Behavior**: When `LOG_RAW_DATA=True`, `mask_pan()`, `sanitize_dict()`, `mask_raw_tic_message()`, `decode_tic_message()`, and `HSMAdapter` preserve unmasked synthetic test values.

<!-- CONTRACT:step01_02 -->
## `step01_02` — Step 1.2 — Processing Systems & Institutions API Contracts
- **GET /api/processing-systems**: Returns all active processing switches.
- **POST /api/processing-systems**: Registers a new processing system.
- **GET /api/institutions**: Returns all member banks with their primary processing system code.
- **POST /api/institutions**: Creates a new bank (defaults to **ITCL** if `processing_system_id` is omitted).
- **GET /api/institutions/{inst_id}/networks**: Lists secondary network participations.
- **POST /api/institutions/{inst_id}/networks**: Links a bank to VISA, Mastercard, or NPSB.
- **GET /api/bin-ranges**: Lists BIN prefixes.
- **GET /api/bin-ranges/lookup/{pan}**: Resolves a PAN to its issuing bank and processing system.

<!-- CONTRACT:step01_03 -->
## `step01_03` — Step 1.3 — Institutions & BINs Frontend Workbench
- **React Route**: `/#/institutions` (`InstitutionsAndBinsPage`)
- **Navigation**: Added under 'CORE BANKING' as '1.5. Banks & Switch BINS'.
- **Tabs**: Member Banks (defaulting creation to ITCL), Processing Systems, Multi-Network Links, and BIN Prefix PAN Router.

<!-- CONTRACT:step03_01 -->
## `step03_01` — Step 3.1 — Full CRUD & Audit Trail (Core Entities)
- **Table `audit_trail`**: `id`, `entity_type`, `entity_id`, `action` (`CREATE`/`UPDATE`/`DELETE`), `performed_by`, `before_state` (JSON), `after_state` (JSON), `change_summary`, `created_at`.
- **PUT /api/customers/{id}**: Updates customer profile with audit logging.
- **DELETE /api/customers/{id}**: Deletes customer (returns 409 Conflict if linked accounts or cards exist unless `?force=true`).
- **PUT /api/accounts/{id}**: Updates account metadata/overdraft.
- **DELETE /api/accounts/{id}**: Deletes account (returns 409 Conflict if balance > 0 or ledger entries exist unless `?force=true`).
- **PUT /api/cards/{id}**: Updates card details.
- **DELETE /api/cards/{id}**: Deletes card (returns 409 Conflict if historical journal entries exist unless `?force=true`).
- **GET /api/audit-trail**: Returns filtered audit trail records.

<!-- CONTRACT:step03_02 -->
## `step03_02` — Step 3.2 — Configuration & Cryptographic Resource CRUD and Audit
- **GET /api/card-profiles**: Lists all configured card profiles.
- **POST /api/card-profiles**: Creates a new card profile.
- **PUT /api/card-profiles/{id}**: Updates profile channel permissions with audit logging.
- **DELETE /api/card-profiles/{id}**: Removes profile (returns 409 Conflict if assigned to active cards unless `?force=true`).
- **DELETE /api/transaction-codes/{id}**: Decommission transaction codes.
- **DELETE /api/response-codes/{id}**: Removes response code mapping.
- **DELETE /api/host-parameters/{id}**: Removes host authorization parameter.
- **PUT /api/hsm/keys/{id}**: Updates HSM key name, status, or usage.
- **DELETE /api/hsm/keys/{id}**: Removes key reference (returns 409 Conflict if historical cryptographic operations reference key unless `?force=true`).

<!-- CONTRACT:step06 -->
## `step06` — Step 6 — PIN, PVV and Card Generation Lab Contracts
- **POST /api/cards/{card_id}/pin**: Recalculates card PVV/offset, resets retry counter, updates `pin_changed_at`, logs audit entry.
- **POST /api/cards/generate-test-card**: Generates Luhn-valid synthetic PAN under bank BIN, computes PVV and CVV, seeds card, account link, limits, and EMV profiles.
- **POST /api/crypto/calculate-pvv**: Visa PVV calculation with intermediate 3DES and decimalization trace.
- **POST /api/crypto/calculate-cvv**: CVV1/CVV2 calculation under CVK.
- **POST /api/crypto/pack-pin-block**: Packs clear PIN into ISO-0, ISO-1, or ISO-3 encrypted block under AWK.
- **React Route**: `/#/card-lab` (`CardCryptoLabPage`).

<!-- CONTRACT:step07 -->
## `step07` — Step 7 — Operational & Cryptographic Log Portal Contracts
- **Header `X-Correlation-ID`**: Propagated across every HTTP request and tied to database logs.
- **Table `api_audit_logs`**: `correlation_id`, `http_method`, `path`, `status_code`, `duration_ms`, `request_body`, `response_body`.
- **Table `crypto_events`**: `correlation_id`, `operation_type`, `step_number`, `step_name`, `key_id`, `key_kcv`, `raw_input`, `raw_output`, `expected_output`, `status`.
- **GET /api/logs/timeline**: Aggregates transactions, API logs, and HSM operations chronologically.
- **GET /api/logs/correlation/{id}**: Returns correlated API request and granular 6-step HSM transformations.
- **React Route**: `/#/log-portal` (`UnifiedLogPortalPage`).

<!-- CONTRACT:step08 -->
## `step08` — Step 8 — Authorizer Rules Engine Contracts
- **Table `authorizer_rules`**: `id`, `rule_code`, `name`, `priority`, `stage`, `rule_mode`, `expression`, `action` (`DECLINE`/`APPROVE`/`FLAG`), `response_code`, `message`, `hit_count`, `enabled`.
- **GET /api/authorizer-rules**: Lists configured custom authorizer rules.
- **POST /api/authorizer-rules**: Creates rule with expression syntax validation.
- **POST /api/authorizer-rules/dry-run**: Safely tests AST expressions against arbitrary JSON transaction context payloads.
- **Host Pipeline**: Custom authorizer rules execute before HSM verification; matching DECLINE rules stop processing and return custom response codes with `TransactionCheck` logging.
- **React Route**: `/#/authorizer-rules` (`AuthorizerRulesPage`).

<!-- CONTRACT:step09 -->
## `step09` — Step 9 — Simulator Improvements & Dual-Codec Wire Parser
- **Module**: `backend/app/iso_standard_codec.py` (`decode_iso8583_1987`, `build_iso8583_1987`).
- **POST /api/simulator/parse-raw**: Accepts raw wire string, auto-detects `TIC_V2164E` (A4M) or `ISO8583_1987` (Hex bitmap), returns parsed fields and matched transaction code.
- **Client-Side Persistence**: Simulator fields, helper PIN, and transaction checks persist in browser `sessionStorage` (`BAOBAB_SIMULATOR_STATE`), surviving navigation and page refreshes.

<!-- CONTRACT:step10 -->
## `step10` — Step 10 — HSM Key Ceremony & Management Contracts
- **Model Columns**: `hsm_key_references.clear_key_hex`, `hsm_key_references.parent_key_id`.
- **POST /api/hsm/ceremony/assemble-components**: Assembles 2 or 3 clear components via XOR, verifies odd parity, computes KCVs, saves key to database.
- **POST /api/hsm/ceremony/generate-random**: Generates 128/192-bit DES odd-parity key.
- **POST /api/hsm/ceremony/export-under-zmk**: Encrypts working key under ZMK for exchange.
- **POST /api/hsm/ceremony/import-under-zmk**: Decrypts working key under ZMK, saves key to database.
- **Strict Key Resolution**: `HSMAdapter._resolve_key` raises error if key identifier is missing rather than falling back to default.
- **React Route**: `/#/key-ceremony` (`KeyCeremonyWorkbenchPage`).

<!-- CONTRACT:step12 -->
## `step12` — Step 12 — Clearing, Settlement & Reconciliation Contracts
- **Module**: `backend/app/settlement_service.py` (`execute_daily_cutover`, `calculate_fees`, `get_reconciliation_summary`).
- **Tables**: `settlement_batches`, `settlement_entries`, `settlement_positions`.
- **GET /api/settlement/batches**: Lists closed settlement batches.
- **POST /api/settlement/cutover**: Closes the current transaction window, computes interchange/switch fees, and derives net bank positions.
- **GET /api/settlement/reconciliation**: Returns totals for approved, reversed, settled, and pending clearing transactions.
- **POST /api/settlement/run-scenarios**: Automatically generates multi-bank financial transactions for clearing regression testing.
- **React Route**: `/#/settlement` (`ClearingAndSettlementPage`).

<!-- CONTRACT:fix_modern_maintenance -->
## `fix_modern_maintenance` — Modern Customer Maintenance 360 Contracts
- **GET /api/maintenance/search?q=&mode=customer|pan|account|all** — mode-isolated 360 search with de-duplicated cards and auto-healed CardAccount links.
- **PUT /api/cards/{id}/reassign-customer** body `{customer_id}` — move card ownership.
- **React Route**: `/#/customer-maintenance` (`CustomerDataMaintenancePage`) with search mode tabs.
- Balance edit via existing **PUT /api/accounts/{id}** (`available_balance`, `ledger_balance`).
- PIN change via existing **POST /api/cards/{id}/pin**.

<!-- CONTRACT:simulator_workbench_v2 -->
## `simulator_workbench_v2` - Simulator workbench
- **Table**: `simulator_saved_cases` (id, name unique, description, mti, transaction_code, clear_pin_helper, fields JSON, enabled_fields JSON, created_at, updated_at)
- **GET /api/simulator-workbench/next-ids**: last STAN/RRN in `transactions` and the next free values
- **GET/POST /api/simulator-workbench/cases**, **GET/PUT/DELETE /api/simulator-workbench/cases/{id}**: saved simulator cases (POST returns 409 for a duplicate name unless `overwrite` is true)
- **Browser storage**: key `BAOBAB_SIMULATOR_STATE_V2` (localStorage) holds the last simulator session
