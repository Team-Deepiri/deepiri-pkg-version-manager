import logging
import os
import subprocess
from pathlib import Path

import typer
from packaging.version import Version
from rich import print as rprint

from deepiri_pkg_version_manager.deps.dependency_registry import DependencyRegistry
from deepiri_pkg_version_manager.tags.tag_manager import TagManager


def run_command(
    command: list[str],
    cwd: str | None = None,
    env_overrides: dict | None = None,
) -> str | None:
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
    clean = run_command(["git", "status", "--porcelain"], dep_path)
    if clean is None:
        logging.error("[red]Error:[/red] Failed to check if working tree is clean")
        return False
    elif clean.strip() != "":
        logging.error(
            "[red]Error:[/red] Working tree is not clean, ensure all changes are committed or stashed before pushing a new tag."
        )
        return False

    logging.info("[green]Working tree is clean[/green]")
    return True


def is_synced_with_main(dep_path: str) -> bool:
    if run_command(["git", "fetch", "origin"], dep_path) is None:
        logging.error("[red]Error:[/red] Failed to fetch origin")
        return False

    branch = run_command(["git", "branch", "--show-current"], dep_path)
    if branch is None or branch.strip() == "":
        logging.error("[red]Error:[/red] Detached HEAD state detected. Please checkout a branch.")
        return False

    head = run_command(["git", "rev-parse", "HEAD"], dep_path)
    main = run_command(["git", "rev-parse", "main"], dep_path)
    origin_main = run_command(["git", "rev-parse", "origin/main"], dep_path)

    if head is None or main is None or origin_main is None:
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
        logging.error(
            "[red]Error:[/red] Working tree is not clean, ensure all changes are committed or stashed before pushing a new tag."
        )
        return False

    if not is_synced_with_main(dep_path):
        logging.error(
            f"[red]Error:[/red] '{dependency}' is not in sync with main branch, ensure you have pulled the latest changes from main and do not have any local commits before pushing a new tag."
        )
        return False

    return True


def remove_check(dependency: str, registry: DependencyRegistry):
    dep = registry.get(dependency)
    if not dep:
        logging.error(f"[red]Error:[/red] Dependency '{dependency}' not found")
        return False

    dep_path = dep.repo_path
    if not clean_working_tree(dep_path):
        logging.error(
            "[red]Error:[/red] Working tree is not clean, ensure all changes are committed or stashed before pushing a new tag."
        )
        return False

    logging.info(f"[green]Remove check passed for '{dependency}'[/green]")
    return True


def is_valid_push_state(dep_path: str, tag_name: str) -> bool:
    if not clean_working_tree(dep_path):
        logging.error(
            "[red]Error:[/red] Working tree is not clean, ensure all changes are committed or stashed before pushing a new tag."
        )
        return False

    if not is_synced_with_main(dep_path):
        logging.error(
            "[red]Error:[/red] Dependency is not in sync with main branch, ensure you have pulled the latest changes from main and do not have any local commits before pushing a new tag."
        )
        return False

    head = run_command(["git", "rev-parse", "HEAD"], dep_path)
    tag = run_command(["git", "rev-parse", tag_name + "^{commit}"], dep_path)
    if head is None or tag is None:
        logging.error("Failed to resolve commit hashes")
        return False

    if head.strip() != tag.strip():
        logging.error(
            f"[red]Error:[/red] Tag '{tag_name}' does not point to HEAD; recreate it at HEAD before pushing"
        )
        return False

    logging.info("Push state is valid")
    return True


def check_valid_format(tag_name: str):
    if (
        not tag_name.startswith("v")
        or not tag_name.count(".") == 2
        or not tag_name.split(".")[0].strip("v").isdigit()
        or not tag_name.split(".")[1].isdigit()
        or not tag_name.split(".")[2].isdigit()
    ):
        logging.error(
            f"[red]Error:[/red] Invalid tag format '{tag_name}', use format v<major>.<minor>.<patch>"
        )
        return False
    else:
        logging.info(f"[green]Tag '{tag_name}' is valid format[/green]")
        return True


def check_valid_tag(tag_name: str, dependency: str, dep_path: str):
    if not check_valid_format(tag_name):
        return False

    tags = run_command(["git", "tag", "--sort=-v:refname"], dep_path)
    if tags is None:
        logging.error(f"[red]Error:[/red] Failed to get recent tag in '{dependency}'")
        return False
    elif tags.strip() == "":
        logging.error(f"[green]No tags exist in '{dependency}'[/green]")
        return True

    if tags:
        latest_tag = tags.strip().split("\n")[0]
        if Version(tag_name) <= Version(latest_tag):
            logging.error(
                f"[red]Error:[/red] Tag '{tag_name}' is not greater than latest tag '{latest_tag}' in '{dependency}'"
            )
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
        logging.error("[red]Error:[/red] No version field found in pyproject.toml")
        return False

    with open(pyproject_path, "w") as f:
        toml.dump(data, f)

    logging.info(f"[green]Updated version to '{version}' in pyproject.toml[/green]")
    return True


def bump_version(dep, version: str):
    branch = f"version/{version}"
    checkout = run_command(["git", "checkout", "-b", branch], dep.repo_path)
    if checkout is None:
        logging.error(f"[red]Error:[/red] Failed to checkout branch '{branch}' in '{dep.name}'")
        return False
    else:
        logging.info(f"[green]Checked out branch '{branch}' in '{dep.name}'[/green]")

    if dep.package_type == "npm":
        output = run_command(
            ["npm", "version", version.strip("v"), "--no-git-tag-version"], dep.repo_path
        )
        if output is None:
            logging.error(f"[red]Error:[/red] Failed to bump version in '{dep.name}'")
            return False
        else:
            logging.info(f"[green]Bumped version to '{version}' in '{dep.name}'[/green]")

        result = run_command(["git", "add", "package.json"], dep.repo_path)
    elif dep.package_type == "poetry":
        output = run_command(["poetry", "version", version.strip("v")], dep.repo_path)
        if output is None:
            logging.error(f"[red]Error:[/red] Failed to bump version in '{dep.name}'")
            return False
        else:
            logging.info(f"[green]Bumped version to '{version}' in '{dep.name}'[/green]")

        result = run_command(["git", "add", "pyproject.toml"], dep.repo_path)
    elif dep.package_type == "pip":
        if not update_pyproject_version(dep.repo_path, version):
            logging.error(
                f"[red]Error:[/red] Failed to update version in pyproject.toml in '{dep.name}'"
            )
            return False
        else:
            logging.info(
                f"[green]Updated version to '{version}' in pyproject.toml in '{dep.name}'[/green]"
            )

        result = run_command(["git", "add", "pyproject.toml"], dep.repo_path)

    if result is None:
        logging.error(
            f"[red]Error:[/red] Failed to add pyproject.toml to staging area in '{dep.name}'"
        )
        return False
    else:
        logging.info(f"[green]Added pyproject.toml to staging area in '{dep.name}'[/green]")

    commit = run_command(
        [
            "git",
            "commit",
            "-m",
            f"Deepiri-Package-Version-Manager: Bump version ({dep.package_type}) to {version}",
        ],
        dep.repo_path,
    )
    if commit is None:
        logging.error(f"[red]Error:[/red] Failed to commit changes in '{dep.name}'")
        return False
    else:
        logging.info(f"[green]Committed changes in '{dep.name}'[/green]")

    return True


def push_sanitization(dependency: str, tag_name: str, dep_path: str):
    remote_tags = run_command(["git", "ls-remote", "--tags", "origin"], dep_path)
    if remote_tags is None:
        logging.error(
            f"[red]Error:[/red] Failed to check if '{tag_name}' exists remotely in '{dependency}'"
        )
        return False
    elif remote_tags.strip() == "":
        logging.info(f"[green]No tags exist remotely in {dependency}[/green]")
        return True
    elif remote_tags.strip() != "":
        tags = set()
        for tag in remote_tags.strip().split("\n"):
            if "refs/tags/" in tag:
                tag = tag.split("refs/tags/")[1]
                tag = tag.replace("^{}", "")
                tags.add(tag)

        if not tags:
            logging.info(f"[green]No tags exist with ref/tags/ in '{dependency}'[/green]")
            return True

        latest_tag = max(tags, key=Version)
        if Version(tag_name) <= Version(latest_tag):
            logging.error(
                f"[red]Error:[/red] Tag '{tag_name}' is not greater than latest tag '{latest_tag}' in '{dependency}'"
            )
            return False
        else:
            logging.info(
                f"[green]Tag '{tag_name}' is greater than latest tag '{latest_tag}' in '{dependency}'[/green]"
            )
            return True
    else:
        logging.error("[red]Error:[/red] during push sanitization.")
        return False


def create_pr(dependency: str, tag_name: str, dep_path: str):
    logging.info("[green]Creating PR...[/green]")
    branch = f"version/{tag_name}"
    push_new_branch = run_command(["git", "push", "-u", "origin", branch], dep_path)
    if push_new_branch is None:
        logging.error(f"[red]Error:[/red] Failed to push branch '{branch}'")
        return False
    else:
        logging.info(f"[green]Pushed branch '{branch}'[/green]")

    pr = run_command(
        [
            "gh",
            "pr",
            "create",
            "--title",
            f"Chore: bump {dependency} version to {tag_name}",
            "--body",
            (
                f"Bump {dependency} version to {tag_name}, PR generated by Deepiri Package Version Manager, "
                f"ensure the branch version/{tag_name} is deleted after the PR is merged, "
                f"via manual deletion or using the command dtm branch-cleanup -d {dependency} -t {tag_name}."
            ),
            "--base",
            "main",
            "--head",
            branch,
        ],
        dep_path,
    )
    if pr is None:
        logging.error("[red]Error:[/red] Failed to create PR")
        return False

    return pr.strip()


def create_tag(
    dependency: str,
    tag_mgr: TagManager,
    registry: DependencyRegistry,
    tag_name: str | None = None,
    description: str = "",
    color: str | None = None,
):
    dep = registry.get(dependency)
    if dep is None:
        logging.error(f"[red]Error:[/red] Dependency '{dependency}' not found")
        raise typer.Exit(1)
    dep_path = dep.repo_path

    if tag_name is None:
        local_tags = run_command(["git", "tag"], dep_path)
        if local_tags is None:
            logging.error(f"[red]Error:[/red] Failed to get local tags in '{dependency}'")
            raise typer.Exit(1)
        elif local_tags.strip() != "":
            logging.error(
                f"[red]Error:[/red] Local tags found in '{dependency}', to use default add behavior there should be no local tags."
            )
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
        logging.error("[red]Error:[/red] Failed to add tag")

    _sha = run_command(["git", "rev-parse", "HEAD"], dep_path)
    if _sha is None:
        logging.error("[red]Error:[/red] Failed to get commit SHA")
        return False
    commit_sha = _sha.strip()
    logging.info(f"[green]Commit SHA is '{commit_sha}'[/green]")

    output = run_command(["git", "tag", "-a", tag_name, commit_sha, "-m", description], dep_path)
    if output is None:
        logging.error(f"[red]Error:[/red] Failed to create tag '{tag_name} in {dependency}'")
        return False

    logging.info(f"[green]Created tag '{tag_name}' in '{dependency}' locally[/green]")
    return True


def push_tag(
    dependency: str,
    dep_path: str,
    tag_mgr: TagManager,
    registry: DependencyRegistry,
    tag_name: str | None = None,
) -> bool:
    is_repo = run_command(["git", "rev-parse", "--is-inside-work-tree"], dep_path)
    if is_repo is None or is_repo != "true":
        logging.error(
            f"[red]Error:[/red] Dependency '{dependency}' is not a submodule or repository, cannot push tag"
        )
        return False

    if tag_name is None:
        local_tags = run_command(["git", "tag", "--sort=-v:refname"], dep_path)
        if local_tags is None or local_tags.strip() == "":
            logging.error(f"[red]Error:[/red] There are no tags to push in '{dependency}'")
            return False
        tag_name = local_tags.strip().split("\n")[0]
        logging.info(f"[green]Pushing latest tag '{tag_name}' in '{dependency}'[/green]")

    if not is_valid_push_state(dep_path, tag_name):
        logging.error("[red]Error:[/red] Push state is not valid")
        return False

    exists_in_db = tag_mgr.check_tag_exists_in_dependency(dependency, tag_name)
    if not exists_in_db:
        logging.error(f"[red]Error:[/red] Tag '{tag_name}' not found in dependency '{dependency}'")
        return False
    else:
        logging.info(f"[green]Tag '{tag_name}' exists in dependency '{dependency}'[/green]")

    exists_locally = run_command(["git", "tag", "--list", tag_name], dep_path)
    if exists_locally is None or exists_locally.strip() == "":
        logging.error(f"[red]Error:[/red] Tag '{tag_name}' not found locally in '{dependency}'")
        return False
    else:
        logging.info(f"[green]Tag '{tag_name}' exists locally in '{dependency}'[/green]")

    dep = registry.get(dependency)
    if not bump_version(dep, tag_name):
        logging.error("[red]Error:[/red] Failed to bump version")
        return False
    else:
        logging.info(f"[green]Bumped version to '{tag_name}' in '{dependency}'[/green]")

    if not push_sanitization(dependency, tag_name, dep_path):
        logging.error("[red]Error:[/red] Push sanitization failed")
        return False

    commit_sha = run_command(["git", "rev-parse", "HEAD"], dep_path)
    if commit_sha is None:
        logging.error("[red]Error:[/red] Failed to get commit SHA")
        return False
    else:
        logging.info(f"[green]Commit SHA is '{commit_sha}'[/green]")

    pr = create_pr(dependency, tag_name, dep_path)
    if not pr:
        logging.error("[red]Error:[/red] Failed to create PR")
        return False
    else:
        logging.info(f"[green]Created PR '{pr}'[/green]")
        rprint(f"[green]Created PR '{pr}'[/green]")

    desc = run_command(
        ["git", "for-each-ref", f"refs/tags/{tag_name}", "--format=%(contents)"], dep_path
    )
    if desc is None:
        logging.error("[red]Error:[/red] Failed to get tag description")
        return False
    else:
        logging.info(f"[green]Tag description is '{desc}'[/green]")
        desc = desc.strip()

    output = run_command(["git", "tag", "-fa", tag_name, commit_sha, "-m", desc], dep_path)
    if output is None:
        logging.error(f"[red]Error:[/red] Failed to push tag '{tag_name}' to '{dependency}'")
        return False
    else:
        logging.info(f"[green]Pushed tag '{tag_name}' to '{dependency}'[/green]")

    push = run_command(["git", "push", "origin", tag_name], dep_path)
    if push is None:
        logging.error(f"[red]Error:[/red] Failed to push tag '{tag_name}' to '{dependency}'")
        return False
    else:
        logging.info(f"[green]Pushed tag '{tag_name}' to '{dependency}'[/green]")

    checkout_main = run_command(["git", "checkout", "main"], dep_path)
    if checkout_main is None:
        logging.error("[red]Error:[/red] Failed to checkout main branch")
        return False
    else:
        logging.info("[green]Checked out main branch[/green]")

    logging.info(f"[green]Tag '{tag_name}' pushed to '{dependency}'[/green]")
    return True


def update_repo_with_new_tag(dependency, tag_name: str, dep_path: str, desc: str) -> bool:
    if not bump_version(dependency, tag_name):
        logging.error("[red]Error:[/red] Failed to bump version")
        return False
    else:
        logging.info(f"[green]Bumped version to '{tag_name}' in '{dependency.name}'[/green]")

    commit_sha = run_command(["git", "rev-parse", "HEAD"], dep_path)
    if commit_sha is None:
        logging.error("[red]Error:[/red] Failed to get commit SHA")
        return False
    else:
        logging.info(f"[green]Commit SHA is '{commit_sha}'[/green]")

    pr = create_pr(dependency.name, tag_name, dep_path)
    if not pr:
        logging.error("[red]Error:[/red] Failed to create PR")
        return False
    else:
        logging.info(f"[green]Created PR '{pr}'[/green]")

    if tag_name == "v0.0.0":
        add_local = run_command(["git", "tag", "-a", tag_name, commit_sha, "-m", desc], dep_path)
        if add_local is None:
            logging.error(
                f"[red]Error:[/red] Failed to add tag '{tag_name}' to '{dependency.name}'"
            )
            return False
        else:
            logging.info(f"[green]Added tag '{tag_name}' to '{dependency.name}' locally[/green]")
    else:
        output = run_command(["git", "tag", "-fa", tag_name, commit_sha, "-m", desc], dep_path)
        if output is None:
            logging.error(
                f"[red]Error:[/red] Failed to retarget tag '{tag_name}' in '{dependency.name}'"
            )
            return False
        else:
            logging.info(
                f"[green]Forced tag '{tag_name}' to commit '{commit_sha}' in '{dependency.name}'[/green]"
            )

    if tag_name != "v0.0.0":
        delete_remote = run_command(["git", "push", "origin", "--delete", tag_name], dep_path)
        if delete_remote is None:
            logging.error(
                f"[red]Error:[/red] Failed to delete tag '{tag_name}' from '{dependency.name}'"
            )
            return False
        else:
            logging.info(
                f"[green]Deleted tag '{tag_name}' from '{dependency.name}' remotely[/green]"
            )

    push = run_command(["git", "push", "origin", tag_name], dep_path)
    if push is None:
        logging.error(f"[red]Error:[/red] Failed to push tag '{tag_name}' to '{dependency.name}'")
        return False
    else:
        logging.info(f"[green]Pushed tag '{tag_name}' to '{dependency.name}'[/green]")

    return True


def remove_tag(
    dependency: str, tag_name: str, tag_mgr: TagManager, registry: DependencyRegistry
) -> bool:
    dep = registry.get(dependency)
    if dep is None:
        logging.error(f"[red]Error:[/red] Dependency '{dependency}' not found")
        return False
    dep_path = dep.repo_path
    pt1 = pt2 = True

    check_local = run_command(["git", "tag", "--list", tag_name], dep_path)
    if check_local is None or check_local.strip() == "":
        logging.info(f"[yellow]Tag '{tag_name}' does not exist locally in '{dependency}'[/yellow]")
        pt1 = False
    else:
        if tag_mgr.check_tag_exists_in_dependency(dependency, tag_name):
            success = tag_mgr.remove_tag_from_dependency(dependency, tag_name)
            if success:
                logging.info(f"[green]Removed tag '{tag_name}' from '{dependency}' in db[/green]")
            else:
                logging.error(
                    "[red]Error:[/red] Tag or dependency not found in storage when it should be there"
                )
                return False
        else:
            logging.info(
                f"[yellow]Tag '{tag_name}' does not exist in '{dependency}' storage[/yellow]"
            )
            pt1 = False

        remove_locally = run_command(["git", "tag", "-d", tag_name], dep_path)
        if remove_locally is None:
            logging.error(
                f"[red]Error:[/red] Failed to remove tag '{tag_name}' from '{dependency}'"
            )
            return False
        else:
            logging.info(f"[green]Removed tag '{tag_name}' from '{dependency}' locally[/green]")

    check_remote = run_command(
        ["git", "ls-remote", "--tags", "--sort=-v:refname", "origin"], dep_path
    )
    if check_remote is None:
        logging.error(
            f"[red]Error:[/red] Failed to check if tag '{tag_name}' exists remotely in '{dependency}'"
        )
        return False
    elif check_remote.strip() != "":
        tags = [
            tag.split("refs/tags/")[1].strip("^{}")
            for tag in check_remote.strip().split("\n")
            if "^{}" in tag
        ]
        if tag_name not in tags:
            logging.info(
                f"[yellow]Tag '{tag_name}' does not exist remotely in '{dependency}'[/yellow]"
            )
            pt2 = False
        else:
            most_recent_tag = tags[0]
            if len(tags) > 1:
                new_tag = tags[1]
            else:
                new_tag = "v0.0.0"

            delete = run_command(["git", "push", "origin", "--delete", tag_name], dep_path)
            if delete is None:
                logging.error(
                    f"[red]Error:[/red] Failed to delete tag '{tag_name}' from '{dependency}'"
                )
                return False
            else:
                logging.info(f"[green]Deleted tag '{tag_name}' from '{dependency}'[/green]")

                if tag_name == most_recent_tag:
                    if new_tag != "v0.0.0":
                        desc = run_command(
                            ["git", "for-each-ref", f"refs/tags/{new_tag}", "--format=%(contents)"],
                            dep_path,
                        )
                        if desc is None:
                            logging.error("[red]Error:[/red] Failed to get tag description")
                            return False
                        else:
                            logging.info(f"[green]Tag description is '{desc}'[/green]")
                            desc = desc.strip()
                    else:
                        desc = "Initial tag"

                    if not update_repo_with_new_tag(dep, new_tag, dep_path, desc):
                        logging.error(
                            "[red]Error:[/red] Failed to update repository with most recent tag"
                        )
                        return False
                    else:
                        logging.info(
                            f"[green]Updated repository with most recent tag in '{dependency}'[/green]"
                        )
    else:
        logging.info(f"[yellow]There are no remote tags in '{dependency}'[/yellow]")
        pt2 = False

    return pt1 or pt2


def update_helper(
    dependency: str,
    tag_mgr: TagManager,
    dep_path: str,
    type: str,
    description: str = "",
    color: str | None = None,
) -> "str | None":
    recent_local = run_command(["git", "tag", "--sort=-v:refname"], dep_path)
    if recent_local is None or recent_local.strip() == "":
        logging.error(f"[red]Error:[/red] No tags found in '{dependency}'")
        return None
    else:
        tag_name = recent_local.strip().split("\n")[0]
        logging.info(f"[green]Recent local tag in '{dependency}' is '{recent_local}'[/green]")

    if type == "patch":
        tag = tag_name.split(".")
        tag[-1] = str(int(tag[-1]) + 1)
        new_tag = ".".join(tag)
    elif type == "minor":
        tag = tag_name.split(".")
        tag[-2] = str(int(tag[-2]) + 1)
        tag[-1] = "0"
        new_tag = ".".join(tag)
    elif type == "major":
        tag = tag_name.split(".")
        tag[0] = "v" + str(int(tag[0].lstrip("v")) + 1)
        tag[-2] = "0"
        tag[-1] = "0"
        new_tag = ".".join(tag)
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

    added_locally = run_command(["git", "tag", "-a", new_tag, "-m", description], dep_path)
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


def dep_org_repo(dep) -> tuple[str, str] | None:
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


def dep_clone_dir(dep, clone_root: Path) -> Path | None:
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


def branch_cleanup(dependency: str, tag_name: str) -> bool:
    branch = f"version/{tag_name}"
    registry = DependencyRegistry()
    dep = registry.get(dependency)
    if dep is None:
        logging.error(f"[red]Error:[/red] Dependency '{dependency}' not found")
        return False
    dep_path = dep.repo_path
    if dep_path is None:
        logging.error(f"[red]Error:[/red] Dependency '{dependency}' not found")
        return False
    else:
        logging.info(f"[green]Dependency '{dependency}' found at '{dep_path}'[/green]")

    pt1 = 0
    check_exists_locally = run_command(["git", "branch", "--list", branch], dep_path)
    if check_exists_locally is None or check_exists_locally.strip() == "":
        logging.info(f"[yellow]Branch '{branch}' does not exist locally[/yellow]")
        pt1 += 1
    else:
        logging.info(f"[green]Branch '{branch}' exists locally[/green]")
        delete_branch = run_command(["git", "branch", "-D", branch], dep_path)
        if delete_branch is None:
            logging.error(f"[red]Error:[/red] Failed to delete branch '{branch}': {delete_branch}")
            return False
        else:
            logging.info(f"[green]Deleted branch '{branch}' locally[/green]")

    check_exists_remotely = run_command(["git", "ls-remote", "--heads", "origin", branch], dep_path)
    if check_exists_remotely is None or check_exists_remotely.strip() == "":
        logging.info(f"[yellow]Branch '{branch}' does not exist remotely[/yellow]")
        if pt1 == 1:
            logging.error(
                f"[red]Error:[/red] Branch '{branch}' does not exist either locally or remotely"
            )
            return False
    else:
        logging.info(f"[green]Branch '{branch}' exists remotely[/green]")
        delete_remote = run_command(["git", "push", "origin", "--delete", branch], dep_path)
        if delete_remote is None:
            logging.error(
                f"[red]Error:[/red] Failed to delete branch '{branch}' remotely: {delete_remote}"
            )
            return False
        else:
            logging.info(f"[green]Deleted branch '{branch}' remotely[/green]")

    return True
