from pydantic import BaseModel, Field

from app.models.common import new_id, utcnow


class UploadBatch(BaseModel):
    id: str = Field(default_factory=new_id)
    filename: str
    mapping_profile_id: str
    mapping_profile_name: str
    row_count: int = 0
    ok_count: int = 0
    duplicate_count: int = 0
    needs_review_count: int = 0
    uploaded_at: str = Field(default_factory=lambda: utcnow().isoformat())
