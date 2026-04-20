# Recipe Sharing Platform

## Overview
A full-stack web application for sharing and discovering recipes. Users can browse and search recipes by available ingredients, while approved contributors can upload their own. Built with a Python/Flask backend and an Angular frontend.

## Core Capabilities

- **Authentication & Authorization** — JWT-based stateless authentication. Role-based access control across three tiers: Reader, Uploader, and Admin. Decorator-enforced permissions on all protected server routes.
- **Ingredient-Based Search** — Users input ingredients they have on hand; the server computes a match score for every recipe and returns results sorted by relevance. Recipes below 20% match are filtered out.
- **Recipe Gallery** — Browse all recipes with filtering by type (Dairy, Meat, Parve), and prep time. Sortable by prep time or alphabetically (A-Z).
- **Image Processing Pipeline** — Each uploaded image is automatically processed into three variants (greyscale, rotated, sharpened) using Pillow. All four files are stored server-side and served as a per-recipe gallery.
- **Upload Approval Flow** — Users can request upload permissions. Admins review and approve requests from a dedicated management panel.

## Technology Stack

- **Backend:** Python 3, Flask, SQLAlchemy (ORM), SQLite
- **Frontend:** Angular
- **Security:** Flask-Bcrypt, PyJWT, Flask-CORS
- **Media Processing:** Pillow (PIL)
- **Configuration:** python-dotenv

## Directory Structure

```
.
├── server/
│   ├── app.py               # Entry point and route definitions
│   ├── models.py            # SQLAlchemy ORM models
│   ├── uploads/             # Stored images (original + 3 variants per recipe)
│   ├── instance/
│   │   └── recipes.db       # SQLite database
│   └── .env                 # Environment variables (not committed)
└── client/                  # Angular frontend application
```

## Setup & Installation

**Prerequisites:** Python 3.8+ and pip.

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the server directory:

```
SECRET_KEY=your_secure_randomized_string_here
```

3. Run the server:

```bash
python app.py
```

On first run, the database schema is created automatically and a default admin account is provisioned.

## Default Admin Account

- **Email:** admin@example.com
- **Password:** Admin123!

Change these credentials before any non-development deployment.

## API Reference

**Authentication**
- `POST /register` — Register a new user account.
- `POST /login` — Authenticate and receive a JWT.

**Recipes**
- `GET /recipes` — Retrieve all recipes (summary view).
- `GET /recipes/<id>` — Retrieve full recipe details including image variants.
- `POST /recipes` — Add a new recipe with image upload *(Uploader / Admin only)*.
- `DELETE /recipes/<id>` — Delete a recipe and its associated files *(Admin only)*.

**Search**
- `POST /search/ingredients` — Search recipes by ingredient list; returns scored, sorted results.

**Admin**
- `GET /admin/requests` — View pending uploader permission requests *(Admin only)*.
- `POST /admin/requests` — Approve a user's upload request *(Admin only)*.
- `POST /request-upload-permission` — Submit a permission request *(authenticated users)*.
