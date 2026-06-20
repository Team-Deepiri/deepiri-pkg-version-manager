from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Dependency(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    repo_path: str
    package_type: str = Field(default="npm")
    version: str | None = None
    description: str | None = None
    git_url: str | None = None
    git_rev: str | None = None
    git_tag: str | None = None
    git_tags: list[str] = Field(default_factory=list)
    is_submodule: bool = False
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class Tag(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    color: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class DependencyTag(BaseModel):
    dependency_id: UUID
    tag_id: UUID

    class Config:
        from_attributes = True


class DependencyEdge(BaseModel):
    from_dependency_id: UUID
    to_dependency_id: UUID
    version_constraint: str | None = None
    relationship_type: str = Field(default="depends_on")

    class Config:
        from_attributes = True


class DependencyDetail(Dependency):
    tags: list[Tag] = Field(default_factory=list)
    dependents: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class VersionInfo(BaseModel):
    current: str | None = None
    wanted: str | None = None
    latest: str | None = None
    git_rev: str | None = None
    is_outdated: bool = False
