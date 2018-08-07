from flask import Flask
from appkernel import AppKernelEngine, Controller
import os
import pytest
try:
    import simplejson as json
except ImportError:
    import json

flask_app = Flask(__name__)
flask_app.config['SECRET_KEY'] = 'S0m3S3cr3tC0nt3nt!'
flask_app.testing = True

# todo: test all http methods
# todo: test circuit breaker
# todo: test retry, and timing


@pytest.fixture
def app():
    return flask_app


def setup_module(module):
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    print('\nModule: >> {} at {}'.format(module, current_file_path))
    kernel = AppKernelEngine('test_app', app=flask_app, cfg_dir='{}/../'.format(current_file_path), development=True)


def setup_function(function):
    """ executed before each method call
    """
    print('\n\nSETUP ==> ')