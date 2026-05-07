---
artifact_id: "5db3a71af0e6065c"
category: "data_model"
name: "stockker.models.schemas.StockResponse"
source_files: ["stockker/models/schemas.py"]
source_lines: {"stockker/models/schemas.py": [65, 99]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "a49e807aba9b3a208943741df0dd1ceb231fb47562cac718f883c5e309e3c823"
---
# stockker.models.schemas.StockResponse

## Overview

The `StockResponse` model is a Pydantic schema used to represent stock data in the Stockker application. This model is utilized for validating and serializing stock-related data, ensuring that the data conforms to the expected structure and types.

## Fields

- **id** (`int`, required): Unique identifier for the stock entry.
- **user_id** (`int`, required): Identifier for the user who owns the stock.
- **ticker** (`str`, required): Stock ticker symbol.
- **company_name** (`str`, required): Name of the company associated with the stock.
- **quantity** (`float`, required): Quantity of stocks held.
- **current_price** (`float`, required): Current market price of the stock.
- **purchase_price** (`float`, required): Price at which the stock was purchased.
- **stop_loss_price** (`Optional[float]`, required): Price at which the stock should be sold to limit losses (optional).
- **take_profit_price** (`Optional[float]`, required): Price at which the stock should be sold to realize profits (optional).
- **purchase_date** (`Optional[datetime]`, required): Date when the stock was purchased (optional).
- **currency** (`str`, required): Currency in which the stock is traded.
- **exchange** (`Optional[str]`, required): Stock exchange where the stock is listed (optional).
- **created_at** (`datetime`, required): Timestamp indicating when the stock entry was created.
- **updated_at** (`datetime`, required): Timestamp indicating the last update to the stock entry.
- **current_value** (`Optional[float]`, required): Current value of the stock holdings (optional).
- **profit_loss_amount** (`Optional[float]`, required): Calculated profit or loss amount (optional).
- **profit_loss_percentage** (`Optional[float]`, required): Calculated profit or loss percentage (optional).

## Base Classes

- `BaseModel`: Inherits from Pydantic's BaseModel for data validation and settings management.

## Methods

No additional methods are defined in this schema beyond those inherited from `BaseModel`.

## Usage

This schema is primarily used in API responses to provide structured and validated stock data to clients.

## Source Provenance

- **Source File**: `stockker/models/schemas.py`
- **Lines**: 65-99
