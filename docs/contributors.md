# Contributing

## Development environment

Clone the repository::

```bash
git clone git@github.com:accelero-cloud/appkernel.git
cd appkernel
```

Create and activate a virtual environment::

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the package in editable mode with all development dependencies::

```bash
pip install -e ".[dev]"
```

### Set up git hooks

The repository ships pre-commit and pre-push hooks that run tests and linting
automatically::

```bash
cd .git/hooks
ln -sf ../../hooks/pre-commit ./pre-commit
ln -sf ../../hooks/pre-push ./pre-push
cd ../..
```

### Run the tests

Most tests require a running MongoDB instance. The easiest way is Docker::

```bash
docker run -d --name mongo -p 27017:27017 mongo:latest
```

Then run the full test suite from the project root::

```bash
pytest ./tests
```

Some tests also require compiled translations::

```bash
cd tests && pybabel compile -d ./translations && cd ..
```

AppKernel requires **MongoDB 4.0+**. If you have an older local installation,
pull the latest image::

```bash
docker pull mongo:latest
```

_PyCharm hint_: set your Project Interpreter to the `.venv` environment, and
mark `.idea/`, `appkernel.egg-info/`, and `.venv/` as excluded directories.

## Publishing to PyPI

Build the distribution::

```bash
pip install --upgrade build twine
python -m build
```

Upload to TestPyPI for a dry run::

```bash
twine upload --repository testpypi dist/*
```

When everything looks good, publish to PyPI::

```bash
twine upload dist/*
```

If you maintain a `~/.pypirc` with named repositories, you can use the
shorthand::

```bash
twine upload -r pypi dist/*
```
