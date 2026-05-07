---
artifact_id: "79e3763389712fb4"
category: "config"
name: "Dockerfile"
source_files: ["Dockerfile"]
source_lines: {"Dockerfile": [1, 39]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "e0b3cebbfaeba1020f9c7fb8c94cff26d5568b5c1c5f9edada37926be1b033d2"
---
# Dockerfile

This document provides a detailed reference for the Docker configuration used to build and run the application in a containerized environment.

## Overview

The Dockerfile defines the environment in which the Flask application runs, including dependencies and configurations necessary for the application to operate correctly within a Docker container.

## Dockerfile Instructions

Below is a breakdown of each instruction in the Dockerfile:

### 1. Base Image
```dockerfile
FROM python:3.9-slim
```
- **Description**: Specifies the base image for the Docker container. In this case, it uses the official Python 3.9 slim image.
- **Source Provenance**: Dockerfile (Line 1)

### 2. Set Working Directory
```dockerfile
WORKDIR /app
```
- **Description**: Sets the working directory inside the container to `/app`.
- **Source Provenance**: Dockerfile (Line 3)

### 3. Copy Requirements File
```dockerfile
COPY requirements.txt .
```
- **Description**: Copies the `requirements.txt` file from the host machine to the current working directory in the container.
- **Source Provenance**: Dockerfile (Line 5)

### 4. Install Dependencies
```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```
- **Description**: Installs the Python dependencies listed in `requirements.txt`. The `--no-cache-dir` option ensures that the cache is not saved, reducing the size of the final image.
- **Source Provenance**: Dockerfile (Line 7)

### 5. Copy Application Code
```dockerfile
COPY . .
```
- **Description**: Copies all files and directories from the host machine to the current working directory in the container.
- **Source Provenance**: Dockerfile (Line 9)

### 6. Expose Port
```dockerfile
EXPOSE 5000
```
- **Description**: Informs Docker that the container listens on the specified network ports at runtime. Here, it exposes port 5000.
- **Source Provenance**: Dockerfile (Line 11)

### 7. Command to Run Application
```dockerfile
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "stockker:create_app()"]
```
- **Description**: Specifies the command to run the application. This command starts the Flask application using Gunicorn with 4 worker processes and binds it to all interfaces on port 5000.
- **Source Provenance**: Dockerfile (Line 13)

## Environment Variables

The application relies on several environment variables for configuration. These must be set when running the Docker container:

- `AUTHORIZED_TOKENS`: A list of authorized tokens for access control.
- `DATABASE_URL`: The URL for the database connection.
- `SECRET_KEY`: A secret key for session management and cryptographic signing.

## Building the Docker Image

To build the Docker image, navigate to the root directory of the repository and run the following command:

```bash
docker build -t stockker-app .
```

## Running the Docker Container

To run the Docker container, use the following command, replacing `<your-env-file>` with the path to your environment file:

```bash
docker run -p 5000:5000 --env-file <your-env-file> stockker-app
```

This command maps port 5000 of the container to port 5000 on the host machine and loads environment variables from the specified file.

## Source Provenance

- **Dockerfile**: Lines 1-39

This documentation is generated based on the provided Dockerfile and the repository analysis. For more detailed information, refer to the [README.md](README.md) and other documentation files in the repository.
