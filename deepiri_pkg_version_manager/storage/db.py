from pathlib import Path
from sqlalchemy import create_engine, Column, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import uuid

Base = declarative_base()


class DependencyDB(Base):
    __tablename__ = "dependencies"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True, index=True)
    repo_path = Column(String(512), nullable=False)
    package_type = Column(String(50), default="npm")
    version = Column(String(50))
    description = Column(Text)
    git_url = Column(String(512))
    git_rev = Column(String(100))
    git_tag = Column(String(100))
    git_tags = Column(Text, default="[]")
    is_submodule = Column(Boolean, default=False)
    extra_data = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TagDB(Base):
    __tablename__ = "tags"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text)
    color = Column(String(7))
    created_at = Column(DateTime, default=datetime.utcnow)


class DependencyTagDB(Base):
    __tablename__ = "dependency_tags"
    
    dependency_id = Column(String(36), ForeignKey("dependencies.id"), primary_key=True)
    tag_id = Column(String(36), ForeignKey("tags.id"), primary_key=True)


class DependencyEdgeDB(Base):
    __tablename__ = "dependency_edges"
    
    from_dependency_id = Column(String(36), ForeignKey("dependencies.id"), primary_key=True)
    to_dependency_id = Column(String(36), ForeignKey("dependencies.id"), primary_key=True)
    version_constraint = Column(String(100))
    relationship_type = Column(String(50), default="depends_on")


def get_db_path() -> Path:
    home = Path.home()
    deepiri_dir = home / ".deepiri"
    deepiri_dir.mkdir(exist_ok=True)
    return deepiri_dir / "dtm.db"


def get_engine(db_path: Path = None):
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
    Session = sessionmaker(bind=engine)
    return Session()
