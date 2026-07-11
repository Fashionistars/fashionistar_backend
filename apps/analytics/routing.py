"""
apps/analytics/routing.py
==========================
WebSocket URL patterns for real-time analytics dashboards.

Routes:
  ws://host/ws/analytics/realtime/ — AnalyticsRealtimeConsumer
"""

from django.urls import path

from apps.analytics.consumers import AnalyticsRealtimeConsumer

websocket_urlpatterns = [
    path("ws/analytics/realtime/", AnalyticsRealtimeConsumer.as_asgi()),
]
