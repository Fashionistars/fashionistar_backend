import os
import glob

patterns = [
    "*.log",
    "pytest_output*.txt",
    "pytest_failures.log",
    "pytest_order_payment_latest.log",
    "webhook.log",
    "application.log",
    "backend-runserver.log",
    "backend-uvicorn.log",
    "*.sqlite3"
]

backend_dir = "c:\\Users\\FASHIONISTAR\\OneDrive\\Documenti\\FASHIONISTAR_ANTAGRAVITY\\fashionistar_backend"

for pattern in patterns:
    for filepath in glob.glob(os.path.join(backend_dir, pattern)):
        try:
            if os.path.isfile(filepath):
                os.remove(filepath)
                print(f"Deleted: {filepath}")
        except Exception as e:
            print(f"Error deleting {filepath}: {e}")

# also check if static/staticfiles/media are present and delete them if we want to save space, but let's keep them if they are small or ignored.
# Let's check size of static/staticfiles
for d in ["static", "staticfiles", "media"]:
    dirpath = os.path.join(backend_dir, d)
    if os.path.exists(dirpath):
        print(f"Directory {d} exists")
