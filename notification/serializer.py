from rest_framework import serializers

from notification.models import CancelledOrder, Notification





# Define a serializer for the CancelledOrder model
class CancelledOrderSerializer(serializers.ModelSerializer):

    class Meta:
        model = CancelledOrder
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(CancelledOrderSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new cancelled order, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3



class NotificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Notification
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(NotificationSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new coupon user, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3


class NotificationSummarySerializer(serializers.Serializer):
    un_read_noti = serializers.IntegerField(default=0)
    read_noti = serializers.IntegerField(default=0)
    all_noti = serializers.IntegerField(default=0)




