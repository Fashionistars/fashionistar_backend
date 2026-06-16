# apps/product/tests/test_draft_session.py
import uuid
import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.product.models import ProductDraftSession, ProductDraftStatus, Product
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def vendor_user(db):
    user = User.objects.create_user(
        email="vendor_test_draft@fashionistar.com",
        password="VendorPassword123!",
        role="vendor",
        is_verified=True,
        is_active=True,
    )
    
    from apps.vendor.models import VendorProfile
    VendorProfile.objects.create(
        user=user,
        store_name="Adaeze Test Shop",
        store_slug="adaeze-test-shop",
    )
    return user

@pytest.fixture
def other_vendor_user(db):
    user = User.objects.create_user(
        email="other_vendor@fashionistar.com",
        password="VendorPassword123!",
        role="vendor",
        is_verified=True,
        is_active=True,
    )
    from apps.vendor.models import VendorProfile
    VendorProfile.objects.create(
        user=user,
        store_name="Other Shop",
        store_slug="other-shop",
    )
    return user

@pytest.fixture
def category(db):
    from apps.catalog.models import Category
    return Category.objects.create(name="Accessories", slug="accessories")

@pytest.mark.django_db
class TestProductDraftSessionAPI:
    def test_draft_lifecycle(self, api_client, vendor_user, category):
        # Authenticate via DRF force_authenticate
        api_client.force_authenticate(user=vendor_user)
        
        # 1. Create a draft
        url_list = reverse("product:vendor-product-draft-list")
        draft_key = str(uuid.uuid4())
        idempotency_key = str(uuid.uuid4())
        payload = {
            "title": "Uncommitted Draft Agbada",
            "description": "This is a very long description that satisfies the length validation of 20 chars.",
            "price": "55000.00",
            "category_ids": [str(category.id)],
            "sub_category_ids": [],
            "stock_qty": 10,
        }
        
        response = api_client.post(
            url_list,
            {
                "draft_key": draft_key,
                "idempotency_key": idempotency_key,
                "payload": payload,
                "current_step": 2,
            },
            format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        data = response.json()
        assert data["data"]["draft_key"] == draft_key
        assert data["data"]["current_step"] == 2
        
        # 2. List drafts (Ninja async endpoint)
        token = str(AccessToken.for_user(vendor_user))
        response = api_client.get(
            "/api/v1/ninja/products/vendor/drafts/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 200, response.content
        drafts = response.json()
        assert len(drafts) >= 1
        assert drafts[0]["draft_key"] == draft_key
        
        # 3. Retrieve draft detail (Ninja async endpoint)
        response = api_client.get(
            f"/api/v1/ninja/products/vendor/drafts/{draft_key}/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 200, response.content
        assert response.json()["payload"]["title"] == "Uncommitted Draft Agbada"
        
        # 4. Update the draft (DRF sync endpoint)
        url_detail = reverse("product:vendor-product-draft-detail", kwargs={"draft_key": draft_key})
        updated_payload = payload.copy()
        updated_payload["title"] = "Updated Draft Agbada"
        response = api_client.patch(
            url_detail,
            {
                "payload": updated_payload,
                "current_step": 3,
            },
            format="json"
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.json()["data"]["payload"]["title"] == "Updated Draft Agbada"
        assert response.json()["data"]["current_step"] == 3
        
        # 5. Commit the draft to a full product (DRF sync endpoint)
        url_commit = reverse("product:vendor-product-draft-commit", kwargs={"draft_key": draft_key})
        response = api_client.post(url_commit)
        assert response.status_code == status.HTTP_200_OK, response.data
        
        # Verify product was created
        product_slug = response.json()["data"]["slug"]
        product = Product.objects.get(slug=product_slug)
        assert product.title == "Updated Draft Agbada"
        assert product.price == Decimal("55000.00")
        assert product.vendor == vendor_user.vendor_profile
        
        # Check draft session status is now COMMITTED
        draft_session = ProductDraftSession.all_objects.get(draft_key=draft_key)
        assert draft_session.status == ProductDraftStatus.COMMITTED
        assert draft_session.linked_product == product

    def test_discard_draft(self, api_client, vendor_user, category):
        api_client.force_authenticate(user=vendor_user)
        url_list = reverse("product:vendor-product-draft-list")
        
        draft_key = str(uuid.uuid4())
        payload = {
            "title": "To Be Discarded",
            "description": "Short but valid description 20 chars",
            "price": "10000.00",
            "category_ids": [str(category.id)],
        }
        api_client.post(
            url_list,
            {"draft_key": draft_key, "payload": payload},
            format="json"
        )
        
        url_detail = reverse("product:vendor-product-draft-detail", kwargs={"draft_key": draft_key})
        response = api_client.delete(url_detail)
        assert response.status_code == status.HTTP_200_OK
        
        # Verify database record soft-deleted or status set to discarded
        draft_session = ProductDraftSession.all_objects.get(draft_key=draft_key)
        assert draft_session.status == ProductDraftStatus.DISCARDED
        assert draft_session.is_deleted is True  # SoftDeleteModel field is_deleted

    def test_draft_key_collision(self, api_client, vendor_user, other_vendor_user, category):
        # 1. Create a draft as first vendor
        api_client.force_authenticate(user=vendor_user)
        url_list = reverse("product:vendor-product-draft-list")
        draft_key = str(uuid.uuid4())
        payload = {
            "title": "Vendor 1 Draft",
            "description": "Short but valid description 20 chars",
            "price": "10000.00",
            "category_ids": [str(category.id)],
        }
        response = api_client.post(
            url_list,
            {"draft_key": draft_key, "payload": payload},
            format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        
        # 2. Try to create a draft with same key as first vendor (should update/reuse and return 201)
        payload["title"] = "Vendor 1 Draft Updated"
        response2 = api_client.post(
            url_list,
            {"draft_key": draft_key, "payload": payload},
            format="json"
        )
        assert response2.status_code == status.HTTP_201_CREATED
        assert response2.json()["data"]["payload"]["title"] == "Vendor 1 Draft Updated"
        
        # 3. Authenticate as other vendor and try to use same key (should fail with 400)
        api_client.force_authenticate(user=other_vendor_user)
        response3 = api_client.post(
            url_list,
            {"draft_key": draft_key, "payload": payload},
            format="json"
        )
        assert response3.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists for another vendor" in response3.json()["message"]

    def test_draft_commit_with_large_shipping_and_gender_alias(self, api_client, vendor_user, category):
        api_client.force_authenticate(user=vendor_user)
        url_list = reverse("product:vendor-product-draft-list")
        draft_key = str(uuid.uuid4())
        payload = {
            "title": "Large Shipping & Gender Alias Draft",
            "description": "Short but valid description 20 chars",
            "price": "10000.00",
            "category_ids": [str(category.id)],
            "gender_target": "male",
            "shipping_amount": "250000000.00",
        }
        response = api_client.post(
            url_list,
            {"draft_key": draft_key, "payload": payload},
            format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Commit draft
        url_commit = reverse("product:vendor-product-draft-commit", kwargs={"draft_key": draft_key})
        response_commit = api_client.post(url_commit)
        assert response_commit.status_code == status.HTTP_200_OK, response_commit.data

        product_slug = response_commit.json()["data"]["slug"]
        product = Product.objects.get(slug=product_slug)
        assert product.gender_target == "men"
        assert product.shipping_amount == Decimal("250000000.00")

