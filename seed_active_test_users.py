import os
import sys
import django
import json

# Add current file directory to python path for importing Django modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

print("Current Dir:", current_dir)
print("Files in Current Dir:", os.listdir(current_dir))
print("sys.path:", sys.path)

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.development')
django.setup()

from apps.authentication.models import UnifiedUser
from apps.vendor.models import VendorProfile
from apps.client.models import ClientProfile

def seed_users():
    # Load emails
    email_file_path = r"c:\Users\FASHIONISTAR\OneDrive\Documenti\FASHIONISTAR_ANTAGRAVITY\fashionista_frontend\tests\e2e\.tmp\active-test-emails.json"
    
    if not os.path.exists(email_file_path):
        print(f"Error: active-test-emails.json not found at {email_file_path}")
        return
        
    with open(email_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    client_email = data.get("clientEmail")
    vendor_email = data.get("vendorEmail")
    
    password = "FashionTestUser2026!"
    
    print(f"Seeding Client Email: {client_email}")
    print(f"Seeding Vendor Email: {vendor_email}")
    
    # 1. Seed Client
    client_user, created = UnifiedUser.objects.get_or_create(
        email=client_email,
        defaults={
            "role": "client",
            "auth_provider": "email",
            "first_name": "Chidi",
            "last_name": "Client",
        }
    )
    client_user.set_password(password)
    client_user.is_active = True
    client_user.is_verified = True
    client_user.save()
    
    client_profile = ClientProfile.get_or_create_for_user(client_user)
    client_profile.default_shipping_address = "10 Kingsway Road, Ikoyi, Lagos"
    client_profile.state = "Lagos"
    client_profile.country = "Nigeria"
    client_profile.preferred_size = "XL"
    client_profile.style_preferences = ["casual", "afrocentric"]
    client_profile.is_profile_complete = True
    client_profile.save()
    
    print(f"Client user {'created' if created else 'updated'} & activated.")

    # 2. Seed Vendor
    vendor_user, created = UnifiedUser.objects.get_or_create(
        email=vendor_email,
        defaults={
            "role": "vendor",
            "auth_provider": "email",
            "first_name": "Amara",
            "last_name": "Vendor",
        }
    )
    vendor_user.set_password(password)
    vendor_user.is_active = True
    vendor_user.is_verified = True
    vendor_user.save()
    
    vendor_profile = VendorProfile.get_or_create_for_user(vendor_user)
    vendor_profile.store_name = "Adaeze Couture"
    vendor_profile.city = "Lagos"
    vendor_profile.state = "Lagos"
    vendor_profile.country = "Nigeria"
    vendor_profile.address = "10 Kingsway Road"
    vendor_profile.is_active = True
    vendor_profile.is_verified = True
    vendor_profile.save()
    
    print(f"Vendor user {'created' if created else 'updated'} & activated.")
    print("Seeding complete successfully!")

if __name__ == "__main__":
    seed_users()
