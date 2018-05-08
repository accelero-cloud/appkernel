What are we building here?
--------------------------
The vision of the project is to provide you with a full-fledged microservice chassis, as defined by Chris Richardson.

Currently supported (and fully tested) features:
------------------------------------------------

* REST endpoints over HTTP
* Full range of CRUD operations
* Customizable resource endpoints
* Customizable, multiple item endpoints
* Filtering and Sorting
* Pagination
* Data Validation
* Extensible Data Validation
* Default Values
* Projections
* Embedded Resource Serialization
* Custom ID Fields
* MongoDB Aggregation Framework
* Powered by Flask

Why did we built this?
----------------------
* We had the need to build a myriad of small services in our daily business, ranging from data-aggregation pipelines, to housekeeping services and other process automation services. These do share similar requirements and the underlying infrastructure needed to be rebuilt and tested over and over again. The question arose: what if we avoid spending valuable time on the boilerplate and focus only on the fun part?

* Often time takes a substantial effort to make a valuable internal hack or proof of concept presentable to customers, until it reaches the maturity in terms reliability, fault tolerance and security. What if all these non-functional requirements would be taken care by an underlying platform?

* There are several initiatives out there (Flask Admin, Flask Rest Extension and so), which do target parts of the problem, but they either need substantial effort to make them play nice together, either they feel complicated and uneasy to use. We wanted something simple and beautiful, which we love working with.

* These were the major driving question, which lead to the development of App Kernel.

How does it works?
------------------
AppKernel is built around the concepts of Domain Driven Design. You can start the project by laying out the model. The first step is to define the validation and data generations rules. For making life easier, one can also set default values. Than one can extend several built-in classes in order to augment the model with extended functionality:

* extending the Repository class (or its descendants) adds and ORM persistency capability to the model;
* extending the Service class (or its descendants) add the capability to expose the model over REST services;