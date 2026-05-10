from django.contrib import admin
from store.models import CartOrderItem, CouponUsers, Product, Tag,  DeliveryCouriers, CartOrder, Gallery, ProductFaq, Review,  Specification, Coupon, Color, Size, Wishlist
from import_export.admin import ImportExportModelAdmin
from django import forms
from store.models import Vendor


@admin.action(description="Mark selected products as published")
def make_published(modeladmin, request, queryset):
    queryset.update(status="published")
    
@admin.action(description="Mark selected products as In Review")
def make_in_review(modeladmin, request, queryset):
    queryset.update(status="in_review")
    
@admin.action(description="Mark selected products as Featured")
def make_featured(modeladmin, request, queryset):
    queryset.update(featured=True)

class ProductImagesAdmin(admin.TabularInline):
    model = Gallery

class SpecificationAdmin(admin.TabularInline):
    model = Specification

class ColorAdmin(admin.TabularInline):
    model = Color

class SizeAdmin(admin.TabularInline):
    model = Size

class CartOrderItemsInlineAdmin(admin.TabularInline):
    model = CartOrderItem

class CouponUsersInlineAdmin(admin.TabularInline):
    model = CouponUsers


class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = '__all__'

    # vendor = forms.ModelChoiceField(queryset=Vendor.objects.filter(user__is_staff=True))
    vendor = forms.ModelChoiceField(queryset=Vendor.objects.all())
    

class ProductAdmin(ImportExportModelAdmin):
    inlines = [ProductImagesAdmin, SpecificationAdmin, ColorAdmin, SizeAdmin]
    search_fields = ['title', 'price', 'slug']
    list_filter = ['featured', 'status', 'in_stock',  'vendor']
    list_editable = ['featured', 'status', 'hot_deal', 'special_offer']
    list_display = ['product_image', 'title',   'price', 'featured', 'shipping_amount', 'in_stock' ,'stock_qty', 'order_count', 'vendor' ,'status', 'featured', 'special_offer' ,'hot_deal']
    actions = [make_published, make_in_review, make_featured]
    list_per_page = 100
    prepopulated_fields = {"slug": ("title", )}
    form = ProductAdminForm


    
class TagAdmin(ImportExportModelAdmin):
    list_display = ['title', 'category', 'active']
    prepopulated_fields = {"slug": ("title", )}


class CartOrderAdmin(ImportExportModelAdmin):
    inlines = [CartOrderItemsInlineAdmin]
    search_fields = ['oid', 'full_name', 'email', 'mobile']
    list_editable = ['order_status', 'payment_status']
    list_filter = ['payment_status', 'order_status']
    list_display = ['oid', 'payment_status', 'order_status', 'sub_total', 'shipping_amount', 'service_fee' ,'total', 'saved' ,'date']


class CartOrderItemsAdmin(ImportExportModelAdmin):
    list_filter = ['delivery_couriers', 'applied_coupon']
    list_editable = ['date']
    list_display = ['order_id', 'vendor', 'product' ,'qty', 'price', 'sub_total', 'shipping_amount' , 'service_fee', 'total' , 'delivery_couriers', 'applied_coupon', 'date']

class ProductFaqAdmin(ImportExportModelAdmin):
    list_editable = [ 'active', 'answer']
    list_display = ['user', 'question', 'answer' ,'active']
    


class ProductOfferAdmin(ImportExportModelAdmin):
    list_display = ['user', 'product', 'price','status', 'email']

class CouponAdmin(ImportExportModelAdmin):
    inlines = [CouponUsersInlineAdmin]
    list_editable = ['code', 'active', ]
    list_display = ['vendor' ,'code', 'discount', 'active', 'date']
        

class ProductReviewAdmin(ImportExportModelAdmin):
    list_editable = ['active']
    list_editable = ['active']
    list_display = ['user', 'product', 'review', 'reply' ,'rating', 'active']


class DeliveryCouriersAdmin(ImportExportModelAdmin):
    list_editable = ['couriers_tracking_website_address', 'url_parameter']
    list_display = ['couriers_name', 'couriers_tracking_website_address', 'url_parameter']

admin.site.register(Review, ProductReviewAdmin)
admin.site.register(Product, ProductAdmin)
admin.site.register(Tag, TagAdmin)
admin.site.register(CartOrder, CartOrderAdmin)
admin.site.register(CartOrderItem, CartOrderItemsAdmin)
admin.site.register(ProductFaq, ProductFaqAdmin)
admin.site.register(Coupon, CouponAdmin)
admin.site.register(Wishlist)
admin.site.register(DeliveryCouriers, DeliveryCouriersAdmin)
# admin.site.register(Size )
# admin.site.register(Color )
# admin.site.register(Specification )
# admin.site.register(Gallery )