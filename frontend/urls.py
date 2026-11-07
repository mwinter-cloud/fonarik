from django.urls import path, re_path
from .views import *


urlpatterns = [
    path('post-item/<int:id>', post_item),
    path('article-item/<int:id>', article_item),
    re_path(r'^', IndexView.as_view()),
]