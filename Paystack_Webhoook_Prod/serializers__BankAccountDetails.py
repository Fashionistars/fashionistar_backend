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









        








# ===========================          ANOTHER WORKINBG CODETOUSE LATER      ==================================

# class BankAccountDetailsSerializer(serializers.ModelSerializer):
#     user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
#     vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all(), required=False, allow_null=True)
#     bank_code = serializers.CharField(max_length=10, write_only=True, required=False)
    
#     class Meta:
#         model = BankAccountDetails
#         fields = [
#            'id',
#             'user',
#             'vendor',
#             'account_number',
#             'account_full_name',
#             'bank_name',
#              'paystack_Recipient_Code',
#             'bank_code',
#         ]
    
    
#     def to_representation(self, instance):
#           representation = super().to_representation(instance)
#           if isinstance(instance, OrderedDict):
#                representation['bank_name'] = instance.get('bank_name')
#           else:
#                representation['bank_name'] = instance.bank_name
#           return representation
        
#     def get_error_detail(self, error):
#         if isinstance(error, list):
#             return [self.get_error_detail(item) for item in error]
#         elif isinstance(error, dict):
#             return {key: self.get_error_detail(value) for key, value in error.items()}
#         else:
#              return str(error)

#     @property
#     def errors(self):
#          if self._errors is not None:
#               if isinstance(self._errors, dict):
#                    return {key: self.get_error_detail(value) for key, value in self._errors.items()}
#               elif isinstance(self._errors, list):
#                     return [self.get_error_detail(value) for value in self._errors]
#          return {}
    
#     def to_internal_value(self, data):
#         data = super().to_internal_value(data)
#         if data.get('bank_name'):
#             from Paystack_Webhoook_Prod.BANKS_LIST import BANK_CHOICES
#             bank_name = data.get('bank_name')
#             for bank in BANK_CHOICES:
#               if bank['bank_name'] == bank_name:
#                   data['bank_code'] = bank['bank_code']
#                   return data
#             raise serializers.ValidationError("Invalid bank name")
#         return data












































































































# =======================================    THE MAIN CODE I WILL USE =============================================================

# from rest_framework import serializers
# from userauths.models import User
# from vendor.models import Vendor
# from Paystack_Webhoook_Prod.models import BankAccountDetails
# from rest_framework.exceptions import ValidationError
# from collections import OrderedDict

# class BankAccountDetailsSerializer(serializers.ModelSerializer):
#     user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
#     vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all(), required=False, allow_null=True)
#     bank_code = serializers.CharField(max_length=10, write_only=True, required=False)
    
#     class Meta:
#         model = BankAccountDetails
#         fields = [
#            'id',
#             'user',
#             'vendor',
#             'account_number',
#             'account_full_name',
#             'bank_name',
#              'paystack_Recipient_Code',
#             'bank_code',
#         ]
    
#     def validate_bank_name(self, value):
#         """
#         Validates that the bank_name is a valid one and return the bank code.
#         """
#         from Paystack_Webhoook_Prod.BANKS_LIST import BANK_CHOICES
#         for bank in BANK_CHOICES:
#              if bank['bank_name'] == value:
#                   return bank['bank_code']
#         raise serializers.ValidationError("Invalid bank name")
    
#     def to_representation(self, instance):
#           representation = super().to_representation(instance)
#           if isinstance(instance, OrderedDict):
#                representation['bank_name'] = instance.get('bank_name')
#           else:
#                representation['bank_name'] = instance.bank_name
#           return representation
        
#     def get_error_detail(self, error):
#         if isinstance(error, list):
#             return [self.get_error_detail(item) for item in error]
#         elif isinstance(error, dict):
#             return {key: self.get_error_detail(value) for key, value in error.items()}
#         else:
#              return str(error)

#     @property
#     def errors(self):
#          if self._errors is not None:
#               if isinstance(self._errors, dict):
#                    return {key: self.get_error_detail(value) for key, value in self._errors.items()}
#               elif isinstance(self._errors, list):
#                     return [self.get_error_detail(value) for value in self._errors]
#          return {}


































































































# from rest_framework import serializers
# from userauths.models import User
# from vendor.models import Vendor
# from Paystack_Webhoook_Prod.models import BankAccountDetails
# from rest_framework.exceptions import ValidationError
# from collections import OrderedDict

# class BankAccountDetailsSerializer(serializers.ModelSerializer):
#     user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
#     vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all(), required=False, allow_null=True)
#     bank_code = serializers.CharField(max_length=10, write_only=True, required=False)
    
#     class Meta:
#         model = BankAccountDetails
#         fields = [
#            'id',
#             'user',
#             'vendor',
#             'account_number',
#             'account_full_name',
#             'bank_name',
#              'paystack_Recipient_Code',
#             'bank_code',
#         ]
    
#     def validate_bank_name(self, value):
#         """
#         Validates that the bank_name is a valid one and return the bank code.
#         """
#         from Paystack_Webhoook_Prod.BANKS_LIST import BANK_CHOICES
#         for bank in BANK_CHOICES:
#              if bank['bank_name'] == value:
#                   return bank['bank_code']
#         raise serializers.ValidationError("Invalid bank name")
    
#     def to_representation(self, instance):
#           representation = super().to_representation(instance)
#           if isinstance(instance, OrderedDict):
#                representation['bank_name'] = instance.get('bank_name')
#           else:
#                representation['bank_name'] = instance.bank_name
#           return representation
        
#     def get_error_detail(self, error):
#         if isinstance(error, list):
#             return [self.get_error_detail(item) for item in error]
#         elif isinstance(error, dict):
#             return {key: self.get_error_detail(value) for key, value in error.items()}
#         else:
#              return str(error)

#     @property
#     def errors(self):
#          if self._errors is not None:
#               if isinstance(self._errors, dict):
#                    return {key: self.get_error_detail(value) for key, value in self._errors.items()}
#               elif isinstance(self._errors, list):
#                     return [self.get_error_detail(value) for value in self._errors]
#          return {}












































































































# from rest_framework import serializers
# from userauths.models import User
# from vendor.models import Vendor
# from Paystack_Webhoook_Prod.models import BankAccountDetails
# from Paystack_Webhoook_Prod.BANKS_LIST import  BANK_CHOICES
# from rest_framework.exceptions import ValidationError

# class BankAccountDetailsSerializer(serializers.ModelSerializer):
#     user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
#     vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all(), required=False, allow_null=True)
#     bank_code = serializers.CharField(max_length=10, write_only=True, required=False)
    
#     class Meta:
#         model = BankAccountDetails
#         fields = [
#            'id',
#             'user',
#             'vendor',
#             'account_number',
#             'account_full_name',
#             'bank_name',
#              'paystack_Recipient_Code',
#             'bank_code',
#         ]
    
#     def validate_bank_name(self, value):
#         """
#         Validates that the bank_name is a valid one and return the bank code.
#         """
        
#         print(BANK_CHOICES)  # Add this line
#         for bank in BANK_CHOICES:
#              if bank['bank_name'] == value:
#                   return bank['bank_code']
#         raise serializers.ValidationError("Invalid bank name")
    
#     def to_representation(self, instance):
#         representation = super().to_representation(instance)
#         representation['bank_name'] = instance.bank_name # Returns the saved value rather than the code.
#         return representation
    
#     def to_internal_value(self, data):
#         data = super().to_internal_value(data)
#         if data.get('bank_name'):
#             bank_code = self.validate_bank_name(data.get('bank_name'))
#             data['bank_code'] = bank_code
#         return data
    
#     def get_error_detail(self, error):
#         if isinstance(error, list):
#             return [self.get_error_detail(item) for item in error]
#         elif isinstance(error, dict):
#             return {key: self.get_error_detail(value) for key, value in error.items()}
#         else:
#              return str(error)

#     @property
#     def errors(self):
#          if self._errors is not None:
#               if isinstance(self._errors, dict):
#                    return {key: self.get_error_detail(value) for key, value in self._errors.items()}
#               elif isinstance(self._errors, list):
#                     return [self.get_error_detail(value) for value in self._errors]
#          return {}







































































































































































































# +++++++++++++++++++++++++++++++++++++++++++               OLD CODE    +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++



# from rest_framework import serializers
# from userauths.models import User
# from vendor.models import Vendor


# from Paystack_Webhoook_Prod.models import BankAccountDetails
# from Paystack_Webhoook_Prod.BANKS_LIST import  BANK_CHOICES







# class BankAccountDetailsSerializer(serializers.ModelSerializer):
#     user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
#     vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all(), required=False, allow_null=True)
    
#     class Meta:
#         model = BankAccountDetails
#         fields = [
#            'id',
#             'user',
#             'vendor',
#             'account_number',
#             'account_full_name',
#             'bank_name',
#              'paystack_Recipient_Code',
#         ]
#         extra_kwargs = {
#             'bank_code': {'write_only': True}
#         }
    
#     def validate_bank_name(self, value):
#         """
#         Validates that the bank_name is a valid one and return the bank code.
#         """
#         bank_choices = dict(BANK_CHOICES)
#         if value not in bank_choices.values():
#             raise serializers.ValidationError("Invalid bank name")
        
#         for code, name in BANK_CHOICES:
#             if name == value:
#                 return code
    
#     def to_internal_value(self, data):
#          data = super().to_internal_value(data)
#          if data.get('bank_name'):
#             bank_code = self.validate_bank_name(data.get('bank_name'))
#             data['bank_code'] = bank_code
#          return data



























# # class BankAccountDetailsSerializer(serializers.ModelSerializer):
# #     user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
# #     vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all(), required=False, allow_null=True)

# #     class Meta:
# #         model = BankAccountDetails
# #         fields = [
# #             'id',
# #             'user',
# #             'vendor',
# #             'account_number',
# #             'account_full_name',
# #             'bank_name',
# #              'paystack_Recipient_Code',
           
# #         ]
    
# #     def validate_bank_name(self, value):
# #         """
# #         Validates that the bank_name is a valid one and return the bank code.
# #         """
# #         bank_choices = dict(BANK_CHOICES)
# #         if value not in bank_choices.values():
# #              raise serializers.ValidationError("Invalid bank name")
        
# #         for code, name in BANK_CHOICES:
# #             if name == value:
# #                 return code


# #     def to_internal_value(self, data):
# #         data = super().to_internal_value(data)
# #         if data.get('bank_name'):
# #            bank_code = self.validate_bank_name(data.get('bank_name'))
# #            data['bank_code'] = bank_code
# #         return data


















