import json
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional

import typer
from dotenv import dotenv_values
from packaging.version import Version

from deepiri_pkg_version_manager.deps.dependency_registry import DependencyRegistry
from deepiri_pkg_version_manager.tags.tag_manager import TagManager


env_path = Path(".env")
env = dotenv_values(".env") if env_path.exists() else {}
GITHUB_PAT = env.get("GITHUB_PAT", "-1")

def run_command(
    command: List[str],
    cwd: Optional[str] = None,
    env_overrides: Optional[dict] = None,
) -> Optional[str]:
    try:
        proc_env = os.environ.copy()
        if env_overrides:
            proc_env.update(env_overrides)

        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            env=proc_env,
        )
        return result.stdout.strip()

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        logging.error(f"[red]Error:[/red] {error_msg}")
        return None

    except FileNotFoundError as e:
        logging.error(f"[red]Error:[/red] Command not found: {e}")
        return None

    except Exception as e:
        logging.error(f"[red]Unexpected Error:[/red] {e}")
        return None


def check_org_permissions(org: str) -> bool:
    result = subprocess.run(
        ["gh", "api", f"orgs/{org}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return result.returncode == 0


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


def check_valid_format(tag_name: str):
    if not tag_name.startswith("v") or not tag_name.count(".") == 2 or not tag_name.split(".")[0].strip("v").isdigit() or not tag_name.split(".")[1].isdigit() or not tag_name.split(".")[2].isdigit():
        logging.error(f"[red]Error:[/red] Invalid tag format '{tag_name}', use format v<major>.<minor>.<patch>")
        return False
    else:
        logging.info(f"[green]Tag '{tag_name}' is valid format[/green]")
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

    pr = run_command([
        'gh', 'pr', 'create',
        '--title', f"Chore: bump {dependency} version to {tag_name}",
        '--body', f"Bump {dependency} version to {tag_name}, PR generated by Deepiri Package Version Manager",
        '--base', 'main',
        '--head', branch
    ], dep_path)
    if pr is None:
        logging.error(f"[red]Error:[/red] Failed to create PR")
        return False
    else:
        logging.info(f"[green]Created PR '{pr}'[/green]")

    return pr.strip()


def validate_pr(pr_url: str, dep_path: str):
    allowed_files = ['package.json', 'pyproject.toml', 'requirements.txt', 'poetry.lock', 'package-lock.json', 'yarn.lock']

    number = int(pr_url.rstrip("/").split("/")[-1])
    org = pr_url.rstrip("/").split("/")[-4]
    repo = pr_url.rstrip("/").split("/")[-3]
    repo_path = f"{org}/{repo}"

    view_raw = run_command(['gh', 'pr', 'view', str(number), '--repo', repo_path, '--json', 'files'], dep_path)
    if view_raw is None:
        logging.error(f"[red]Error:[/red] Failed to validate PR '{pr_url}'")
        return False
    else:
        try:
            view = json.loads(view_raw)
        except json.JSONDecodeError:
            logging.error(f"[red]Error:[/red] Failed to parse PR '{pr_url}'")
            return False

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
    if GITHUB_PAT == "-1":
        logging.error(f"GitHub PAT is not set, please set it in the .env file as GITHUB_PAT to enable auto-merge")
        return False

    github_env = {
        "GH_TOKEN": GITHUB_PAT,
        "GITHUB_TOKEN": GITHUB_PAT,
    }

    if not validate_pr(pr_url, dep_path):
        logging.error(f"[red]Error:[/red] Failed to validate PR '{pr_url}'")
        return False
    else:
        logging.info(f"[green]Validated PR '{pr_url}'[/green]")

    pr_url = pr_url.rstrip("/").split("/")
    number = pr_url[-1]
    repo_path = f"{pr_url[-4]}/{pr_url[-3]}"
    if not run_command(['gh', 'pr', 'review', str(number), '--repo', repo_path, '--approve'], dep_path, env_overrides=github_env):
        logging.error(f"[red]Error:[/red] Failed to approve PR '{pr_url}'")
        return False
    else:
        logging.info(f"[green]Approved PR '{pr_url}'[/green]")

    if not run_command(['gh', 'pr', 'merge', str(number), '--repo', repo_path, '--merge'], dep_path, env_overrides=github_env):
        logging.error(f"[red]Error:[/red] Failed to merge PR '{pr_url}'")
        return False
    else:
        logging.info(f"[green]Merged PR '{pr_url}'[/green]")

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


def update_repo_with_new_tag(dependency, tag_name: str, dep_path: str) -> bool:
    if not bump_version(dependency, tag_name):
        logging.error(f"[red]Error:[/red] Failed to bump version")
        return False
    else:
        logging.info(f"[green]Bumped version to '{tag_name}' in '{dependency}'[/green]")

    pr = create_pr(dependency.name, tag_name, dep_path)
    if not pr:
        logging.error(f"[red]Error:[/red] Failed to create PR")
        return False
    else:
        logging.info(f"[green]Created PR '{pr}'[/green]")

    if not auto_merge(pr, f"version/{tag_name}", dep_path):
        logging.error(f"[red]Error:[/red] Failed to merge the version bump PR")
        return False
    else:
        logging.info(f"[green]Merged the version bump PR[/green]")

    #check this again, may need to remove/push the new tag again to catch it up to the current commit
    # not the v0.0.0 case, but other cases where we bring up an old tag
    if tag_name == "v0.0.0":
        output = run_command(['git', 'push', 'origin', tag_name], dep_path)
        if output is None:
            logging.error(f"[red]Error:[/red] Failed to push tag '{tag_name}' to '{dependency}'")
            return False
        else:
            logging.info(f"[green]Pushed tag '{tag_name}' to '{dependency}'[/green]")

    return True


def remove_tag(dependency: str, tag_name: str, tag_mgr: TagManager, registry: DependencyRegistry) -> bool:
    dep = registry.get(dependency)
    dep_path = dep.repo_path
    pt1 = pt2 = True

    check_local = run_command(['git', 'tag', '--list', tag_name], dep_path)
    if check_local is None or check_local.strip() == "":
        logging.info(f"[yellow]Tag '{tag_name}' does not exist locally in '{dependency}'[/yellow]")
        pt1 = False
    else:
        if tag_mgr.check_tag_exists_in_dependency(dependency, tag_name):
            success = tag_mgr.remove_tag_from_dependency(dependency, tag_name)
            if success:
                logging.info(f"[green]Removed tag '{tag_name}' from '{dependency}' in db[/green]")
            else:
                logging.error(f"[red]Error:[/red] Tag or dependency not found in storage when it should be there")
                return False
        else:
            logging.info(f"[yellow]Tag '{tag_name}' does not exist in '{dependency}' storage[/yellow]")
            pt1 = False

        remove_locally = run_command(['git', 'tag', '-d', tag_name], dep_path)
        if remove_locally is None:
            logging.error(f"[red]Error:[/red] Failed to remove tag '{tag_name}' from '{dependency}'")
            return False
        else:
            logging.info(f"[green]Removed tag '{tag_name}' from '{dependency}' locally[/green]")

    check_remote = run_command(['git', 'ls-remote', '--tags', '--sort=-v:refname', 'origin'], dep_path)
    if check_remote is None:
        logging.error(f"[red]Error:[/red] Failed to check if tag '{tag_name}' exists remotely in '{dependency}'")
        return False
    elif check_remote.strip() != "":
        tags = [tag.split('refs/tags/')[1].strip('^{}') for tag in check_remote.strip().split("\n") if '^{}' in tag]
        if tag_name not in tags:
            logging.info(f"[yellow]Tag '{tag_name}' does not exist remotely in '{dependency}'[/yellow]")
            pt2 = False
        else:
            most_recent_tag = tags[0]
            if len(tags) > 1:
                new_tag = tags[1]
            else:
                new_tag = "v0.0.0"

            delete = run_command(['git', 'push', 'origin', '--delete', tag_name], dep_path)
            if delete is None:
                logging.error(f"[red]Error:[/red] Failed to delete tag '{tag_name}' from '{dependency}'")
                return False
            else:
                logging.info(f"[green]Deleted tag '{tag_name}' from '{dependency}'[/green]")

                if tag_name == most_recent_tag:
                    if not update_repo_with_new_tag(dep, new_tag, dep_path):
                        logging.error(f"[red]Error:[/red] Failed to update repository with most recent tag")
                        return False
                    else:
                        logging.info(f"[green]Updated repository with most recent tag in '{dependency}'[/green]")
    else:
        logging.info(f"[yellow]There are no remote tags in '{dependency}'[/yellow]")
        pt2 = False

    return pt1 or pt2


def update_helper(dependency: str, tag_mgr: TagManager, dep_path: str, type: str, description: str = "", color: Optional[str] = None) -> "str | None":
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


def is_path_under(child: Path, parent: Path) -> bool:
    """True when `child` equals or is contained in `parent` (callers should resolve first)."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def dep_org_repo(dep) -> Optional[tuple[str, str]]:
    """Best-effort (org, repo) for a registered dep, from git_url or clone path.

    Returns ``("", repo)`` when only a ``./repos/<repo>/`` fallback is available,
    so callers can distinguish authoritative org matches from path-based guesses.
    """
    git_url = (getattr(dep, "git_url", "") or "").strip()
    if git_url:
        url = git_url.removesuffix(".git")
        for sep in (":", "/"):
            marker = f"github.com{sep}"
            if marker in url:
                tail = url.split(marker, 1)[1].strip("/")
                parts = tail.split("/")
                if len(parts) >= 2:
                    return parts[0], parts[1]
                break

    try:
        parts = Path(dep.repo_path).resolve().parts
    except (OSError, ValueError, AttributeError):
        return None
    if "repos" in parts:
        idx = parts.index("repos")
        if idx + 1 < len(parts):
            return "", parts[idx + 1]
    return None


def dep_clone_dir(dep, clone_root: Path) -> Optional[Path]:
    """Return ``<clone_root>/<repo>/`` for a dep cloned by ``scan_org``, else None."""
    try:
        dep_path = Path(dep.repo_path).resolve()
    except (OSError, ValueError, AttributeError):
        return None
    root = clone_root.resolve()
    if not is_path_under(dep_path, root):
        return None
    relative_parts = dep_path.relative_to(root).parts
    if not relative_parts:
        return None
    return root / relative_parts[0]
