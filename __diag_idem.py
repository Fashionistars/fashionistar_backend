import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from django.test import Client
from unittest.mock import patch
from django.core.cache.backends.locmem import LocMemCache

_lc = LocMemCache('test', {})
oversized_key = 'x' * 129

with patch('apps.authentication.middleware.idempotency._get_cache', return_value=_lc):
    c = Client()
    r = c.post(
        '/api/v1/auth/register/',
        data='{"dummy":1}',
        content_type='application/json',
        HTTP_X_IDEMPOTENCY_KEY=oversized_key,
    )
    print('Status:', r.status_code)
    print('Content:', r.content[:300])
    print('Header received:')
    print('  len(key):', len(oversized_key))
