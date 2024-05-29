from rest_framework import serializers
from .models import Collections

class CollectionsSerializer(serializers.ModelSerializer):
    """
    Purpose:
    The to_representation method is used to control how the instance of the model is transformed into a JSON-serializable dictionary that can be returned by the API.

    Parameters:

    instance: The model instance being serialized.
    Returns:

    A dictionary containing the serialized data. In this case, it includes the background_image and image fields.
    Functionality:

    Calls the super().to_representation(instance) method to get the default representation of the instance.
    Decodes the background_image and image binary fields from their byte format to UTF-8 strings.
    Updates the representation dictionary with the decoded values.
    Returns the modified representation dictionary.
    Usage:
    This method is useful when you need to customize the output format of your serialized data, particularly for fields that require special handling, such as binary fields that need to be converted to a string format for JSON serialization.

    to_internal_value Method
    """
    background_image = serializers.CharField()
    image = serializers.CharField()

    class Meta:
        model = Collections
        fields = ['id', 'background_image', 'image']
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['background_image'] = instance.background_image.decode('utf-8')
        representation['image'] = instance.image.decode('utf-8')
        return representation

    def to_internal_value(self, data):
        internal_value = super().to_internal_value(data)
        internal_value['background_image'] = data['background_image'].encode('utf-8')
        internal_value['image'] = data['image'].encode('utf-8')
        return internal_value
