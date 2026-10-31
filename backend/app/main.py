"""
main.py
FastAPI Application Entry Point connecting the seven core modules:
1. database.py
2. models.py
3. schemas.py
4. api_routes.py
5. host_engine.py
6. hsm_adapter.py
7. iso_tic.py
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api_routes import router
from app.config import settings
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
    description="BAOBAB-Inspired Private Banking Host Simulator with Compass Plus TW TIC/TCI v2.164e and Thales 10K Soft-HSM Integration",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health_check():
    return {
        "status": "ONLINE",
        "application": settings.APP_NAME,
        "hsm_mode": settings.HSM_MODE,
    }
