"""
URL additions for search
"""

from django.urls import path, include

urlpatterns += [
    path('api/search/', include('search.urls')),
]

