import os
import sys
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.development')
django.setup()

from django.contrib import admin

print("Checking all registered ModelAdmins...")

for model, model_admin in admin.site._registry.items():
    try:
        print(f"Checking {model._meta.label} with {model_admin.__class__.__name__}...", end=" ")
        errors = model_admin.check()
        if errors:
            print(f"FAILED (found {len(errors)} issues)")
        else:
            print("OK")
    except Exception as e:
        print(f"CRASHED: {e}")
        import traceback
        traceback.print_exc()
        # We don't exit here, we want to see if multiple crash or just one
