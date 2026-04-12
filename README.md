# Deepiri Package Version Manager

Dependency graph and version management tool for Deepiri 

## Installation

```bash
pip install -e .
```

## Usage

```bash
dtm scan --path ../deepiri-platform
dtm deps
dtm graph
dtm install <package>
```

## Commands

| Command | Description | Usage |
|------|--------------|---------|
| `scan` | Scan repositories and build the dependency graph database. | `dtm scan --path ../deepiri-platform` |
| `clear` | Clear dependencies from the dependency database. | `dtm clear` |
| `deps` | List all dependencies, or show details for one dependency. | `dtm deps` / `dtm deps deepiri-pkg-version-manager --tags` |
| `graph` | Display the dependency tree or query dependencies/dependents. | `dtm graph` / `dtm graph --root deepiri-pkg-version-manager` |
| `install` | Generate install commands for one dependency or all dependencies. | `dtm install deepiri-pkg-version-manager --dry-run` |
| `outdated` | Show dependencies with version mismatches. | `dtm outdated` |
| `sync` | Sync versions across dependency relationships. | `dtm sync --dry-run` |
| `export` | Export dependency data as JSON or DOT. | `dtm export --format json --output deps.json` |
| `display` | Launch the desktop UI for tag management workflows. | `dtm display` |
| `tag add` | Add a tag to a dependency (description required). | `dtm tag add deepiri-pkg-version-manager v1.2.3 -d "Release notes"` |
| `tag push` | Push a local tag to the remote repository. | `dtm tag push deepiri-pkg-version-manager v1.2.3` |
| `tag remove` | Remove a tag from DB, local git, and remote (if present). | `dtm tag remove deepiri-pkg-version-manager v1.2.3` |
| `tag list` | List tags for all dependencies or one dependency. | `dtm tag list` / `dtm tag list deepiri-pkg-version-manager` |
| `tag patch` | Create the next patch tag from the latest local tag. | `dtm tag patch deepiri-pkg-version-manager -d "Patch release"` |
| `tag minor` | Create the next minor tag from the latest local tag. | `dtm tag minor deepiri-pkg-version-manager -d "Minor release"` |
| `tag major` | Create the next major tag from the latest local tag. | `dtm tag major deepiri-pkg-version-manager -d "Major release"` |
