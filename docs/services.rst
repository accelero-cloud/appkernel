Services
========
The vision of the project is to provide you with a full-fledged microservice chassis, as defined by Chris Richardson.

.. warning::
    Work in progress section of documentation.

* Full range of CRUD operations

* :ref:`REST endpoints over HTTP`
* :ref:`Filtering and Sorting`
* :ref:`Pagination`
* :ref:`Embedded Resource Serialization`
* Projections
* Customizable resource endpoints

* :ref:`Powered by Flask`

REST endpoints over HTTP
````````````````````````clear
USE CASE / MOTIVATION
Let's assume that we have created a User class extending the :class:`Model` and the :class:`Service`. Now we'd like to expose it as a REST endpoint ::

    if __name__ == '__main__':
        app = Flask(__name__)
        kernel = AppKernelEngine('demo app', app=app)
        kernel.register(User)
        kernel.run()

Powered by Flask
````````````````
