

The following code-snippet prepares your python-cli to execute the examples from this documentation: ::

    import threading
    from flask import Flask
    from passlib.handlers.pbkdf2 import pbkdf2_sha256
    from flask_babel import _
    from appkernel import Property, Model, MongoRepository, Service, UniqueIndex, Email, NotEmpty, content_hasher, \
        AppKernelEngine, Regexp, CurrentSubject, ServiceException, Anonymous, Role
    from appkernel.service import link

    app = Flask('demo')
    kernel = AppKernelEngine('demo', app=app, enable_defaults=True)
    thread = threading.Thread(target=kernel.run, args=())
    thread.daemon = True
    thread.start()