# Repository Guidelines

## Project Structure & Module Organization
The root currently holds `.idea/` for JetBrains run configurations and `.venv/` for the local Python 3.14 environment; keep both uncommitted except the few shared XML files already checked in. Place modules inside `src/` (for example, `src/pdf_tools/` for extractors or CLI wrappers) and include `__init__.py` files so imports stay explicit. Mirror that layout in `tests/` (e.g., `tests/pdf_tools/test_extractor.py`) and store sample PDFs under `samples/`, loading them via relative paths instead of copying fixtures around.

## Build, Test, and Development Commands
Create or refresh the virtual environment before hacking:
```bash
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
```
Use `python -m pdf_tools.cli input.pdf --out reports/out.json` to exercise the CLI directly from `src/`. Run automated checks with `python -m pytest -q`. Once a `pyproject.toml` lives at the root, run `python -m pip install -e .` to develop against the editable package.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation, snake_case functions, UpperCamelCase classes, and CAPS_WITH_UNDERSCORES constants. Prefer dataclasses for structured payloads, type-annotate public APIs, and split modules that exceed ~400 lines into `src/pdf_tools/utils/` helpers. Run `ruff check src tests` and `black src tests` before committing (configure both in `pyproject.toml`).

## Testing Guidelines
Standardize on pytest. Name files `test_<module>.py`, functions `test_<behavior>`, and load fixture PDFs via `pathlib.Path("samples/fixtures")` to avoid brittle paths. Track regression data in `samples/` and target at least 90% statement coverage using `pytest --cov=src --cov-report=term-missing`. Every feature touching rendering, parsing, or export paths must land with a regression test or a documented reason.

## Commit & Pull Request Guidelines
Commits should use concise, imperative subjects under 72 characters (e.g., `Add text extraction pipeline`). Reference issues with `Refs #123` or `Fixes #123` in the body. Pull requests should include a short summary, validation notes (commands run and results), screenshots or diffs for PDF output changes, and a checklist of new tests or follow-up tasks. Request a review before merging even when the change seems trivial.

## Security & Configuration Tips
Never commit PDFs containing customer data; redact or synthesize fixtures and store secrets in environment variables or `.env.local` entries ignored by git. Keep `.idea/` edits limited to shared dictionaries or run configurations so contributors on other IDEs do not inherit personal paths, and avoid touching `.venv/` entirely.
