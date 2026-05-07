---
artifact_id: "d73e68e2ed64b77b"
category: "data_model"
name: "stockker.models.schemas.UserLogin"
source_files: ["stockker/models/schemas.py"]
source_lines: {"stockker/models/schemas.py": [22, 25]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "65f54549a60382c081cb99660b9b24d34ceb645a9a780033e4f9609cd29d3028"
---
# stockker.models.schemas.UserLogin

## Overview

The `UserLogin` model is a Pydantic schema used for validating user login credentials. It defines the structure and types of data required for a user to log in to the application.

## Fields

- **email** (`EmailStr`)
  - **Description**: The email address of the user.
  - **Constraints**: Must be a valid email string.
  - **Nullable**: False
  - **Default**: None

- **password** (`str`)
  - **Description**: The password associated with the user's account.
  - **Constraints**: No specific constraints mentioned.
  - **Nullable**: False
  - **Default**: None

## Inheritance

- Inherits from `BaseModel` provided by Pydantic.

## Usage

This schema is typically used in the authentication process to validate the user's email and password before granting access.

## Example

```python
from stockker.models.schemas import UserLogin

login_data = UserLogin(
    email="user@example.com",
    password="securepassword123"
)
```

## Source Provenance

- **Source File**: `stockker/models/schemas.py`
- **Lines**: 22-25
