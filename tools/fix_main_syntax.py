#!/usr/bin/env python3
"""
tools/fix_main_syntax.py
1. Fixes the unclosed parenthesis in backend/app/main.py for CorrelationTraceMiddleware.
2. Creates backend/conftest.py to ensure `app` is always importable when running pytest from any directory.
3. Automatically runs py_compile to verify syntax.
"""

from pathlib import Path
import py_compile
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
MAIN_FILE = BASE_DIR / "backend" / "app" / "main.py"
CONFTEST_FILE = BASE_DIR / "backend" / "conftest.py"

CLEAN_MAIN_CODE = '''"""
main.py
FastAPI Application Entry Point connecting core banking switch modules,
Soft-HSM adapters, wire codecs, and correlation trace middleware.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api_routes import router
from app.routers.institutions_router import router as institutions_router
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
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Rajon Private Banking Host Simulator with Rajon TIC/TCI v2.164e and Thales 10K Soft-HSM Integration",
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


@app.get("/health")
def health_check():
    return {
        "status": "ONLINE",
        "application": settings.APP_NAME,
        "hsm_mode": settings.HSM_MODE,
        "log_raw_data": getattr(settings, "LOG_RAW_DATA", True),
    }
'''

CONFTEST_CODE = '''"""
backend/conftest.py — Ensures backend directory is in sys.path for pytest
"""
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
'''


def main() -> int:
    print("=" * 70)
    print("  FIXING backend/app/main.py & CREATING backend/conftest.py")
    print("=" * 70)

    # 1. Normalize line endings and write clean main.py
    normalized_main = CLEAN_MAIN_CODE.lstrip("\n").replace("\r\n", "\n").replace("\n", "\r\n")
    MAIN_FILE.write_text(normalized_main, encoding="utf-8", newline="")
    print(f"  [FIXED] {MAIN_FILE.relative_to(BASE_DIR)}")

    # 2. Syntax check main.py
    try:
        py_compile.compile(str(MAIN_FILE), doraise=True)
        print("  [OK] backend/app/main.py passed Python syntax verification.")
    except py_compile.PyCompileError as exc:
        print(f"  [ERROR] Syntax error in main.py: {exc}")
        return 1

    # 3. Create conftest.py
    normalized_conftest = CONFTEST_CODE.lstrip("\n").replace("\r\n", "\n").replace("\n", "\r\n")
    CONFTEST_FILE.write_text(normalized_conftest, encoding="utf-8", newline="")
    print(f"  [CREATED] {CONFTEST_FILE.relative_to(BASE_DIR)}")

    print("=" * 70)
    print("  Syntax fix complete.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())