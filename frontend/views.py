from django.views.generic import TemplateView
from api.models import Customization, Post, Article, Image
from django.shortcuts import render, get_object_or_404, redirect

class IndexView(TemplateView):
    template_name = 'frontend/index.html'
    
    def get_context_data(self, * args, ** kwargs):
        context = super().get_context_data( * args, ** kwargs)
        queryset = Customization.objects.all()
        sitename, created = queryset.get_or_create(type='sitename')
        if sitename.content == '':
            title = 'Gartensea'
        else:
            title = sitename.content
        context['title'] = title
        logo, created = queryset.get_or_create(type='logo')
        context['logo'] = logo.file
        return context
        
