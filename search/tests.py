from django.test import TestCase
from django.urls import reverse, resolve
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .models import SearchableContent


class SearchAPITest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='u', password='p')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        SearchableContent.objects.create(
            content_type='notes', content_id=1, title='نمونه', content='نمونه متن برای تست', metadata={}
        )

    def test_search_content_requires_q(self):
        url = '/api/search/content/'
        res = self.client.get(url)
        self.assertEqual(res.status_code, 400)

    def test_search_content_ok(self):
        url = '/api/search/content/?q=نمونه&page=1&page_size=10'
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertIn('results', res.data)

    def test_suggestions(self):
        url = '/api/search/suggestions/?q=نم'
        res = self.client.get(url)
        self.assertIn(res.status_code, [200, 400])

