
The following snippet bootstraps AppKernel in development mode so you can
follow along with the examples in this documentation from Python's interactive
interpreter::

    from appkernel import (
        AppKernelEngine, Model, MongoRepository,
        Required, Generator, Validators, Converter, Default,
        Email, NotEmpty, create_uuid_generator, content_hasher,
        MongoUniqueIndex,
    )
    from typing import Annotated

    kernel = AppKernelEngine('demo', enable_defaults=True)

``enable_defaults=True`` connects to MongoDB on ``localhost:27017`` and uses
a database named ``app`` — no ``cfg.yml`` required for quick experiments.
