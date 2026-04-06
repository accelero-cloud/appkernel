# AppKernel — Developer Setup Guide

## Prerequisites

- [Homebrew](https://brew.sh) — macOS package manager
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — fast Python package manager
- Python 3.12+
- Docker Desktop — for running MongoDB in a container

Install Homebrew if you haven't:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Install uv via Homebrew:
```bash
brew install uv
```

Install Docker Desktop via Homebrew:
```bash
brew install --cask docker
```

Then open Docker Desktop at least once to complete the installation.

---

## MongoDB via Docker

Start a MongoDB container (binds to `localhost:27017`):
```bash
docker run -d --name appkernel-mongo \
  -p 27017:27017 \
  --restart unless-stopped \
  mongo:7
```

### Daily MongoDB management

```bash
docker start appkernel-mongo    # start (after machine reboot)
docker stop appkernel-mongo     # stop
docker logs appkernel-mongo     # view logs
docker rm -f appkernel-mongo    # destroy and remove
```

To verify it's running:
```bash
docker ps --filter name=appkernel-mongo
```

---

## First-Time Setup

```bash
# 1. Create the virtual environment
uv venv

# 2. Activate it
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# 3. Install runtime + development dependencies
uv pip install -r requirements.txt -r dev-requirements.txt -e .
```

The `-e .` flag installs the package in editable mode so local changes to `appkernel/` take effect immediately without reinstalling.

---

## Daily Workflow

### Activate the environment

```bash
source .venv/bin/activate
```

Your shell prompt will show `(.venv)` when active.

### Adding a new dependency

```bash
# Runtime dependency (add to requirements.txt manually, then):
uv pip install <package>

# Dev-only dependency (add to dev-requirements.txt manually, then):
uv pip install <package>
```

After editing either file, sync the environment:
```bash
uv pip install -r requirements.txt -r dev-requirements.txt
```

---

## Running Tests

### Full test suite
```bash
pytest tests/
```

### Single test file
```bash
pytest tests/model_test.py -v
```

### Single test
```bash
pytest tests/model_test.py::test_required_field -v
```

### With output (print statements visible)
```bash
pytest tests/test_rbac.py -s -v
```

### With short tracebacks (recommended for large suites)
```bash
pytest tests/ --tb=short
```

### With coverage report
```bash
coverage run -m pytest tests/
coverage report                  # terminal summary
coverage html                    # open htmlcov/index.html in browser
```

### Guard against accidental test deletion
Before a large refactor, capture the baseline:
```bash
pytest tests/ --collect-only -q | tail -1
# e.g. "188 tests collected"
```
After the refactor, verify the count matches.

---

## Linting & Code Quality

### Pylint (structural analysis, best for catching real bugs)
```bash
pylint appkernel/
pylint appkernel/ --rcfile=./pylintrc   # with project config
```

### Flake8 (style + quick checks)
```bash
flake8 appkernel/ --show-source --statistics --count
```

### autopep8 (auto-fix PEP 8 style issues)
```bash
# Preview changes only
autopep8 --diff appkernel/service.py

# Apply fixes in-place
autopep8 --in-place appkernel/service.py

# Apply recursively to the whole package
autopep8 --in-place --recursive appkernel/
```

---

## Project Layout

```
appkernel/        # framework source
tests/            # pytest test suite (requires MongoDB)
  conftest.py     # Motor event loop patch (needed for async Motor across test runs)
  utils.py        # shared test models (User, Project, Task, Order, ...)
config/           # sample cfg.yml for local dev
```

### Running specific test groups

| Group | Command |
|---|---|
| Model/serialisation | `pytest tests/model_test.py tests/test_serialisation.py -v` |
| Repository (MongoDB) | `pytest tests/repo_test.py -v` |
| REST service layer | `pytest tests/service_base_test.py -v` |
| Security / RBAC | `pytest tests/test_rbac.py -v` |
| HTTP client | `pytest tests/test_http_client.py -v` |
| All non-DB tests | `pytest tests/model_test.py tests/test_validators.py tests/test_utils.py tests/test_http_client.py -v` |

---

## Environment Variables & Config

Tests connect to MongoDB at `localhost:27017` using the `appkernel` database. Override via `cfg.yml`:

```yaml
appkernel:
  mongo:
    host: my-mongo-host
    db: mydb
```

Or pass the host flag when running the app:
```bash
python app.py -h my-mongo-host:27017
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'appkernel'`**
The editable install is missing. Run `uv pip install -e .` from the project root.

**`pymongo.errors.ServerSelectionTimeoutError`**
MongoDB container is not running. Start it with `docker start appkernel-mongo` or recreate it (see MongoDB via Docker section above).

**Tests parametrized over `[trio]` backend fail**
`trio` should not be installed — `anyio[trio]` was intentionally changed to `anyio` in `requirements.txt`. If trio crept back in, run `uv pip uninstall trio`.

**`422 Unprocessable Entity` in service tests**
FastAPI's automatic validation conflicts with the query DSL. All routes use `include_in_schema=False` — check that new routes include this flag.
