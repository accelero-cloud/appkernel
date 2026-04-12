# Features & Roadmap

The framework aims to cover the requirements of the Microservice Patterns documented by [Chris Richardson](http://microservices.io/patterns/index.html).

## Model features

A `Model` is a central domain object (e.g. User, Project, Task) that serves as the single source of truth for persistence, validation, serialisation, and REST exposure.

- [x] validation using multiple built-in and custom validators
- [x] JSON serialisation and deserialisation
- [x] JSON Schema generation (Draft-04)
- [x] value generators (UUID, timestamp, current user)
- [x] value converters (password hashing, normalisation)
- [x] wire-format marshallers (timestamp, date↔datetime)
- [x] fields excluded from wire format (`Field(exclude=True)`)

## ORM features

A thin and expressive Object–Document Mapping layer on top of MongoDB.

- [x] basic CRUD (create, update, delete) operations
- [x] active-record style query DSL
- [x] automatically generated and prefixed document IDs
- [x] index management (standard, unique, text)
- [x] MongoDB document schema validation
- [x] built-in serialisation converters
- [x] auditable fields (inserted, updated, version)
- [x] document versioning with optimistic locking (HTTP 409 on conflict)
- [x] bulk inserts
- [x] atomic field updates
- [ ] predefined database filters
- [ ] field projections
- [ ] transactions (multi-document)

## REST Service Endpoints

- [x] REST services (GET, PUT, POST, PATCH, DELETE)
- [x] HATEOAS links on model responses
- [x] model metadata and JSON schema endpoints
- [x] URL query interface (filter, sort, paginate, aggregate)
- [x] read-only by default; write methods opt-in
- [x] role-based access control (RBAC)
- [x] JWT authentication (RS256)
- [x] machine-readable error messages
- [x] OpenAPI 3.0 / Swagger UI support
- [x] file storage (filesystem and GridFS backends, validation chain)
- [x] rate limiting (fixed-window, per-endpoint overrides, 429 + Retry-After)
- [x] circuit breaker (CLOSED / OPEN / HALF_OPEN, per-upstream)
- [x] CORS support
- [x] API versioning (URL prefixes, view models, deprecation signals)
- [ ] JSONP
- [ ] GraphQL support
- [ ] conditional requests (ETags, If-None-Match)
- [ ] OAuth2 support
- [ ] GeoJSON field type

## Performance controls

- [ ] resource-level cache control
- [ ] data integrity and concurrency control beyond optimistic locking

## Microservice infrastructure

- [x] externalised configuration (cfg.yml, env vars, CLI flags)
- [x] inter-service HTTP client with connection pooling and circuit breaker
- [ ] scheduler and background task executor
- [ ] health check endpoints
- [ ] metrics collection (Prometheus / OpenTelemetry)
- [ ] service registration and discovery
- [ ] CQRS
- [ ] event sourcing
- [ ] SAGA pattern
- [ ] Redis-backed rate limiter for multi-instance deployments
- [ ] S3 / Azure Blob / GCS storage backends
