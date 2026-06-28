# apps/client/tests/test_client_selectors.py
"""
Enterprise Test Suite — Client Domain Selectors & Model DB Methods.

5-Tier Testing Coverage:
  Tier 1  — Unit: sync selectors + model DB classmethods
  Tier 1b — Unit: async selectors via async_to_sync wrapper
  Tier 2  — Integration: reverse FK traversal correctness
  Tier 3  — Concurrency: race conditions + idempotency (PostgreSQL only)
  Tier 4  — Atomic: transaction.atomic() block validation
  Tier 5  — N+1 Boundary: assertNumQueries guards

Testing Principles:
  ─ Race conditions: ThreadPoolExecutor (PostgreSQL), skipped on SQLite
  ─ Idempotency: same operation called N times → same result
  ─ Concurrency: Thread pool executor for sync multi-threaded tests
  ─ transaction.atomic: assertRaises + rollback coverage
  ─ Async selectors: tested via asgiref.sync.async_to_sync wrapper
    (no pytest-asyncio dependency required)
"""
from __future__ import annotations

from asgiref.sync import async_to_sync
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.db import connection
from django.test import TestCase, TransactionTestCase

from apps.authentication.models import UnifiedUser
from apps.client.models import ClientAddress, ClientProfile
from apps.client.selectors.client_selectors import (
    aget_client_address_list,
    aget_client_dashboard_snapshot,
    aget_client_order_stats,
    aget_client_profile_or_none,
    get_client_address_list,
    get_client_dashboard_snapshot,
    get_client_order_stats,
    get_client_profile_or_none,
    get_client_stats,
)


# ── Detect database engine ─────────────────────────────────────────────────
def _is_sqlite() -> bool:
    """Return True if the test DB is SQLite (concurrent writes not supported)."""
    return connection.vendor == "sqlite"


# ── Fixtures ───────────────────────────────────────────────────────────────

def make_user(email: str = "test@fashionistar.test") -> UnifiedUser:
    """Create a client UnifiedUser for testing."""
    return UnifiedUser.objects.create_user(
        email=email,
        password="TestPass123!",
        role="client",
    )


def make_profile(user: UnifiedUser) -> ClientProfile:
    """Create a ClientProfile for user."""
    return ClientProfile.objects.create(
        user=user,
        preferred_size="M",
        default_shipping_address="123 Test St, Lagos",
        style_preferences=["casual", "afrocentric"],
        state="Lagos",
        country="Nigeria",
    )


def make_address(
    profile: ClientProfile,
    is_default: bool = False,
    label: str = "Home",
) -> ClientAddress:
    """Create a ClientAddress for a profile."""
    return ClientAddress.objects.create(
        client=profile,
        label=label,
        full_name="Test Client",
        phone="+2348012345678",
        street_address="123 Test Street, VI",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        postal_code="100001",
        is_default=is_default,
    )


# ══════════════════════════════════════════════════════════════════════
#  TIER 1 — SYNC SELECTOR UNIT TESTS
# ══════════════════════════════════════════════════════════════════════


class TestSyncSelectors(TestCase):
    """Unit tests for all sync client selectors."""

    def setUp(self):
        self.user = make_user("sync_client@fashionistar.test")
        self.profile = make_profile(self.user)

    def test_get_client_profile_or_none_returns_profile(self):
        result = get_client_profile_or_none(self.user)
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.profile.pk)

    def test_get_client_profile_or_none_returns_none_for_no_profile(self):
        new_user = make_user("no_profile@fashionistar.test")
        result = get_client_profile_or_none(new_user)
        self.assertIsNone(result)

    def test_get_client_stats_returns_correct_fields(self):
        stats = get_client_stats(self.user)
        self.assertIn("total_orders", stats)
        self.assertIn("total_spent_ngn", stats)
        self.assertIn("is_profile_complete", stats)
        self.assertIn("preferred_size", stats)
        self.assertEqual(stats["preferred_size"], "M")

    def test_get_client_stats_returns_defaults_for_missing_profile(self):
        new_user = make_user("no_profile2@fashionistar.test")
        stats = get_client_stats(new_user)
        self.assertEqual(stats["total_orders"], 0)

    def test_get_client_address_list_empty_by_default(self):
        result = get_client_address_list(self.user)
        self.assertEqual(result, [])

    def test_get_client_address_list_returns_correct_fields(self):
        make_address(self.profile, is_default=True)
        result = get_client_address_list(self.user)
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertEqual(row["full_name"], "Test Client")
        self.assertEqual(row["street_address"], "123 Test Street, VI")
        self.assertEqual(row["city"], "Lagos")
        self.assertTrue(row["is_default"])

    def test_get_client_address_list_ordered_default_first(self):
        make_address(self.profile, is_default=False, label="Office")
        make_address(self.profile, is_default=True, label="Home")
        result = get_client_address_list(self.user)
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0]["is_default"])

    def test_get_client_dashboard_snapshot_structure(self):
        make_address(self.profile, is_default=True)
        snapshot = get_client_dashboard_snapshot(self.user)
        self.assertIn("profile", snapshot)
        self.assertIn("addresses", snapshot)
        self.assertIn("order_stats", snapshot)
        self.assertIn("wishlist_count", snapshot)
        self.assertEqual(snapshot["profile"]["preferred_size"], "M")
        self.assertEqual(len(snapshot["addresses"]), 1)

    def test_get_client_order_stats_zero_when_no_orders(self):
        stats = get_client_order_stats(self.user)
        self.assertEqual(stats["total_orders"], 0)
        self.assertEqual(stats["total_spent_ngn"], 0.0)
        self.assertEqual(stats["pending_count"], 0)


# ══════════════════════════════════════════════════════════════════════
#  TIER 1b — ASYNC SELECTOR UNIT TESTS (via async_to_sync)
#  No pytest-asyncio dependency — works in standard Django TestCase.
# ══════════════════════════════════════════════════════════════════════


class TestAsyncSelectors(TestCase):
    """Async selector tests using async_to_sync wrapper."""

    def _run(self, coro):
        """Execute a coroutine in the test context using async_to_sync."""
        return async_to_sync(coro)()

    def test_aget_client_profile_or_none_returns_profile(self):
        user = make_user("async_profile@fashionistar.test")
        ClientProfile.objects.create(user=user, preferred_size="L")

        async def _test():
            result = await aget_client_profile_or_none(user)
            return result

        result = async_to_sync(_test)()
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_size, "L")

    def test_aget_client_profile_or_none_returns_none(self):
        user = make_user("async_no_profile@fashionistar.test")

        async def _test():
            return await aget_client_profile_or_none(user)

        result = async_to_sync(_test)()
        self.assertIsNone(result)

    def test_aget_client_address_list_returns_correct_fields(self):
        user = make_user("async_addr@fashionistar.test")
        profile = ClientProfile.objects.create(user=user)
        ClientAddress.objects.create(
            client=profile,
            full_name="Async Client",
            phone="+2348099999999",
            street_address="10 Async Lane",
            city="Abuja",
            state="FCT",
            is_default=True,
        )

        async def _test():
            return await aget_client_address_list(user)

        result = async_to_sync(_test)()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["full_name"], "Async Client")
        self.assertEqual(result[0]["city"], "Abuja")
        self.assertTrue(result[0]["is_default"])

    def test_aget_client_dashboard_snapshot_structure(self):
        user = make_user("async_dash@fashionistar.test")
        ClientProfile.objects.create(user=user, preferred_size="S")

        async def _test():
            return await aget_client_dashboard_snapshot(user)

        snapshot = async_to_sync(_test)()
        self.assertIn("profile", snapshot)
        self.assertIn("addresses", snapshot)
        self.assertIn("order_stats", snapshot)
        self.assertIn("wishlist_count", snapshot)
        self.assertEqual(snapshot["profile"]["preferred_size"], "S")

    def test_aget_client_order_stats_zeros_for_new_client(self):
        user = make_user("async_stats@fashionistar.test")

        async def _test():
            return await aget_client_order_stats(user)

        stats = async_to_sync(_test)()
        self.assertEqual(stats["total_orders"], 0)
        self.assertEqual(stats["pending_count"], 0)


# ══════════════════════════════════════════════════════════════════════
#  TIER 2 — INTEGRATION: REVERSE FK TRAVERSAL CORRECTNESS
# ══════════════════════════════════════════════════════════════════════


class TestReverseFKTraversal(TestCase):
    """
    Verifies that reverse FK accessors work correctly end-to-end.
    These tests confirm the related_name conventions are correct
    across the client, address, and order domains.
    """

    def setUp(self):
        self.user = make_user("fk_test@fashionistar.test")
        self.profile = make_profile(self.user)

    def test_user_client_profile_reverse_onetone(self):
        """user.client_profile → ClientProfile (OneToOne reverse)."""
        accessed = self.user.client_profile
        self.assertEqual(accessed.pk, self.profile.pk)

    def test_profile_client_addresses_reverse_fk(self):
        """profile.client_addresses → ClientAddress queryset (FK reverse)."""
        make_address(self.profile, label="Home")
        make_address(self.profile, label="Office")
        qs = self.profile.client_addresses.filter(is_deleted=False)
        self.assertEqual(qs.count(), 2)
        labels = set(qs.values_list("label", flat=True))
        self.assertIn("Home", labels)
        self.assertIn("Office", labels)

    def test_get_default_for_client_classmethod(self):
        """ClientAddress.get_default_for_client traverses is_default=True."""
        make_address(self.profile, is_default=False, label="Office")
        make_address(self.profile, is_default=True, label="Home")
        default = ClientAddress.get_default_for_client(self.profile)
        self.assertIsNotNone(default)
        self.assertEqual(default.label, "Home")
        self.assertTrue(default.is_default)

    def test_get_list_for_profile_default_first(self):
        """ClientAddress.get_list_for_profile returns default-first ordering."""
        make_address(self.profile, is_default=False, label="Office")
        make_address(self.profile, is_default=True, label="Home")
        rows = ClientAddress.get_list_for_profile(self.profile)
        self.assertEqual(rows[0]["label"], "Home")
        self.assertTrue(rows[0]["is_default"])

    def test_increment_orders_uses_f_expression(self):
        """increment_orders() uses F() — no stale read race."""
        self.profile.increment_orders(amount_ngn=5000)
        self.profile.increment_orders(amount_ngn=3000)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_orders, 2)
        self.assertEqual(self.profile.total_spent_ngn, Decimal("8000.00"))

    def test_update_completeness_sets_flag_correctly(self):
        """update_completeness() sets is_profile_complete based on fields."""
        self.profile.update_completeness()
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_profile_complete)

    def test_update_completeness_clears_flag_when_incomplete(self):
        """update_completeness() clears flag when required fields missing."""
        self.profile.preferred_size = ""
        self.profile.save(update_fields=["preferred_size"])
        self.profile.update_completeness()
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_profile_complete)


# ══════════════════════════════════════════════════════════════════════
#  TIER 3 — CONCURRENCY & IDEMPOTENCY
#  NOTE: ThreadPoolExecutor tests require PostgreSQL.
#        On SQLite these tests are skipped — use the k6 load test
#        against the dev-tunnel for concurrency validation.
# ══════════════════════════════════════════════════════════════════════


class TestIdempotency(TransactionTestCase):
    """
    Idempotency tests — same operation N times → same result.
    Uses TransactionTestCase so real DB transactions are committed
    and visible across threads.
    """

    def test_get_or_create_for_user_is_idempotent_sequential(self):
        """
        ClientProfile.get_or_create_for_user() called 10 times sequentially
        must create exactly ONE profile.
        (SQLite-safe version of the concurrency test.)
        """
        user = make_user("idempotent_profile@fashionistar.test")
        results = [ClientProfile.get_or_create_for_user(user) for _ in range(10)]
        pks = {r.pk for r in results}
        self.assertEqual(len(pks), 1, "Expected exactly 1 ClientProfile PK")
        self.assertEqual(
            ClientProfile.objects.filter(user=user).count(),
            1,
            "Expected exactly 1 ClientProfile row in DB",
        )

    @pytest.mark.skipif(
        _is_sqlite(),
        reason="SQLite does not support concurrent writes — use PostgreSQL for this test",
    )
    def test_get_or_create_for_user_is_idempotent_concurrent(self):
        """
        ClientProfile.get_or_create_for_user() called 10 times concurrently
        must create exactly ONE profile (PostgreSQL only).
        """
        user = make_user("idempotent_concurrent@fashionistar.test")

        def _create():
            return ClientProfile.get_or_create_for_user(user)

        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(_create) for _ in range(10)]
            results = [f.result() for f in futures]

        pks = {r.pk for r in results}
        self.assertEqual(len(pks), 1, "Expected exactly 1 ClientProfile PK")
        self.assertEqual(ClientProfile.objects.filter(user=user).count(), 1)

    def test_set_as_default_is_idempotent_sequential(self):
        """
        ClientAddress.set_as_default() called 3 times sequentially
        must keep exactly ONE default (SQLite-safe version).
        """
        user = make_user("idempotent_default_seq@fashionistar.test")
        profile = make_profile(user)
        addr1 = make_address(profile, is_default=False, label="Home")
        addr2 = make_address(profile, is_default=False, label="Office")
        addr3 = make_address(profile, is_default=False, label="Warehouse")

        ClientAddress.set_as_default(addr1.pk, profile)
        ClientAddress.set_as_default(addr2.pk, profile)
        ClientAddress.set_as_default(addr3.pk, profile)

        defaults = ClientAddress.objects.filter(client=profile, is_default=True)
        self.assertEqual(defaults.count(), 1)
        self.assertEqual(defaults.first().label, "Warehouse")

    @pytest.mark.skipif(
        _is_sqlite(),
        reason="SQLite table locking prevents concurrent writes — use PostgreSQL",
    )
    def test_set_as_default_is_idempotent_concurrent(self):
        """
        ClientAddress.set_as_default() with 3 concurrent calls
        must result in exactly ONE default address (PostgreSQL only).
        """
        user = make_user("idempotent_default_conc@fashionistar.test")
        profile = make_profile(user)
        addr1 = make_address(profile, is_default=False, label="Home")
        addr2 = make_address(profile, is_default=False, label="Office")
        addr3 = make_address(profile, is_default=False, label="Warehouse")

        def _set_default(address_id):
            return ClientAddress.set_as_default(address_id, profile)

        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = [
                ex.submit(_set_default, addr1.pk),
                ex.submit(_set_default, addr2.pk),
                ex.submit(_set_default, addr3.pk),
            ]
            [f.result() for f in futures]

        defaults = ClientAddress.objects.filter(client=profile, is_default=True)
        self.assertEqual(defaults.count(), 1)

    def test_increment_orders_sequential_correctness(self):
        """
        increment_orders() uses F() expression — 10 sequential calls
        must result in total_orders=10 (no lost updates).
        """
        user = make_user("sequential_inc@fashionistar.test")
        profile = make_profile(user)
        profile.total_orders = 0
        profile.total_spent_ngn = Decimal("0.00")
        profile.save()

        for _ in range(10):
            profile.increment_orders(amount_ngn=100)

        profile.refresh_from_db()
        self.assertEqual(profile.total_orders, 10)
        self.assertEqual(profile.total_spent_ngn, Decimal("1000.00"))


# ══════════════════════════════════════════════════════════════════════
#  TIER 4 — transaction.atomic() BLOCK VALIDATION
# ══════════════════════════════════════════════════════════════════════


class TestAtomicBlocks(TransactionTestCase):
    """
    Verifies transaction.atomic() behaviour on critical write paths.
    Uses TransactionTestCase to allow real transaction commits/rollbacks.
    """

    def test_set_as_default_rolls_back_on_invalid_address(self):
        """
        ClientAddress.set_as_default() with a non-existent address_id
        must raise DoesNotExist and roll back — no partial state change.
        """
        user = make_user("atomic_default@fashionistar.test")
        profile = make_profile(user)
        addr = make_address(profile, is_default=True, label="Home")

        with self.assertRaises(ClientAddress.DoesNotExist):
            ClientAddress.set_as_default(address_id=999999, profile=profile)

        # Original default must remain unchanged after rollback
        addr.refresh_from_db()
        self.assertTrue(addr.is_default)

    def test_get_or_create_for_user_is_atomic(self):
        """
        get_or_create_for_user() uses transaction.atomic() + select_for_update().
        Verify the profile returned is always consistent.
        """
        user = make_user("atomic_create@fashionistar.test")
        profile1 = ClientProfile.get_or_create_for_user(user)
        profile2 = ClientProfile.get_or_create_for_user(user)
        self.assertEqual(profile1.pk, profile2.pk)

    def test_address_save_clears_old_default_atomically(self):
        """
        ClientAddress.save() with is_default=True must clear other defaults
        in the same client atomically before creating the new one.
        """
        user = make_user("atomic_addr@fashionistar.test")
        profile = make_profile(user)
        addr1 = make_address(profile, is_default=True, label="Home")
        addr2 = make_address(profile, is_default=False, label="Office")

        addr2.is_default = True
        addr2.save()

        addr1.refresh_from_db()
        addr2.refresh_from_db()

        self.assertFalse(addr1.is_default)
        self.assertTrue(addr2.is_default)
        self.assertEqual(
            ClientAddress.objects.filter(client=profile, is_default=True).count(), 1
        )


# ══════════════════════════════════════════════════════════════════════
#  TIER 5 — N+1 BOUNDARY: assertNumQueries GUARDS
# ══════════════════════════════════════════════════════════════════════


class TestNPlusOneGuards(TestCase):
    """
    N+1 query guards — each selector must execute a predictable,
    bounded number of DB queries regardless of data size.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("n1_guard@fashionistar.test")
        cls.profile = make_profile(cls.user)
        # Create 5 addresses
        for i in range(5):
            make_address(cls.profile, label=f"Addr{i}", is_default=(i == 0))

    def test_get_address_list_single_query(self):
        """get_address_list() must execute exactly 1 joined address query."""
        with self.assertNumQueries(1):
            ClientProfile.get_address_list(self.user)

    def test_get_full_dashboard_snapshot_bounded_queries(self):
        """
        get_full_dashboard_snapshot() executes exactly 7 queries:
          1. ClientProfile.objects.get(user=user)            [select_related]
          2. ClientAddress list query via client__user join  [addresses]
          3. Order aggregate (total_orders, total_spent)     [agg]
          4. Order count — pending_payment                   [count]
          5. Order count — active statuses                   [count]
          6. Order count — completed statuses                [count]
          7. ProductWishlist count                           [count]
        """
        with self.assertNumQueries(7):
            ClientProfile.get_full_dashboard_snapshot(self.user)

    def test_get_stats_for_user_single_query(self):
        """get_stats_for_user() must be exactly 1 query (.values().get())."""
        with self.assertNumQueries(1):
            ClientProfile.get_stats_for_user(self.user)

    def test_get_default_for_client_single_query(self):
        """ClientAddress.get_default_for_client() must be exactly 1 query."""
        with self.assertNumQueries(1):
            ClientAddress.get_default_for_client(self.profile)

    def test_get_list_for_profile_single_query(self):
        """ClientAddress.get_list_for_profile() must be exactly 1 query."""
        with self.assertNumQueries(1):
            ClientAddress.get_list_for_profile(self.profile)
