---
artifact_id: "b14e00b70b2eba2a"
category: "data_model"
name: "stockker.models.schemas.StockUpdate"
source_files: ["stockker/models/schemas.py"]
source_lines: {"stockker/models/schemas.py": [52, 56]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "1d80c7f4dd29540d53a1c4a329618a90fee1e188afb16836422917faf920d6fd"
---
# stockker.models.schemas.StockUpdate

## Overview

The `StockUpdate` class is a Pydantic model used for validating and updating stock-related data within the Stockker application. This model ensures that the data adheres to specific constraints before being processed or stored.

## Fields

- **quantity** (`Optional[float]`)
  - **Constraints**: Greater than 0 (`gt=0`)
  - **Default**: `Field(None, gt=0)`
  - **Nullable**: False
  - **Description**: Represents the quantity of stocks to be updated. Must be greater than zero.

- **stop_loss_price** (`Optional[float]`)
  - **Constraints**: Greater than or equal to 0 (`ge=0`)
  - **Default**: `Field(None, ge=0)`
  - **Nullable**: False
  - **Description**: Defines the stop loss price for the stock. Must be non-negative.

- **take_profit_price** (`Optional[float]`)
  - **Constraints**: Greater than or equal to 0 (`ge=0`)
  - **Default**: `Field(None, ge=0)`
  - **Nullable**: False
  - **Description**: Specifies the take profit price for the stock. Must be non-negative.

## Inheritance

- Inherits from `BaseModel` provided by Pydantic.

## Usage

The `StockUpdate` model is utilized in scenarios where stock quantities and price thresholds need to be updated, ensuring that the input data meets the specified criteria.

## Source Provenance

- **Source File**: `stockker/models/schemas.py`
- **Lines**: 52-56
