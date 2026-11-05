"""
main.py
FastAPI Application Entry Point connecting core banking switch modules,
Soft-HSM adapters, wire codecs, and correlation trace middleware.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api_routes import router
from app.routers.institutions_router import router as institutions_router
# [PATCH lmk_centric_key_mgmt:main_router]
from app.routers.lmk_key_management_router import router as lmk_key_management_router
# [PATCH tx_log_viewer_v2:main_router_import]
from app.routers.transaction_logs_router import (
    router as transaction_logs_router,
    backfill_historical_transaction_metadata,
)
from app.config import settings
from app.context_trace import CorrelationTraceMiddleware
from app.database import SessionLocal, init_db
from app.seed_data import seed_initial_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_initial_data(db)
# [PATCH tx_log_viewer_v2:main_startup_backfill]
        backfill_historical_transaction_metadata(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="BAOBAB-Inspired Private Banking Host Simulator with Compass Plus TW TIC/TCI v2.164e and Thales 10K Soft-HSM Integration",
    lifespan=lifespan,
)

# Correlation Tracing Middleware (must be added before CORS so X-Correlation-ID is on all responses)
app.add_middleware(CorrelationTraceMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID"],
)

app.include_router(router)
app.include_router(institutions_router)
app.include_router(lmk_key_management_router)
# [PATCH tx_log_viewer_v2:main_include_router]
app.include_router(transaction_logs_router)
# [PATCH simulator_workbench_v2:main_router]
from app.simulator_workbench_router import router as simulator_workbench_router
app.include_router(simulator_workbench_router)


@app.get("/health")
def health_check():
    return {
        "status": "ONLINE",
        "application": settings.APP_NAME,
        "hsm_mode": settings.HSM_MODE,
        "log_raw_data": getattr(settings, "LOG_RAW_DATA", True),
    }
