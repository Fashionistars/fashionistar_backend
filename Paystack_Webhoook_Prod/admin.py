from django.contrib import admin
from Paystack_Webhoook_Prod.models import Transaction, BankAccountDetails

admin.site.register(Transaction)
admin.site.register(BankAccountDetails)
# Register your models here.
