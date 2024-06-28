from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from notification.models import Notification

# Register your models here.



class NotificationAdmin(ImportExportModelAdmin):
    list_editable = ['seen']
    list_display = ['order', 'seen', 'user', 'vendor', 'date']





admin.site.register(Notification, NotificationAdmin)
