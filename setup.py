# encoding=utf8

from codecs import open
from os import path
from setuptools import setup, find_packages

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='appkernel',
    version='2.0.0',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=[
        'pyyaml',
        'pymongo>=4.0,<5.0',
        'simplejson',
        'fastapi>=0.100',
        'uvicorn[standard]>=0.20',
        'python-multipart',
        'wrapt',
        'passlib>=1.7.4',
        'jsonschema',
        'babel',
        'pyjwt>=2.0',
        'cryptography',
        'aiohttp',
        'requests',
    ],
    tests_require=['pytest', 'httpx', 'requests-mock', 'codecov', 'pytest-cov', 'money'],
    include_package_data=True,
    platforms='any',
    url='https://github.com/accelero-cloud/',
    license='Apache 2.0',
    author='thingsplode',
    author_email='tamas.csaba@gmail.com',
    description='An easy to use API framework.',
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords=['microservice', 'fastapi', 'pymongo', 'serverless', 'rest', 'serialisation', 'orm', 'mongo', 'api',
              'rest api'],
    classifiers=[
        'Environment :: Console',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: POSIX',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
    ],
    package_data={
        '': ['cfg.yml', '*.json'],
    },
    entry_points="""
    [babel.extractors]
    model_messages = appkernel.util:extract_model_messages
    """,
)
