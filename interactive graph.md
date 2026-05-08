# 🌐 Interactive Code Graph (Documentation Feature)

## Overview
An interactive visualization of the codebase that helps developers understand structure, relationships, and the impact of changes in real time.

> The graph is not just a visualization — it is a navigable interface to explore documentation and understand system behavior.

---

## Purpose
- Provide a high-level understanding of the codebase
- Enable navigation between components and their documentation
- Visually highlight the impact of code changes (PRs)
- Help developers trace workflows across the system

---

## Graph Structure

### Nodes
Represent key components of the system:
- Services / Modules (primary focus)
- API Endpoints
- (Optional) Key Functions

### Edges
Represent relationships:
- Function calls
- Module imports
- Service interactions
- API → handler mappings

---

## Core Features

### 1. Interactive Navigation
- Click on a node to view:
  - Module documentation
  - API details
  - Related workflows
- Acts as an entry point into the documentation system

---

### 2. PR Impact Visualization (Key Feature)
- Highlight nodes affected by a PR:
  - Changed nodes → Red
  - Indirectly affected nodes → Orange
- Helps answer:
  > “What parts of the system does this change affect?”

---

### 3. View Modes
Switch between different levels of abstraction:
- Service-level view (default)
- API-level view
- (Optional) Function-level view

---

### 4. Workflow Tracing
- Select a workflow (e.g., Login, Payment)
- Graph highlights the flow path across components

Example:
Client → API → Auth Service → Database

---

## Data Model

```json
{
  "nodes": [
    { "id": "api", "type": "service" },
    { "id": "auth", "type": "service" },
    { "id": "login", "type": "endpoint" }
  ],
  "edges": [
    { "from": "api", "to": "auth" },
    { "from": "login", "to": "auth" }
  ]
}