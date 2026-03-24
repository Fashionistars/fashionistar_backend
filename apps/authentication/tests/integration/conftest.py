# apps/authentication/tests/integration/conftest.py
"""
Integration Test Conftest
=========================
Ensures ALL integration test functions get database access automatically.
Using an autouse fixture is more reliable than `pytestmark` which only marks
the conftest module itself, not the test modules within the directory.
"""
import pytest


@pytest.fixture(autouse=True)
def db_access_for_all_integration_tests(db):
    """
    Grant database access to every integration test automatically.
    LoginSerializer.validate() always queries UnifiedUser.objects even for
    negative test cases (wrong password, missing user) — so DB access is
    required even when no user fixture is passed.
    """
    pass
