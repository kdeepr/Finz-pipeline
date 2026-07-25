from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pymongo.database import Database

from app.config import get_settings
from app.deps import db_dep
from app.ingestion import mapping_repo
from app.ingestion.parser import UnsupportedFileType
from app.ingestion.service import MappingMismatchError, ingest_file, preview_file
from app.models.upload_batch import UploadBatch

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/preview")
async def preview_upload(file: UploadFile):
    content = await file.read()
    try:
        return preview_file(file.filename, content)
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=UploadBatch)
async def create_upload(
    file: UploadFile,
    mapping_profile_id: str = Form(...),
    bank_account_override: str | None = Form(None),
    db: Database = Depends(db_dep),
):
    mapping = mapping_repo.get_profile(db, mapping_profile_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail=f"Column mapping profile '{mapping_profile_id}' not found")

    content = await file.read()
    settings = get_settings()
    try:
        return ingest_file(
            db,
            file.filename,
            content,
            mapping,
            bank_account_override=bank_account_override,
            allowed_currencies=settings.allowed_currencies,
        )
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MappingMismatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[UploadBatch])
def list_uploads(db: Database = Depends(db_dep)):
    docs = db["upload_batches"].find({}, {"_id": 0}).sort("uploaded_at", -1)
    return [UploadBatch(**doc) for doc in docs]


@router.get("/{batch_id}", response_model=UploadBatch)
def get_upload(batch_id: str, db: Database = Depends(db_dep)):
    doc = db["upload_batches"].find_one({"id": batch_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Upload batch not found")
    return UploadBatch(**doc)
