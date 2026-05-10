import requests
import sqlite3
import uuid
from pprint import pprint
import time

BASE_URL = "http://localhost:8000/api/v1"
DB_PATH = "../db.sqlite3"  # Relative to where we run it (fashionistar_backend)
session = requests.Session()

def get_otp_for_email(email):
    # Connect to SQLite to grab the OTP for testing
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM authentication_unifieduser WHERE email = ?", (email,))
    user_id = cursor.fetchone()[0]
    # In locmem cache we can't easily grab it from external python script because locmem is tied to the Django process.
    # WAIT! The OTP is stored in Django cache... LocMemCache is per-process.
    # To get it, we need to run this script THROUGH django manage.py shell, or we can just write a management command.
    pass

# We will rewrite this file as a Django management command to access the cache directly, 
# or just run it via `manage.py shell -c "..."`
