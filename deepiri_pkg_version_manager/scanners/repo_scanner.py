import json
import re
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass, field
from rich.console import Console

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

console = Console()


@dataclass
class ScannedDependency:
    name: str
    repo_path: str
    package_type: str  # "npm", "poetry", "pip"
    version: Optional[str] = None
    description: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)
    git_url: Optional[str] = None
    git_rev: Optional[str] = None
    git_tag: Optional[str] = None
    git_tags: list[str] = field(default_factory=list)
    is_submodule: bool = False
    submodule_path: Optional[str] = None


def normalize_package_name(name: str) -> str:
    """Normalize package name for comparison."""
    if name.startswith("@"):
        parts = name.split("/")
        return parts[0] + "/" + parts[1] if len(parts) > 1 else parts[0]
    return name.split("#")[0].split(":")[0].strip()


def is_internal_dep(dep_name: str) -> bool:
    """Check if a dependency is internal (Deepiri)."""
    patterns = [
        r"^@deepiri/",
        r"^deepiri-",
        r"^@diri/",
        r"^diri-",
        r"^deepiri$",
    ]
    return any(re.match(p, dep_name) for p in patterns)


def extract_git_info(repo_path: Path) -> tuple[Optional[str], Optional[str], Optional[str], list[str]]:
    """Extract git URL, current revision, current tag, and all tags from a repo."""
    git_url = None
    git_rev = None
    git_tag = None
    git_tags = []
    
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            git_url = result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            git_rev = result.stdout.strip()[:8]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            git_tag = result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    try:
        result = subprocess.run(
            ["git", "tag", "-l", "--sort=-version:refname"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            git_tags = [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    return git_url, git_rev, git_tag, git_tags


def check_git_submodules(repo_path: Path) -> list[dict]:
    """Check if repo has git submodules."""
    submodules = []
    
    try:
        result = subprocess.run(
            ["git", "submodule", "status"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        rev = parts[0]
                        path = parts[1]
                        if is_internal_dep(path.split("/")[-1] if "/" in path else path):
                            submodules.append({
                                "path": path,
                                "rev": rev,
                            })
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    return submodules


def scan_package_json(repo_path: Path) -> Optional[ScannedDependency]:
    """Scan package.json for npm/Node.js dependencies."""
    package_json = repo_path / "package.json"
    if not package_json.exists():
        return None

    try:
        with open(package_json) as f:
            data = json.load(f)

        name = data.get("name", repo_path.name)
        version = data.get("version")
        description = data.get("description")

        deps = data.get("dependencies", {})
        internal_deps = [
            normalize_package_name(dep)
            for dep in deps.keys()
            if is_internal_dep(dep)
        ]

        git_url, git_rev, git_tag, git_tags = extract_git_info(repo_path)

        result = ScannedDependency(
            name=name,
            repo_path=str(repo_path),
            package_type="npm",
            version=version,
            description=description,
            dependencies=internal_deps,
            git_url=git_url,
            git_rev=git_rev,
            git_tag=git_tag,
            git_tags=git_tags,
        )

        # Check for file: dependencies (local)
        for dep_name, dep_version in deps.items():
            if dep_version.startswith("file:"):
                internal_deps.append(normalize_package_name(dep_name))

        return result

    except (json.JSONDecodeError, IOError) as e:
        console.print(f"[yellow]Warning:[/yellow] Failed to parse {package_json}: {e}")
        return None


def scan_pyproject_toml(repo_path: Path) -> Optional[ScannedDependency]:
    """Scan pyproject.toml for Poetry or pip dependencies."""
    pyproject = repo_path / "pyproject.toml"
    if not pyproject.exists():
        return None

    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)

        project = data.get("project", {})
        poetry = data.get("tool", {}).get("poetry", {})
        
        name = project.get("name") or poetry.get("name") or repo_path.name
        version = project.get("version") or poetry.get("version")
        description = project.get("description") or poetry.get("description")
        
        is_poetry = bool(poetry.get("dependencies"))

        internal_deps = []

        if is_poetry:
            deps = poetry.get("dependencies", {})
            for dep_name, dep_value in deps.items():
                if is_internal_dep(dep_name):
                    git_info = extract_git_dependency(dep_value)
                    if git_info:
                        internal_deps.append(dep_name)
                    else:
                        internal_deps.append(dep_name)
        else:
            deps = project.get("dependencies", [])
            for dep in deps:
                if isinstance(dep, str):
                    dep_name = dep.split()[0]
                    if is_internal_dep(dep_name):
                        internal_deps.append(dep_name)
                elif isinstance(dep, dict):
                    dep_name = dep.get("dep", "")
                    if is_internal_dep(dep_name):
                        internal_deps.append(dep_name)

        git_url, git_rev, git_tag, git_tags = extract_git_info(repo_path)

        result = ScannedDependency(
            name=name,
            repo_path=str(repo_path),
            package_type="poetry" if is_poetry else "pip",
            version=str(version) if version else None,
            description=description,
            dependencies=internal_deps,
            git_url=git_url,
            git_rev=git_rev,
            git_tag=git_tag,
            git_tags=git_tags,
        )

        return result

    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Failed to parse {pyproject}: {e}")
        return None


def extract_git_dependency(dep_value) -> Optional[dict]:
    """Extract git info from Poetry git dependency."""
    if isinstance(dep_value, dict):
        git_url = dep_value.get("git")
        if git_url:
            rev = dep_value.get("rev") or dep_value.get("branch") or dep_value.get("tag", "main")
            return {"git": git_url, "rev": rev}
    elif isinstance(dep_value, str):
        if dep_value.startswith("git+") or dep_value.startswith("git://"):
            return {"git": dep_value, "rev": "main"}
    return None


def scan_poetry_lock(repo_path: Path) -> dict:
    """Parse poetry.lock for locked versions."""
    lock_file = repo_path / "poetry.lock"
    if not lock_file.exists():
        return {}
    
    try:
        with open(lock_file, "rb") as f:
            data = tomllib.load(f)
        
        locked = {}
        for package in data.get("package", []):
            name = package.get("name", "")
            version = package.get("version", "")
            if is_internal_dep(name):
                locked[name] = version
        return locked
    except Exception:
        return {}


def scan_requirements_txt(repo_path: Path) -> Optional[ScannedDependency]:
    """Scan requirements.txt for pip dependencies."""
    req_files = ["requirements.txt", "requirements-dev.txt", "requirements-test.txt"]
    
    for req_file in req_files:
        req_path = repo_path / req_file
        if req_path.exists():
            break
    else:
        return None

    try:
        internal_deps = []
        version = None
        
        with open(req_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                # Handle various formats: package==1.0.0, package>=1.0, git+https://...
                match = re.match(r"^([a-zA-Z0-9_-]+)", line)
                if match:
                    pkg_name = match.group(1)
                    if is_internal_dep(pkg_name):
                        internal_deps.append(pkg_name)
                
                # Extract version if available
                if not version:
                    vmatch = re.search(r"==([0-9.]+)", line)
                    if vmatch:
                        version = vmatch.group(1)

        git_url, git_rev, git_tag, git_tags = extract_git_info(repo_path)

        result = ScannedDependency(
            name=repo_path.name,
            repo_path=str(repo_path),
            package_type="pip",
            version=version,
            dependencies=internal_deps,
            git_url=git_url,
            git_rev=git_rev,
            git_tag=git_tag,
            git_tags=git_tags,
        )

        return result

    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Failed to parse {req_path}: {e}")
        return None


def scan_pipfile(repo_path: Path) -> Optional[ScannedDependency]:
    """Scan Pipfile for pipenv dependencies."""
    pipfile = repo_path / "Pipfile"
    if not pipfile.exists():
        return None

    try:
        with open(pipfile, "rb") as f:
            data = tomllib.load(f)

        packages = data.get("packages", {})
        dev_packages = data.get("dev-packages", {})
        
        all_deps = {**packages, **dev_packages}
        
        internal_deps = []
        for dep_name, dep_value in all_deps.items():
            if is_internal_dep(dep_name):
                internal_deps.append(dep_name)

        git_url, git_rev, git_tag, git_tags = extract_git_info(repo_path)

        result = ScannedDependency(
            name=repo_path.name,
            repo_path=str(repo_path),
            package_type="pipenv",
            dependencies=internal_deps,
            git_url=git_url,
            git_rev=git_rev,
            git_tag=git_tag,
            git_tags=git_tags,
        )

        return result

    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Failed to parse {pipfile}: {e}")
        return None


def scan_directory(
    root_path: Path,
    package_types: list[str] = None,
    verbose: bool = False,
) -> list[ScannedDependency]:
    """Scan a directory for all package types."""
    if package_types is None:
        package_types = ["npm", "poetry", "pip"]

    if verbose:
        console.print(f"[cyan]Scanning:[/cyan] {root_path}")
        console.print(f"[cyan]Package types:[/cyan] {', '.join(package_types)}")

    all_results = []
    seen_names = set()

    # Check for git submodules first
    submodules = check_git_submodules(root_path)
    if submodules and verbose:
        console.print(f"[cyan]Found {len(submodules)} submodules[/cyan]")
        for sm in submodules:
            console.print(f"  [blue]→[/blue] {sm['path']} @ {sm['rev'][:7]}")

    # Scan all subdirectories
    scan_dirs = [root_path]
    
    # Add submodule paths
    for sm in submodules:
        submodule_full_path = root_path / sm["path"]
        if submodule_full_path.exists():
            scan_dirs.append(submodule_full_path)

    for scan_dir in scan_dirs:
        for subdir in [scan_dir] + list(scan_dir.rglob("*")):
            if not subdir.is_dir():
                continue

            # Skip hidden and common ignore directories
            skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".tox"}
            if any(skip in subdir.parts for skip in skip_dirs):
                continue

            result = None

            # Try each scanner based on package_types
            if "npm" in package_types:
                result = scan_package_json(subdir)
            
            if not result and "poetry" in package_types:
                result = scan_pyproject_toml(subdir)
            
            if not result and "pip" in package_types:
                result = scan_pipfile(subdir) or scan_requirements_txt(subdir)

            if result and result.name not in seen_names:
                seen_names.add(result.name)
                all_results.append(result)
                
                if verbose:
                    console.print(f"  [green]✓[/green] {result.name} ({result.package_type})")
                    if result.git_rev:
                        console.print(f"    @ {result.git_rev}")

    return all_results


def get_install_command(dep: ScannedDependency, package_manager: str = None) -> str:
    """Generate install command for a dependency based on its type."""
    pkg_type = package_manager or dep.package_type
    
    if pkg_type == "npm" or dep.package_type == "npm":
        if dep.git_tag:
            return f"npm install {dep.name}@{dep.git_tag}"
        elif dep.git_url:
            return f"npm install {dep.name}@{dep.git_url}#{dep.git_rev or 'main'}"
        elif dep.version:
            return f"npm install {dep.name}@{dep.version}"
        return f"npm install {dep.name}"
    
    elif pkg_type in ("poetry", "pip") or dep.package_type in ("poetry", "pip"):
        if dep.git_tag:
            return f"poetry add git@{dep.git_url}#{dep.git_tag}"
        elif dep.git_url:
            rev = dep.git_rev or "main"
            return f"poetry add git@{dep.git_url}@{rev}"
        elif dep.version:
            return f"poetry add {dep.name}@{dep.version}"
        return f"poetry add {dep.name}"
    
    elif pkg_type == "pipenv" or dep.package_type == "pipenv":
        if dep.git_url:
            rev = dep.git_rev or "main"
            return f"pipenv install git+{dep.git_url}@{rev}#egg={dep.name}"
        elif dep.version:
            return f"pipenv install {dep.name}=={dep.version}"
        return f"pipenv install {dep.name}"
    
    elif pkg_type == "pip":
        if dep.git_url:
            rev = dep.git_rev or "main"
            return f"pip install git+{dep.git_url}@{rev}#egg={dep.name}"
        elif dep.version:
            return f"pip install {dep.name}=={dep.version}"
        return f"pip install {dep.name}"
    
    return f"# Unknown package type: {dep.package_type}"


def get_install_all_command(dep: ScannedDependency, package_manager: str = None) -> str:
    """Generate install all dependencies command for a package."""
    pkg_type = package_manager or dep.package_type
    
    if pkg_type == "npm" or dep.package_type == "npm":
        return f"cd {dep.repo_path} && npm install"
    
    elif pkg_type in ("poetry", "pip") or dep.package_type in ("poetry", "pip"):
        return f"cd {dep.repo_path} && poetry install"
    
    elif pkg_type == "pipenv" or dep.package_type == "pipenv":
        return f"cd {dep.repo_path} && pipenv install"
    
    elif pkg_type == "pip":
        return f"cd {dep.repo_path} && pip install -r requirements.txt"
    
    return f"# Unknown package type: {dep.package_type}"


def version_sync_needed(registry_dep: ScannedDependency, current_dep: ScannedDependency) -> bool:
    """Check if version sync is needed between two dependencies."""
    if not registry_dep.version or not current_dep.version:
        return False
    
    if registry_dep.version != current_dep.version:
        return True
    
    if registry_dep.git_rev and current_dep.git_rev:
        return registry_dep.git_rev != current_dep.git_rev
    
    return False
