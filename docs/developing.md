## Developing App Kernel

### Prepare the development environment
After cloning the project:
```bash
cd appkernel
pip install -U virtualenv
virtualenv venv
source venv/bin/activate
pip install -e .
```

### Run the tests on demand
```bash
pip install pytest
pytest tests/ -s -v --capture=no
```

### Run pylint on demand
```bash
pip install pylint
pylint appkernel
```

### Setup git hooks

```bash
cd .git/hooks
ln -sf ../../hooks/pre-commit ./pre-commit
ln -sf ../../hooks/pre-push ./pre-push
cd ../..
```
### Build & Package Manually

While you have the following configuration in ~/.pypirc:
```bash
index-servers=
	pypi
	pypitest

[pypi]
username=user
password=pass

[pypitest]
username=user
password=pass
```
You can register at [LIVE](https://pypi.python.org/pypi?%3Aaction=register_form) and [TEST](https://testpypi.python.org/pypi?%3Aaction=register_form).
Check the setup and load:

```bash
python setup.py register -r pypitest
```
*this step is not required anymore, since pre-registration is no more required


Than upload the package in both of the repositories
```bash
source ./venv/bin/activate
python setup.py build bdist_wheel upload -r pypitest
python setup.py build bdist_wheel upload -r pypi
```

Update:
```bash
python setup.py build install upload -r pypitest
```