# Install

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## Docs Tooling

```bash
pip install -r docs/requirements-docs.txt
```

## Build Docs Locally

```bash
mkdocs serve
```

or:

```bash
mkdocs build --strict
```
