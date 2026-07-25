from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.deps import db_dep
from app.ingestion import mapping_repo
from app.models.column_mapping import ColumnMappingCreate, ColumnMappingProfile

router = APIRouter(prefix="/api/column-mappings", tags=["column-mappings"])


@router.post("", response_model=ColumnMappingProfile)
def create_mapping(payload: ColumnMappingCreate, db: Database = Depends(db_dep)):
    return mapping_repo.create_profile(db, payload)


@router.get("", response_model=list[ColumnMappingProfile])
def list_mappings(db: Database = Depends(db_dep)):
    return mapping_repo.list_profiles(db)
