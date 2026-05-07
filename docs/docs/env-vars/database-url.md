---
artifact_id: "6aac49a831c2331f"
category: "env_var"
name: "DATABASE_URL"
source_files: ["stockker/config.py"]
source_lines: {"stockker/config.py": [5, 5]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "369341b37df8097082031453d7389e6c580d726ef2627c2ee2a4ff9fb70b565c"
---
# DATABASE_URL

## Overview

The `DATABASE_URL` environment variable is crucial for configuring the connection string that the application uses to interact with the database. This variable is essential for setting up the SQLAlchemy ORM, which is used throughout the application for database operations.

## Usage

The `DATABASE_URL` should be set in the environment where the application is deployed. It is referenced in the `stockker/config.py` file to configure the SQLAlchemy engine.

### Example

```python
# stockker/config.py:5
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///default.db")
```

In this example, if the `DATABASE_URL` environment variable is not set, the application will default to using an SQLite database named `default.db`.

## Format

The format of the `DATABASE_URL` should follow the standard SQLAlchemy URL format:

```
dialect+driver://username:password@host:port/database
```

- **dialect**: The database system (e.g., `postgresql`, `mysql`, `sqlite`).
- **driver**: The DBAPI to use (e.g., `psycopg2` for PostgreSQL, `pymysql` for MySQL).
- **username**: The username for the database.
- **password**: The password for the database.
- **host**: The hostname or IP address of the database server.
- **port**: The port number on which the database server is listening.
- **database**: The name of the database to connect to.

### Example Connection Strings

- **PostgreSQL**:
  ```
  postgresql+psycopg2://user:password@localhost:5432/mydatabase
  ```

- **MySQL**:
  ```
  mysql+pymysql://user:password@localhost:3306/mydatabase
  ```

- **SQLite**:
  ```
  sqlite:///path/to/database.db
  ```

## Security Considerations

- **Secret Management**: Ensure that the `DATABASE_URL` does not contain sensitive information such as passwords in plain text. Consider using a secrets manager or environment variable management tool to securely handle sensitive data.
- **Environment-Specific URLs**: Use different `DATABASE_URL` values for development, testing, and production environments to avoid accidental data leakage or corruption.

## Source Provenance

- **Source File**: `stockker/config.py`
- **Source Lines**: 5
