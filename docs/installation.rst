Installation
============

.. warning::
    Work in progress section of documentation.

The short version: ::

    pip install appkernel

The longer version:

Create  your project folder: ::

    mkdir my_project && cd my_project

Install virtual environment (a dedicated workspace where you will install your dependency libraries and these won't enter in conflict with other projects): ::

    pip install --user pipenv
    virtualenv -p python3 venv
    source venv/bin/activate

.. note::
    depending on your installation, you might need to use the command pip3 instead of pip;

Check the python version: ::

    python --version
    Python 3.7.0

If all went good you should have a Python 3.X version (please note: the software is tested with Pyhton 3.6 and 3.7).

Now we are ready to install Appernel and all of its dependencies: ::

    pip install appkernel
