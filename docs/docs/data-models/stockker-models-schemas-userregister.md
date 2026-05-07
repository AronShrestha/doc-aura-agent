---
artifact_id: "e72d7e4a9d12b67e"
category: "data_model"
name: "stockker.models.schemas.UserRegister"
source_files: ["stockker/models/schemas.py"]
source_lines: {"stockker/models/schemas.py": [7, 19]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "6f0e9dc793c50831e023c9326a753ac087433c54c7838d88da900e3eebc0e418"
---
# stockker.models.schemas.UserRegister

## Overview

The `UserRegister` model is a Pydantic schema used for validating user registration data. It inherits from `BaseModel` and includes fields for email, password, and full name. The model also includes a custom validator for the password field.

## Fields

- **email** (`EmailStr`)
  - **Description**: The user's email address.
  - **Constraints**: Must be a valid email string.
  - **Nullable**: False
  - **Default**: None

- **password** (`str`)
  - **Description**: The user's password.
  - **Constraints**: Minimum length of 6 characters.
  - **Nullable**: False
  - **Default**: `Field(..., min_length=6)`

- **full_name** (`str`)
  - **Description**: The user's full name.
  - **Constraints**: Minimum length of 2 characters, maximum length of 100 characters.
  - **Nullable**: False
  - **Default**: `Field(..., min_length=2, max_length=100)`

## Validators

- **validate_password**
  - **Description**: A custom validator for the password field. This validator ensures that the password meets specific criteria (e.g., complexity requirements).

## Source Provenance

- **Source File**: `stockker/models/schemas.py`
- **Source Lines**: 7-19

---

*This documentation was generated based on the provided source code and does not include any external references or additional context beyond what was supplied.*
