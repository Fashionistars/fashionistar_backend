import os

backend_dir = "c:\\Users\\FASHIONISTAR\\OneDrive\\Documenti\\FASHIONISTAR_ANTAGRAVITY\\fashionistar_backend"
files = os.listdir(backend_dir)
print(f"Total items in dir: {len(files)}")

large_files = [
    "application.log",
    "webhook.log",
    "pytest_order_payment_latest.log",
    "backend-runserver.log",
    "backend-uvicorn.log",
    "pytest_output.txt",
    "pytest_output_nocolor.txt",
    "pytest_failures.log"
]

for name in files:
    if name in large_files or name.endswith(".log") or (name.startswith("pytest_output") and name.endswith(".txt")):
        filepath = os.path.join(backend_dir, name)
        if os.path.isfile(filepath):
            size = os.path.getsize(filepath)
            print(f"Found match: {name} ({size} bytes)")
            try:
                os.remove(filepath)
                print(f"Successfully deleted {name}")
            except Exception as e:
                print(f"Error deleting {name}: {e}")
                # If file is locked, try to truncate it to 0 bytes!
                try:
                    with open(filepath, "w") as f:
                        f.truncate(0)
                    print(f"Successfully truncated {name} to 0 bytes")
                except Exception as ex:
                    print(f"Failed to truncate {name}: {ex}")
