# appkernel
**Python micro-services made easy**: a beautiful and opinionated micro-service framework which enables you
to start a REST application from zero to production within hours.

We've spent the time on analysing the stack, made the hard choices in terms of Database/ORM/Security/Rate Limiting so
you don't have to.

### Why we did this?
* We had the need to build a myriad of small services in our daily business, ranging from data-aggregation pipelines, to housekeeping services and
other process automation services. These do share similar requirements and the stack needs to be rebuilt and tested over and over again. The question arose:
what if how could we avoid spending valuable time with the boilerplate and focus only on the fund part?
* There are several initiatives out there (Flask Admin, Flask Rest Extension and so), which do target parts of the problem, but they either don't play well
together or need substantial effort to make them play nice together. What about a curated set of frameworks, extensions, glued together in a way that you
can start building the actual business logic within the first minutes of your project?
* Often time takes a substantial effort to make a valuable internal hack or proof of concept presentable to customers, until it reaches the maturity in terms reliability, fault
tolerance and security. What if all these aspects would be taken care by the underlying platform?

These were the major driving question, which lead to the development of App Kernel.

### What we did?

AppKernel is built around the concepts of Domain Driven Design. You can start the project by laying out the model.
In the example below we build a small Task manager. All Tasks belong to one Project.
```python
from appkernel import Model, AuditableRepository, Parameter, NotEmpty
from datetime import datetime

class Task(Model, AuditableRepository):
    id = Parameter(str, required=True, generator=uui_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty])
    description = Parameter(str, required=True, validators=[NotEmpty])
    completed = Parameter(bool, required=True, default_value=False)
    created = Parameter(datetime, required=True, generator=date_now_generator)
    closed_date = Parameter(datetime, validators=[Past])

class Project(Model, AuditableRepository):
    name = Parameter(str, required=True, validators=[NotEmpty()])
    tasks = Parameter(list, sub_type=Task)
```
That's it, now you have validation, JSON serialisation, database persistency, strategies for automatic data generation.



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

Than upload the package in both of the repositories
```bash
source ./venv/bin/activate
python setup.py build bdist_wheel upload -r pypitest
python setup.py build bdist_wheel upload -r pypi
```
