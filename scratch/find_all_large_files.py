import os

backend_dir = "c:\\Users\\FASHIONISTAR\\OneDrive\\Documenti\\FASHIONISTAR_ANTAGRAVITY\\fashionistar_backend"
print("Scanning for files over 1MB...")

for root, dirs, files in os.walk(backend_dir):
    # Skip .venv to avoid scanning thousands of files if not needed, or scan it just in case?
    # Actually let's NOT skip .venv, let's see if there are large files there too.
    # But wait, scanning .venv might take a second. That's fine.
    for name in files:
        filepath = os.path.join(root, name)
        try:
            size = os.path.getsize(filepath)
            if size > 1024 * 1024: # > 1MB
                print(f"{filepath} : {size / (1024*1024):.2f} MB")
                # Attempt to delete or truncate it!
                if ".venv" not in filepath and ".git" not in filepath:
                    try:
                        os.remove(filepath)
                        print(f"--> Deleted {name}")
                    except Exception as e:
                        print(f"--> Error deleting {name}: {e}")
                        try:
                            with open(filepath, "w") as f:
                                f.truncate(0)
                            print(f"--> Truncated {name} to 0 bytes")
                        except Exception as ex:
                            print(f"--> Failed to truncate {name}: {ex}")
        except Exception:
            pass
