from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _



class UserauthsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'userauths'
    verbose_name = _("User Authentication")

    def ready(self):
        import userauths.tasks  # noqa




# # userauths/apps.py
# from django.apps import AppConfig
# from django.utils.translation import gettext_lazy as _


# class UserauthsConfig(AppConfig):
#     default_auto_field = 'django.db.BigAutoField'
#     name = 'userauths'
#     verbose_name = _("User Authentication")

#     def ready(self):
#         import userauths.celery_tasks  # noqa