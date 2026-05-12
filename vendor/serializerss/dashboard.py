# vendor/Views/serializerss/dashboard.py

from rest_framework import serializers



class DashboardStatsSerializer(serializers.Serializer):
    """
    Serializer for the main Vendor Dashboard Overview.

    This serializer is specifically designed to provide the key performance
    indicators (KPIs) shown in the main dashboard view, ensuring an
    efficient and targeted data payload.
    """
    # Note: We are not using a ModelSerializer because this data is aggregated
    # from multiple sources, not from a single model instance.
    store_review_average = serializers.DecimalField(max_digits=3, decimal_places=2)
    store_review_count = serializers.IntegerField()
    average_order_value = serializers.DecimalField(max_digits=12, decimal_places=2)
    out_of_stock_count = serializers.IntegerField()
    unfulfilled_orders_count = serializers.IntegerField()
    sales_total = serializers.DecimalField(max_digits=12, decimal_places=2)

    # We can add 'new_chats_count' later when the chat model is implemented.
    # new_chats_count = serializers.IntegerField()