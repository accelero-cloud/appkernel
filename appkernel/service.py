#!/usr/bin/python
from flask import Flask

app = Flask(__name__)
app.config['SECRET_KEY'] = 'S0m3S3cr3tC0nt3nt!'

if __name__ == '__main__':
    init_app()