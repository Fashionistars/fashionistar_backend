import os
import ast

def check_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            content = f.read()
            tree = ast.parse(content)
        except Exception:
            return
            
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'format_html':
                # Check if total arguments (args + kwargs) is less than 2
                # format_html(format_string, *args, **kwargs)
                # If there are no args and kwargs, then len(node.args) == 1 and len(node.keywords) == 0
                if len(node.args) == 1 and len(node.keywords) == 0:
                    print(f"File: {filepath}, Line: {node.lineno}")
                    # Print the line content
                    lines = content.splitlines()
                    if node.lineno - 1 < len(lines):
                        print(f"  Code: {lines[node.lineno - 1].strip()}")

def main():
    apps_dir = r"C:\Users\FASHIONISTAR\OneDrive\Documenti\FASHIONISTAR_ANTAGRAVITY\fashionistar_backend\apps"
    for root, dirs, files in os.walk(apps_dir):
        for file in files:
            if file.endswith('.py'):
                check_file(os.path.join(root, file))

if __name__ == '__main__':
    main()
