# encoding=utf8

from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='appkernel',
    # 1.2.0.dev1  # Development release
    # 1.2.0a1     # Alpha Release
    # 1.2.0b1     # Beta Release
    # 1.2.0rc1    # Release Candidate
    # 1.2.0       # Final Release
    version='1.1.0',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=[
        'pyyaml', 'enum34', 'pymongo==3.7.1', 'simplejson',
        'Flask > 0.12.3', 'werkzeug', 'eventlet',
        'wrapt', 'passlib==1.7.1', 'jsonschema',
        'flask-babel', 'babel', 'pyjwt', 'cryptography',
        'recommonmark', 'sets', 'money',
        'aiohttp', 'cchardet', 'aiodns', 'requests'
        # , 'Flask-SocketIO==2.9.2', 'Flask-Login==0.4.0', 'Flask-Session==0.3.1',
        # 'flask-emails', 'flask-httpauth', 'flask-cors',
        # 'python-engineio==1.7.0', 'python-socketio==1.8.1',
        # 'flasgger', 'eventlet', 'six==1.10.0',
        # "jsonstruct==0.2a1", "mockito"
        # 'redis',
    ],
    tests_require=['pytest', 'pytest-flask', 'requests-mock', 'codecov', 'pytest-cov'],
    include_package_data=True,
    platforms='any',
    url='https://appkernel.accelero.cloud',
    license='Apache 2.0',
    author='csaba',
    author_email='tamas.csaba@gmail.com',
    description='An easy to use, beautiful, opinionated micro-service-chassis.',
    long_description=long_description,
    keywords=['microservice', 'flask', 'pymongo'],
    # classifier options are available here: https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Environment :: Console',
        'Environment :: Web Environment',
        'Framework :: Flask',
        'Intended Audience :: Developers',
        'Operating System :: POSIX',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
    ],
    package_data={
        '': ['cfg.yml', '*.json'],
        # If any package contains *.txt or *.rst files, include them:
        # '': ['*.txt', '*.rst'],
        # And include any *.msg files found in the 'hello' package, too:
        # 'hello': ['*.msg'],
    },
    entry_points="""
    [babel.extractors]
    model_messages = appkernel.util:extract_model_messages
    """,
)
