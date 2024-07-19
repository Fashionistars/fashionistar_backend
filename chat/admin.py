# from django.contrib import admin
# from chat.models import Message

# class MessageAdmin(admin.ModelAdmin):
#     search_fields  = ['sender','recipient', 'message', 'files', 'timestamp']
#     list_display  = ['sender','recipient', 'message', 'files', 'timestamp']
    

  
# admin.site.register(Message, MessageAdmin)


# chat/admin.py

from django.contrib import admin
from .models import Message

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['sender', 'recipient', 'message', 'timestamp']
    readonly_fields = ['timestamp']

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True
