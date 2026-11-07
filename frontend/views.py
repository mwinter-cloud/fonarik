from django.views.generic import TemplateView
from api.models import Customization, Post, Article, Image
from django.shortcuts import render, get_object_or_404, redirect
from bs4 import BeautifulSoup

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
        
def post_item(request, id):
    post = get_object_or_404(Post, id=id)
    text = post.text
    text = text[:180] + '...' if len(text) > 180 else text
    cleantext = BeautifulSoup(text, "html.parser").text
    if Image.objects.filter(post=post).exists():
        cover = Image.objects.filter(post=post).latest('id').file
    else:
        logo, created = Customization.objects.all().get_or_create(type='logo')
        cover = logo.file
    sitename, created = Customization.objects.all().get_or_create(type='sitename')
    if sitename.content == '':
        sitename = 'Гортензия'
    else:
        sitename = sitename.content
    context = {
        'id': id,
        'sitename': sitename,
        'text': cleantext,
        'cover': cover,
        'type': 'post'
    }
    return render(request, 'frontend/item.html', context=context)
      
def article_item(request, id):
    article = get_object_or_404(Article, id=id)
    text = article.text
    text = text[:180] + '...' if len(text) > 180 else text
    cleantext = BeautifulSoup(text, "html.parser").text
    if article.cover:
        cover = article.cover
    else:
        logo, created = Customization.objects.all().get_or_create(type='logo')
        cover = logo.file
    sitename, created = Customization.objects.all().get_or_create(type='sitename')
    if sitename.content == '':
        sitename = 'l-217'
    else:
        sitename = sitename.content
    context = {
        'id': id,
        'sitename': sitename,
        'text': cleantext,
        'cover': cover,
        'type': 'article'
    }
    return render(request, 'frontend/item.html', context=context)