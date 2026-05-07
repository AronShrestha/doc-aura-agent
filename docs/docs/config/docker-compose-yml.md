---
artifact_id: "46220a9449527854"
category: "config"
name: "docker-compose.yml"
source_files: ["docker-compose.yml"]
source_lines: {"docker-compose.yml": [1, 16]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "395c8b5d5852ff4da0d8bd893160d3692ab361c9a7a906f5a7215cc105217b7e"
---
# docker-compose.yml

## Overview

This document provides a reference for the `docker-compose.yml` file, which is used to define and run multi-container Docker applications. The configuration specifies the services, networks, and volumes required to orchestrate the application containers.

## Configuration Details

### Version

- **version**: '3.8'
  - Specifies the version of the Docker Compose file format.

### Services

The `docker-compose.yml` file defines the following services:

#### Web

- **image**: `python:3.9-slim`
  - Uses the official Python 3.9 slim image as the base.
- **command**: `sh -c "pip install -r requirements.txt && python stockker/__init__.py"`
  - Installs the required Python packages and starts the application.
- **volumes**:
  - `./:/app`: Mounts the current directory to `/app` inside the container.
- **ports**:
  - `"5000:5000"`: Maps port 5000 on the host to port 5000 on the container.
- **environment**:
  - `AUTHORIZED_TOKENS`: List of authorized tokens.
  - `DATABASE_URL`: URL for the database connection.
  - `SECRET_KEY`: Secret key for Flask sessions.
- **depends_on**:
  - `db`: Ensures that the database service is started before the web service.

#### DB

- **image**: `postgres:13`
  - Uses the official PostgreSQL 13 image.
- **environment**:
  - `POSTGRES_DB`: Name of the database.
  - `POSTGRES_USER`: Username for the database.
  - `POSTGRES_PASSWORD`: Password for the database user.
- **volumes**:
  - `db_data:/var/lib/postgresql/data`: Persists the database data.

### Volumes

- **db_data**: Named volume to persist PostgreSQL data.

## Example

```yaml
version: '3.8'

services:
  web:
    image: python:3.9-slim
    command: sh -c "pip install -r requirements.txt && python stockker/__init__.py"
    volumes:
      - ./:/app
    ports:
      - "5000:5000"
    environment:
      - AUTHORIZED_TOKENS=your_tokens_here
      - DATABASE_URL=postgresql://user:password@db:5432/dbname
      - SECRET_KEY=your_secret_key_here
    depends_on:
      - db

  db:
    image: postgres:13
    environment:
      POSTGRES_DB: dbname
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      db_data:/var/lib/postgresql/data

volumes:
  db_data:
```

## Source Provenance

- **File**: `docker-compose.yml`
- **Lines**: 1-16
