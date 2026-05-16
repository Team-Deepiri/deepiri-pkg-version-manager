import os
import sys
import json
import typer
import subprocess
import logging
from typing import Optional, List
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.syntax import Syntax


def _configure_qt_runtime_env() -> None:
    is_wsl = "microsoft" in os.uname().release.lower() or bool(os.environ.get("WSL_DISTRO_NAME"))
    if not is_wsl:
        return

    if not os.environ.get("DISPLAY"):
        os.environ["DISPLAY"] = ":0"

    os.environ["QT_QPA_PLATFORM"] = "xcb"


_configure_qt_runtime_env()

from PySide6.QtWidgets import QApplication

from deepiri_pkg_version_manager.utils import (
    check_org_permissions,
    create_tag,
    dep_clone_dir,
    dep_org_repo,
    dependency_tree_check,
    is_path_under,
    push_tag,
    remove_check,
    remove_tag,
    run_command,
    update_helper,
    branch_cleanup
)
from deepiri_pkg_version_manager.deps.dependency_registry import DependencyRegistry
from deepiri_pkg_version_manager.tags.tag_manager import TagManager
from deepiri_pkg_version_manager.scanners.repo_scanner import scan_directory, get_install_command, get_install_all_command
from deepiri_pkg_version_manager.scanners.org_scanner import scan_org

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
    org: Optional[str] = typer.Option(
        None,
        "--org",
        "-o",
        help="Organization to scan",
    ),
    repo: Optional[str] = typer.Option(
        None,
        "--repo",
        "-r",
        help="Repository to scan (default: all repositories)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to database"),
    clear: bool = typer.Option(False, "--clear", help="Clear existing data before scanning")
):
    """Scan repositories and build dependency graph."""
    
    if org and path:
        logging.error(f"[red]Error:[/red] Specify either a path or an organization, not both")
        raise typer.Exit(1)

    if not org and not path:
        path = Path(__file__).parent.parent / "deepiri-platform"

    if path is not None and not path.exists():
        logging.error(f"[red]Error:[/red] Path does not exist: {path}")
        raise typer.Exit(1)

    types = ["npm", "poetry", "pip"] if "all" in package_type else package_type

    if path is not None:
        console.print(f"[cyan]Scanning:[/cyan] {path}")
        console.print(f"[cyan]Types:[/cyan] {', '.join(types)}")

        scanned = scan_directory(path, package_types=types, verbose=verbose)
    else:
        if not check_org_permissions(org):
            logging.error(f"[red]Error:[/red] You do not have permission to scan this organization")
            raise typer.Exit(1)

        console.print(f"[cyan]Scanning:[/cyan] {org}")
        console.print(f"[cyan]Types:[/cyan] {', '.join(types)}")

        try: 
            with console.status(f"[green]Scanning organization {org}, this may take a while...[/green]"):
                scanned = scan_org(org, repo, package_types=types, verbose=verbose)
        except Exception as e:
            rprint(f"[red]Error:[/red] {e}, check logs for more information")
            raise typer.Exit(1)
    
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
def clear_db(
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Path to clear"),
    org: Optional[str] = typer.Option(None, "--org", "-o", help="Organization to clear"),
    repo: Optional[str] = typer.Option(
        None, "--repo", "-r", help="Repository to clear (requires --org)"
    )
):
    if path and org:
        logging.error("[red]Error:[/red] Specify either a path or an organization, not both")
        raise typer.Exit(1)

    if repo and not org:
        logging.error("[red]Error:[/red] --repo requires --org")
        raise typer.Exit(1)

    registry = DependencyRegistry()
    clone_root = Path("repos")

    if not path and not org:
        registry.clear_all()
        if clone_root.exists():
            if run_command(["rm", "-rf", str(clone_root)]) is None:
                logging.error("[red]Error:[/red] Failed to clear repos directory")
                raise typer.Exit(1)
        console.print("[green]Cleared all dependencies and cloned repos[/green]")
        return

    if path is not None:
        if not path.exists():
            logging.error(f"[red]Error:[/red] Path does not exist: {path}")
            raise typer.Exit(1)

        target = path.resolve()
        removed: list[str] = []
        for dep in registry.get_all():
            try:
                dep_path = Path(dep.repo_path).resolve()
            except (OSError, ValueError):
                continue
            if is_path_under(dep_path, target):
                if registry.delete(dep.name):
                    removed.append(dep.name)

        console.print(
            f"[green]Removed {len(removed)} dependencies under {path}[/green]"
        )
        return

    target_repo = repo.lower() if repo else None
    org_lc = org.lower()

    removed_names: list[str] = []
    clone_dirs_to_remove: set[Path] = set()
    matched_repos: set[str] = set()

    for dep in registry.get_all():
        meta = dep_org_repo(dep)
        if not meta:
            continue
        dep_org, dep_repo = meta
        dep_repo_lc = dep_repo.lower()

        if dep_org:
            if dep_org.lower() != org_lc:
                continue
        elif target_repo is None or dep_repo_lc != target_repo:
            continue

        if target_repo is not None and dep_repo_lc != target_repo:
            continue

        if registry.delete(dep.name):
            removed_names.append(dep.name)
            matched_repos.add(dep_repo)
            clone_dir = dep_clone_dir(dep, clone_root)
            if clone_dir is not None:
                clone_dirs_to_remove.add(clone_dir)

    if target_repo is not None and not clone_dirs_to_remove:
        candidate = clone_root / repo
        if candidate.exists():
            clone_dirs_to_remove.add(candidate.resolve())

    for clone_dir in clone_dirs_to_remove:
        if clone_dir.exists():
            if run_command(["rm", "-rf", str(clone_dir)]) is None:
                logging.error(
                    f"[red]Error:[/red] Failed to remove clone directory {clone_dir}"
                )

    target_desc = f"{org}/{repo}" if repo else org
    console.print(
        f"[green]Removed {len(removed_names)} dependencies across "
        f"{len(matched_repos) or (1 if target_repo else 0)} repos for {target_desc}[/green]"
    )


@app.command("deps")
def list_dependencies(
    name: Optional[str] = typer.Argument(None, help="Specific dependency to show"),
    package_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    show_tags: bool = typer.Option(False, "--tags", "-T", help="Show tags")
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
    dependencies: Optional[str] = typer.Option(None, "--dependencies", help="Find all packages X depends on")
):
    """Display dependency graph."""
    from deepiri_pkg_version_manager.ui.graphDisplay import DependencyGraphView
    registry = DependencyRegistry()
    g = registry.build_graph()

    app = QApplication(sys.argv)
    window = DependencyGraphView(g, root=root)
    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())


@app.command()
def install(
    dependency: Optional[str] = typer.Argument(None, help="Dependency to install (or all)"),
    package_manager: Optional[str] = typer.Option(None, "--manager", "-m", help="Force package manager: npm, poetry, pip, pipenv"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Show commands without running"),
    all_deps: bool = typer.Option(False, "--all", "-a", help="Install all dependencies in package")
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
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Show changes without applying")
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
    format: str = typer.Option("json", "--format", "-f", help="Output format: json, dot")
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


@tag_app.command("add")
def tag_add(
    dependency: str = typer.Argument(..., help="Dependency name"),
    tag_name: Optional[str] = typer.Argument(None, help="Tag name"),
    description: str = typer.Option(..., "--description", "-d", help="Tag description"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)")
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

    if tag_name is None:
        rprint(f"[green]To push tag remotely run: dtm tag push {dependency} v0.0.0[/green]")
    else:
        rprint(f"[green]To push tag remotely run: dtm tag push {dependency} {tag_name}[/green]")


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
        if not push_tag(dependency, dep_path, tag_mgr, registry, tag_name):
            console.log(f"[red]Error:[/red] Check logs for more information")
            raise typer.Exit(1)
    
    rprint(f"[green]Tag '{tag_name}' pushed to '{dependency}'[/green]")


@tag_app.command("remove")
def tag_remove(
    dependency: str = typer.Argument(..., help="Dependency name"),
    tag_name: str = typer.Argument(..., help="Tag name")
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
    dependency: Optional[str] = typer.Argument(None, help="Dependency name (optional)")
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


@tag_app.command("patch")
def tag_patch(
    dependency: str = typer.Argument(..., help="Dependency name"),
    description: str = typer.Option(..., "--description", "-d", help="Tag description"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)")
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
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)")
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
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Tag color (hex)")
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


@app.command("branch-cleanup")
def branchCleanup(
    dep_name: str = typer.Option(..., "-d", "--dependency", help="Dependency name"),
    tag_name: str = typer.Option(..., "-t", "--tag", help="Tag name")
):
    with console.status("[green]Cleaning up branch...[/green]"):
        bc = branch_cleanup(dep_name, tag_name)
            
    if not bc:    
        rprint(f"[red]Error:[/red] Failed to cleanup branch, check logs for more information")
        raise typer.Exit(1)
    else:
        rprint(f"[green]Branch 'version/{tag_name}' cleaned up[/green]")


@app.command("display")
def ui():
    """Launch UI."""
    from deepiri_pkg_version_manager.ui.display import PackageManagerUI

    app = QApplication(sys.argv)
    window = PackageManagerUI()
    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    app()
