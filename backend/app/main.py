from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chart_of_accounts, classification, mappings, pnl, qbo, reconciliation, transactions, uploads
from app.classification.vendor_directory import seed_default_vendors
from app.db import get_db
from app.ingestion import mapping_repo
from app.ingestion.bank_accounts import seed_default_aliases


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = get_db()
    seed_default_aliases(db)
    seed_default_vendors(db)
    mapping_repo.seed_default_profile(db)
    yield


app = FastAPI(title="Finz Accounting Data Pipeline", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mappings.router)
app.include_router(uploads.router)
app.include_router(transactions.router)
app.include_router(classification.router)
app.include_router(pnl.router)
app.include_router(qbo.router)
app.include_router(reconciliation.router)
app.include_router(chart_of_accounts.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
