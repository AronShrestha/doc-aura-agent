---
artifact_id: "0ca98dfe41e2f141"
category: "data_model"
name: "stockker.models.schemas.PriceUpdate"
source_files: ["stockker/models/schemas.py"]
source_lines: {"stockker/models/schemas.py": [59, 62]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "0d97aef523b5878650eac20ff44ec3cdfe4b63bfb0cb369388b77764f3798a35"
---
# stockker.models.schemas.PriceUpdate

## Overview

The `PriceUpdate` model is a Pydantic schema used for validating and representing price update data within the Stockker application. This model ensures that the data adheres to specific constraints, particularly for the `price_type` and `price` fields.

## Fields

### price_type

- **Type**: `str`
- **Constraints**: Must match the regular expression pattern `^(stop-loss|take-profit)$`.
- **Default**: `Field(..., pattern='^(stop-loss|take-profit)$')`
- **Nullable**: `False`

This field specifies the type of price update, which can either be "stop-loss" or "take-profit".

### price

- **Type**: `float`
- **Constraints**: Must be greater than or equal to 0.
- **Default**: `Field(..., ge=0)`
- **Nullable**: `False`

This field represents the price value associated with the update. It must be a non-negative floating-point number.

## Usage

The `PriceUpdate` model is utilized in scenarios where price updates need to be validated and processed, such as updating stock prices in the application.

## Example

```python
from stockker.models.schemas import PriceUpdate

# Creating an instance of PriceUpdate
price_update = PriceUpdate(price_type="stop-loss", price=150.75)

# Accessing fields
print(price_update.price_type)  # Output: stop-loss
print(price_update.price)       # Output: 150.75
```

## Source Provenance

- **Source File**: `stockker/models/schemas.py`
- **Source Lines**: 59-62
