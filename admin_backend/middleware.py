# middleware.py
from django.http import HttpResponsePermanentRedirect

class AppendSlashMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.endswith('/') and request.method == 'POST':
            return HttpResponsePermanentRedirect(request.path + '/')
        response = self.get_response(request)
        return response
