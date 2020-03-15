## Development environment

Clone the project:

```bash
git clone git@github.com:accelero-cloud/appkernel.git
```

After cloning the project, you might want to setup a virtual environment:

```bash
cd appkernel
pip install --user pipenv
virtualenv -p python3 .venv
source venv/bin/activate
pip install -e .
pip install -r dev-requirements.txt
```

Since astroid (a dependency of pylint) is not supporting python 3.7 yet, you might need to run the
command from above if your pylint analysis ends with `RuntimeError: generator raised StopIteration`.

```bash
pip install --pre -U pylint astroid
```

_Hint for PyCharm users_

- you might want to set the Project Interpreter (in the project settings) to the virtual environment just have created;
- you might want to set to excluded your .idea, appkernel.egg-info and venv folder in case of using Pycharm;

#### Setup git hooks

The project features pre-commit and pre-push hooks for automatically running tests and pylint:

```bash
cd .git/hooks
ln -sf ../../hooks/pre-commit ./pre-commit
ln -sf ../../hooks/pre-push ./pre-push
cd ../..
```

#### Preparing test execution

Some tests require compiled translations:

```bash
cd tests
pybabel compile -d ./translations
```

And many others a working local mongo db:

```bash
docker create -v ~/data:/data/db -p 27017:27017 --name mongo mongo
docker start mongo
```

...where `~/data` might be replaced by any folder where you would like to store
database files;

_Hint_: the schema installation feature expects a MongoDB version min. 3.6.
In case you have an older version you might need to upgrade your mongo image (`docker pull mongo:latest`).

Run the following command in the test folder:

```bash
pytest
```

### Publish the project to PyPi

Make sure yuo have the latest twine version:

```bash
python3 -m pip install --upgrade twine
```

Make a test run:

```bash
python setup.py build -vf && python setup.py bdist_wheel
twine upload --repository-url https://test.pypi.org/legacy/ dist/*
```

Once we are ready we can upload the package the repo:

```bash
python setup.py build -vf && python setup.py bdist_wheel
twine upload dist/*
```

In case you have a ~/.pypirc you can use the shortcut names:

```bash
[distutils]
index-servers=
	pypi
	pypitest

[pypi]
#repository=https://pypi.python.org/pypi
username=user
password=pass

[pypitest]
#repository=https://testpypi.python.org/pypi
username=user
password=pass
```

```bash
twine upload -r pypitest dist/*
```

### Migration to Python3

```bash
sudo apt install python3-pip
python -m pip install --upgrade pip
sudo update-alternatives --install /usr/bin/python python /usr/bin/python2.7 1
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.5 2
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.6 3
update-alternatives --list python
sudo pip install --upgrade pip
virtualenv -p /usr/bin/python3.6 venv3
source ./venv3/bin/activate
pip install pylint
```
