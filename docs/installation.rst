Installation
============

.. warning::
    Work in progress section of documentation.

The short story
...............
::

    pip install appkernel

The long story
..............

Create  your project folder: ::

    mkdir my_project && cd my_project

Install virtual environment (a dedicated workspace where you will install your dependency libraries and these won't enter in conflict with other projects): ::

    pip install --user pipenv
    virtualenv -p python3 venv
    source venv/bin/activate

.. note::
    depending on your development environment, you might need to use the command pip3 instead of pip;

Check the python version: ::

    python --version
    Python 3.7.0

If all went good you should have a Python 3.X version (please note: the software is tested with Pyhton 3.6 and 3.7).

Now we are ready to install Appernel and all of its dependencies: ::

    pip install appkernel

Creating a microservice
=======================

Take the following sample as a minimalist microservice (offering CRUD operations for an Order Model). Save it into the orderservice.py file ::

    from datetime import datetime
    from flask import Flask
    from appkernel import AppKernelEngine, Model, MongoRepository, Property, create_uuid_generator, date_now_generator


    class Order(Model, MongoRepository):
        id = Property(str, generator=create_uuid_generator('O'))
        products = Property(list, required=True)
        order_date = Property(datetime, required=True, generator=date_now_generator)


    if __name__ == '__main__':
        app_id = f'{Order.__name__} Service'
        kernel = AppKernelEngine(app_id)
        kernel.register(Order, methods=['GET', 'POST', 'DELETE'])
        kernel.run()



Create docker file
..................

   Dump the following content in a file named: order_service_docker_file. ::

    FROM python:3.7-alpine

    RUN apk update && apk upgrade
    RUN apk add --update \
        python \
        python-dev \
        py-pip \
        build-base \
      && pip install virtualenv \
      && rm -rf /var/cache/apk/*
    RUN apk --no-cache add libxml2-dev libxslt-dev libffi-dev openssl-dev python3-dev
    RUN apk --no-cache add --virtual build-dependencies
    RUN pip install appkernel gevent
    WORKDIR /app
    COPY . /app

    EXPOSE 5000
    CMD ["python", "orderservice.py", "-h 172.17.0.2"]

The third parameter in the command section is the address of the Mongo docker image. One can check the address of his own
installation with the following command: ::

    docker inspect bridge |grep -A 5 mongo

Build the image
...............

Let's build the docker image in the current service directory: ::

    docker build -t order_service_image -f order_service_docker_file .

Run the image
.............

And as a last stap we start the service ::

    docker run --name orderservice -d -p 5000:5000 order_service_image

You can list the log file: ::

    docker exec -it orderservice tail -fn 300 /order_service.log

Alternative status output  check could be done with the following command
(note: by default this won't show you anything, since appkernel is not writing to the standard output if it is set to production mode): ::

    docker logs orderservice

Alternatively you can run the image in interactive mode ::

    docker run -it --rm --name order-service order_service_image sh

Optionally you can create a config file
........................................

Just create a file under the name cfg.yml and place it next to your service initiator script: ::

    appkernel:
      logging:
        file_name: myapp.log # the name of the log file
        max_size: 5048 # the maximum size of a log file
        backup_count: 5 # the max. number of log files
      server:
        address: 0.0.0.0 # the bind address
        port: 8080 # the port to expose the services
        shutdown_timeout: 10 # the time left to finish current jobs upon shutdown
        backlog: 100 # the number of connection accepted after the current threads are busy
      mongo:
        host: localhost # the address of the mongo service
        db: appkernel # the name of the database in the mongo instance
      i18n:
        #languages: ['en','en-US' ,'de', 'de-DE']
        languages: ['en-US','de-DE'] # the supported translatio nlanguages