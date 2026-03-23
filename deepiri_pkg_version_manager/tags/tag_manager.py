from typing import Optional
from uuid import UUID
from rich.console import Console

from .tag_models import Tag, TagWithCount
from ..storage.db import (
    DependencyDB,
    TagDB,
    DependencyTagDB,
    get_session,
    init_db,
)

console = Console()


class TagManager:
    def __init__(self):
        init_db()
        self.session = get_session()

    def create_tag(
        self,
        name: str,
        description: str = None,
        color: str = None,
    ) -> Tag:
        existing = self.session.query(TagDB).filter_by(name=name).first()
        if existing:
            existing.description = description
            existing.color = color
            self.session.commit()
            return self._db_to_model(existing)
        
        db = TagDB(
            name=name,
            description=description,
            color=color,
        )
        self.session.add(db)
        self.session.commit()
        return self._db_to_model(db)

    def get_tag(self, name: str) -> Optional[Tag]:
        db = self.session.query(TagDB).filter_by(name=name).first()
        if db:
            return self._db_to_model(db)
        return None

    def get_all_tags(self) -> list[Tag]:
        dbs = self.session.query(TagDB).all()
        return [self._db_to_model(db) for db in dbs]

    def get_tags_with_counts(self) -> list[TagWithCount]:
        tags = self.get_all_tags()
        results = []
        for tag in tags:
            count = self.session.query(DependencyTagDB).filter_by(tag_id=str(tag.id)).count()
            results.append(TagWithCount(tag=tag, dependency_count=count))
        return results

    def add_tag_to_dependency(self, dep_name: str, tag_name: str) -> bool:
        dep_db = self.session.query(DependencyDB).filter_by(name=dep_name).first()
        tag_db = self.session.query(TagDB).filter_by(name=tag_name).first()
        
        if not dep_db or not tag_db:
            return False
        
        existing = self.session.query(DependencyTagDB).filter_by(
            dependency_id=dep_db.id,
            tag_id=tag_db.id,
        ).first()
        
        if existing:
            return True
        
        link = DependencyTagDB(
            dependency_id=dep_db.id,
            tag_id=tag_db.id,
        )
        self.session.add(link)
        self.session.commit()
        return True

    def remove_tag_from_dependency(self, dep_name: str, tag_name: str) -> bool:
        dep_db = self.session.query(DependencyDB).filter_by(name=dep_name).first()
        tag_db = self.session.query(TagDB).filter_by(name=tag_name).first()
        
        if not dep_db or not tag_db:
            return False
        
        link = self.session.query(DependencyTagDB).filter_by(
            dependency_id=dep_db.id,
            tag_id=tag_db.id,
        ).first()
        
        if link:
            self.session.delete(link)
            self.session.commit()
            return True
        return False

    def get_dependency_tags(self, dep_name: str) -> list[Tag]:
        dep_db = self.session.query(DependencyDB).filter_by(name=dep_name).first()
        if not dep_db:
            return []
        
        tag_dbs = self.session.query(TagDB).join(DependencyTagDB).filter(
            DependencyTagDB.dependency_id == dep_db.id
        ).all()
        
        return [self._db_to_model(db) for db in tag_dbs]

    def check_tag_exists_in_dependency(self, dep_name: str, tag_name: str) -> bool:
        dep_db = self.session.query(DependencyDB).filter_by(name=dep_name).first()
        if not dep_db:
            return False
        
        tag_db = self.session.query(TagDB).filter_by(name=tag_name).first()
        if not tag_db:
            return False
        
        return self.session.query(DependencyTagDB).filter_by(dependency_id=dep_db.id, tag_id=tag_db.id).first() is not None

    def delete_tag(self, name: str) -> bool:
        db = self.session.query(TagDB).filter_by(name=name).first()
        if db:
            self.session.query(DependencyTagDB).filter_by(tag_id=db.id).delete()
            self.session.delete(db)
            self.session.commit()
            return True
        return False

    def _db_to_model(self, db: TagDB) -> Tag:
        return Tag(
            id=UUID(db.id),
            name=db.name,
            description=db.description,
            color=db.color,
        )
