"""
context_trace.py — Request-Scoped Correlation and Cryptographic Event Tracing
Uses contextvars to trace end-to-end execution across API routes and HSM cryptographic steps.
"""

from contextvars import ContextVar
import json
import time
from typing import Any, Dict, List, Optional
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Request-scoped correlation ID
current_correlation_id: ContextVar[str] = ContextVar("current_correlation_id", default="")
# Request-scoped crypto event collector
current_crypto_trace: ContextVar[List[Dict[str, Any]]] = ContextVar("current_crypto_trace", default=[])


def get_correlation_id() -> str:
    cid = current_correlation_id.get()
    if not cid:
        cid = f"CORR-{uuid.uuid4().hex[:12].upper()}"
        current_correlation_id.set(cid)
    return cid


def record_crypto_step(
    operation_type: str,
    step_number: int,
    step_name: str,
    key_id: Optional[str] = None,
    key_kcv: Optional[str] = None,
    raw_input: Optional[str] = None,
    raw_output: Optional[str] = None,
    expected_output: Optional[str] = None,
    status: str = "COMPLETED",
    details: Optional[Dict[str, Any]] = None,
    duration_ms: int = 1,
) -> Dict[str, Any]:
    """Record an individual cryptographic transformation step into the current request trace."""
    event = {
        "correlation_id": get_correlation_id(),
        "operation_type": operation_type,
        "step_number": step_number,
        "step_name": step_name,
        "key_id": key_id,
        "key_kcv": key_kcv,
        "raw_input": raw_input,
        "raw_output": raw_output,
        "expected_output": expected_output,
        "status": status,
        "details": details or {},
        "duration_ms": max(1, duration_ms),
    }
    trace = current_crypto_trace.get()
    trace.append(event)
    return event


class CorrelationTraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Establish or extract correlation ID
        corr_id = request.headers.get("X-Correlation-ID") or f"CORR-{uuid.uuid4().hex[:12].upper()}"
        token_corr = current_correlation_id.set(corr_id)
        token_trace = current_crypto_trace.set([])

        t0 = time.perf_counter()
        
        # Read body safely for API auditing (skip websockets)
        req_body = None
        if request.url.path.startswith("/api") and not request.url.path.startswith("/api/ws"):
            try:
                body_bytes = await request.body()
                if body_bytes:
                    try:
                        req_body = json.loads(body_bytes.decode("utf-8"))
                    except Exception:
                        req_body = {"raw": body_bytes.decode("utf-8", errors="replace")}
            except Exception:
                pass

        try:
            response: Response = await call_next(request)
        except Exception:
            current_correlation_id.reset(token_corr)
            current_crypto_trace.reset(token_trace)
            raise

        dur_ms = max(1, int((time.perf_counter() - t0) * 1000))
        response.headers["X-Correlation-ID"] = corr_id

        # 2. Persist ApiAuditLog and CryptoEvents asynchronously or at end of request
        if request.url.path.startswith("/api") and not request.url.path.startswith("/api/ws"):
            try:
                from app.database import SessionLocal
                from app.models import ApiAuditLog, CryptoEvent
                
                db = SessionLocal()
                try:
                    audit = ApiAuditLog(
                        correlation_id=corr_id,
                        http_method=request.method,
                        path=request.url.path,
                        status_code=response.status_code,
                        client_ip=request.client.host if request.client else "127.0.0.1",
                        user_agent=request.headers.get("User-Agent", "Unknown"),
                        duration_ms=dur_ms,
                        request_headers=dict(request.headers),
                        request_body=req_body,
                        response_body={"status": response.status_code},
                    )
                    db.add(audit)
                    
                    # Flush crypto trace events collected during this request
                    trace_events = current_crypto_trace.get()
                    for ev in trace_events:
                        db.add(CryptoEvent(**ev))
                    
                    db.commit()
                except Exception:
                    db.rollback()
                finally:
                    db.close()
            except Exception:
                pass

        current_correlation_id.reset(token_corr)
        current_crypto_trace.reset(token_trace)
        return response
