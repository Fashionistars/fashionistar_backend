from django.contrib.auth import get_user_model
from django.test import TestCase
from .models import Vendor
from store.models import Product
from rest_framework.test import APIClient

User = get_user_model()

class VendorStoreViewTest(TestCase):
    def setUp(self):
        # Create a user and a vendor
        self.user = User.objects.create_user(
            email='vendoruser@example.com',
            phone='+2347082190857',
            password='password123',
            role=User.VENDOR
        )
        self.vendor = Vendor.objects.create(user=self.user)

        # Create some products for this vendor
        self.product1 = Product.objects.create(
            sku='SKU12345', vendor=self.vendor, title='Product 1', price=100.00
        )
        self.product2 = Product.objects.create(
            sku='SKU67890', vendor=self.vendor, title='Product 2', price=200.00
        )

        self.client = APIClient()
    
    def test_get_vendor_store_products(self):
        response = self.client.get(f'/vendor/{self.vendor.id}/store/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['title'], 'Product 1')
        self.assertEqual(response.data[1]['title'], 'Product 2')