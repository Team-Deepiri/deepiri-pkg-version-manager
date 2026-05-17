"""
If auto merge were to be implemented in the future, this function is setup to merge the PR using a PAT, which
is required because branch protections prevent the author of the PR from merging it, see the example code block
below to see how it may be used.
"""

# Use this for fetching and storing the PAT in a global variable
env_path = Path(".env")
env = dotenv_values(".env") if env_path.exists() else {}
GITHUB_PAT = env.get("GITHUB_PAT", "-1")


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

"""
Example:

merge = auto_merge(pr, f"version/{tag_name}", dep_path)
if not merge:
    logging.error(f"[red]Error:[/red] Failed to merge the version bump PR")
    return False
else:
    logging.info(f"[green]Merged the version bump PR[/green]")
"""