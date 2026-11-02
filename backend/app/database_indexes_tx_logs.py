"""
database_indexes_tx_logs.py — Safe Additive Performance Indexes for Transaction Log Viewer
Creates composite and single-column indexes if they do not already exist.
Never drops or alters existing data.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS ix_tx_logs_created_at_desc ON transactions (created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_tx_logs_auth_tx_status ON transactions (authorization_status, transaction_status)",
    "CREATE INDEX IF NOT EXISTS ix_tx_logs_rrn_stan ON transactions (rrn, stan)",
    "CREATE INDEX IF NOT EXISTS ix_tx_logs_correlation_id ON transactions (correlation_id)",
    "CREATE INDEX IF NOT EXISTS ix_tx_logs_masked_pan ON transactions (masked_pan)",
    "CREATE INDEX IF NOT EXISTS ix_tx_logs_ps_code_mti_rc ON transactions (ps_code, mti, response_code)",
    "CREATE INDEX IF NOT EXISTS ix_tx_logs_issuer_acquirer ON transactions (issuer_institution_id, acquirer_institution_id)",
    "CREATE INDEX IF NOT EXISTS ix_tx_logs_terminal_merchant ON transactions (terminal_id, merchant_id)",
    "CREATE INDEX IF NOT EXISTS ix_tx_logs_source_account ON transactions (source_account)",
    "CREATE INDEX IF NOT EXISTS ix_tx_trace_tx_id_order ON transaction_trace_events (transaction_id, event_order)",
]


def ensure_transaction_log_indexes(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in INDEX_STATEMENTS:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass
