import json
import typer
import subprocess
from typing import Optional, List
import subprocess
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.syntax import Syntax
from packaging.version import Version

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
        rprint(f"[red]Error:[/red] Path does not exist: {path}")
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
    registry = DependencyRegistry()
    g = registry.build_graph()
    
    if g.graph.number_of_nodes() == 0:
        rprint("[yellow]No graph data. Run 'dtm scan' first.[/yellow]")
        return
    
    if dependents:
        result = g.get_all_dependents_recursive(dependents)
        if result:
            console.print(f"[cyan]Packages depending on '{dependents}':[/cyan]")
            for r in sorted(result):
                console.print(f"  - {r}")
        else:
            console.print(f"[yellow]No dependents found for '{dependents}'[/yellow]")
        return
    
    if dependencies:
        result = g.get_all_dependencies_recursive(dependencies)
        if result:
            console.print(f"[cyan]Packages '{dependencies}' depends on:[/cyan]")
            for r in sorted(result):
                console.print(f"  - {r}")
        else:
            console.print(f"[yellow]No dependencies found for '{dependencies}'[/yellow]")
        return
    
    if g.has_cycle():
        console.print("[yellow]Warning: Graph contains cycles![/yellow]")
        cycles = g.get_cycles()
        for cycle in cycles:
            console.print(f"  - {' -> '.join(cycle)}")
    
    tree = g.to_tree_string(root=root)
    console.print(f"\n[bold]Dependency Tree:[/bold]\n{tree}")


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


def run_git_command(command: List[str], cwd: str) -> Optional[str]:
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
        rprint(f"[red]Git Error:[/red] {error_msg}")
        return None

    except Exception as e:
        rprint(f"[red]Unexpected Error:[/red] {e}")
        return None


def dependency_tree_check(dependency: str, registry: DependencyRegistry):
    dep = registry.get(dependency)
    if not dep:
        rprint(f"[red]Error:[/red] Dependency '{dependency}' not found")
        return False

    dep_path = dep.repo_path
    if not clean_working_tree(dep_path):
        rprint(f"[red]Error:[/red] Working tree is not clean, ensure all changes are committed or stashed before pushing a new tag.")
        return False

    return True


def clean_working_tree(dep_path: str) -> bool:
    clean = run_git_command(['git', 'status', '--porcelain'], dep_path)
    if clean is None:
        rprint(f"[red]Error:[/red] Failed to check if working tree is clean")
        return False
    elif clean.strip() != '':
        rprint(f"[red]Error:[/red] Working tree is not clean, ensure all changes are committed or stashed before pushing a new tag.")
        return False
    else:
        rprint(f"[green]Working tree is clean[/green]")
        return True


def check_valid_tag(tag_name: str, dependency: str, dep_path: str):
    if not check_valid_format(tag_name):
        return False

    tags = run_git_command(['git', 'tag', '--sort=-v:refname'], dep_path)
    if tags is None:
        rprint(f"[red]Error:[/red] Failed to get recent tag in '{dependency}'")
        return False
    elif tags.strip() == "":
        rprint(f"[green]No tags exist in '{dependency}'[/green]")
        return True
    
    if tags:
        latest_tag = tags.strip().split("\n")[0]
        if Version(tag_name) <= Version(latest_tag):
            rprint(f"[red]Error:[/red] Tag '{tag_name}' is not greater than latest tag '{latest_tag.join(".")}' in '{dependency}'")
            return False
    
    rprint(f"[green]Tag '{tag_name}' is valid in '{dependency}'[/green]")
    return True


def check_valid_format(tag_name: str):
    if not tag_name.startswith("v") or not tag_name.count(".") == 2 or not tag_name.split(".")[0].strip("v").isdigit() or not tag_name.split(".")[1].isdigit() or not tag_name.split(".")[2].isdigit():
        rprint(f"[red]Error:[/red] Invalid tag format '{tag_name}', use format v<major>.<minor>.<patch>")
        return False
    else:
        return True


def create_tag(dependency: str, tag_mgr: TagManager, registry: DependencyRegistry, tag_name: Optional[str] = None, description: Optional[str] = None, color: Optional[str] = None):
    dep = registry.get(dependency)
    dep_path = dep.repo_path

    if tag_name is None:
        local_tags = run_git_command(['git', 'tag'], dep_path)
        if local_tags is None:
            rprint(f"[red]Error:[/red] Failed to get local tags in '{dependency}'")
            raise typer.Exit(1)
        elif local_tags.strip() != "":
            rprint(f"[red]Error:[/red] Local tags found in '{dependency}', to use default add behavior there should be no local tags.")
            raise typer.Exit(1)
        else:
            tag_name = "v0.0.0"
    else:
        if not check_valid_tag(tag_name, dependency, dep_path):
            raise typer.Exit(1)

    tag_mgr.create_tag(name=tag_name, description=description, color=color)
    success = tag_mgr.add_tag_to_dependency(dependency, tag_name)
    if success:
        rprint(f"[green]Added tag '{tag_name}' to '{dependency}' in db[/green]")
    else:
        rprint(f"[red]Error:[/red] Failed to add tag")

    if description is not None:
        output = run_git_command(['git', 'tag', '-a', tag_name, '-m', description], dep.repo_path)
    else:
        output = run_git_command(['git', 'tag', tag_name], dep.repo_path)

    if output is None:
        rprint(f"[red]Error:[/red] Failed to create tag '{tag_name} in {dependency}'")
    else:
        rprint(f"[green]Created tag '{tag_name}' in '{dependency}' locally[/green]")

    rprint(f"[green]To push tag remotely run: dtm tag push {dependency} {tag_name}[/green]")

@tag_app.command("add")
def tag_add(
    dependency: str = typer.Argument(..., help="Dependency name"),
    tag_name: Optional[str] = typer.Argument(None, help="Tag name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Tag description"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)"),
):
    """Add a tag to a dependency."""
    tag_mgr = TagManager()
    registry = DependencyRegistry()
    if not dependency_tree_check(dependency, registry):
        raise typer.Exit(1)
    create_tag(dependency, tag_mgr, registry, tag_name, description, color)


def push_sanitization(dependency: str, tag_name: str, dep_path: str):
    remote_tags = run_git_command(['git', 'ls-remote', '--tags', 'origin'], dep_path)
    if remote_tags is None:
        rprint(f"[red]Error:[/red] Failed to check if '{tag_name}' exists remotely in '{dependency}'")
        return False
    elif remote_tags.strip() == "":
        rprint(f"[green]No tags exist remotely in {dependency}[/green]")
        return True
    elif remote_tags.strip() != "":
        tags = set()
        for tag in remote_tags.strip().split('\n'):
            if 'refs/tags/' in tag:
                tag = tag.split('refs/tags/')[1]
                tag = tag.replace('^{}', '')
                tags.add(tag)
        
        if not tags:
            rprint(f"[green]No tags exist with ref/tags/ in '{dependency}'[/green]")
            return True

        latest_tag = max(tags, key=Version)
        if Version(tag_name) <= Version(latest_tag):
            rprint(f"[red]Error:[/red] Tag '{tag_name}' is not greater than latest tag '{latest_tag}' in '{dependency}'")
            return False
        else:
            rprint(f"[green]Tag '{tag_name}' is greater than latest tag '{latest_tag}' in '{dependency}'[/green]")
            return True
    else:
        rprint(f"[red]Error:[/red] during push sanitization.")
        return False


def push_submodule(dependency: str, tag_name: str, dep_path: str):
    """Update dependency root if dependency is a submodule"""
    checkout = run_git_command(['git', 'checkout', tag_name], dep_path)
    if checkout is None:
        rprint(f"[red]Error:[/red] Failed to checkout tag '{tag_name}' in '{dependency}'")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Checked out tag '{tag_name}' in '{dependency}'[/green]")

    main_path = Path(__file__).parent.parent / "deepiri-platform"
    add = run_git_command(['git', 'add', dep_path], main_path)
    if add is None:
        rprint(f"[red]Error:[/red] Failed to add changes in '{dependency}'")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Added changes in '{dependency}' to main repository[/green]")
    
    commit = run_git_command(['git', 'commit', '-m', f"Update dependency '{dependency}' to tag '{tag_name}'"], main_path)
    if commit is None:
        rprint(f"[red]Error:[/red] Failed to commit changes in '{dependency}'")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Committed changes in '{dependency}' to main repository[/green]")
        
    push = run_git_command(['git', 'push', 'origin', 'HEAD'], main_path)
    if push is None:
        rprint(f"[red]Error:[/red] Failed to push new version '{tag_name}' in '{dependency}' to main repository")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Pushed new version '{tag_name}' in '{dependency}' to main repository[/green]")


def push_tag(dependency: str, dep_path: str, tag_mgr: TagManager, tag_name: Optional[str] = None):
    is_repo = run_git_command(['git', 'rev-parse', '--is-inside-work-tree'], dep_path)
    if is_repo is None or is_repo != 'true':
        rprint(f"[red]Error:[/red] Dependency '{dependency}' is not a submodule or repository, cannot push tag")
        raise typer.Exit(1)

    if tag_name is None:
        local_tags = run_git_command(['git', 'tag', '--sort=-v:refname'], dep_path)
        if local_tags is None or local_tags.strip() == "":
            rprint(f"[red]Error:[/red] There are no tags to push in '{dependency}'")
            raise typer.Exit(1)
        elif local_tags.strip() != "":
            tag_name = local_tags.strip().split("\n")[0]
            rprint(f"[green]Pushing latest tag '{tag_name}' in '{dependency}'[/green]")
    
    exists_in_db = tag_mgr.check_tag_exists_in_dependency(dependency, tag_name)
    if not exists_in_db:
        rprint(f"[red]Error:[/red] Tag '{tag_name}' not found in dependency '{dependency}'")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Tag '{tag_name}' exists in dependency '{dependency}'[/green]")

    exists_locally = run_git_command(['git', 'tag', '--list', tag_name], dep_path)
    if exists_locally is None or exists_locally.strip() == "":
        rprint(f"[red]Error:[/red] Tag '{tag_name}' not found locally in '{dependency}'")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Tag '{tag_name}' exists locally in '{dependency}'[/green]")

    if not push_sanitization(dependency, tag_name, dep_path):
        rprint(f"[red]Error:[/red] Push sanitization failed")
        raise typer.Exit(1)

    output = run_git_command(['git', 'push', 'origin', tag_name], dep_path)
    if output is None:
        rprint(f"[red]Error:[/red] Failed to push tag '{tag_name}' to '{dependency}'")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Pushed tag '{tag_name}' to '{dependency}'[/green]")


@tag_app.command("push")
def tag_push(
    dependency: str = typer.Argument(..., help="Dependency name"),
    tag_name: Optional[str] = typer.Argument(None, help="Tag name")
):
    """Push a tag to a dependency."""
    tag_mgr = TagManager()
    registry = DependencyRegistry()

    dep = registry.get(dependency)
    dep_path = dep.repo_path
    if not dependency_tree_check(dependency, registry):
        raise typer.Exit(1)
    push_tag(dependency, dep_path, tag_mgr, tag_name)
    if dep.is_submodule:
        push_submodule(dependency, tag_name, dep_path)


def remove_tag(dependency: str, tag_name: str, tag_mgr: TagManager, registry: DependencyRegistry):
    dep = registry.get(dependency)
    dep_path = dep.repo_path

    success = tag_mgr.remove_tag_from_dependency(dependency, tag_name)
    if success:
        rprint(f"[green]Removed tag '{tag_name}' from '{dependency}' in db[/green]")
    else:
        rprint(f"[red]Error:[/red] Tag or dependency not found")
        raise typer.Exit(1)

    remove_locally = run_git_command(['git', 'tag', '-d', tag_name], dep_path)
    if remove_locally is None:
        rprint(f"[red]Error:[/red] Failed to remove tag '{tag_name}' from '{dependency}'")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Removed tag '{tag_name}' from '{dependency}' locally[/green]")
    
    check_remote = run_git_command(['git', 'ls-remote', '--tags', 'origin', tag_name], dep_path)
    if check_remote is None:
        rprint(f"[red]Error:[/red] Failed to check if tag '{tag_name}' exists remotely in '{dependency}'")
        raise typer.Exit(1)
    elif check_remote.strip() != "":
        delete = run_git_command(['git', 'push', 'origin', '--delete', tag_name], dep_path)
        if delete is None:
            rprint(f"[red]Error:[/red] Failed to delete tag '{tag_name}' from '{dependency}'")
            raise typer.Exit(1)
        else:
            rprint(f"[green]Deleted tag '{tag_name}' from '{dependency}'[/green]")
    else:
        rprint(f"[green]Tag '{tag_name}' does not exist remotely in '{dependency}'[/green]")


@tag_app.command("remove")
def tag_remove(
    dependency: str = typer.Argument(..., help="Dependency name"),
    tag_name: str = typer.Argument(..., help="Tag name"),
):
    """Remove a tag from a dependency."""
    tag_mgr = TagManager()
    registry = DependencyRegistry()
    if not dependency_tree_check(dependency, registry):
        raise typer.Exit(1)
    remove_tag(dependency, tag_name, tag_mgr, registry)


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


def update_helper(dependency: str, tag_name: str, type: str, description: Optional[str] = None, color: Optional[str] = None):
    tag_mgr = TagManager()
    registry = DependencyRegistry()

    dep = registry.get(dependency)
    if not dep:
        rprint(f"[red]Error:[/red] Dependency '{dependency}' not found")
        raise typer.Exit(1)
    
    dep_path = dep.repo_path
    if not clean_working_tree(dep_path):
        rprint(f"[red]Error:[/red] Working tree is not clean, ensure all changes are committed or stashed before pushing a new tag.")
        raise typer.Exit(1)

    check_db = tag_mgr.check_tag_exists_in_dependency(dependency, tag_name)
    if not check_db:
        rprint(f"[red]Error:[/red] Tag '{tag_name}' not found in dependency '{dependency}'")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Tag '{tag_name}' found in dependency '{dependency}'[/green]")

    local_tag = run_git_command(['git', 'tag', '--list', tag_name], dep_path)
    if local_tag is None or local_tag.strip() == "":
        rprint(f"[red]Error:[/red] Tag '{tag_name}' not found locally in '{dependency}'")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Tag '{tag_name}' found locally in '{dependency}'[/green]")

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
        rprint(f"[red]Error:[/red] Invalid type '{type}'")
        raise typer.Exit(1)

    tag_mgr.create_tag(name=new_tag, description=description, color=color)
    added = tag_mgr.add_tag_to_dependency(dependency, new_tag)
    if not added:
        rprint(f"[red]Error:[/red] Failed to add tag '{new_tag}' to '{dependency}'")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Added tag '{new_tag}' to '{dependency}'[/green]")

    if description is not None:
        added_locally = run_git_command(['git', 'tag', '-a', new_tag, '-m', description], dep_path)
    else:
        added_locally = run_git_command(['git', 'tag', new_tag], dep_path)

    if added_locally is None:
        rprint(f"[red]Error:[/red] Failed to add tag '{new_tag}' locally in '{dependency}'")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Added tag '{new_tag}' locally in '{dependency}'[/green]")

    rprint(f"[green]To add tag remotely run: dtm tag push {dependency} {new_tag}[/green]")


@tag_app.command("patch")
def tag_patch(
    dependency: str = typer.Argument(..., help="Dependency name"),
    tag_name: str = typer.Argument(..., help="Tag name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Tag description"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)"),
):
    update_helper(dependency, tag_name, "patch", description, color)


@tag_app.command("minor")
def tag_minor(
    dependency: str = typer.Argument(..., help="Dependency name"),
    tag_name: str = typer.Argument(..., help="Tag name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Tag description"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)"),
):
    update_helper(dependency, tag_name, "minor", description, color)


@tag_app.command("major")
def tag_major(
    dependency: str = typer.Argument(..., help="Dependency name"),
    tag_name: str = typer.Argument(..., help="Tag name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Tag description"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)"),
):
    update_helper(dependency, tag_name, "major", description, color)


@app.command("display")
def ui():
    """Launch animated TUI."""
    rprint("[yellow]TUI not yet implemented. Use CLI commands instead.[/yellow]")
    import sys
    from PySide6.QtWidgets import QApplication
    from deepiri_pkg_version_manager.ui.display import PackageManagerUI

    app = QApplication(sys.argv)
    window = PackageManagerUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    app()
