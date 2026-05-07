---
artifact_id: "18f55d1c7e8eab4e"
category: "env_var"
name: "AUTHORIZED_TOKENS"
source_files: ["stockker/config.py"]
source_lines: {"stockker/config.py": [7, 7]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "eda4a37aae8210c1e9092d6088db5be374a2f3268233990c6fcc5916917e4236"
---
# AUTHORIZED_TOKENS

## Description

The `AUTHORIZED_TOKENS` environment variable is used to specify a list of tokens that are authorized to access certain protected endpoints within the application. This variable is crucial for implementing token-based access control, ensuring that only requests with valid tokens can perform specific actions.

## Usage

The `AUTHORIZED_TOKENS` variable should contain a comma-separated list of tokens. Each token must match exactly to be considered valid.

### Example

```plaintext
AUTHORIZED_TOKENS=token1,token2,token3
```

## Security Considerations

- **Secret Management**: Since `AUTHORIZED_TOKENS` contains sensitive information, it should be managed securely. Avoid hardcoding tokens in your source code.
- **Environment Isolation**: Ensure that different environments (development, staging, production) use distinct sets of tokens to prevent unauthorized access across environments.

## Source Provenance

- **Source File**: `stockker/config.py`
- **Lines**: 7

This documentation provides a reference for the `AUTHORIZED_TOKENS` environment variable, detailing its usage and security considerations. For further information on how tokens are utilized within the application, refer to the relevant sections in the [README.md](README.md) and the source code.
