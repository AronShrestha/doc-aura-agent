---
artifact_id: "29f43e93722fd15a"
category: "env_var"
name: "Environment Variables"
source_files: ["stockker/config.py"]
source_lines: {"stockker/config.py": [4, 4]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "2d69c98a2c3e9108c6d1cd3f8c4df8dcedcf37b19184285f4fb78b9193131d76"
---
# Environment Variables

This document lists and describes all environment variables used in the application, providing necessary context and usage instructions.

## List of Environment Variables

### SECRET_KEY
- **Description**: This variable is used to sign session cookies and other security-related tasks.
- **Usage**: Set this to a random secret value that should not be shared publicly.
- **Secret-like**: Yes
- **Source**: `stockker/config.py` (Line 4)

### DATABASE_URL
- **Description**: This variable specifies the URL for the database connection.
- **Usage**: Format should be compatible with SQLAlchemy, e.g., `postgresql://user:password@localhost/dbname`.
- **Secret-like**: No
- **Source**: `stockker/config.py` (Line 5)

### AUTHORIZED_TOKENS
- **Description**: This variable contains a list of authorized tokens for accessing certain parts of the application.
- **Usage**: Provide a comma-separated list of tokens.
- **Secret-like**: Yes
- **Source**: `stockker/config.py` (Line 7)

## Source Provenance

- **SECRET_KEY**: Defined in `stockker/config.py` at Line 4.
- **DATABASE_URL**: Defined in `stockker/config.py` at Line 5.
- **AUTHORIZED_TOKENS**: Defined in `stockker/config.py` at Line 7.
