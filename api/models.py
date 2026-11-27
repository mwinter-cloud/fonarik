from django.db import models
from django.contrib.auth.models import User
from io import BytesIO
from django.core.files.base import ContentFile
from PIL import Image

class Post(models.Model):
    text = models.CharField(max_length=10000, blank=True)
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

class LoginAttempt(models.Model):
    username = models.CharField(max_length=150, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['success', 'created_at']),
            models.Index(fields=['ip', 'created_at']),
        ]

    def __str__(self):
        return f"{self.username} {'ok' if self.success else 'fail'} {self.created_at}"

class AdminAction(models.Model):
    ACTIONS = [
        ('delete_post', 'delete_post'),
        ('delete_comment', 'delete_comment'),
        ('delete_article', 'delete_article'),
        ('delete_article_comment', 'delete_article_comment'),
        ('delete_user', 'delete_user'),
        ('block_user', 'block_user'),
        ('edit_customization', 'edit_customization'),
    ]
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=32, choices=ACTIONS)
    target_id = models.IntegerField(null=True, blank=True)
    target_repr = models.CharField(max_length=200, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} {self.target_repr}"

class PostViewDaily(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='daily_views')
    date = models.DateField(db_index=True)
    views = models.PositiveIntegerField(default=0)
    clever_views = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [('post', 'date')]
        ordering = ['-date']

    def __str__(self):
        return f"{self.post_id} {self.date} {self.views}"