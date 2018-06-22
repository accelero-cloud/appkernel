## Development environment

Clone the project:
```bash
git clone git@github.com:accelero-cloud/appkernel.git
```

After cloning the project, you might want to setup a virtual environment:

```bash
cd appkernel
pip install -U virtualenv
virtualenv venv
source venv/bin/activate
pip install -e .
```

*Hint for PyCharm users*

* you might want to set the Project Interpreter (in the project settings) to the virtual environment just have created;
* you might want to set to excluded your .idea, appkernel.egg-info and venv folder in case of using Pycharm;

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

*Hint*: the schema installation feature expects a MongoDB version min. 3.6.
 In case you have an older version you might need to upgrade your mongo image (`docker pull mongo:latest`).

Run the following command in the test folder:
```bash
pytest
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