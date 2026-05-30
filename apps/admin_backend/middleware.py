# apps/admin_backend/middleware.py
from django.http import HttpResponsePermanentRedirect
from asgiref.sync import iscoroutinefunction, markcoroutinefunction

class AppendSlashMiddleware:
    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        if not request.path.endswith('/') and request.method == 'POST':
            return HttpResponsePermanentRedirect(request.path + '/')
        return self.get_response(request)

    async def __acall__(self, request):
        if not request.path.endswith('/') and request.method == 'POST':
            return HttpResponsePermanentRedirect(request.path + '/')
        return await self.get_response(request)
