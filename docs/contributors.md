### Setting up the development environment

After cloning the project:

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

*Hint*: in case you use PyCharm

* you would want to set the Project Interpreter (in the project settings) to the virtual environment just have created
* you might want to set to excluded your .idea, appkernel.egg-info and venv folder in case of using Pycharm.

Setup git hooks

```bash
cd .git/hooks
ln -sf ../../hooks/pre-commit ./pre-commit
ln -sf ../../hooks/pre-push ./pre-push
cd ../..
```

### Preparing test execution

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
...where ~/data might be replaced by any folder where you would like to store
database files;

*Hint*: the schema installation feature expects a MongoDB version min. 3.6.
 In case you have an older version you might need to upgrade your mongo image.