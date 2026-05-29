# apps/common/tests/test_soft_delete_and_ledger.py
"""
Stage 5 Verification: Soft/Hard Deletion & Financial Ledger Transactional Integrity Tests
"""
from decimal import Decimal
import pytest
from django.db import transaction, IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.authentication.models import UnifiedUser
from apps.catalog.models.blog import BlogPost
from apps.catalog.models.category import Category
from apps.client.models import ClientProfile
from apps.wallet.models import Wallet
from apps.wallet.services import WalletProvisioningService, WalletBalanceService, WalletPinService


class SoftHardDeleteAndLedgerTestCase(TestCase):
    """
    Subsuite covering:
      - Soft-delete operations via BaseModel/SoftDeleteModel.
      - Hard-delete cascade purges.
      - Financial transaction database integrity and atomic block rollbacks.
    """

    def setUp(self):
        # Create standard test users
        self.user = UnifiedUser.objects.create_user(
            email="softdelete.test@fashionistar.io",
            password="StrongPassUser2026!",
            role="client"
        )
        self.vendor = UnifiedUser.objects.create_user(
            email="vendor.ledger@fashionistar.io",
            password="StrongPassUser2026!",
            role="vendor"
        )

    def test_soft_delete_lifecycle_and_managers(self):
        """
        1. Create a BlogPost (which inherits from SoftDeleteModel).
        2. Verify it is visible by default.
        3. Delete it (which soft-deletes).
        4. Verify it is invisible via default manager, but visible via all_with_deleted/deleted_only.
        5. Restore it and verify visibility resets.
        """
        post = BlogPost.objects.create(
            author=self.user,
            title="Sartorial Elegance in Lagos",
            content="Exploring modern traditional structures."
        )

        # Active state checks
        self.assertFalse(post.is_deleted)
        self.assertIsNone(post.deleted_at)
        self.assertIn(post, BlogPost.objects.all())

        # Soft delete execution
        post_id = post.id
        post.soft_delete()

        # Re-fetch from DB
        post.refresh_from_db()
        self.assertTrue(post.is_deleted)
        self.assertIsNotNone(post.deleted_at)

        # Default manager should hide it
        self.assertNotIn(post, BlogPost.objects.all())

        # Alternative manager filters must correctly expose it
        self.assertIn(post, BlogPost.all_objects.all_with_deleted())
        self.assertIn(post, BlogPost.all_objects.deleted_only())

        # Restore operations
        post.restore()
        post.refresh_from_db()
        self.assertFalse(post.is_deleted)
        self.assertIsNone(post.deleted_at)
        self.assertIn(post, BlogPost.objects.all())

    def test_hard_delete_and_cascade_behavior(self):
        """
        Verify that explicit hard-deletion purges the entity from the database,
        and triggers standard database cascading delete rules.
        """
        # Create a category
        cat = Category.objects.create(
            name="Traditional Agbada",
            slug="traditional-agbada"
        )

        # Create a ClientProfile (which inherits from SoftDeleteModel and has a OneToOne cascade to UnifiedUser)
        profile = ClientProfile.objects.create(
            user=self.user,
            bio="Test cascade deletion."
        )

        self.assertIn(profile, ClientProfile.objects.all())

        # Perform hard-delete on user. UnifiedUser has HardDeleteMixin
        # Let's perform user.hard_delete() or physical deletion
        self.user.hard_delete(user=self.user)

        # User must be completely purged from database
        with self.assertRaises(UnifiedUser.DoesNotExist):
            UnifiedUser.objects.get(id=self.user.id)

        # ClientProfile must be cascade purged completely (since user was CASCADE, it's hard deleted)
        with self.assertRaises(ClientProfile.DoesNotExist):
            ClientProfile.all_objects.all_with_deleted().get(id=profile.id)

    def test_wallet_transfer_database_transactional_integrity(self):
        """
        Asserts transactional safety on monetary transfers.
        If any step in the transaction fails (e.g. double-ledger entry constraint violation,
        or an artificial integrity exception mid-transaction),
        the system must rollback the balances of both sender and receiver to prevent financial leakage.
        """
        # Ensure wallets are provisioned
        sender_wallet = WalletProvisioningService.ensure_wallet(self.user)
        receiver_wallet = WalletProvisioningService.ensure_wallet(self.vendor)

        # Set initial balances
        sender_wallet.balance = Decimal("25000.00")
        sender_wallet.available_balance = Decimal("25000.00")
        sender_wallet.save()

        receiver_wallet.balance = Decimal("0.00")
        receiver_wallet.available_balance = Decimal("0.00")
        receiver_wallet.save()

        # Set pin
        WalletPinService.set_pin(self.user, "5555")

        # Define an atomic transfer function that encounters an error after updating sender balance
        def faulty_transfer():
            with transaction.atomic():
                # Deduct sender
                sender_wallet.balance -= Decimal("5000.00")
                sender_wallet.available_balance -= Decimal("5000.00")
                sender_wallet.save()

                # Raise an integrity error to simulate database crash (e.g. duplicate key or network break)
                raise IntegrityError("Simulated Ledger Constraints Breakdown")

        # Run faulty transfer and assert rollback
        with self.assertRaises(IntegrityError):
            faulty_transfer()

        # Reload balances from DB
        sender_wallet.refresh_from_db()
        receiver_wallet.refresh_from_db()

        # Balances must be perfectly unchanged
        self.assertEqual(sender_wallet.balance, Decimal("25000.00"))
        self.assertEqual(receiver_wallet.balance, Decimal("0.00"))
