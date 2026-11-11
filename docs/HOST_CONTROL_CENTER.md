# Rajon Host Control Center - quick guide

Menu: **14. Host Control Center**. It replaces the old *Host Configuration* table and menu *7.5 Authorizer Rules*: both are now the **Rules & Checks** tab.

## Where it sits in the authorization pipeline

```
card / customer / account checks
  -> Local Host policy            (host status, hours, source, channel, transaction matrix, currency, country, MCC, owner, velocity)
  -> Authorization profile limits (existing limit engine)
  -> Authorizer rules             (existing)
  -> Algo Control  PRE_AUTH       (your Python / SQL blocks)
  -> PIN / CVV / HSM checks
  -> balance + legacy limits
  -> Algo Control  POST_AUTH      (your Python / SQL blocks)
  -> approve + post to the ledger
```

## Local Host tab

* Left: **Global Default** plus one entry per bank. A bank inherits the Global policy section by section.
* On a bank, switch **Override** on for a section to give that bank its own values. Sections left off follow Global.
* Sections: Host status & defaults, Channel control, Source systems (ON_US, ITCL, NPSB, VISA, MASTERCARD ...),
  Transaction matrix, Cross-border, MCC, Terminal owners, Velocity.
* **Policy simulator** at the bottom evaluates a sample transaction against the saved policy.
* Changes apply to the next transaction immediately after **Save policy**. No restart needed.

Default decline codes: 57 not permitted, 61 exceeds amount, 13 below minimum, 65 velocity, 91 host unavailable, 58 terminal owner.

## Rules & Checks tab

Three layers, from simple to advanced: built-in checks, simple rules, Algo Control.

**Built-in checks** - switches for the protections the host engine really reads:

| Check | What it does | Decline |
|---|---|---|
| Account balance check | balance + overdraft must cover a debit | 51 |
| Card limit check | per-transaction and daily limits of the card (menu 5) | 61 |
| Account limit check | per-transaction and daily limits of the account (menu 6) | 61 |

Switching one OFF applies to every bank immediately. (Older versions of the page set the parameter to inactive but the engine
ignored that, so a check never really turned off. Fixed.) Request router / response builder / POS response control are stored as
reference only: the engine does not read them.

**My simple rules** - "if this, then decline / approve / flag" without code. Build the condition with dropdowns
(field, operator, value, ALL / ANY) or write the expression yourself; see the plain-words summary, test it on a real card, save.
Fields: `amount trancode currency hour mcc terminal_id is_foreign card_status account_balance daily_used institution.code
acquirer_bank ps_name bin channel` ... Rules run in priority order before the PIN / HSM checks. Anything more complex
(per bank, per card profile, history, block card / customer) belongs in Algo Control.

## Algo Control tab

An algo is a Python or SQL block with a scope (whole host, one bank, or one card profile), a stage and a mode.

| Setting | Meaning |
|---|---|
| Stage PRE_AUTH | runs before PIN / HSM checks (cheap risk checks, velocity, blocks) |
| Stage POST_AUTH | runs after balance and limits passed, just before posting (can see `account.balance_after`) |
| Mode MONITOR | shadow mode: logs what it WOULD do, never declines or blocks. Start here, then switch to ENFORCE |
| Priority | lower number runs first |
| On error | SKIP = ignore a broken algo (fail-open), DECLINE = fail-closed |

### Python

```python
if tx.channel == 'ATM' and tx.amount > 20000 and (tx.hour >= 23 or tx.hour < 5):
    decline('57', 'High value ATM cash at night')

if history.declines('10m', 'card') >= 3:
    block_card('3 declines in 10 minutes', '62')

if customer.risk == 'HIGH' and tx.is_foreign and tx.amount > 20000:
    block_customer('HIGH risk customer abroad', '62')

if customer.is_vip and tx.amount < 50000:
    approve('VIP allow-list')        # stops the other algos; PIN, balance and limits still apply

flag('just watch this one')          # logs a warning, the transaction continues
return True                          # applies the default action set in the form
```

Decisions: `approve()`, `decline(rc, msg)`, `block_card(msg, rc)`, `block_customer(msg, rc)`, `flag(msg)`, `log(text)`.
`history.count / declines / approved / sum_amount / distinct / last` and `sql("SELECT ...", **params)` are available.
History excludes the transaction being authorized.

Not allowed: imports, `while`, `class`, `**`, file / network access, names starting with `_`. `range()` is limited to 2000 items.
Each run has a 400 ms / instruction budget.

### SQL

One read-only SELECT. It matches when the first column of the first row is true / non-zero.

```sql
SELECT COUNT(*) >= 3 FROM transactions
WHERE card_id = :card_id AND authorization_status = 'DECLINED' AND transaction_datetime >= :since_15m
```

Or choose the outcome from SQL by returning the columns `action`, `response_code`, `message`:

```sql
SELECT 'BLOCK_CARD' AS action, '62' AS response_code, 'Many terminals' AS message
WHERE (SELECT COUNT(DISTINCT terminal_id) FROM transactions
       WHERE card_id = :card_id AND transaction_datetime >= :since_1h) >= 4
```

### Fields Reference button

Lists every field (Python path and SQL parameter), the helpers and the SQL tables. Click a name to insert it in the editor.
Examples: `tx.amount`, `tx.hour` (terminal time from DE12, else host clock), `tx.host_hour` (always host clock),
`tx.channel`, `terminal.owner`, `bank.name`, `profile.auth_name`, `customer.risk`, `card.status`, `account.balance`.

### Actions

| Action | Effect (ENFORCE mode) |
|---|---|
| DECLINE | declines with the response code |
| BLOCK_CARD | sets the card to BLOCKED (audit logged) and declines; later transactions decline with 05 |
| BLOCK_CUSTOMER | sets the customer to BLOCKED (audit logged) and declines |
| APPROVE | risk-layer allow-list: skips the remaining algos. It never bypasses PIN, HSM, limit or balance checks |
| FLAG | writes a warning to the system log and continues |

Every save keeps a version (History button) that you can restore. The execution log lists matches and errors.

## Operations

* Host clock offset: set the environment variable `HOST_UTC_OFFSET_HOURS` (default 6).
* A bug in an algo or in the policy engine can never take the host down: errors are logged and the transaction continues
  (unless the algo is set to fail-closed).
* Algos are written by an authenticated administrator and run inside the host process in a restricted sandbox.
  Keep the admin login private.
