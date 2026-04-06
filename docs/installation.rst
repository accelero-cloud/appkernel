Installation
============

The short story
...............

::

    pip install appkernel

The long story
..............

Create your project folder::

    mkdir my_project && cd my_project

Set up a virtual environment::

    python3 -m venv venv
    source venv/bin/activate

.. note::
    AppKernel requires Python 3.12 or later.

Verify your Python version::

    python --version
    Python 3.12.x

Install AppKernel and all its dependencies::

    pip install appkernel

Creating a microservice
=======================

The following is a minimal microservice that exposes CRUD operations for an Order model.
Save it as ``orderservice.py``::

    from datetime import datetime
    from typing import Annotated
    from appkernel import AppKernelEngine, Model, MongoRepository, Required, Generator
    from appkernel import create_uuid_generator, date_now_generator


    class Order(Model, MongoRepository):
        id: Annotated[str | None, Generator(create_uuid_generator('O'))] = None
        products: Annotated[list | None, Required()] = None
        order_date: Annotated[datetime | None, Required(), Generator(date_now_generator)] = None


    if __name__ == '__main__':
        kernel = AppKernelEngine('Order Service')
        kernel.register(Order, methods=['GET', 'POST', 'DELETE'])
        kernel.run()

Start the service::

    python orderservice.py
    INFO:     Uvicorn running on http://0.0.0.0:5000 (Press CTRL+C to quit)

Configuration file
..................

Create a ``cfg.yml`` file next to your service script to override defaults::

    appkernel:
      logging:
        file_name: myapp.log      # log file name
        max_size: 5048            # maximum log file size in bytes
        backup_count: 5           # number of archived log files to keep
      server:
        address: 0.0.0.0          # bind address
        port: 8080                # listening port
        shutdown_timeout: 10      # seconds to allow in-flight requests to finish on shutdown
      mongo:
        host: localhost           # MongoDB host (accepts full mongodb:// URI)
        db: appkernel             # database name
      i18n:
        languages: ['en-US', 'de-DE']   # supported translation languages

Docker deployment
.................

Create a ``Dockerfile``::

    FROM python:3.12-slim

    WORKDIR /app
    COPY . /app

    RUN pip install appkernel

    EXPOSE 5000
    CMD ["python", "orderservice.py"]

Build the image::

    docker build -t order_service_image .

Find your local MongoDB container's IP if needed::

    docker inspect bridge | grep -A 5 mongo

Run the container::

    docker run --name orderservice -d -p 5000:5000 order_service_image

Stream logs::

    docker logs -f orderservice

Run in interactive mode::

    docker run -it --rm --name order-service order_service_image sh
