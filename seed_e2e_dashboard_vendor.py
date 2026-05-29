import os
import sys
import django

# Set up Django environment
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.development')
django.setup()

from apps.authentication.models import UnifiedUser
from apps.vendor.models import VendorProfile
from apps.client.models import ClientProfile

def seed_dashboard_vendor():
    # 1. Vendor Account Details
    vendor_email = "vendor.vision.DASHBOARD.2026@gmail.com"
    vendor_password = "VendorTest@2026!"
    
    print(f"Seeding / Ensuring Vendor User: {vendor_email}")
    vendor_user, created = UnifiedUser.objects.get_or_create(
        email=vendor_email,
        defaults={
            "role": "vendor",
            "auth_provider": "email",
            "first_name": "TestVendorDASHBOARD",
            "last_name": "VisionDASHBOARD",
        }
    )
    vendor_user.set_password(vendor_password)
    vendor_user.is_active = True
    vendor_user.is_verified = True
    vendor_user.save()
    
    print(f"Vendor User {'created' if created else 'updated'}.")

    # 2. Vendor Profile Details
    vendor_profile, created_profile = VendorProfile.objects.get_or_create(
        user=vendor_user,
        defaults={
            "store_name": "Adaeze Couture",
            "city": "Lagos",
            "state": "Lagos",
            "country": "Nigeria",
            "address": "10 Kingsway Road",
            "is_active": True,
            "is_verified": True
        }
    )
    if not created_profile:
        vendor_profile.store_name = "Adaeze Couture"
        vendor_profile.city = "Lagos"
        vendor_profile.state = "Lagos"
        vendor_profile.country = "Nigeria"
        vendor_profile.address = "10 Kingsway Road"
        vendor_profile.is_active = True
        vendor_profile.is_verified = True
        vendor_profile.save()
        
    print(f"Vendor Profile {'created' if created_profile else 'updated'}.")
    
    # 3. Align Admin Account
    admin_email = "admin@fashionistar.io"
    admin_password = "FashionAdmin2026!"
    print(f"Aligning Admin User: {admin_email}")
    try:
        admin_user = UnifiedUser.objects.get(email=admin_email)
        admin_user.set_password(admin_password)
        admin_user.is_active = True
        admin_user.is_verified = True
        admin_user.save()
        print("Admin account password aligned.")
    except UnifiedUser.DoesNotExist:
        # Create admin
        admin_user = UnifiedUser.objects.create_superuser(
            email=admin_email,
            password=admin_password,
            role="admin",
            first_name="Fashion",
            last_name="Admin",
            is_active=True,
            is_verified=True
        )
        print("Admin account created.")
        
    # 4. Align Client Account
    client_email = "client.vision.2026@gmail.com"
    client_password = "ClientTest@2026!"
    print(f"Aligning Client User: {client_email}")
    client_user, created_client = UnifiedUser.objects.get_or_create(
        email=client_email,
        defaults={
            "role": "client",
            "auth_provider": "email",
            "first_name": "Chidi",
            "last_name": "Client",
        }
    )
    client_user.set_password(client_password)
    client_user.is_active = True
    client_user.is_verified = True
    client_user.save()
    
    client_profile = ClientProfile.get_or_create_for_user(client_user)
    client_profile.default_shipping_address = "10 Kingsway Road, Ikoyi, Lagos"
    client_profile.state = "Lagos"
    client_profile.country = "Nigeria"
    client_profile.is_profile_complete = True
    client_profile.save()
    print(f"Client account {'created' if created_client else 'updated'}.")

    print("Success: E2E Verification Accounts seeded successfully!")

if __name__ == "__main__":
    seed_dashboard_vendor()
