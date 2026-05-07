---
artifact_id: "29f43e93722fd15a"
category: "data_model"
name: "stockker.models.schemas.UserResponse"
source_files: ["stockker/models/schemas.py"]
source_lines: {"stockker/models/schemas.py": [28, 36]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "68b35afa69e73bebba582763c477c9c199c4b6d2352e1960381c286ebd9d4d25"
---
# stockker.models.schemas.UserResponse

## Overview

The `UserResponse` model is a Pydantic schema used to define the structure of user response data in the Stockker application. This schema ensures that the data returned to the client after user-related operations (such as registration or login) adheres to a consistent format.

## Fields

- **id** (`int`)
  - **Description**: Unique identifier for the user.
  - **Nullable**: False
  - **Constraints**: None

- **email** (`str`)
  - **Description**: Email address of the user.
  - **Nullable**: False
  - **Constraints**: None

- **full_name** (`str`)
  - **Description**: Full name of the user.
  - **Nullable**: False
  - **Constraints**: None

- **created_at** (`datetime`)
  - **Description**: Timestamp indicating when the user was created.
  - **Nullable**: False
  - **Constraints**: None

## Inheritance

- **BaseModel**
  - The `UserResponse` class inherits from Pydantic's `BaseModel`, which provides data validation and settings management using Python type annotations.

## Usage

This schema is primarily used in the authentication and user management parts of the application to standardize the user data format returned to the client.

## Example

```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Doe",
  "created_at": "2023-10-01T12:34:56"
}
```

## Source Provenance

- **Source File**: `stockker/models/schemas.py`
- **Source Lines**: 28-36
