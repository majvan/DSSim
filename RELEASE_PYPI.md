# PyPI Release Guide

This project is now configured for PyPI publishing with version `1.0.1`.

## 1) Prepare release commit

1. Ensure `dssim/__init__.py` has the target `__version__`.
2. Commit all release-related changes.
3. Create and push a tag:

```bash
git tag v1.0.1
git push origin v1.0.1
```

## 2) Build distributions

```bash
python -m pip install -U pip build twine
rm -rf dist build *.egg-info
python -m build
python -m twine check dist/*
```

Expected artifacts:

- `dist/dssim-1.0.1.tar.gz`
- `dist/dssim-1.0.1-py3-none-any.whl`

## 3) Publish to TestPyPI (recommended first)

```bash
python -m twine upload --repository testpypi dist/*
python -m pip install --index-url https://test.pypi.org/simple/ dssim==1.0.1
```

## 4) Publish to PyPI

```bash
python -m twine upload dist/*
```

## 5) Verify install from PyPI

```bash
python -m pip install -U dssim==1.0.1
python -c "import dssim; print(dssim.__version__)"
```
