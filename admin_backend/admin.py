from django.contrib import admin
from admin_backend.models import Category, Brand
from import_export.admin import ImportExportModelAdmin


# Register your models here.
class CategoryAdmin(ImportExportModelAdmin):
    list_editable = [ 'active']
    list_display = ['title', 'thumbnail', 'active']


class BrandAdmin(ImportExportModelAdmin):
    list_editable = [ 'active']
    list_display = ['title', 'brand_image', 'active']




admin.site.register(Brand, BrandAdmin)
admin.site.register(Category, CategoryAdmin)
