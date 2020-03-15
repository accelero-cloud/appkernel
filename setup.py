# encoding=utf8

from codecs import open
from os import path
from setuptools import setup, find_packages
try:  # for pip >= 10
    from pip._internal.req import parse_requirements
except ImportError:  # for pip <= 9.0.3
    from pip.req import parse_requirements

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

reqs = parse_requirements('requirements.txt', session=False)
requirements = [str(ir.req) for ir in reqs]

setup(
    name='appkernel',
    # 1.2.0.dev1  # Development release
    # 1.2.0a1     # Alpha Release
    # 1.2.0b1     # Beta Release
    # 1.2.0rc1    # Release Candidate
    # 1.2.0       # Final Release
    version='1.2.4',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    setup_requires=['pytest-runner'],
    install_requires=requirements,
    tests_require=['pytest', 'pytest-flask', 'requests-mock', 'codecov', 'pytest-cov', 'recommonmark', 'money'],
    include_package_data=True,
    platforms='any',
    url='https://github.com/accelero-cloud/',
    license='Apache 2.0',
    author='thingsplode',
    author_email='tamas.csaba@gmail.com',
    description='An easy to use API framework.',
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords=['microservice', 'flask', 'pymongo', 'serverless', 'rest', 'flask', 'serialisation', 'orm', 'mongo', 'api',
              'rest api'],
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
