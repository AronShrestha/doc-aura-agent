---
artifact_id: "f2528773e47b49c0"
category: "data_model"
name: "stockker.models.schemas.PortfolioResponse"
source_files: ["stockker/models/schemas.py"]
source_lines: {"stockker/models/schemas.py": [102, 109]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "e5f405526791696e05586e80f61c66ac50e7cc0583c592c24a421d0e91c65b5e"
---
# stockker.models.schemas.PortfolioResponse

## Overview

The `PortfolioResponse` model is a Pydantic schema used to represent the response structure for a portfolio in the Stockker application. This model encapsulates details about the stocks held in the portfolio, including their current values, total investments, and profit or loss metrics.

## Fields

- **stocks** (`List[StockResponse]`)
  - A list of `StockResponse` objects representing each stock in the portfolio.
  - **Constraints**: None
  - **Default**: `None`
  - **Nullable**: False
  - **Type**: `List[StockResponse]`

- **total_value** (`float`)
  - The total market value of all stocks in the portfolio.
  - **Constraints**: None
  - **Default**: `None`
  - **Nullable**: False
  - **Type**: `float`

- **total_invested** (`float`)
  - The total amount invested in the portfolio.
  - **Constraints**: None
  - **Default**: `None`
  - **Nullable**: False
  - **Type**: `float`

- **total_profit_loss** (`float`)
  - The total profit or loss amount for the portfolio.
  - **Constraints**: None
  - **Default**: `None`
  - **Nullable**: False
  - **Type**: `float`

- **total_profit_loss_percentage** (`float`)
  - The total profit or loss percentage for the portfolio.
  - **Constraints**: None
  - **Default**: `None`
  - **Nullable**: False
  - **Type**: `float`

- **last_updated** (`datetime`)
  - The timestamp indicating when the portfolio was last updated.
  - **Constraints**: None
  - **Default**: `None`
  - **Nullable**: False
  - **Type**: `datetime`

## Inheritance

- Inherits from `BaseModel` provided by Pydantic.

## Usage

This model is primarily used in the API response for the `/api/get_portfolio` endpoint, where it aggregates and returns the portfolio details to the client.

## Source Provenance

- **Source File**: `stockker/models/schemas.py`
- **Source Lines**: 102-109
