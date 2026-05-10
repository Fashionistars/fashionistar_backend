# vendor/Views/serializerss/chart_ashboard.py

from rest_framework import serializers



class TotalOrdersChartSerializer(serializers.Serializer):
    """
    Serializer for the "Total Orders" chart data points.
    Represents the count of orders aggregated by month.
    """
    month = serializers.IntegerField()
    orders_count = serializers.IntegerField()


class RevenueAnalyticsChartSerializer(serializers.Serializer):
    """
    Serializer for the "Revenue Analytics" chart data points.
    Represents the total revenue aggregated by month.
    """
    month = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)