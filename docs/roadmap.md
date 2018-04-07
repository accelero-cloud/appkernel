# Roadmap

The framework is supposed to cover all or most of the requirements of the Microservice Patterns documented by [Chris Richardson](http://microservices.io/patterns/index.html).

## Basic features
- [ ] database schema validation and schema management
- [x] validation on the data model using multiple custom validators
- [x] builtin converters for serialising or deserialising the model to various other formats
- [x] automated marshaling of objects to and from json
- [x] basic CRUD operations
- [x] audited fields (created, updated)
- [ ] index management on the database
- [x] automatically generate prefixed database ID
- [ ] File Storage
- [ ] simplified logging
- [ ] REST services
- [x] HATEOAS actions on model
- [ ] graphql support
- [ ] swagger support
- [ ] scheduler and background task executor
- [ ] basic authentication and JWT token support
- [ ] OAUTH
- [ ] rate limiting and circuit breaker
- [ ] Conditional Requests
- [ ] Data Integrity and Concurrency Control
- [ ] Bulk Inserts
- [ ] Resource-level Cache Control
- [ ] API Versioning
- [ ] Document Versioning
- [ ] JSONP
- [ ] Read-only by default
- [ ] Predefined Database Filters
- [ ] Projections
- [ ] Rate Limiting
- [ ] GeoJSON
- [ ] Internal Resources
- [ ] Enhanced Logging
- [ ] Operations Log

## Microservice Interaction
- [ ] externalized configuration
- [ ] logging, health checks
- [ ] CQRS
- [ ] Even sourcing
- [ ] SAGA Pattern
- [ ] circuit breakers
- [ ] metrics
- [ ] service registration and discovery
