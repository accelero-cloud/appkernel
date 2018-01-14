#!/usr/bin/python
from flask import Flask
from appkernel import AppKernelEngine

print('Initialising under {}'.format(__name__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'S0m3S3cr3tC0nt3nt!'


def init_app():
    kernel = AppKernelEngine('test_app', app=app)
    kernel.run()


if __name__ == '__main__':
    init_app()
