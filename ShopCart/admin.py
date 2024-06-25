from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

# Register your models here.
from ShopCart.models import Cart





class CartAdmin(ImportExportModelAdmin):
    list_display = ['product', 'cart_id', 'qty', 'price', 'sub_total' , 'total',  'size', 'color', 'date']







admin.site.register(Cart, CartAdmin)
