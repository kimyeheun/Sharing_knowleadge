from . import  home
from django.contrib import admin
from django.urls import path
from . import *

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home , name="home"),
]
