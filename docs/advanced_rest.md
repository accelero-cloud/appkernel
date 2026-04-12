# Advanced REST features

## JSON Schema

Every registered model automatically exposes a JSON Schema endpoint that
clients can use for validation or form generation.

**Request**
```bash
curl http://127.0.0.1:5000/users/schema
```

**Response**
```json
{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "additionalProperties": true,
  "properties": {
    "email":    { "format": "email", "type": "string" },
    "id":       { "type": "string" },
    "name":     { "type": "string" },
    "roles":    { "items": { "type": "string" }, "type": "array" }
  },
  "required": ["name", "id"],
  "title": "User",
  "type": "object"
}
```

Pass `mongo_compatibility=True` when using the schema as a MongoDB collection
validator, since MongoDB handles some types (dates, ObjectIds) differently from
standard JSON Schema.

## UI Metadata

In addition to JSON Schema, AppKernel provides a richer metadata endpoint
optimised for dynamic frontend rendering::

```bash
curl http://127.0.0.1:5000/users/meta
```

The response lists each field with its type, required status, validators,
default value, and a translatable label — everything a form generator or
schema-driven UI needs in one call.

See [the Model](the_model) and [Services](services) sections for the full
reference.
