# Features & Roadmap

The framework is supposed to cover the requirements of the Microservice Patterns documented by [Chris Richardson](http://microservices.io/patterns/index.html).

## Model features
A `Model` is a central data object, representing the domain of our business logic (eg. User, Project, Task, etc.).
- [x] validation on the data model using multiple custom validators
- [x] json serialisation support
- [x] json schema generator
- [x] value generators
- [x] value converters
- [x] omitted fields

## ORM features
Appkernel features a thin and beautiful Object Relational Mapping (ORM/a.k.a database access layer / repository) implementation, making access to your data a super-simple task.
- [x] basic CRUD (create/update/delete) operations
- [x] easy to use active record style queries
- [x] automatically generated prefixed database ID
- [x] index management (unique index, text index, etc.) on the database
- [x] database schema validation and schema management
- [x] builtin converters for serialising or deserialising the model to and from various other formats
- [x] audited fields (eg. automatically added created, updated, updated_by fields)
- [x] document versioning
- [x] Bulk Inserts
- [ ] Predefined Database Filters
- [ ] Projections
- [ ] Internal Resources

## REST Service Endpoints
- [x] REST services (GET, PUT, POST, PATCH, DELETE)
- [x] HATEOAS actions on model
- [x] model metadata and json schema
- [x] URL query interface
- [x] Read-only by default
- [x] role based account management (RBAC)
- [x] basic authentication and JWT token support
- [x] customised, machine readable error messages
- [ ] File Storage
- [ ] simplified logging
- [ ] JSONP
- [ ] graphql support
- [ ] OpenApi support
- [ ] Conditional Requests
- [ ] OAUTH
- [ ] rate limiting and circuit breaker
- [ ] API Versioning
- [ ] GeoJSON
- [ ] webflow a web state machine

## Performance controls
- [ ] Data Integrity and Concurrency Control
- [ ] Resource-level Cache Control

## Microservice Infrastructure
- [x] externalized configuration
- [ ] scheduler and background task executor
- [ ] logging, health checks
- [ ] CQRS
- [ ] Event sourcing
- [ ] SAGA Pattern
- [ ] circuit breakers
- [ ] metrics
- [ ] service registration and discovery
- [ ] Enhanced Logging
- [ ] Operations Log
