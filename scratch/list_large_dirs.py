import os

def list_dirs(start_path):
    print(f"Scanning {start_path}...")
    for root, dirs, files in os.walk(start_path):
        # ignore common things manually in print to see what remains
        if any(p in root for p in [".venv", ".git", ".pytest_cache", ".uv-cache", "__pycache__"]):
            continue
        if len(files) > 10:
            print(f"{root}: {len(files)} files, {len(dirs)} subdirs")

list_dirs("c:\\Users\\FASHIONISTAR\\OneDrive\\Documenti\\FASHIONISTAR_ANTAGRAVITY\\fashionistar_backend")
