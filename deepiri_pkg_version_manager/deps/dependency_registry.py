from typing import Optional
from uuid import UUID
from rich.console import Console
from rich.table import Table
import json

from .dependency_models import Dependency, DependencyDetail
from ..tags.tag_models import Tag, TagWithCount
from ..scanners.repo_scanner import ScannedDependency
from ..storage.db import (
    DependencyDB,
    TagDB,
    DependencyTagDB,
    DependencyEdgeDB,
    get_session,
    init_db,
)
from ..graph.dependency_graph import DependencyGraph

console = Console()


class DependencyRegistry:
    def __init__(self):
        init_db()
        self.session = get_session()

    def register(
        self,
        name: str,
        repo_path: str,
        package_type: str = "npm",
        version: str = None,
        description: str = None,
        git_url: str = None,
        git_rev: str = None,
        git_tag: str = None,
        git_tags: list[str] = None,
        is_submodule: bool = False,
    ) -> Dependency:
        import json
        existing = self.session.query(DependencyDB).filter_by(name=name).first()
        git_tags_json = json.dumps(git_tags) if git_tags else "[]"
        if existing:
            existing.repo_path = repo_path
            existing.package_type = package_type
            existing.version = version
            existing.description = description
            existing.git_url = git_url
            existing.git_rev = git_rev
            existing.git_tag = git_tag
            existing.git_tags = git_tags_json
            existing.is_submodule = is_submodule
            self.session.commit()
            return self._db_to_model(existing)
        
        db = DependencyDB(
            name=name,
            repo_path=repo_path,
            package_type=package_type,
            version=version,
            description=description,
            git_url=git_url,
            git_rev=git_rev,
            git_tag=git_tag,
            git_tags=git_tags_json,
            is_submodule=is_submodule,
        )
        self.session.add(db)
        self.session.commit()
        return self._db_to_model(db)

    def register_from_scanned(self, scanned: ScannedDependency) -> Dependency:
        """Register a scanned dependency."""
        return self.register(
            name=scanned.name,
            repo_path=scanned.repo_path,
            package_type=scanned.package_type,
            version=scanned.version,
            description=scanned.description,
            git_url=scanned.git_url,
            git_rev=scanned.git_rev,
            git_tag=scanned.git_tag,
            git_tags=scanned.git_tags,
            is_submodule=scanned.is_submodule,
        )

    def register_many(self, deps: list[dict]) -> list[Dependency]:
        results = []
        for dep in deps:
            result = self.register(
                name=dep["name"],
                repo_path=dep["repo_path"],
                package_type=dep.get("package_type", "npm"),
                version=dep.get("version"),
                description=dep.get("description"),
                git_url=dep.get("git_url"),
                git_rev=dep.get("git_rev"),
            )
            results.append(result)
        return results

    def get(self, name: str) -> Optional[Dependency]:
        db = self.session.query(DependencyDB).filter_by(name=name).first()
        if db:
            return self._db_to_model(db)
        return None

    def get_all(self) -> list[Dependency]:
        dbs = self.session.query(DependencyDB).all()
        return [self._db_to_model(db) for db in dbs]

    def get_by_type(self, package_type: str) -> list[Dependency]:
        dbs = self.session.query(DependencyDB).filter_by(package_type=package_type).all()
        return [self._db_to_model(db) for db in dbs]

    def get_detail(self, name: str) -> Optional[DependencyDetail]:
        db = self.session.query(DependencyDB).filter_by(name=name).first()
        if not db:
            return None
        
        dep_dict = {
            "id": db.id,
            "name": db.name,
            "repo_path": db.repo_path,
            "package_type": db.package_type,
            "version": db.version,
            "description": db.description,
            "git_url": db.git_url,
            "git_rev": db.git_rev,
            "git_tag": db.git_tag,
            "is_submodule": db.is_submodule,
        }
        
        tag_dbs = self.session.query(TagDB).join(DependencyTagDB).filter(
            DependencyTagDB.dependency_id == str(db.id)
        ).all()
        tags = [self._tag_db_to_model(tdb) for tdb in tag_dbs]
        
        graph = self.build_graph()
        dependencies = graph.get_dependencies(name)
        dependents = graph.get_dependents(name)
        
        dep_dict["tags"] = tags
        dep_dict["dependencies"] = dependencies
        dep_dict["dependents"] = dependents
        
        return DependencyDetail(**dep_dict)

    def update_version(self, name: str, version: str, git_rev: str = None) -> bool:
        db = self.session.query(DependencyDB).filter_by(name=name).first()
        if db:
            db.version = version
            if git_rev:
                db.git_rev = git_rev
            self.session.commit()
            return True
        return False

    def delete(self, name: str) -> bool:
        db = self.session.query(DependencyDB).filter_by(name=name).first()
        if db:
            self.session.query(DependencyTagDB).filter(
                DependencyTagDB.dependency_id == db.id
            ).delete()
            self.session.query(DependencyEdgeDB).filter(
                (DependencyEdgeDB.from_dependency_id == db.id) |
                (DependencyEdgeDB.to_dependency_id == db.id)
            ).delete()
            self.session.delete(db)
            self.session.commit()
            return True
        return False

    def add_edge(self, from_name: str, to_name: str, version_constraint: str = None):
        from_db = self.session.query(DependencyDB).filter_by(name=from_name).first()
        to_db = self.session.query(DependencyDB).filter_by(name=to_name).first()
        
        if from_db and to_db:
            edge = DependencyEdgeDB(
                from_dependency_id=from_db.id,
                to_dependency_id=to_db.id,
                version_constraint=version_constraint,
            )
            self.session.merge(edge)
            self.session.commit()

    def clear_all(self):
        """Clear all dependencies and edges."""
        self.session.query(DependencyEdgeDB).delete()
        self.session.query(DependencyTagDB).delete()
        self.session.query(DependencyDB).delete()
        self.session.commit()

    def build_graph(self) -> DependencyGraph:
        graph = DependencyGraph()
        
        deps = self.get_all()
        for dep in deps:
            graph.add_node(str(dep.id), name=dep.name)
        
        edges = self.session.query(DependencyEdgeDB).all()
        for edge in edges:
            graph.add_edge(edge.from_dependency_id, edge.to_dependency_id)
        
        return graph

    def get_outdated(self) -> list[tuple[Dependency, Dependency]]:
        """Get pairs of (current, wanted) outdated dependencies."""
        outdated = []
        graph = self.build_graph()
        
        for dep in self.get_all():
            wanted = graph.get_dependencies(dep.name)
            for want_name in wanted:
                wanted_dep = self.get(want_name)
                if wanted_dep and dep.version != wanted_dep.version:
                    outdated.append((dep, wanted_dep))
        
        return outdated

    def _db_to_model(self, db: DependencyDB) -> Dependency:
        import json
        try:
            git_tags = json.loads(db.git_tags) if db.git_tags else []
        except json.JSONDecodeError:
            git_tags = []
        return Dependency(
            id=UUID(db.id),
            name=db.name,
            repo_path=db.repo_path,
            package_type=db.package_type,
            version=db.version,
            description=db.description,
            git_url=db.git_url,
            git_rev=db.git_rev,
            git_tag=db.git_tag,
            git_tags=git_tags,
            is_submodule=db.is_submodule,
        )

    def _tag_db_to_model(self, db: TagDB) -> Tag:
        return Tag(
            id=UUID(db.id),
            name=db.name,
            description=db.description,
            color=db.color,
        )
