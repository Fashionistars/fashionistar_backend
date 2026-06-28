import django
import os
import sys

def main():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.development')
    django.setup()

    from apps.authentication.models import UnifiedUser
    from django.apps import apps

    email = 'client.vision.2026@gmail.com'
    user = UnifiedUser.all_objects.filter(email=email).first()

    if not user:
        print(f"User {email} not found. Nothing to delete.")
        return

    print(f"Found user: {user.email} (ID: {user.id})")

    # Keep a set of models we processed to avoid infinite recursion or duplicate logs
    processed_models = set()

    # Step 1: Force delete relations that might have PROTECT or CASCADE
    # We will do multiple passes to make sure we catch cascading protection.
    for i in range(5):
        print(f"Pass {i+1} of cleaning relations...")
        deleted_any = False
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if field.is_relation and field.related_model == UnifiedUser:
                    filter_kwargs = {field.name: user}
                    try:
                        # Try standard objects first
                        qs = model.objects.filter(**filter_kwargs)
                        if qs.exists():
                            print(f"Deleting {qs.count()} instances from {model.__name__} (via field: {field.name})")
                            qs.delete()
                            deleted_any = True
                    except Exception:
                        # Fallback to all_objects if available
                        try:
                            if hasattr(model, 'all_objects'):
                                qs = model.all_objects.filter(**filter_kwargs)
                                if qs.exists():
                                    print(f"Deleting {qs.count()} instances from {model.__name__} via all_objects")
                                    qs.delete()
                                    deleted_any = True
                        except Exception as e2:
                            print(f"Could not delete from {model.__name__}: {e2}")
        if not deleted_any:
            print("No more relations found to delete.")
            break

    # Step 2: Delete sessions specifically
    try:
        from apps.authentication.models import UserSession
        UserSession.objects.filter(user=user).delete()
        print("Sessions cleaned up.")
    except Exception as e:
        print(f"Error cleaning sessions: {e}")

    # Step 3: Delete user
    try:
        user.delete()
        print(f"Successfully deleted user {email}!")
    except Exception as e:
        print(f"Failed to delete user {email}: {e}")
        # Let's try raw delete as last resort
        try:
            print("Attempting raw delete on UnifiedUser...")
            UnifiedUser.all_objects.filter(email=email)._raw_delete(UnifiedUser._state.db)
            print(f"Successfully RAW deleted user {email}!")
        except Exception as e2:
            print(f"Raw delete also failed: {e2}")

if __name__ == '__main__':
    main()
