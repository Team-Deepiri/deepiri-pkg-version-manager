import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from deepiri_pkg_version_manager.utils import run_command
from deepiri_pkg_version_manager.scanners.repo_scanner import (
    ScannedDependency,
    scan_directory,
)

console = Console()

CLONE_DIR = Path("./repos")


def list_org_repos(org: str) -> list[str]:
    output = run_command(
        ["gh", "repo", "list", org, "--limit", "200", "--json", "name", "-q", ".[].name"]
    )
    if not output:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def clone_repo(org: str, repo: str, base_dir: Path = CLONE_DIR) -> Optional[Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    target = base_dir / repo

    if target.exists():
        return target.resolve()

    logging.info(f"[cyan]Cloning[/cyan] {org}/{repo} -> {target}")
    if run_command(["gh", "repo", "clone", f"{org}/{repo}", str(target)]) is None:
        return None
    return target.resolve()


def scan_org(
    org: str,
    repo: Optional[str] = None,
    package_types: Optional[list[str]] = None,
    verbose: bool = False,
    base_dir: Path = CLONE_DIR,
) -> list[ScannedDependency]:
    repos = list_org_repos(org)
    if not repos:
        logging.error(
            f"No repositories returned for organization '{org}'. "
            "Check that 'gh auth status' is OK and the org name is correct."
        )
        raise typer.Exit(1)

    if repo:
        if repo not in repos:
            logging.error(f"Repository '{repo}' not found in organization '{org}'")
            raise typer.Exit(1)
        repos = [repo]

    all_scanned: list[ScannedDependency] = []
    for r in repos:
        repo_path = clone_repo(org, r, base_dir=base_dir)
        if repo_path is None:
            logging.warning(f"[yellow]Skipping {org}/{r} (clone failed)[/yellow]")
            continue

        if verbose:
            logging.info(f"[cyan]Scanning:[/cyan] {repo_path}")

        scanned = scan_directory(
            repo_path,
            package_types=package_types,
            verbose=verbose,
        )
        all_scanned.extend(scanned)

    return all_scanned
