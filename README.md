<<<<<<< HEAD
# DRF Project

This is a Django REST Framework project.

## Getting Started

Follow these instructions to get a copy of the project up and running on your local machine for development and testing purposes.

## Installation

### Prerequisites

Ensure you have the following installed on your machine:

- Python 3.x
- pip (Python package installer)
- Git

### Clone the Repository

First, clone the repository to your local machine:

```bash
https://github.com/Fashionistars/fashionistar_backend.git
cd fashionistar_backend
```
### Create a Virtual Environment

###### It's recommended to use a virtual environment to manage your project's dependencies. You can create one using venv:

```bash
python -m venv venv
```
* Activate the Virtual Environment
Activate the virtual environment by running the appropriate command for your operating system:

- Windows:
```bash
venv\Scripts\activate
```
- macOS/Linux:
```bash
source venv/bin/activate
```
### Install Dependencies
With the virtual environment activated, install the project dependencies listed in requirements.txt:

```bash
pip install -r requirements.txt
```
### Set Up the Database
Apply the database migrations to set up the database schema: Default to sqlite

```bash
python manage.py makemigrations
```

```bash
python manage.py migrate
```

### Collect Static Files

```bash
python manage.py collectstatic
```
### Running the Project
Start the development server:

```bash
python manage.py runserver
```
 The project will be accessible at http://127.0.0.1:8000/ by default.
=======

# fashionistar_backend
>>>>>>> 0b0d902 (Update README.md)
