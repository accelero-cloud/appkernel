# Roadmap

The framework is supposed to cover all or most of the requirements of the Microservice Patterns documented by [Chris Richardson](http://microservices.io/patterns/index.html).

## Model features
- [x] validation on the data model using multiple custom validators
- [x] json serialisation support
- [x] generators
- [ ] converters

## Database features
- [x] basic CRUD operations
- [ ] easy to use active record style queries
- [x] automatically generate prefixed database ID
- [x] index management on the database
- [ ] database schema validation and schema management
- [x] builtin converters for serialising or deserialising the model to various other formats
- [x] automated marshaling of objects to and from json
- [x] audited fields (created, updated)
- [x] Document Versioning
- [ ] Bulk Inserts
- [ ] Predefined Database Filters
- [ ] Projections
- [ ] Internal Resources

## REST Service Endpoints
- [ ] File Storage
- [ ] simplified logging
- [X] REST services
- [x] HATEOAS actions on model
- [ ] object metadata
- [ ] JSONP
- [ ] graphql support
- [ ] swagger support
- [ ] Conditional Requests
- [ ] basic authentication and JWT token support
- [ ] OAUTH
- [ ] rate limiting and circuit breaker
- [ ] API Versioning
- [ ] Read-only by default
- [ ] GeoJSON
- [ ] webflow

## Performance controls
- [ ] Data Integrity and Concurrency Control
- [ ] Resource-level Cache Control

## Microservice Interaction
- [ ] scheduler and background task executor
- [x] externalized configuration
- [ ] logging, health checks
- [ ] CQRS
- [ ] Event sourcing
- [ ] SAGA Pattern
- [ ] circuit breakers
- [ ] metrics
- [ ] service registration and discovery
- [ ] Enhanced Logging
- [ ] Operations Log
