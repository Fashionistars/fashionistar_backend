# FASHIONISTAR AI — Backend

> Enterprise-Grade eCommerce Backend · Django 6.0 · Python 3.12+ · Dual-Engine API (DRF + Ninja)

## Getting Started

Follow these instructions to get a copy of the project up and running on your local machine for development and testing purposes.

## Prerequisites

Ensure you have the following installed on your machine:

- Python 3.12+
- pip (Python package installer)
- Git
- Redis (for caching and background tasks)
- PostgreSQL 14+ (production) or SQLite (local dev)

## Installation

### Clone the Repository

```bash
git clone https://github.com/Fashionistars/fashionistar_backend.git
cd fashionistar_backend
```

### Create a Virtual Environment

It's recommended to use a virtual environment to manage your project's dependencies:

```bash
python -m venv venv
```

Activate the virtual environment:

- **Windows:**
  ```bash
  venv\Scripts\activate
  ```
- **macOS/Linux:**
  ```bash
  source venv/bin/activate
  ```

### Install Dependencies

With the virtual environment activated, install the project dependencies:

```bash
pip install -r requirements.txt
```

### Environment Variables

Copy the example environment file and fill in your secrets:

```bash
cp .env.example .env
```

### Set Up the Database

Apply the database migrations to set up the database schema:

```bash
python manage.py makemigrations
python manage.py migrate
```

### Collect Static Files

```bash
python manage.py collectstatic
```

## Running the Project

Start the development server:

```bash
python manage.py runserver
```

The project will be accessible at `http://127.0.0.1:8000/` by default.

## Architecture

See [`AGENT_PLAN.MD`](../AGENT_PLAN.MD) and [`BACKEND_ARCHITECTURE_JAN_2026.MD`](BACKEND_ARCHITECTURE_JAN_2026.MD) for the full architectural blueprint.

## License

Proprietary — Fashionistar AI © 2024–2026
