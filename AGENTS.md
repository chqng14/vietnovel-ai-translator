# Repository Guidelines

## Project Structure & Module Organization

This is a local AI novel translator. `app.py` defines the FastAPI server, routes, static hosting, and SSE stream. Translation and task lifecycle logic belongs in `translate_engine.py`; site-specific extraction belongs in `scraper.py`. Keep glossary persistence in `glossary_manager.py`, output generation in `exporter.py`, and CLI behavior in `translate.py`.

The plain HTML/CSS/JavaScript client is under `static/`. Runtime outputs and the glossary live in `storage/`; generated `.txt`, `.md`, and `.epub` files are not source code. No automated test directory currently exists.

## Build, Test, and Development Commands

Use Python 3.14+ and install CUDA-enabled PyTorch separately before the remaining dependencies:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt
python app.py
```

The UI is available at `http://localhost:8000`. For a syntax check that does not load a model, run:

```bash
python -m compileall app.py exporter.py glossary_manager.py scraper.py translate.py translate_engine.py
```

Exercise CLI changes with `python translate.py --text "Hello world" --format txt`. End-to-end checks may download models and require GPU inference.

## Coding Style & Naming Conventions

Follow PEP 8: four-space indentation, `snake_case` functions/variables, and `PascalCase` classes. Add type hints to public APIs and docstrings for non-obvious behavior. Keep handlers thin and delegate domain logic. Preserve two-space JavaScript indentation, `camelCase` names, and kebab-case CSS classes/HTML IDs. Save text as UTF-8 because prompts and UI copy contain Vietnamese.

## Testing Guidelines

No test framework or coverage threshold is configured yet. New non-trivial behavior should include `pytest` tests under `tests/`, named `test_<module>.py`, with test functions named `test_<behavior>`. Mock network scraping, Hugging Face model loading, and GPU calls. For UI/API changes, manually verify scrape or direct-text input, SSE progress, pause/resume/cancel, glossary CRUD, and each affected export format.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout, so use concise imperative commits such as `fix: preserve paragraph order` or `feat: add Kakuyomu parser`. Keep unrelated changes separate. Pull requests should explain the user-visible change, list verification commands, note GPU/model requirements, link relevant issues, and include screenshots for changes under `static/`. Never commit model caches, secrets, `__pycache__/`, or incidental files generated in `storage/`.

## Security & Configuration

The default server binds to the LAN, permits broad CORS access, has no authentication, and accepts scrape URLs. Do not expose it publicly without restricting the host and origins, adding authentication, and validating URLs to mitigate SSRF.
