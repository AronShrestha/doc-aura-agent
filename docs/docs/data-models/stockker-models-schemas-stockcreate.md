---
artifact_id: "4d152b14e23856a1"
category: "data_model"
name: "stockker.models.schemas.StockCreate"
source_files: ["stockker/models/schemas.py"]
source_lines: {"stockker/models/schemas.py": [39, 49]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "b7beeb11919a42a94ab5cf2f84a6acc24ea8cd0ee475c61d525fae94aac7d55d"
---
# stockker.models.schemas.StockCreate

## Overview

The `StockCreate` model is a Pydantic schema used for validating and creating stock entries in the Stockker application. This model ensures that all necessary fields are provided and meet specific constraints before a stock entry is created in the database.

## Fields

- **ticker** (`str`)
  - **Constraints**: Must match the pattern `'^[A-Z]{1,5}$'`.
  - **Description**: The ticker symbol of the stock, typically a 1 to 5 uppercase letter code.
  
- **company_name** (`str`)
  - **Constraints**: Minimum length of 1 character, maximum length of 200 characters.
  - **Description**: The full name of the company issuing the stock.
  
- **quantity** (`float`)
  - **Constraints**: Must be greater than 0.
  - **Description**: The number of shares purchased.
  
- **purchase_price** (`float`)
  - **Constraints**: Must be greater than 0.
  - **Description**: The price at which each share was purchased.
  
- **stop_loss_price** (`Optional[float]`)
  - **Constraints**: Must be greater than or equal to 0.
  - **Description**: The price at which the stock should be sold to limit losses (optional).
  
- **take_profit_price** (`Optional[float]`)
  - **Constraints**: Must be greater than or equal to 0.
  - **Description**: The price at which the stock should be sold to secure profits (optional).
  
- **purchase_date** (`Optional[datetime]`)
  - **Description**: The date on which the stock was purchased (optional).
  
- **currency** (`str`)
  - **Constraints**: Default value is `'USD'`, must match the pattern `'^[A-Z]{3}$'`.
  - **Description**: The currency in which the stock was purchased, typically a 3 uppercase letter ISO currency code.
  
- **exchange** (`Optional[str]`)
  - **Description**: The stock exchange where the stock is listed (optional).

## Inheritance

- Inherits from `BaseModel` provided by Pydantic.

## Usage

This model is primarily used in the creation of new stock entries within the Stockker application. It ensures that all required fields are present and valid before the data is processed further or stored in the database.

## Source Provenance

- **Source File**: `stockker/models/schemas.py`
- **Lines**: 39-49
