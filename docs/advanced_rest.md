#### Json Schema Support
**Request**
```bash
curl -i -X GET \
 'http://127.0.0.1:5000/users/schema'
```
**Response**
```json
{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "additionalProperties": true,
  "properties": {
    "email": {
      "format": "email",
      "type": "string"
    },
    "id": {
      "type": "string"
    },
    "name": {
      "type": "string"
    },
    "password": {
      "type": "string"
    },
    "roles": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "required": [
    "email",
    "password",
    "name",
    "id"
  ],
  "title": "User",
  "type": "object"
}
```