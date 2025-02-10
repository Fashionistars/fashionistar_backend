from rest_framework import serializers
from userauths.models import User
from vendor.models import Vendor
from Paystack_Webhoook_Prod.models import BankAccountDetails
from rest_framework.exceptions import ValidationError
from collections import OrderedDict


class BankAccountDetailsSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all(), required=False, allow_null=True)
    
    class Meta:
        model = BankAccountDetails
        fields = [
           'id',
            'user',
            'vendor',
            'account_number',
            'account_full_name',
            'bank_name',
            'paystack_Recipient_Code',
        ]
    
    
    def to_representation(self, instance):
          representation = super().to_representation(instance)
          if isinstance(instance, OrderedDict):
               representation['bank_name'] = instance.get('bank_name')
          else:
               representation['bank_name'] = instance.bank_name
          return representation
        
    def get_error_detail(self, error):
        if isinstance(error, list):
            return [self.get_error_detail(item) for item in error]
        elif isinstance(error, dict):
            return {key: self.get_error_detail(value) for key, value in error.items()}
        else:
             return str(error)

    @property
    def errors(self):
         if self._errors is not None:
              if isinstance(self._errors, dict):
                   return {key: self.get_error_detail(value) for key, value in self._errors.items()}
              elif isinstance(self._errors, list):
                    return [self.get_error_detail(value) for value in self._errors]
         return {}
    
    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        if data.get('bank_name'):
            from Paystack_Webhoook_Prod.BANKS_LIST import BANK_CHOICES
            bank_name = data.get('bank_name')
            for bank in BANK_CHOICES:
              if bank['bank_name'] == bank_name:
                  data['bank_code'] = bank['bank_code']
                  return data
            raise serializers.ValidationError("Invalid bank name")
        return data



