---
artifact_id: "82eca0eae6f06a2a"
category: "function"
name: "Creating the Application"
source_files: ["stockker/__init__.py"]
source_lines: {"stockker/__init__.py": [19, 36]}
generated_at: "2026-05-06T04:16:16.612192+00:00"
repo_sha: "main"
content_hash: "2c844b6ef0c0ae2f0fdac79c44ebadd9e7c917bf84b831d61a5c0a1007e86348"
---
# Creating the Application

## Overview

This guide provides step-by-step instructions on how to create and configure the main application instance using Flask, Pydantic, SQLAlchemy, and other related frameworks.

## Step-by-Step Instructions

### Step 1: Import Necessary Modules

Start by importing the required modules and classes from Flask, SQLAlchemy, and other libraries.

```python
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
```

### Step 2: Initialize Application Components

Initialize the Flask app, SQLAlchemy, and LoginManager instances.

```python
app = Flask(__name__)
db = SQLAlchemy()
login_manager = LoginManager()
```

### Step 3: Configure the Application

Load the configuration settings from an object. This object typically contains settings such as `DATABASE_URL`, `SECRET_KEY`, and others.

```python
app.config.from_object('stockker.config.Config')
```

### Step 4: Register Blueprints

Register any blueprints that your application uses. Blueprints help organize your application into components.

```python
# Example of registering a blueprint
# from stockker.routes.api import api_bp
# app.register_blueprint(api_bp)
```

### Step 5: Initialize Extensions

Initialize the SQLAlchemy and LoginManager extensions with the Flask app.

```python
db.init_app(app)
login_manager.init_app(app)
```

### Step 6: Define User Loader Callback

Define a user loader callback for the LoginManager. This function is used to reload the user object from the user ID stored in the session.

```python
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
```

### Step 7: Create the Application Instance

Finally, create the application instance by calling the `create_app` function.

```python
def create_app():
    app = Flask(__name__)
    app.config.from_object('stockker.config.Config')
    
    db.init_app(app)
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
    
    # Register blueprints here
    # app.register_blueprint(api_bp)
    
    return app
```

## Source Provenance

- **Source File**: `stockker/__init__.py`
- **Source Lines**: 19-36
- **Function Signature**: `def create_app()`
- **Artifact ID**: `82eca0eae6f06a2a`
