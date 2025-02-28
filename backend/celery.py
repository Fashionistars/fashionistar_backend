import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps configs.
app.autodiscover_tasks()


# @app.task(bind=True, ignore_result=True)
# def debug_task(self):
#     print(f'Request: {self.request!r}')





@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')






















# # backend/celery.py
# import os
# from celery import Celery
# from django.conf import settings

# # Set the default Django settings module for Celery
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# app = Celery('backend')

# # Load task modules from all registered Django app configs.
# app.config_from_object('django.conf:settings', namespace='CELERY')

# # Auto-discover tasks in all installed apps
# app.autodiscover_tasks()

# # Optional configuration - useful for development
# app.conf.update(
#     result_expires=3600,  # Results expire after an hour
# )

# # Ensure celery is aware of Django settings
# app.conf.update(settings.CELERY)