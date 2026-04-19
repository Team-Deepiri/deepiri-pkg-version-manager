import os
import json
import subprocess
import re
import sys
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ORG = "Team-Deepiri"
CLONE_DIR = "./repos"
OUTPUT_FILE = "dep-config.json"

dependency_map = {}

def run(cmd):
    return subprocess.check_output(cmd, shell=True, text=True).strip()

def ensure_cloned(repo):
    path = os.path.join(CLONE_DIR, repo)
    if not os.path.exists(path):
        print(f"Cloning {repo}...")
        run(f"git clone https://github.com/{ORG}/{repo}.git {path}")
    return path

def add_dependency(dep_name, entry):
    if dep_name not in dependency_map:
        dependency_map[dep_name] = {"dependents": []}

    # avoid duplicates
    if entry not in dependency_map[dep_name]["dependents"]:
        dependency_map[dep_name]["dependents"].append(entry)

def parse_gitmodules(repo_name, path):
    gm_path = os.path.join(path, ".gitmodules")
    if not os.path.exists(gm_path):
        return

    with open(gm_path, "r") as f:
        content = f.read()

    matches = re.findall(r'path = (.+)\n\s*url = (.+)', content)

    for sub_path, url in matches:
        dep_name = url.split("/")[-1].replace(".git", "")
        add_dependency(dep_name, {
            "repo": f"{ORG}/{repo_name}",
            "type": "submodule",
            "path": sub_path
        })

def parse_package_json(repo_name, path):
    pkg_path = os.path.join(path, "package.json")
    if not os.path.exists(pkg_path):
        return

    with open(pkg_path) as f:
        data = json.load(f)

    for section in ["dependencies", "devDependencies"]:
        deps = data.get(section, {})
        for dep in deps:
            if dep.startswith("deepiri") or dep.startswith("diri"):
                add_dependency(dep, {
                    "repo": f"{ORG}/{repo_name}",
                    "type": "npm",
                    "package": dep
                })

def parse_pyproject(repo_name, path):
    py_path = os.path.join(path, "pyproject.toml")
    if not os.path.exists(py_path):
        return

    data = tomllib.load(py_path)

    # look through all sections for git dependencies
    text = open(py_path).read()
    matches = re.findall(r'git\s*=\s*".*github.com/.+/(.+?)\.git"', text)

    for dep in matches:
        add_dependency(dep, {
            "repo": f"{ORG}/{repo_name}",
            "type": "python",
            "package": dep
        })

def main():
    os.makedirs(CLONE_DIR, exist_ok=True)

    print("Fetching repo list...")
    repos = run(f"gh repo list {ORG} --limit 200 --json name -q '.[].name'").splitlines()

    for repo in repos:
        try:
            path = ensure_cloned(repo)
            print(f"Scanning {repo}...")

            parse_gitmodules(repo, path)
            parse_package_json(repo, path)
            parse_pyproject(repo, path)

        except Exception as e:
            print(f"Error processing {repo}: {e}")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(dependency_map, f, indent=2)

    print(f"\n✅ Config written to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()