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
dtm tag add <package> <tag> -d "<description>"
dtm tag push <package> <tag>
dtm tag remove <package> <tag>
dtm tag patch <package> <tag> -d "<description>"
dtm tag minor <package> <tag> -d "<description>"
dtm tag major <package> <tag> -d "<description>"
```
