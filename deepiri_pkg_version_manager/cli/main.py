import sys
import json
import typer
import subprocess
import logging
from typing import Optional, List
import subprocess
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.syntax import Syntax
from packaging.version import Version
from PySide6.QtWidgets import QApplication

from deepiri_pkg_version_manager.deps.dependency_registry import DependencyRegistry
from deepiri_pkg_version_manager.tags.tag_manager import TagManager
from deepiri_pkg_version_manager.scanners.repo_scanner import scan_directory, get_install_command, get_install_all_command, version_sync_needed
from deepiri_pkg_version_manager.graph.dependency_graph import DependencyGraph

app = typer.Typer(
    name="dtm",
    help="Deepiri Package Version Manager - Dependency graph and version management",
    add_completion=False,
)
console = Console()

tag_app = typer.Typer(help="Manage dependency tags")
app.add_typer(tag_app, name="tag")

logging.basicConfig(
    filename="package_version_manager.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


@app.command()
def scan(
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        "-p",
        help="Path to scan (default: ../deepiri-platform relative to repo)",
    ),
    package_type: List[str] = typer.Option(
        ["all"],
        "--type",
        "-t",
        help="Package types to scan: npm, poetry, pip, all",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to database"),
    clear: bool = typer.Option(False, "--clear", help="Clear existing data before scanning"),
):
    """Scan repositories and build dependency graph."""
    if path is None:
        path = Path(__file__).parent.parent / "deepiri-platform"
    
    if not path.exists():
        logging.error(f"[red]Error:[/red] Path does not exist: {path}")
        raise typer.Exit(1)
    
    types = ["npm", "poetry", "pip"] if "all" in package_type else package_type
    
    console.print(f"[cyan]Scanning:[/cyan] {path}")
    console.print(f"[cyan]Types:[/cyan] {', '.join(types)}")
    
    scanned = scan_directory(path, package_types=types, verbose=verbose)
    
    console.print(f"\n[green]Found {len(scanned)} packages[/green]")
    
    if save:
        registry = DependencyRegistry()
        
        if clear:
            console.print("[yellow]Clearing existing data...[/yellow]")
            registry.clear_all()
        
        for dep in scanned:
            registry.register_from_scanned(dep)
        
        for dep in scanned:
            for dep_name in dep.dependencies:
                registry.add_edge(dep.name, dep_name)
        
        console.print("[green]Saved to database[/green]")
    
    return scanned


@app.command("clear")
def clear_db():
    registry = DependencyRegistry()
    registry.clear_all()
    console.print("[green]Database cleared[/green]")


@app.command("deps")
def list_dependencies(
    name: Optional[str] = typer.Argument(None, help="Specific dependency to show"),
    package_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    show_tags: bool = typer.Option(False, "--tags", "-T", help="Show tags"),
):
    """List all dependencies or show details for one."""
    registry = DependencyRegistry()
    
    if name:
        detail = registry.get_detail(name)
        if not detail:
            rprint(f"[red]Error:[/red] Dependency '{name}' not found")
            raise typer.Exit(1)
        
        console.print(f"\n[bold cyan]{detail.name}[/bold cyan]")
        console.print(f"  Type: {detail.package_type}")
        console.print(f"  Version: {detail.version or 'unknown'}")
        console.print(f"  Path: {detail.repo_path}")
        if detail.git_url:
            console.print(f"  Git: {detail.git_url}")
        if detail.git_rev:
            console.print(f"  Revision: {detail.git_rev}")
        if detail.git_tag:
            console.print(f"  Tag: {detail.git_tag}")
        if detail.git_tags:
            console.print(f"  All Tags: {', '.join(detail.git_tags[:5])}{'...' if len(detail.git_tags) > 5 else ''}")
        if detail.is_submodule:
            console.print(f"  [yellow]Submodule: Yes[/yellow]")
        if detail.description:
            console.print(f"  Description: {detail.description}")
        
        if detail.dependencies:
            console.print(f"\n  [bold]Dependencies:[/bold]")
            for d in detail.dependencies:
                console.print(f"    - {d}")
        
        if detail.dependents:
            console.print(f"\n  [bold]Dependents:[/bold]")
            for d in detail.dependents:
                console.print(f"    - {d}")
        
        if detail.tags:
            console.print(f"\n  [bold]Tags:[/bold]")
            tags_str = ", ".join([t.name for t in detail.tags])
            console.print(f"    {tags_str}")
    else:
        if package_type:
            deps = registry.get_by_type(package_type)
        else:
            deps = registry.get_all()
        
        if not deps:
            rprint("[yellow]No dependencies found. Run 'dtm scan' first.[/yellow]")
            return
        
        table = Table(title="Dependencies")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Version")
        table.add_column("Git Rev", style="dim")
        
        for dep in deps:
            table.add_row(
                dep.name, 
                dep.package_type, 
                dep.version or "-",
                dep.git_rev or "-"
            )
        
        console.print(table)


@app.command()
def graph(
    root: Optional[str] = typer.Option(None, "--root", "-r", help="Root package to display"),
    dependents: Optional[str] = typer.Option(None, "--dependents", help="Find all packages depending on X"),
    dependencies: Optional[str] = typer.Option(None, "--dependencies", help="Find all packages X depends on"),
):
    """Display dependency graph."""
    from deepiri_pkg_version_manager.ui.graphDisplay import DependencyGraphView
    registry = DependencyRegistry()
    g = registry.build_graph()

    app = QApplication(sys.argv)
    window = DependencyGraphView(g, root=root)
    window.show()
    sys.exit(app.exec())


@app.command()
def install(
    dependency: Optional[str] = typer.Argument(None, help="Dependency to install (or all)"),
    package_manager: Optional[str] = typer.Option(None, "--manager", "-m", help="Force package manager: npm, poetry, pip, pipenv"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Show commands without running"),
    all_deps: bool = typer.Option(False, "--all", "-a", help="Install all dependencies in package"),
):
    """Generate or run install commands for dependencies."""
    registry = DependencyRegistry()
    
    if dependency:
        deps = [registry.get(dependency)]
        if not deps[0]:
            rprint(f"[red]Error:[/red] Dependency '{dependency}' not found")
            raise typer.Exit(1)
    else:
        deps = registry.get_all()
    
    commands = []
    for dep in deps:
        if all_deps:
            cmd = get_install_all_command(dep, package_manager)
        else:
            cmd = get_install_command(dep, package_manager)
        
        commands.append((dep.name, cmd))
        
        console.print(f"\n[cyan]{dep.name}:[/cyan]")
        syntax = Syntax(cmd, "bash", theme="monokai")
        console.print(syntax)
    
    if not dry_run:
        for name, cmd in commands:
            console.print(f"\n[yellow]Executing:[/yellow] {name}")
            try:
                subprocess.run(cmd, shell=True, check=True)
            except subprocess.CalledProcessError as e:
                rprint(f"[red]Error:[/red] {e}")


@app.command()
def outdated():
    """Check for outdated dependencies."""
    registry = DependencyRegistry()
    
    outdated_pairs = registry.get_outdated()
    
    if not outdated_pairs:
        console.print("[green]All dependencies are in sync![/green]")
        return
    
    table = Table(title="Outdated Dependencies")
    table.add_column("Package", style="cyan")
    table.add_column("Current", style="yellow")
    table.add_column("Wanted", style="green")
    
    for current, wanted in outdated_pairs:
        table.add_row(current.name, current.version or "-", wanted.version or "-")
    
    console.print(table)


@app.command()
def sync(
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Show changes without applying"),
):
    """Sync versions across the dependency graph."""
    registry = DependencyRegistry()
    graph = registry.build_graph()
    
    changes = []
    
    for dep in registry.get_all():
        dependents = graph.get_dependents(dep.name)
        for dependent_name in dependents:
            dependent = registry.get(dependent_name)
            if dependent and dep.version:
                if dependent.version != dep.version:
                    changes.append((dependent_name, dependent.version, dep.version, dep.name))
    
    if not changes:
        console.print("[green]All versions are in sync![/green]")
        return
    
    table = Table(title="Version Changes Needed")
    table.add_column("Package", style="cyan")
    table.add_column("Current", style="yellow")
    table.add_column("New", style="green")
    table.add_column("From", style="magenta")
    
    for pkg, current, new, from_dep in changes:
        table.add_row(pkg, current or "-", new or "-", from_dep)
    
    console.print(table)
    
    if not dry_run:
        for pkg, current, new, from_dep in changes:
            registry.update_version(pkg, new)
        console.print("[green]Versions synced![/green]")


@app.command()
def export(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json, dot"),
):
    """Export dependency graph."""
    registry = DependencyRegistry()
    graph = registry.build_graph()
    
    if format == "json":
        data = {
            "dependencies": [
                {
                    "name": d.name,
                    "version": d.version,
                    "type": d.package_type,
                    "git_url": d.git_url,
                    "git_rev": d.git_rev,
                    "git_tag": d.git_tag,
                }
                for d in registry.get_all()
            ],
            "graph": graph.to_dict(),
        }
        output_str = json.dumps(data, indent=2)
    elif format == "dot":
        lines = ["digraph dependencies {"]
        for edge in graph.graph.edges:
            from_name = graph.get_node_name(edge[0])
            to_name = graph.get_node_name(edge[1])
            if from_name and to_name:
                lines.append(f'  "{from_name}" -> "{to_name}";')
        lines.append("}")
        output_str = "\n".join(lines)
    else:
        rprint(f"[red]Unknown format:[/red] {format}")
        raise typer.Exit(1)
    
    if output:
        output.write_text(output_str)
        console.print(f"[green]Exported to {output}[/green]")
    else:
        console.print(output_str)


def run_command(command: List[str], cwd: str) -> Optional[str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        logging.error(f"[red]Error:[/red] {error_msg}")
        return None

    except Exception as e:
        logging.error(f"[red]Unexpected Error:[/red] {e}")
        return None


def dependency_tree_check(dependency: str, registry: DependencyRegistry):
    dep = registry.get(dependency)
    if not dep:
        logging.error(f"[red]Error:[/red] Dependency '{dependency}' not found")
        return False

    dep_path = dep.repo_path
    if not clean_working_tree(dep_path):
        logging.error(f"[red]Error:[/red] Working tree is not clean, ensure all changes are committed or stashed before pushing a new tag.")
        return False

    if not is_synced_with_main(dep_path):
        logging.error(f"[red]Error:[/red] '{dependency}' is not in sync with main branch, ensure you have pulled the latest changes from main and do not have any local commits before pushing a new tag.")
        return False

    return True


def clean_working_tree(dep_path: str) -> bool:
    clean = run_command(['git', 'status', '--porcelain'], dep_path)
    if clean is None:
        logging.error(f"[red]Error:[/red] Failed to check if working tree is clean")
        return False
    elif clean.strip() != '':
        logging.error(f"[red]Error:[/red] Working tree is not clean, ensure all changes are committed or stashed before pushing a new tag.")
        return False
    
    logging.info(f"[green]Working tree is clean[/green]")
    return True


def is_synced_with_main(dep_path: str) -> bool:
    if run_command(['git', 'fetch', 'origin'], dep_path) is None:
        logging.error("[red]Error:[/red] Failed to fetch origin")
        return False

    branch = run_command(['git', 'branch', '--show-current'], dep_path)
    if branch is None or branch.strip() == "":
        logging.error("[red]Error:[/red] Detached HEAD state detected. Please checkout a branch.")
        return False

    head = run_command(['git', 'rev-parse', 'HEAD'], dep_path)
    main = run_command(['git', 'rev-parse', 'main'], dep_path)
    origin_main = run_command(['git', 'rev-parse', 'origin/main'], dep_path)

    if None in (head, main, origin_main):
        logging.error("[red]Error:[/red] Failed to resolve commit hashes")
        return False

    head = head.strip()
    main = main.strip()
    origin_main = origin_main.strip()

    if head != main:
        logging.error("[red]Error:[/red] Current branch is not at the same commit as local main")
        return False

    if main != origin_main:
        logging.error("[red]Error:[/red] Local main is not up-to-date with origin/main")
        return False

    logging.info("[green]Branch is aligned with main and origin/main[/green]")
    return True

def check_valid_tag(tag_name: str, dependency: str, dep_path: str):
    if not check_valid_format(tag_name):
        return False

    tags = run_command(['git', 'tag', '--sort=-v:refname'], dep_path)
    if tags is None:
        logging.error(f"[red]Error:[/red] Failed to get recent tag in '{dependency}'")
        return False
    elif tags.strip() == "":
        logging.error(f"[green]No tags exist in '{dependency}'[/green]")
        return True
    
    if tags:
        latest_tag = tags.strip().split("\n")[0]
        if Version(tag_name) <= Version(latest_tag):
            logging.error(f"[red]Error:[/red] Tag '{tag_name}' is not greater than latest tag '{latest_tag.join(".")}' in '{dependency}'")
            return False
    
    logging.info(f"[green]Tag '{tag_name}' is valid in '{dependency}'[/green]")
    return True


def check_valid_format(tag_name: str):
    if not tag_name.startswith("v") or not tag_name.count(".") == 2 or not tag_name.split(".")[0].strip("v").isdigit() or not tag_name.split(".")[1].isdigit() or not tag_name.split(".")[2].isdigit():
        logging.error(f"[red]Error:[/red] Invalid tag format '{tag_name}', use format v<major>.<minor>.<patch>")
        return False
    else:
        logging.info(f"[green]Tag '{tag_name}' is valid format[/green]")
        return True


def update_pyproject_version(repo_path: str, version: str):
    import toml

    pyproject_path = os.path.join(repo_path, "pyproject.toml")
    data = toml.load(pyproject_path)

    if "project" in data and "version" in data["project"]:
        data["project"]["version"] = version
    elif "tool" in data and "poetry" in data["tool"]:
        data["tool"]["poetry"]["version"] = version
    else:
        logging.error(f"[red]Error:[/red] No version field found in pyproject.toml")
        return False

    with open(pyproject_path, "w") as f:
        toml.dump(data, f)

    logging.info(f"[green]Updated version to '{version}' in pyproject.toml[/green]")
    return True


def bump_version(dep, version: str):
    if dep.package_type == "npm":
        output = run_command(['npm', 'version', version.strip('v'), '--no-git-tag-version'], dep.repo_path) 
        if output is None:
            logging.error(f"[red]Error:[/red] Failed to bump version in '{dep.name}'")
            return False
        else:
            logging.info(f"[green]Bumped version to '{version}' in '{dep.name}'[/green]")

        result = run_command(['git', 'add', 'package.json'], dep.repo_path)
    elif dep.package_type == "poetry":
        output = run_command(['poetry', 'version', version.strip('v')], dep.repo_path)
        if output is None:
            logging.error(f"[red]Error:[/red] Failed to bump version in '{dep.name}'")
            return False
        else:
            logging.info(f"[green]Bumped version to '{version}' in '{dep.name}'[/green]")

        result = run_command(['git', 'add', 'pyproject.toml'], dep.repo_path)
    elif dep.package_type == "pip":
        if not update_pyproject_version(dep.repo_path, version):
            logging.error(f"[red]Error:[/red] Failed to update version in pyproject.toml in '{dep.name}'")
            return False
        else:
            logging.info(f"[green]Updated version to '{version}' in pyproject.toml in '{dep.name}'[/green]")

        result = run_command(['git', 'add', 'pyproject.toml'], dep.repo_path)

    if result is None:
        logging.error(f"[red]Error:[/red] Failed to add pyproject.toml to staging area in '{dep.name}'")
        return False
    else:
        logging.info(f"[green]Added pyproject.toml to staging area in '{dep.name}'[/green]")

    commit = run_command(['git', 'commit', '-m', f"Deepiri-Package-Version-Manager: Bump version ({dep.package_type}) to {version}"], dep.repo_path)
    if commit is None:
        logging.error(f"[red]Error:[/red] Failed to commit changes in '{dep.name}'")
        return False
    else:
        logging.info(f"[green]Committed changes in '{dep.name}'[/green]")

    return True

def create_tag(dependency: str, tag_mgr: TagManager, registry: DependencyRegistry, tag_name: Optional[str] = None, description: str = "", color: Optional[str] = None):
    dep = registry.get(dependency)
    dep_path = dep.repo_path

    if tag_name is None:
        local_tags = run_command(['git', 'tag'], dep_path)
        if local_tags is None:
            logging.error(f"[red]Error:[/red] Failed to get local tags in '{dependency}'")
            raise typer.Exit(1)
        elif local_tags.strip() != "":
            logging.error(f"[red]Error:[/red] Local tags found in '{dependency}', to use default add behavior there should be no local tags.")
            raise typer.Exit(1)
        else:
            tag_name = "v0.0.0"
    else:
        if not check_valid_tag(tag_name, dependency, dep_path):
            logging.error(f"[red]Error:[/red] Tag '{tag_name}' is not valid in '{dependency}'")
            raise typer.Exit(1)

    tag_mgr.create_tag(name=tag_name, description=description, color=color)
    success = tag_mgr.add_tag_to_dependency(dependency, tag_name)
    if success:
        logging.info(f"[green]Added tag '{tag_name}' to '{dependency}' in db[/green]")
    else:
        logging.error(f"[red]Error:[/red] Failed to add tag")

    if not bump_version(dep, tag_name):
        logging.error(f"[red]Error:[/red] Failed to bump version")
        return False
    else:
        logging.info(f"[green]Bumped version to '{tag_name}' in '{dependency}'[/green]")

    output = run_command(['git', 'tag', '-a', tag_name, '-m', description], dep.repo_path)
    if output is None:
        logging.error(f"[red]Error:[/red] Failed to create tag '{tag_name} in {dependency}'")
    else:
        logging.info(f"[green]Created tag '{tag_name}' in '{dependency}' locally[/green]")

    return True

@tag_app.command("add")
def tag_add(
    dependency: str = typer.Argument(..., help="Dependency name"),
    tag_name: Optional[str] = typer.Argument(None, help="Tag name"),
    description: str = typer.Option(..., "--description", "-d", help="Tag description"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)"),
):
    """Add a tag to a dependency."""
    with console.status("[green]Adding tag...[/green]"):
        tag_mgr = TagManager()
        registry = DependencyRegistry()
        if not dependency_tree_check(dependency, registry):
            rprint(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)
        if not create_tag(dependency, tag_mgr, registry, tag_name, description, color):
            rprint(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)

    rprint(f"[green]To push tag remotely run: dtm tag push {dependency} {tag_name}[/green]")


def is_valid_push_state(dep_path: str, tag_name: str) -> bool:
    if run_command(['git', 'fetch', 'origin'], dep_path) is None:
        logging.error("Failed to fetch origin")
        return False

    if not clean_working_tree(dep_path):
        return False

    count = run_command(['git', 'rev-list', '--count', 'origin/main..HEAD'], dep_path)
    if count is None:
        logging.error("Failed to count commits ahead of origin/main")
        return False

    if count.strip() != "1":
        logging.error(
            "Branch must be exactly 1 commit ahead of origin/main to push a tag"
        )
        return False

    head = run_command(['git', 'rev-parse', 'HEAD'], dep_path)
    tag = run_command(['git', 'rev-parse', tag_name], dep_path)

    if None in (head, tag):
        logging.error("Failed to resolve commit hashes")
        return False

    logging.info("Push state is valid")
    return True


def create_pr(dependency: str, tag_name: str, dep_path: str):
    logging.info("[green]Creating PR...[/green]")
    branch = f"version/{tag_name}"
    checkout = run_command(['git', 'checkout', '-b', branch], dep_path)
    if checkout is None:
        logging.error(f"[red]Error:[/red] Failed to checkout branch '{branch}'")
        return False
    else:
        logging.info(f"[green]Checked out branch '{branch}'[/green]")

    push_new_branch = run_command(['git', 'push', '-u', 'origin', branch], dep_path)
    if push_new_branch is None:
        logging.error(f"[red]Error:[/red] Failed to push branch '{branch}'")
        return False
    else:
        logging.info(f"[green]Pushed branch '{branch}'[/green]")

    create_pr = run_command([
        'gh', 'pr', 'create',
        '--title', f"Chore: bump {dependency} version to {tag_name}",
        '--body', f"Bump {dependency} version to {tag_name}, PR generated by Deepiri Package Version Manager",
        '--base', 'main',
        '--head', branch
    ], dep_path)
    if create_pr is None:
        logging.error(f"[red]Error:[/red] Failed to create PR")
        return False
    else:
        logging.info(f"[green]Created PR '{create_pr}'[/green]")

    return create_pr.strip()


def validate_pr(pr_url: str):
    allowed_files = ['package.json', 'pyproject.toml', 'requirements.txt', 'poetry.lock', 'package-lock.json', 'yarn.lock']

    number = int(pr_url.rstrip("/").split("/")[-1])
    org = pr_url.rstrip("/").split("/")[-4]
    repo = pr_url.rstrip("/").split("/")[-3]
    repo_path = f"{org}/{repo}"

    view = run_command(['gh', 'pr', 'view', str(number), '--repo', repo_path, '--json', 'files'], dep_path)
    if view is None:
        logging.error(f"[red]Error:[/red] Failed to validate PR '{pr_url}'")
        return False
    else:
        logging.info(f"[green]Fetched PR '{pr_url}'[/green]")

    files = view.get('files')
    if files is None:
        logging.error(f"[red]Error:[/red] Failed to get files from PR '{pr_url}'")
        return False
    else:
        logging.info(f"[green]Got files from PR '{pr_url}'[/green]")

    for file in files:
        if file['path'] not in allowed_files:
            logging.error(f"[red]Error:[/red] File '{file['path']}' is not allowed in PR '{pr_url}'")
            return False
        elif file['additions'] != 1 or file['deletions'] != 1:
            logging.error(f"[red]Error:[/red] File '{file['path']}' has unexpected changes in PR '{pr_url}'")
            return False
        else:
            logging.info(f"[green]File '{file['path']}' is allowed in PR '{pr_url}'[/green]")
    
    return True


def auto_merge(pr_url: str, branch: str, dep_path: str):
    if not validate_pr(pr_url):
        logging.error(f"[red]Error:[/red] Failed to validate PR '{pr_url}'")
        return False
    else:
        logging.info(f"[green]Validated PR '{pr_url}'[/green]")

    pr_url = pr_url.rstrip("/").split("/")
    number = pr_url[-1]
    repo_path = f"{pr_url[-4]}/{pr_url[-3]}"
    if not run_command(['gh', 'pr', 'merge', str(number), '--repo', repo_path, '--merge', '--yes'], dep_path):
        logging.error(f"[red]Error:[/red] Failed to merge PR '{pr_url}'")
        return False
    else:
        logging.info(f"[green]Merged PR '{pr_url}'[/green]")

    #delete branch local and remote
    delete_local = run_command(['git', 'branch', '-d', branch], dep_path)
    if delete_local is None:
        logging.error(f"[red]Error:[/red] Failed to delete branch '{branch}' locally")
        return False
    else:
        logging.info(f"[green]Deleted branch '{branch}' locally[/green]")

    delete_remote = run_command(['git', 'push', 'origin', '--delete', branch], dep_path)
    if delete_remote is None:
        logging.error(f"[red]Error:[/red] Failed to delete branch '{branch}' remotely")
        return False
    else:
        logging.info(f"[green]Deleted branch '{branch}' remotely[/green]")

    return True


def push_sanitization(dependency: str, tag_name: str, dep_path: str):
    remote_tags = run_command(['git', 'ls-remote', '--tags', 'origin'], dep_path)
    if remote_tags is None:
        logging.error(f"[red]Error:[/red] Failed to check if '{tag_name}' exists remotely in '{dependency}'")
        return False
    elif remote_tags.strip() == "":
        logging.info(f"[green]No tags exist remotely in {dependency}[/green]")
        return True
    elif remote_tags.strip() != "":
        tags = set()
        for tag in remote_tags.strip().split('\n'):
            if 'refs/tags/' in tag:
                tag = tag.split('refs/tags/')[1]
                tag = tag.replace('^{}', '')
                tags.add(tag)
        
        if not tags:
            logging.info(f"[green]No tags exist with ref/tags/ in '{dependency}'[/green]")
            return True

        latest_tag = max(tags, key=Version)
        if Version(tag_name) <= Version(latest_tag):
            logging.error(f"[red]Error:[/red] Tag '{tag_name}' is not greater than latest tag '{latest_tag}' in '{dependency}'")
            return False
        else:
            logging.info(f"[green]Tag '{tag_name}' is greater than latest tag '{latest_tag}' in '{dependency}'[/green]")
            return True
    else:
        logging.error(f"[red]Error:[/red] during push sanitization.")
        return False


def push_tag(dependency: str, dep_path: str, tag_mgr: TagManager, tag_name: Optional[str] = None) -> bool:
    is_repo = run_command(['git', 'rev-parse', '--is-inside-work-tree'], dep_path)
    if is_repo is None or is_repo != 'true':
        logging.error(f"[red]Error:[/red] Dependency '{dependency}' is not a submodule or repository, cannot push tag")
        return False

    if tag_name is None:
        local_tags = run_command(['git', 'tag', '--sort=-v:refname'], dep_path)
        if local_tags is None or local_tags.strip() == "":
            logging.error(f"[red]Error:[/red] There are no tags to push in '{dependency}'")
            return False
        elif local_tags.strip() != "":
            tag_name = local_tags.strip().split("\n")[0]
            logging.info(f"[green]Pushing latest tag '{tag_name}' in '{dependency}'[/green]")
    
    exists_in_db = tag_mgr.check_tag_exists_in_dependency(dependency, tag_name)
    if not exists_in_db:
        logging.error(f"[red]Error:[/red] Tag '{tag_name}' not found in dependency '{dependency}'")
        return False
    else:
        logging.info(f"[green]Tag '{tag_name}' exists in dependency '{dependency}'[/green]")

    exists_locally = run_command(['git', 'tag', '--list', tag_name], dep_path)
    if exists_locally is None or exists_locally.strip() == "":
        logging.error(f"[red]Error:[/red] Tag '{tag_name}' not found locally in '{dependency}'")
        return False
    else:
        logging.info(f"[green]Tag '{tag_name}' exists locally in '{dependency}'[/green]")

    if not push_sanitization(dependency, tag_name, dep_path):
        logging.error(f"[red]Error:[/red] Push sanitization failed")
        return False

    pr = create_pr(dependency, tag_name, dep_path)
    if not pr:
        logging.error(f"[red]Error:[/red] Failed to create PR")
        return False
    else:
        logging.info(f"[green]Created PR '{pr}'[/green]")

    merge = auto_merge(pr, f"version/{tag_name}", dep_path)
    if not merge:
        logging.error(f"[red]Error:[/red] Failed to merge the version bump PR")
        return False
    else:
        logging.info(f"[green]Merged the version bump PR[/green]")

    output = run_command(['git', 'push', 'origin', tag_name], dep_path)
    if output is None:
        logging.error(f"[red]Error:[/red] Failed to push tag '{tag_name}' to '{dependency}'")
        return False
    else:
        logging.info(f"[green]Pushed tag '{tag_name}' to '{dependency}'[/green]")

    logging.info(f"[green]Tag '{tag_name}' pushed to '{dependency}'[/green]")
    return True


@tag_app.command("push")
def tag_push(
    dependency: str = typer.Argument(..., help="Dependency name"),
    tag_name: Optional[str] = typer.Argument(None, help="Tag name")
):
    """Push a tag to a dependency."""
    with console.status("[green]Pushing tag...[/green]"):
        tag_mgr = TagManager()
        registry = DependencyRegistry()

        dep = registry.get(dependency)
        dep_path = dep.repo_path
        if not is_valid_push_state(dep_path, tag_name):
            console.log(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)
        if not push_tag(dependency, dep_path, tag_mgr, tag_name):
            console.log(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)
    
    rprint(f"[green]Tag '{tag_name}' pushed to '{dependency}'[/green]")


def update_repo_with_most_recent_tag(dependency, tag_name: str, dep_path: str) -> bool:
    recent_tag = run_command(['git', 'ls-remote', '--tags', '--sort=-v:refname', 'origin'], dep_path)
    if recent_tag is None or recent_tag.strip() == "":
        logging.info(f"[yellow]No remote tags found in '{dependency.name}', defaulting to v0.0.0[/yellow]")
        tag_name = "v0.0.0"
    else:
        tag_name = recent_tag.strip().split("\n")[0]
        logging.info(f"[green]Most recent remote tag in '{dependency.name}' is '{tag_name}'[/green]")

    if not bump_version(dependency, tag_name):
        logging.error(f"[red]Error:[/red] Failed to bump version")
        return False
    else:
        logging.info(f"[green]Bumped version to '{tag_name}' in '{dependency}'[/green]")
    
    if not create_pr(dependency, tag_name, dep_path):
        logging.error(f"[red]Error:[/red] Failed to create PR")
        return False
    else:
        logging.info(f"[green]Created PR '{pr}'[/green]")

    if not auto_merge():
        logging.error(f"[red]Error:[/red] Failed to merge the version bump PR")
        return False
    else:
        logging.info(f"[green]Merged the version bump PR[/green]")

    if tag_name == "v0.0.0":
        output = run_command(['git', 'push', 'origin', tag_name], dep_path)
        if output is None:
            logging.error(f"[red]Error:[/red] Failed to push tag '{tag_name}' to '{dependency}'")
            return False
        else:
            logging.info(f"[green]Pushed tag '{tag_name}' to '{dependency}'[/green]")
    
    return True


def remove_check(dependency: str, registry: DependencyRegistry):
    dep = registry.get(dependency)
    if not dep:
        logging.error(f"[red]Error:[/red] Dependency '{dependency}' not found")
        return False

    dep_path = dep.repo_path
    if not clean_working_tree(dep_path):
        logging.error(f"[red]Error:[/red] Working tree is not clean, ensure all changes are committed or stashed before pushing a new tag.")
        return False

    logging.info(f"[green]Remove check passed for '{dependency}'[/green]")
    return True

def remove_tag(dependency: str, tag_name: str, tag_mgr: TagManager, registry: DependencyRegistry):
    dep = registry.get(dependency)
    dep_path = dep.repo_path

    check_local = run_command(['git', 'tag', '--list', tag_name], dep_path)
    if check_local is None or check_local.strip() == "":
        logging.info(f"[yellow]Tag '{tag_name}' does not exist locally in '{dependency}'[/yellow]")
    else:
        success = tag_mgr.remove_tag_from_dependency(dependency, tag_name)
        if success:
            logging.info(f"[green]Removed tag '{tag_name}' from '{dependency}' in db[/green]")
        else:
            logging.error(f"[red]Error:[/red] Tag or dependency not found in storage")
            return False

        remove_locally = run_command(['git', 'tag', '-d', tag_name], dep_path)
        if remove_locally is None:
            logging.error(f"[red]Error:[/red] Failed to remove tag '{tag_name}' from '{dependency}'")
            return False
        else:
            logging.info(f"[green]Removed tag '{tag_name}' from '{dependency}' locally[/green]")
    
    check_remote = run_command(['git', 'ls-remote', '--tags', 'origin', tag_name], dep_path)
    if check_remote is None:
        logging.error(f"[red]Error:[/red] Failed to check if tag '{tag_name}' exists remotely in '{dependency}'")
        return False
    elif check_remote.strip() != "":
        delete = run_command(['git', 'push', 'origin', '--delete', tag_name], dep_path)
        if delete is None:
            logging.error(f"[red]Error:[/red] Failed to delete tag '{tag_name}' from '{dependency}'")
            return False
        else:
            logging.info(f"[green]Deleted tag '{tag_name}' from '{dependency}'[/green]")
            """if not update_repo_with_most_recent_tag(dep, tag_name, dep_path):
                logging.error(f"[red]Error:[/red] Failed to update repository with most recent tag")
                return False
            else:
                logging.info(f"[green]Updated repository with most recent tag in '{dependency}'[/green]")"""
    else:
        logging.info(f"[green]Tag '{tag_name}' does not exist remotely in '{dependency}'[/green]")

    logging.info(f"[green]Tag '{tag_name}' removed from '{dependency}'[/green]")
    return True


@tag_app.command("remove")
def tag_remove(
    dependency: str = typer.Argument(..., help="Dependency name"),
    tag_name: str = typer.Argument(..., help="Tag name"),
):
    """Remove a tag from a dependency."""
    with console.status("[green]Removing tag...[/green]"):
        tag_mgr = TagManager()
        registry = DependencyRegistry()
        if not remove_check(dependency, registry):
            console.log(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)
        if not remove_tag(dependency, tag_name, tag_mgr, registry):
            console.log(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)

    rprint(f"[green]Tag '{tag_name}' removed from '{dependency}'[/green]")


@tag_app.command("list")
def tag_list(
    dependency: Optional[str] = typer.Argument(None, help="Dependency name (optional)"),
):
    """List tags for a dependency or all tags."""
    tag_mgr = TagManager()
    
    if dependency:
        tags = tag_mgr.get_dependency_tags(dependency)
        if tags:
            console.print(f"[cyan]Tags for '{dependency}':[/cyan]")
            for t in tags:
                console.print(f"  - {t.name}")
                if t.description:
                    console.print(f"    {t.description}")
        else:
            console.print(f"[yellow]No tags for '{dependency}'[/yellow]")
    else:
        tags = tag_mgr.get_tags_with_counts()
        if not tags:
            rprint("[yellow]No tags found[/yellow]")
            return
        
        table = Table(title="All Tags")
        table.add_column("Name", style="cyan")
        table.add_column("Count", style="magenta")
        table.add_column("Description")
        
        for tc in tags:
            table.add_row(
                tc.tag.name,
                str(tc.dependency_count),
                tc.tag.description or "-",
            )
        
        console.print(table)


def update_helper(dependency: str, tag_mgr: TagManager, dep_path: str, type: str, description: str = "", color: Optional[str] = None) -> str | None:
    registry = DependencyRegistry()
    recent_local = run_command(['git', 'tag', '--sort=-v:refname'], dep_path)
    if recent_local is None or recent_local.strip() == "":
        logging.error(f"[red]Error:[/red] No tags found in '{dependency}'")
        return None
    else:
        tag_name = recent_local.strip().split("\n")[0]
        logging.info(f"[green]Recent local tag in '{dependency}' is '{recent_local}'[/green]")

    if type == "patch":
        tag = tag_name.split('.')
        tag[-1] = str(int(tag[-1]) + 1)
        new_tag = '.'.join(tag)
    elif type == "minor":
        tag = tag_name.split('.')
        tag[-2] = str(int(tag[-2]) + 1)
        tag[-1] = '0'
        new_tag = '.'.join(tag)
    elif type == "major":
        tag = tag_name.split('.')
        tag[0] = 'v' + str(int(tag[0].lstrip('v')) + 1)
        tag[-2] = '0'
        tag[-1] = '0'
        new_tag = '.'.join(tag)
    else:
        logging.error(f"[red]Error:[/red] Invalid type '{type}'")
        return None

    tag_mgr.create_tag(name=new_tag, description=description, color=color)
    added = tag_mgr.add_tag_to_dependency(dependency, new_tag)
    if not added:
        logging.error(f"[red]Error:[/red] Failed to add tag '{new_tag}' to '{dependency}'")
        return None
    else:
        logging.info(f"[green]Added tag '{new_tag}' to '{dependency}'[/green]")

    if not bump_version(registry.get(dependency), new_tag):
        logging.error(f"[red]Error:[/red] Failed to bump version")
        return None
    else:
        logging.info(f"[green]Bumped version to '{new_tag}' in '{dependency}'[/green]")

    added_locally = run_command(['git', 'tag', '-a', new_tag, '-m', description], dep_path)
    if added_locally is None:
        logging.error(f"[red]Error:[/red] Failed to add tag '{new_tag}' locally in '{dependency}'")
        return None
    else:
        logging.info(f"[green]Added tag '{new_tag}' locally in '{dependency}'[/green]")

    logging.info(f"[green]To push tag remotely run: dtm tag push {dependency} {new_tag}[/green]")
    return new_tag


@tag_app.command("patch")
def tag_patch(
    dependency: str = typer.Argument(..., help="Dependency name"),
    description: str = typer.Option(..., "--description", "-d", help="Tag description"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)"),
):
    with console.status("[green]Updating dependency tag with patch...[/green]"):
        tag_mgr = TagManager()
        registry = DependencyRegistry()
        
        if not dependency_tree_check(dependency, registry):
            rprint(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)
        dep_path = registry.get(dependency).repo_path
        if update_helper(dependency, tag_mgr, dep_path, "patch", description, color) is None:
            rprint(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)

    rprint(f"[green]To push tag remotely run: dtm tag push {dependency} {new_tag}[/green]")


@tag_app.command("minor")
def tag_minor(
    dependency: str = typer.Argument(..., help="Dependency name"),
    description: str = typer.Option(..., "--description", "-d", help="Tag description"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)"),
):
    with console.status("[green]Updating dependency tag with minor bump...[/green]"):
        tag_mgr = TagManager()
        registry = DependencyRegistry()

        if not dependency_tree_check(dependency, registry):
            rprint(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)
        dep_path = registry.get(dependency).repo_path
        if update_helper(dependency, tag_mgr, dep_path, "minor", description, color) is None:
            rprint(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)

    rprint(f"[green]To push tag remotely run: dtm tag push {dependency} {new_tag}[/green]")


@tag_app.command("major")
def tag_major(
    dependency: str = typer.Argument(..., help="Dependency name"),
    description: str = typer.Option(..., "--description", "-d", help="Tag description"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)"),
):
    with console.status("[green]Updating dependency tag with major bump...[/green]"):
        tag_mgr = TagManager()
        registry = DependencyRegistry()

        if not dependency_tree_check(dependency, registry):
            rprint(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)
        dep_path = registry.get(dependency).repo_path
        if update_helper(dependency, tag_mgr, dep_path, "major", description, color) is None:
            rprint(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)

    rprint(f"[green]To push tag remotely run: dtm tag push {dependency} {new_tag}[/green]")


@app.command("display")
def ui():
    """Launch UI."""
    from deepiri_pkg_version_manager.ui.display import PackageManagerUI

    app = QApplication(sys.argv)
    window = PackageManagerUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    app()
