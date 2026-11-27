from django.urls import path, re_path
from .views import *


urlpatterns = [
    path('article-item/<int:id>', article_item),
    re_path(r'^', IndexView.as_view()),
]
