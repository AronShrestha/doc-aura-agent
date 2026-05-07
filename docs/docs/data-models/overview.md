---
artifact_id: "b7e98cd7e4d85aa2"
category: "data_model"
name: "Data Models"
source_files: ["stockker/models/schemas.py"]
source_lines: {"stockker/models/schemas.py": [28, 36]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "d3367904d384bdeb69eb109b9cd8879001f0889865e0950322b8625f4b0f1f79"
---
# Data Models

This document outlines the data models used in the application, detailing their structure, fields, and relationships. The application leverages Pydantic for data validation and SQLAlchemy for ORM.

## Table of Contents

- [PortfolioResponse](#portfolioresponse)
- [PriceUpdate](#priceupdate)
- [StockCreate](#stockcreate)
- [StockResponse](#stockresponse)
- [StockUpdate](#stockupdate)
- [UserLogin](#userlogin)
- [UserRegister](#userregister)
- [UserResponse](#userresponse)

---

## PortfolioResponse

**Canonical Locator:** `stockker.models.schemas.PortfolioResponse`

**Description:** Represents the response model for a user's portfolio, including details about each stock and overall portfolio metrics.

**Fields:**

- **stocks** (`List[StockResponse]`): A list of stocks in the portfolio.
- **total_value** (`float`): The total current value of the portfolio.
- **total_invested** (`float`): The total amount invested in the portfolio.
- **total_profit_loss** (`float`): The total profit or loss of the portfolio.
- **total_profit_loss_percentage** (`float`): The total profit or loss percentage of the portfolio.
- **last_updated** (`datetime`): The last updated timestamp of the portfolio.

**Source:** [stockker/models/schemas.py:102-109](#)

---

## PriceUpdate

**Canonical Locator:** `stockker.models.schemas.PriceUpdate`

**Description:** Represents the model for updating stock prices with stop-loss or take-profit triggers.

**Fields:**

- **price_type** (`str`): The type of price update, either 'stop-loss' or 'take-profit'.
- **price** (`float`): The price value for the update.

**Constraints:**

- `price_type`: Must match the pattern `'^(stop-loss|take-profit)$'`.
- `price`: Must be greater than or equal to 0.

**Source:** [stockker/models/schemas.py:59-62](#)

---

## StockCreate

**Canonical Locator:** `stockker.models.schemas.StockCreate`

**Description:** Represents the model for creating a new stock entry in the portfolio.

**Fields:**

- **ticker** (`str`): The stock ticker symbol.
- **company_name** (`str`): The name of the company.
- **quantity** (`float`): The quantity of stocks purchased.
- **purchase_price** (`float`): The purchase price per stock.
- **stop_loss_price** (`Optional[float]`): The stop-loss price for the stock.
- **take_profit_price** (`Optional[float]`): The take-profit price for the stock.
- **purchase_date** (`Optional[datetime]`): The date of purchase.
- **currency** (`str`): The currency of the transaction.
- **exchange** (`Optional[str]`): The exchange where the stock is traded.

**Constraints:**

- `ticker`: Must match the pattern `'^[A-Z]{1,5}$'`.
- `company_name`: Must have a length between 1 and 200 characters.
- `quantity`: Must be greater than 0.
- `purchase_price`: Must be greater than 0.
- `stop_loss_price`: Must be greater than or equal to 0.
- `take_profit_price`: Must be greater than or equal to 0.
- `currency`: Must match the pattern `'^[A-Z]{3}$'`.

**Source:** [stockker/models/schemas.py:39-49](#)

---

## StockResponse

**Canonical Locator:** `stockker.models.schemas.StockResponse`

**Description:** Represents the response model for a stock entry in the portfolio, including calculated values like current value and profit/loss.

**Fields:**

- **id** (`int`): The unique identifier for the stock entry.
- **user_id** (`int`): The ID of the user who owns the stock.
- **ticker** (`str`): The stock ticker symbol.
- **company_name** (`str`): The name of the company.
- **quantity** (`float`): The quantity of stocks held.
- **current_price** (`float`): The current market price of the stock.
- **purchase_price** (`float`): The purchase price per stock.
- **stop_loss_price** (`Optional[float]`): The stop-loss price for the stock.
- **take_profit_price** (`Optional[float]`): The take-profit price for the stock.
- **purchase_date** (`Optional[datetime]`): The date of purchase.
- **currency** (`str`): The currency of the transaction.
- **exchange** (`Optional[str]`): The exchange where the stock is traded.
- **created_at** (`datetime`): The creation timestamp of the stock entry.
- **updated_at** (`datetime`): The last updated timestamp of the stock entry.
- **current_value** (`Optional[float]`): The current value of the stock holdings.
- **profit_loss_amount** (`Optional[float]`): The profit or loss amount for the stock holdings.
- **profit_loss_percentage** (`Optional[float]`): The profit or loss percentage for the stock holdings.

**Source:** [stockker/models/schemas.py:65-99](#)

---

## StockUpdate

**Canonical Locator:** `stockker.models.schemas.StockUpdate`

**Description:** Represents the model for updating an existing stock entry in the portfolio.

**Fields:**

- **quantity** (`Optional[float]`): The updated quantity of stocks.
- **stop_loss_price** (`Optional[float]`): The updated stop-loss price for the stock.
- **take_profit_price** (`Optional[float]`): The updated take-profit price for the stock.

**Constraints:**

- `quantity`: Must be greater than 0.
- `stop_loss_price`: Must be greater than or equal to 0.
- `take_profit_price`: Must be greater than or equal to 0.

**Source:** [stockker/models/schemas.py:52-56](#)

---

## UserLogin

**Canonical Locator:** `stockker.models.schemas.UserLogin`

**Description:** Represents the model for user login credentials.

**Fields:**

- **email** (`EmailStr`): The user's email address.
- **password** (`str`): The user's password.

**Source:** [stockker/models/schemas.py:22-25](#)

---

## UserRegister

**Canonical Locator:** `stockker.models.schemas.UserRegister`

**Description:** Represents the model for user registration details.

**Fields:**

- **email** (`EmailStr`): The user's email address.
- **password** (`str`): The user's password.
- **full_name** (`str`): The full name of the user.

**Constraints:**

- `password`: Must have a minimum length of 6 characters.
- `full_name`: Must have a length between 2 and 100 characters.

**Validators:**

- `validate_password`: Validates the password strength.

**Source:** [stockker/models/schemas.py:7-19](#)

---

## UserResponse

**Canonical Locator:** `stockker.models.schemas.UserResponse`

**Description:** Represents the response model for user details.

**Fields:**

- **id** (`int`): The unique identifier for the user.
- **email** (`str`): The user's email address.
- **full_name** (`str`): The full name of the user.
- **created_at** (`datetime`): The creation timestamp of the user account.

**Source:** [stockker/models/schemas.py:28-36](#)

---

### Source Provenance

- **PortfolioResponse**: [stockker/models/schemas.py:102-109](#)
- **PriceUpdate**: [stockker/models/schemas.py:59-62](#)
- **StockCreate**: [stockker/models/schemas.py:39-49](#)
- **StockResponse**: [stockker/models/schemas.py:65-99](#)
- **StockUpdate**: [stockker/models/schemas.py:52-56](#)
- **UserLogin**: [stockker/models/schemas.py:22-25](#)
- **UserRegister**: [stockker/models/schemas.py:7-19](#)
- **UserResponse**: [stockker/models/schemas.py:28-36](#)
