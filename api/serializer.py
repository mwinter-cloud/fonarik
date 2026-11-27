from rest_framework import serializers
from .models import Post, Message, Image, Attachment, Comment, Customization, Tag, Article, ArticleComment, Smile, SpecialPost, LoginAttempt, AdminAction, PostViewDaily
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404

class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = ['id', 'file', 'post']
        
class SpecialPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecialPost
        fields = ['id', 'text', 'order']

class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = ['id', 'text', 'type', 'post']

class PostSupplementsSerializer(serializers.ModelSerializer):
    images = ImageSerializer(many=True)
    attachments = AttachmentSerializer(many=True)

    class Meta:
        model = Post
        fields = ['images', 'attachments']

class PostSerializer(serializers.ModelSerializer):
    comments_count = serializers.IntegerField(
        source='comments.count',
        read_only=True
    )

    class Meta:
        model = Post
        fields = ['id', 'text', 'created_at', 'comments_count', 'click', 'clever_click']

class PostTextSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ['id', 'text']

class FullPostSerializer(serializers.ModelSerializer):
    images = ImageSerializer(many=True)
    attachments = AttachmentSerializer(many=True)

    class Meta:
        model = Post
        fields = ['id', 'text', 'created_at', 'images', 'attachments']

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username']

class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'is_active', 'is_superuser']

class FullUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['pk', 'id', 'email', 'username', 'first_name', 'is_superuser']

    def create(self, validate_data):
        return User.objects.create_user(**validate_data)
        
class MessageCreateSerializer(serializers.ModelSerializer):
    text = serializers.CharField(max_length=300, allow_blank=False, trim_whitespace=True)
    author = FullUserSerializer(read_only=True)
    created_at = serializers.DateTimeField(format='%d.%m.%Y %H:%M', read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'text', 'created_at', 'author', 'parent_message', 'to']

    def validate_to(self, value):
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError('Получатель не найден.')
        return value

    def validate(self, attrs):
        parent_id = attrs.get('parent_message') or 0
        if parent_id:
            if not Message.objects.filter(pk=parent_id).exists():
                raise serializers.ValidationError({'parent_message': 'Сообщение не найдено.'})
            # нельзя отвечать самому себе в том же сообщении — опционально
        return attrs
        
class MessageSerializer(serializers.ModelSerializer):
    author = FullUserSerializer()
    
    class Meta:
        model = Message
        fields = ['id', 'text', 'created_at', 'author', 'parent_message', 'to']      

class CommentSerializer(serializers.ModelSerializer):
    author = FullUserSerializer()

    class Meta:
        model = Comment
        fields = ['id', 'text', 'author', 'created_at']

class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ['id', 'text', 'author', 'created_at', 'post']
        
class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        max_length=90,
        min_length=1,
        style={'input_type': 'password'},
    )

    class Meta:
        model = User
        fields = ['username', 'password']

    def validate_username(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('Логин не может быть пустым.')
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('Указанный логин уже используется.')
        return value

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

class UserProfileRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'first_name']

    def create(self, validate_data):
        return User.objects.create_user(**validate_data)

class FullCustomizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customization
        fields = ['id', 'type', 'content', 'file']

class ContentCustomizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customization
        fields = ['id', 'type', 'content']
        

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name']
        
class CreateArticleSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    class Meta:
        model = Article
        fields = ['id', 'title', 'created_at', 'text', 'description', 'tags', 'cover']
        
class TitleArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ['id', 'title']
        
class ArticleCommentSerializer(serializers.ModelSerializer):
    author = FullUserSerializer()

    class Meta:
        model = ArticleComment
        fields = ['id', 'text', 'author', 'created_at']

class FullArticleSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    comments_count = serializers.IntegerField(
        source='article_comments.count',
        read_only=True
    )
    
    class Meta:
        model = Article
        fields = ['id', 'title', 'created_at', 'text', 'description', 'tags', 'cover', 'comments_count']
        
class ArticleCommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleComment
        fields = ['id', 'text', 'author', 'created_at', 'article']
        
class SmileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Smile
        fields = ['id', 'file']

class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = ['id', 'username', 'ip', 'success', 'created_at']


class AdminActionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True, allow_null=True)

    class Meta:
        model = AdminAction
        fields = ['id', 'username', 'action', 'target_id', 'target_repr', 'created_at']


class PostViewDailySerializer(serializers.ModelSerializer):
    class Meta:
        model = PostViewDaily
        fields = ['date', 'views', 'clever_views']