from django.db import models
from django.contrib.auth.models import User
from io import BytesIO
from django.core.files.base import ContentFile
from PIL import Image

class Post(models.Model):
    text = models.CharField(max_length=1500, blank=True)
    created_at = models.DateTimeField(null=True)
    is_new_post = models.BooleanField(default=False)
    click = models.IntegerField(default=0)
    clever_click = models.IntegerField(default=0)

    def __str__(self):
        return self.text

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['is_new_post'],
                condition=models.Q(is_new_post=True),
                name='unique_new_post_post',
            )
        ]
        
class SpecialPost(models.Model):
    text = models.CharField(max_length=1500, blank=True)
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.text
        
class Message(models.Model):
    text = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    parent_message = models.IntegerField(default=0)
    to = models.IntegerField(default=0)
    read = models.BooleanField(default=False)
    archive = models.BooleanField(default=False)

    def __str__(self):
        return self.text

    class Meta:
        ordering = ['-created_at']

class Comment(models.Model):
    text = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')

    def __str__(self):
        return self.text

class Image(models.Model):
    file = models.ImageField(upload_to="post-images", max_length=255)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images')

    def save(self, *args, **kwargs):
        super().save()

class Attachment(models.Model):
    MUSIC = 'music'
    MOVIE = 'movie'
    BOOK = 'book'
    GAME = 'game'
    LINK = 'link'
    ARTICLE = 'article'
    TYPES_CHOICES = [
        (MUSIC, 'music'),
        (MOVIE, 'movie'),
        (BOOK, 'book'),
        (GAME, 'game'),
        (LINK, 'link'),
        (ARTICLE, 'article'),
    ]
    type = models.CharField(
        max_length=7,
        choices=TYPES_CHOICES,
        default=MUSIC
    )
    text = models.CharField(max_length=90)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='attachments')

    def __str__(self):
        return self.text

class Customization(models.Model):
    type = models.CharField(max_length=28)
    content = models.CharField(max_length=250, blank=True)
    file = models.ImageField(upload_to="site-illustrations", blank=True)

    def __str__(self):
        return self.type

    def save(self, *args, **kwargs):
        if self.file and self.file.name.lower().endswith(('.jpg', '.jpeg')):
            if self._state.adding or self._file_changed():
                self._make_progressive()
        super().save(*args, **kwargs)

    def _file_changed(self):
        """Проверяем, изменился ли файл с момента загрузки из БД."""
        if not self.pk:
            return True
        try:
            old = Customization.objects.get(pk=self.pk)
            return old.file != self.file
        except Customization.DoesNotExist:
            return True

    def _make_progressive(self):
        try:
            self.file.open('rb')
            img = Image.open(self.file).convert('RGB')

            output = BytesIO()
            img.save(
                output,
                format='JPEG',
                quality=80,
                optimize=True,
                progressive=True,
            )
            output.seek(0)

            self.file.save(
                self.file.name.split('/')[-1],
                ContentFile(output.read()),
                save=False,
            )
        except Exception as e:
            print('progressive convert failed:', e)

class Tag(models.Model):
    name = models.CharField(max_length=90)

    def __str__(self):
        return self.name

class Article(models.Model):
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    text = models.CharField(max_length=20000)
    created_at = models.DateTimeField(auto_now_add=True)
    cover = models.ImageField(upload_to="article-images", blank=True)
    tags = models.ManyToManyField(Tag, blank='True')

    def save(self, *args, **kwargs):
        super().save()
    
    def __str__(self):
        return self.title

class ArticleComment(models.Model):
    text = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='article_comments')

    def __str__(self):
        return self.text
       
class Smile(models.Model):
    file = models.ImageField(upload_to='smiles/')

