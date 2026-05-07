---
artifact_id: "a68c803b00c484b8"
category: "module"
name: "API Endpoints"
source_files: ["stockker/routes/api.py"]
source_lines: {"stockker/routes/api.py": [26, 49]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "276c169682499f424f6dacf09b425e00220fb2a99c9aa4c8fd9618ffbfffbeb9"
---
# API Endpoints

This document lists and describes all API endpoints, including their request methods, parameters, and expected responses.

## Table of Contents

- [Health Check](#health-check)
- [Get Portfolio](#get-portfolio)
- [Get Stock Details](#get-stock-details)
- [Save DP Settings](#save-dp-settings)
- [Sync Portfolio](#sync-portfolio)
- [Update Stock Price](#update-stock-price)

---

## Health Check

**Endpoint:** `/health`

**Method:** `GET`

**Description:** Health check endpoint for Docker and monitoring.

**Request Parameters:**
- None

**Response:**

```json
{
  "status": "ok",
  "timestamp": "2023-10-01T12:34:56.789Z"
}
```

**Source Provenance:**
- **File:** `stockker/routes/api.py`
- **Lines:** 200-206

---

## Get Portfolio

**Endpoint:** `/api/portfolio`

**Method:** `GET`

**Description:** Retrieves the current portfolio of stocks for the authenticated user.

**Request Parameters:**
- None

**Response:**

```json
{
  "stocks": [
    {
      "id": 1,
      "symbol": "AAPL",
      "purchase_price": 150.0,
      "quantity": 10,
      "current_price": 160.0,
      "purchase_value": 1500.0,
      "current_value": 1600.0,
      "profit_loss_amount": 100.0,
      "profit_loss_percentage": 6.67
    }
  ],
  "total_purchase_value": 1500.0,
  "total_current_value": 1600.0,
  "total_profit_loss_amount": 100.0,
  "total_profit_loss_percentage": 6.67,
  "timestamp": "2023-10-01T12:34:56.789Z"
}
```

**Source Provenance:**
- **File:** `stockker/routes/api.py`
- **Lines:** 53-72

---

## Get Stock Details

**Endpoint:** `/api/stock/<stock_id>`

**Method:** `GET`

**Description:** Retrieves details for a specific stock identified by `stock_id`.

**Request Parameters:**
- `stock_id` (path parameter): The unique identifier for the stock.

**Response:**

```json
{
  "id": 1,
  "symbol": "AAPL",
  "purchase_price": 150.0,
  "quantity": 10,
  "current_price": 160.0,
  "purchase_value": 1500.0,
  "current_value": 1600.0,
  "profit_loss_amount": 100.0,
  "profit_loss_percentage": 6.67
}
```

**Source Provenance:**
- **File:** `stockker/routes/api.py`
- **Lines:** 14-22

---

## Save DP Settings

**Endpoint:** `/api/save-dp-settings`

**Method:** `POST`

**Description:** Saves settings related to depository participants.

**Request Parameters:**
- JSON body containing the settings data.

**Response:**

```json
{
  "message": "Settings saved successfully"
}
```

**Source Provenance:**
- **File:** `stockker/routes/api.py`
- **Lines:** 186-197

---

## Sync Portfolio

**Endpoint:** `/api/sync-portfolio`

**Method:** `POST`

**Description:** Synchronizes the user's portfolio with external data sources.

**Request Parameters:**
- JSON body containing synchronization data.

**Response:**

```json
{
  "message": "Portfolio synchronized successfully",
  "last_sync": "2023-10-01T12:34:56.789Z"
}
```

**Source Provenance:**
- **File:** `stockker/routes/api.py`
- **Lines:** 76-182

---

## Update Stock Price

**Endpoint:** `/api/stock/<stock_id>/update-price`

**Method:** `POST`

**Description:** Updates the price of a specific stock identified by `stock_id`.

**Request Parameters:**
- `stock_id` (path parameter): The unique identifier for the stock.
- JSON body containing the new price data.

**Response:**

```json
{
  "message": "Stock price updated successfully",
  "stock": {
    "id": 1,
    "symbol": "AAPL",
    "purchase_price": 150.0,
    "quantity": 10,
    "current_price": 165.0,
    "purchase_value": 1500.0,
    "current_value": 1650.0,
    "profit_loss_amount": 150.0,
    "profit_loss_percentage": 10.0
  }
}
```

**Source Provenance:**
- **File:** `stockker/routes/api.py`
- **Lines:** 26-49
