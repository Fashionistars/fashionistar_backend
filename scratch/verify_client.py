import django
import os
import sys

def main():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.development')
    django.setup()

    from apps.authentication.models import UnifiedUser
    email = 'client.vision.2026@gmail.com'
    user = UnifiedUser.all_objects.filter(email=email).first()
    if user:
        user.is_active = True
        user.is_verified = True
        user.save()
        print(f"Successfully activated and verified {email} in database!")
    else:
        print(f"User {email} not found to verify.")

if __name__ == '__main__':
    main()
