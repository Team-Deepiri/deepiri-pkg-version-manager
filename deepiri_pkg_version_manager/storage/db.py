import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class DependencyDB(Base):
    __tablename__ = "dependencies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    repo_path: Mapped[str] = mapped_column(String(512), nullable=False)
    package_type: Mapped[str] = mapped_column(String(50), default="npm")
    version: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    git_url: Mapped[str | None] = mapped_column(String(512))
    git_rev: Mapped[str | None] = mapped_column(String(100))
    git_tag: Mapped[str | None] = mapped_column(String(100))
    git_tags: Mapped[str] = mapped_column(Text, default="[]")
    is_submodule: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_data: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class TagDB(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(7))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DependencyTagDB(Base):
    __tablename__ = "dependency_tags"

    dependency_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("dependencies.id"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(String(36), ForeignKey("tags.id"), primary_key=True)


class DependencyEdgeDB(Base):
    __tablename__ = "dependency_edges"

    from_dependency_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("dependencies.id"), primary_key=True
    )
    to_dependency_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("dependencies.id"), primary_key=True
    )
    version_constraint: Mapped[str | None] = mapped_column(String(100))
    relationship_type: Mapped[str] = mapped_column(String(50), default="depends_on")


def get_db_path() -> Path:
    home = Path.home()
    deepiri_dir = home / ".deepiri"
    deepiri_dir.mkdir(exist_ok=True)
    return deepiri_dir / "dtm.db"


def get_engine(db_path: Path | None = None):
    if db_path is None:
        db_path = get_db_path()
    url = f"sqlite:///{db_path}"
    return create_engine(url, echo=False)


def init_db(engine=None):
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session(engine=None):
    if engine is None:
        engine = get_engine()
    session_factory = sessionmaker(bind=engine)
    return session_factory()
