from django.urls import re_path, include

from . import views

from .api import api

app_name = 'corptools'

urlpatterns = [
    re_path(r'^api/', api.urls),
]
