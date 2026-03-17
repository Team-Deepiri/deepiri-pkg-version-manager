from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class Tag(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class TagWithCount(BaseModel):
    tag: Tag
    dependency_count: int = 0
