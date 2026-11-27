from rest_framework import viewsets
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
import datetime
from django.contrib.auth import authenticate, login, logout
from .models import Post, Image, Attachment, Comment, Customization, Tag, Article, ArticleComment, Smile, SpecialPost, Message, LoginAttempt, AdminAction, PostViewDaily
from django.db.models import Q, Max, F, Sum, Count
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from .serializer import PostSerializer, ImageSerializer, PostSupplementsSerializer, FullPostSerializer, \
    PostTextSerializer, AttachmentSerializer, CommentSerializer, CommentCreateSerializer, \
    FullUserSerializer, UserRegistrationSerializer, UserProfileRegistrationSerializer,\
    FullCustomizationSerializer, ContentCustomizationSerializer, \
    UserListSerializer, TagSerializer, CreateArticleSerializer, FullArticleSerializer, ArticleCommentCreateSerializer, ArticleCommentSerializer, \
    SmileSerializer, SpecialPostSerializer, TitleArticleSerializer, MessageCreateSerializer, \
    MessageSerializer, LoginAttemptSerializer, AdminActionSerializer, PostViewDailySerializer
from django.utils import timezone
from datetime import timedelta
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django.db.models import Sum, Count
from django.contrib.sessions.models import Session
from django.core.cache import cache
import random
import string

RANGE_DAYS = {'7d': 7, '30d': 30, '90d': 90}
REGISTRATION_LIMIT = 10  
REGISTRATION_WINDOW = 3600 
CAPTCHA_TTL = 300  
CAPTCHA_LENGTH = 5

def check_login_rate(ip, username, limit=10, window=300):
    """Не больше limit попыток за window секунд с IP и по username."""
    keys = [f'login:ip:{ip}', f'login:user:{(username or "").lower()}']
    for key in keys:
        count = cache.get(key, 0)
        if count >= limit:
            return False
    return True


def bump_login_rate(ip, username, window=300):
    for key in (f'login:ip:{ip}', f'login:user:{(username or "").lower()}'):
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window)

def get_client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_admin_action(request, action, target=None):
    AdminAction.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        target_id=getattr(target, 'pk', None),
        target_repr=str(target)[:200] if target is not None else '',
        ip=get_client_ip(request),
    )

class LogoutAllView(viewsets.ViewSet):
    def get_permissions(self):
        return [IsAuthenticated()]

    def create(self, request):
        for s in Session.objects.all():
            data = s.get_decoded()
            if data.get('_auth_user_id') == str(request.user.pk):
                s.delete()
        return Response({'result': True})


class HealthView(viewsets.ViewSet):
    def get_permissions(self):
        return [IsAdminUser()]

    def list(self, request):
        from django.db import connection
        db_ok = True
        try:
            with connection.cursor() as c:
                c.execute('SELECT 1')
        except Exception:
            db_ok = False
        return Response({'db': db_ok})

class StatsView(viewsets.ViewSet):
    def get_permissions(self):
        return [IsAdminUser()]

    def list(self, request):
        range_key = request.query_params.get('range', '7d')
        days = RANGE_DAYS.get(range_key, 7)
        now = timezone.now()
        since = now - timedelta(days=days)

        # --- overview ---
        overview = {
            'posts_total': Post.objects.count(),
            'posts_in_range': Post.objects.filter(created_at__gte=since).count(),
            'comments_total': Comment.objects.count(),
            'comments_in_range': Comment.objects.filter(created_at__gte=since).count(),
            'users_total': User.objects.count(),
            'users_in_range': User.objects.filter(date_joined__gte=since).count(),
        }

        # --- traffic ---
        traffic_qs = (
            PostViewDaily.objects
            .filter(date__gte=since.date())
            .values('date')
            .annotate(views=Sum('views'), clever_views=Sum('clever_views'))
            .order_by('date')
        )
        traffic = [
            {
                'date': row['date'].isoformat(),
                'views': row['views'] or 0,
                'clever_views': row['clever_views'] or 0,
            }
            for row in traffic_qs
        ]

        # --- top posts ---
        top_posts = list(
            Post.objects.filter(is_new_post=False)
            .order_by('-click')[:10]
            .values('id', 'text', 'click', 'clever_click', 'created_at')
        )
        for p in top_posts:
            p['created_at'] = p['created_at'].isoformat() if p['created_at'] else None

        # --- security ---
        failed_24h = LoginAttempt.objects.filter(
            success=False, created_at__gte=now - timedelta(hours=24)
        ).count()
        failed_7d = LoginAttempt.objects.filter(
            success=False, created_at__gte=now - timedelta(days=7)
        ).count()

        recent_logins = list(
            LoginAttempt.objects.order_by('-created_at')[:20]
            .values('id', 'username', 'ip', 'success', 'created_at')
        )
        for l in recent_logins:
            l['created_at'] = l['created_at'].isoformat()

        top_failed_ips = list(
            LoginAttempt.objects
            .filter(success=False, created_at__gte=since, ip__isnull=False)
            .values('ip')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )

        admin_actions_raw = list(
            AdminAction.objects.select_related('user').order_by('-created_at')[:20]
            .values('id', 'user__username', 'action', 'target_id', 'target_repr', 'created_at')
        )
        admin_actions = [
            {
                'id': a['id'],
                'username': a['user__username'],
                'action': a['action'],
                'target_id': a['target_id'],
                'target_repr': a['target_repr'],
                'created_at': a['created_at'].isoformat(),
            }
            for a in admin_actions_raw
        ]

        return Response({
            'overview': overview,
            'traffic': traffic,
            'top_posts': top_posts,
            'security': {
                'failed_logins_24h': failed_24h,
                'failed_logins_7d': failed_7d,
                'recent_logins': recent_logins,
                'top_failed_ips': top_failed_ips,
                'admin_actions': admin_actions,
            },
        })

class PostView(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in ('retrieve', 'list', 'count', 'post_supplements_list'):
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def retrieve(self, request, post_id):
        queryset = Post.objects.all()
        item = get_object_or_404(queryset, pk=post_id)
        serializer = PostSerializer(item)
        return Response(serializer.data)
        
    def count(self, request):
        posts = Post.objects.all().filter(is_new_post=False)
        postsCount = posts.count()
        return Response(postsCount)

    def list(self, request, loadedCount, limit):
        queryset = Post.objects.all().filter(is_new_post=False).order_by('-created_at')
        posts = queryset[loadedCount:loadedCount+limit]
        serializer = PostSerializer(posts, many=True)
        return Response(serializer.data)

    def post_supplements_list(self, request, post_id):
        queryset = Post.objects.all()
        post = get_object_or_404(queryset, id=post_id)
        serializer = PostSupplementsSerializer(post)
        return Response(serializer.data)

    def get_new_post(self, request):
        queryset = Post.objects
        post, created = queryset.get_or_create(is_new_post=True)
        serializer = FullPostSerializer(post)
        return Response(serializer.data)

    def set_text(self, request, post_id):
        data = request.data
        queryset = Post.objects.all()
        post = get_object_or_404(queryset, pk=post_id)
        serializer = PostTextSerializer(post, data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        serializer.save()
        return Response(serializer.data)

    def create(self, request):
        queryset = Post.objects.all()
        post = get_object_or_404(queryset, is_new_post=True)
        post.is_new_post = False
        post.created_at = datetime.datetime.now()
        post.save()
        serializer = FullPostSerializer(post)
        return Response(serializer.data)

    def delete(self, request):
        id = request.data.get('post_id')
        post = get_object_or_404(Post.objects, id=id)
        if not request.user.is_superuser:
            return Response(status=403, data={'error': 'Нет прав'})
        for image in Image.objects.filter(post=post):
            image.file.delete(save=True)
        log_admin_action(request, 'delete_post', post)
        post.delete()
        return Response(True)

    def send_click(self, request):
        id = request.data.get('post_id')
        click_counter = request.data.get('click_counter')
        post = get_object_or_404(Post.objects, id=id)
        post.click = click_counter
        post.save()
        today = timezone.localdate()
        obj, _ = PostViewDaily.objects.get_or_create(post=post, date=today)
        PostViewDaily.objects.filter(pk=obj.pk).update(views=F('views') + 1)
        return Response(True)

    def send_clever_click(self, request):
        id = request.data.get('post_id')
        click_counter = request.data.get('click_counter')
        post = get_object_or_404(Post.objects, id=id)
        post.clever_click = click_counter
        post.save()
        today = timezone.localdate()
        obj, _ = PostViewDaily.objects.get_or_create(post=post, date=today)
        PostViewDaily.objects.filter(pk=obj.pk).update(clever_views=F('clever_views') + 1)
        return Response(True)
       
class SpecialPostView(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in ('list'):
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def create(self, request):
        data = request.data
        max_order = SpecialPost.objects.aggregate(max_order=Max('order'))['max_order']
        data['order'] = max_order + 1
        serializer = SpecialPostSerializer(data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        serializer.save()
        return Response(serializer.data)

    def edit_order(self, request):
        id = request.data.get('id')
        direction = request.data.get('direction')
        queryset = SpecialPost.objects.all()
        item = get_object_or_404(queryset, id=id)
        if(direction == 'up'):
            item.order = item.order - 1
        else:
            item.order = item.order + 1
        item.save()
        serializer = SpecialPostSerializer(item)
        return Response(serializer.data['order'])
    
    def list(self, request):
        posts = SpecialPost.objects.all()
        serializer = SpecialPostSerializer(posts, many=True)
        return Response(serializer.data)

    def delete(self, request):
        id = request.data.get('id')
        queryset = SpecialPost.objects.all()
        post = get_object_or_404(queryset, id=id)
        post.delete()
        return Response({'result': True})
        
class MessageView(viewsets.ViewSet):
    def get_permissions(self):
        return [IsAuthenticated()]
    
    def create(self, request):
        data = request.data
        serializer = MessageCreateSerializer(data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        serializer.save(author=request.user)
        if request.user.is_superuser == True:
            parent_message = int(data.get('parent_message'))
            if parent_message != 0:
                item = get_object_or_404(Message.objects, id=parent_message)
                item.read = True
                item.save()
        return Response(serializer.data)
        
    def is_new_message(self, request):
        messages = Message.objects.all()
        message = messages.filter(to=request.user.pk, read=False)
        if message.exists():
            return Response("True")
        else:
            return Response("False")

    def is_message(self, request):
        message = Message.objects.filter(author = request.user)
        if message.exists():
            return Response("True")
        else:
            return Response("False")
        
    def new_message(self, request):
        queryset = Message.objects.all()
        item = get_object_or_404(queryset, to=request.user.pk)
        serializer = MessageSerializer(item)
        return Response(serializer.data)
    
    def list(self, request):
        user = request.user.id
        items = Message.objects.all()
        items = items.filter(to = user, read=False)
        serializer = MessageSerializer(items, many=True)
        return Response(serializer.data)

    def read_list(self, request):
        user = request.user.id
        week_ago = timezone.now() - timedelta(days=7)
        items = Message.objects.all()
        items.filter(to = user, created_at__lt=week_ago).update(archive=True)
        items = items.filter(to = user, read=True, archive=False)
        serializer = MessageSerializer(items, many=True)
        return Response(serializer.data)

    def read(self, request):
        id = request.data.get('item_id')
        item = get_object_or_404(Message.objects, id=id)
        item.read = True
        item.save()
        return Response(True)
        
    def delete(self, request):
        id = request.data.get('item_id')
        item = get_object_or_404(Message.objects, id=id)
        item.delete()
        return Response(True)

class CommentView(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in ('list', 'count'):
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def list(self, request, post_id, loadedItemsCount):
        comments = Comment.objects.filter(post__id=post_id)[loadedItemsCount:loadedItemsCount+30]
        serializer = CommentSerializer(comments, many=True)
        return Response(serializer.data)

    def count(self, request, post_id):
        items = Comment.objects.all().filter(post__id=post_id)
        count = items.count()
        return Response(count)

    def create(self, request):
        data = request.data
        _mutable = data._mutable
        data._mutable = True
        data['author'] = request.user.pk
        data._mutable = _mutable
        serializer = CommentCreateSerializer(data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        new_comment = serializer.save()
        show_data_serializer = CommentSerializer(new_comment)
        return Response(show_data_serializer.data)
        
    def delete(self, request):
        id = request.data.get('comment_id')
        item = get_object_or_404(Comment.objects, id=id)
        log_admin_action(request, 'delete_comment', item)
        item.delete()
        return Response(True)

class ImageView(viewsets.ViewSet):
    def get_permissions(self):
        return [IsAuthenticated()]
    
    def add_image(self, request):
        data = request.data
        serializer = ImageSerializer(data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request):
        id = request.data.get('image_id')
        image = get_object_or_404(Image.objects, id=id)
        if not request.user.is_superuser:
            return Response(status=403, data={'error': 'Нет прав'})
        image.file.delete(save=True)
        image.delete()
        return Response(True)

class AttachmentView(viewsets.ViewSet):
    def get_permissions(self):
        return [IsAuthenticated()]
    
    def create(self, request):
        data = request.data
        serializer = AttachmentSerializer(data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request):
        id = request.data.get('attachment_id')
        attachment = get_object_or_404(Attachment.objects, id=id)
        if not request.user.is_staff:
            return Response(status=403, data={'error': 'Нет прав'})
        attachment.delete()
        return Response(True)

class CaptchaView(viewsets.ViewSet):
    def get_permissions(self):
        return [AllowAny()]

    def create(self, request):
        # генерируем текст без похожих символов (0/O, 1/l/I)
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        text = ''.join(random.choice(alphabet) for _ in range(CAPTCHA_LENGTH))
        captcha_id = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))

        cache.set(f'captcha:{captcha_id}', text.lower(), timeout=CAPTCHA_TTL)

        return Response({
            'captcha_id': captcha_id,
            'text': text,  # клиент рисует сам; в проде можно отдавать SVG
        })

class UserView(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in ('count', 'user_list', 'search_list', 'login_or_registration'):
            return [AllowAny()]
        if self.action in ('block', 'delete'):
            return [IsAdminUser()]
        return [IsAuthenticated()]
    
    def count(self, request):
        users = User.objects.all()
        count = users.count()
        return Response(count)

    def search_list(self, request):
        data = request.data
        search_str = data.get('searchStr')
        loaded_items_count = int(data.get('loadedItemsCount'))
        queryset = User.objects.all().filter(Q(first_name__icontains=search_str))
        queryset = queryset.order_by('-pk')
        users = queryset[loaded_items_count:loaded_items_count+30]
        serializer = UserListSerializer(users, many=True)
        return Response(serializer.data)

    def user_list(self, request, total_count):
        queryset = User.objects.all().order_by('-pk')
        users = queryset[total_count:total_count+30]
        serializer = UserListSerializer(users, many=True)
        return Response(serializer.data)

    def retrieve(self, request):
        queryset = User.objects.all()
        user = get_object_or_404(queryset, pk=request.user.pk)
        serializer = FullUserSerializer(user)
        return Response(serializer.data)

    def login_or_registration(self, request):
        data = request.data
        username = data.get('username')
        password = data.get('password')
        operation = data.get('operation')
        ip = get_client_ip(request)

        if not check_login_rate(ip, username):
            return Response(status=429, data={"error": "Слишком много попыток. Попробуйте позже."})

        if operation == 'registration':
            captcha_id = data.get('captcha_id')
            captcha_input = (data.get('captcha_input') or '').strip().lower()

            if not captcha_id or not captcha_input:
                return Response(status=400, data={'error': 'Введите капчу.'})

            expected = cache.get(f'captcha:{captcha_id}')
            if expected is None:
                return Response(status=400, data={'error': 'Капча устарела. Обновите страницу.'})
            if expected != captcha_input:
                return Response(status=400, data={'error': 'Капча введена неверно.'})

            cache.delete(f'captcha:{captcha_id}')
            reg_key = f'reg:ip:{ip}'
            if cache.get(reg_key, 0) >= REGISTRATION_LIMIT:
                return Response(status=429, data={"error": "Слишком много регистраций. Попробуйте позже."})

            serializer = UserRegistrationSerializer(data=data)
            if not serializer.is_valid():
                return Response(status=400, data=serializer.errors)

            user = serializer.save()
            user.is_active = True
            user.save()

            try:
                cache.incr(reg_key)
            except ValueError:
                cache.set(reg_key, 1, timeout=REGISTRATION_WINDOW)

        user = authenticate(username=username, password=password)

        if user is not None:
            LoginAttempt.objects.create(
                username=username or '', ip=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:300],
                success=True,
            )
            login(request, user)
            request.session.cycle_key()
            return Response(True)

        bump_login_rate(ip, username)
        LoginAttempt.objects.create(
            username=username or '', ip=ip,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:300],
            success=False,
        )
        return Response(status=404, data={"error": "Эти данные не позволяют авторизироваться."})

    def profile_create(self, request):
        data = request.data
        queryset = User.objects.all()
        user = request.user
        user = get_object_or_404(queryset, pk=user.pk)
        serializer = UserProfileRegistrationSerializer(user, data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        serializer.save()
        return Response(serializer.data)

    def change_name(self, request):
        name = request.data.get('name')
        user = request.user
        user.first_name = name
        user.save()
        return Response(True)

    def change_email(self, request):
        email = request.data.get('email')
        user = request.user
        user.email = email
        user.save()
        return Response(True)

    def user_logout(self, request):
        logout(request)
        return Response(True)

    def block(self, request):
        id = request.data.get('user_id')
        queryset = User.objects.all()
        user = get_object_or_404(queryset, id=id)
        log_admin_action(request, 'block_user', user)
        if user.is_active:
            user.is_active = False
        else:
            user.is_active = True
        user.save()
        return Response({'result': True, 'is_active': user.is_active})

    def delete(self, request):
            id = request.data.get('user_id')
            queryset = User.objects.all()
            user = get_object_or_404(queryset, id=id)
            if user.is_superuser or user.pk == request.user.pk:
                return Response(status=403, data={'error': 'Нельзя удалить этого пользователя'})
            log_admin_action(request, 'delete_user', user)
            user.delete()
            return Response({'result': True})

class CustomizationView(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in (
            'styles', 'rules_settings_data', 'privacy_settings_data',
            'sibscribe_permission_settings_data', 'profile_info',
            'profile_about', 'profile_contacts',
        ):
            return [AllowAny()]
        return [IsAdminUser()]
    
    def profile_info(self, request):
        queryset = Customization.objects.all()
        avatar, created = queryset.get_or_create(type='avatar')
        avatar_serializer = FullCustomizationSerializer(avatar)
        name, created = queryset.get_or_create(type='name')
        name_serializer = FullCustomizationSerializer(name)
        email, created = queryset.get_or_create(type='email')
        email_serializer = FullCustomizationSerializer(email)
        city, created = queryset.get_or_create(type='city')
        city_serializer = FullCustomizationSerializer(city)
        status, created = queryset.get_or_create(type='status')
        status_serializer = FullCustomizationSerializer(status)
        data = {
            'avatar': avatar_serializer.data['file'],
            'name': name_serializer.data['content'],
            'email': email_serializer.data['content'],
            'city': city_serializer.data['content'],
            'status': status_serializer.data['content'],
        }
        return Response(data)

    def profile_about(self, request):
        queryset = Customization.objects.all()
        about, created = queryset.get_or_create(type='about')
        about_serializer = FullCustomizationSerializer(about)
        books, created = queryset.get_or_create(type='books')
        books_serializer = FullCustomizationSerializer(books)
        games, created = queryset.get_or_create(type='games')
        games_serializer = FullCustomizationSerializer(games)
        movies, created = queryset.get_or_create(type='movies')
        movies_serializer = FullCustomizationSerializer(movies)
        music, created = queryset.get_or_create(type='music')
        music_serializer = FullCustomizationSerializer(music)
        job, created = queryset.get_or_create(type='job')
        job_serializer = FullCustomizationSerializer(job)
        hobby, created = queryset.get_or_create(type='hobby')
        hobby_serializer = FullCustomizationSerializer(hobby)
        quotes, created = queryset.get_or_create(type='quotes')
        quotes_serializer = FullCustomizationSerializer(quotes)
        data = {
            'about': about_serializer.data['content'],
            'books': books_serializer.data['content'],
            'games': games_serializer.data['content'],
            'movies': movies_serializer.data['content'],
            'music': music_serializer.data['content'],
            'job': job_serializer.data['content'],
            'hobby': hobby_serializer.data['content'],
            'quotes': quotes_serializer.data['content'],
        }
        return Response(data)

    def profile_contacts(self, request):
        queryset = Customization.objects.all()
        item, created = queryset.get_or_create(type='contacts')
        serializer = ContentCustomizationSerializer(item)
        return Response(serializer.data['content'])

    def privacy_settings_data(self, request):
        try:
            needToEnter, create = Customization.objects.all().get_or_create(type='needToEnter')
            if needToEnter.content == '':
                needToEnter.content = 'false'
                needToEnter.save()
        except (ObjectDoesNotExist, MultipleObjectsReturned):
            needToEnter = Customization.objects.filter(type='needToEnter').order_by('id').first()
            Customization.objects.all().filter(type='needToEnter').exclude(pk=needToEnter.pk).delete()
        serializer = ContentCustomizationSerializer(needToEnter)
        return Response(serializer.data['content'])
        
    def rules_settings_data(self, request):
        try:
            rules, create = Customization.objects.all().get_or_create(type='rules')
        except (ObjectDoesNotExist, MultipleObjectsReturned):
            rules = Customization.objects.filter(type='rules').order_by('id').first()
            Customization.objects.all().filter(type='rules').exclude(pk=rules.pk).delete()
        serializer = ContentCustomizationSerializer(rules)
        return Response(serializer.data['content'])

    def styles(self, request):
        queryset = Customization.objects.all()
        background, created = queryset.get_or_create(type='background')
        background_serializer = FullCustomizationSerializer(background)
        color, created = queryset.get_or_create(type='color')
        color_serializer = ContentCustomizationSerializer(color)
        logo, created = queryset.get_or_create(type='logo')
        logo_serializer = FullCustomizationSerializer(logo)
        sitename, created = queryset.get_or_create(type='sitename')
        sitename_serializer = FullCustomizationSerializer(sitename)
        menuColor, created = queryset.get_or_create(type='menuColor')
        menuColor_serializer = FullCustomizationSerializer(menuColor)
        menuTextColor, created = queryset.get_or_create(type='menuTextColor')
        menuTextColor_serializer = FullCustomizationSerializer(menuTextColor)
        MC, created = queryset.get_or_create(type='MC')
        MC_serializer = FullCustomizationSerializer(MC)
        DAC, created = queryset.get_or_create(type='DAC')
        DAC_serializer = FullCustomizationSerializer(DAC)
        EAC, created = queryset.get_or_create(type='EAC')
        EAC_serializer = FullCustomizationSerializer(EAC)
        EC, created = queryset.get_or_create(type='EC')
        EC_serializer = FullCustomizationSerializer(EC)
        
        data = {
            'background': background_serializer.data['file'],
            'color': color_serializer.data['content'],
            'logo': logo_serializer.data['file'],
            'sitename': sitename_serializer.data['content'],
            'menuColor': menuColor_serializer.data['content'],
            'menuTextColor': menuTextColor_serializer.data['content'],
            'MC': MC_serializer.data['content'],
            'DAC': DAC_serializer.data['content'],
            'EAC': EAC_serializer.data['content'],
            'EC': EC_serializer.data['content'],
        }
        return Response(data)

    def edit_file_item(self, request):
        data = request.data
        queryset = Customization.objects.all()
        type = data.get('type')
        item, created = queryset.get_or_create(type=type)
        serializer = FullCustomizationSerializer(item, data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        file_deleting = data.get('file_deleting')
        if file_deleting == "true":
            item.file.delete(save=True)
        new_item = serializer.save()
        serializer = FullCustomizationSerializer(new_item)
        return Response(serializer.data['file'])
        

    def edit_item(self, request):
        new_value = request.data.get('value')
        item = request.data.get('item')
        queryset = Customization.objects.all()
        item, created = queryset.get_or_create(type=item)
        item.content = new_value
        item.save()
        serializer = FullCustomizationSerializer(item)
        return Response(serializer.data['content'])
        
class SmileView(viewsets.ViewSet):
    def add_smile(self, request):
        data = request.data
        serializer = SmileSerializer(data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        serializer.save()
        return Response(serializer.data)
        
    def list(self, request):
        data = request.data
        queryset = Smile.objects.all()
        serializer = SmileSerializer(queryset, many=True)
        return Response(serializer.data)
        
    def delete(self, request):
        id = request.data.get('smile_id')
        item = get_object_or_404(Smile.objects, id=id)
        item.delete()
        return Response(True)
        
class TagView(viewsets.ViewSet):
    def create(self, request):
        data = request.data
        serializer = TagSerializer(data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        serializer.save()
        return Response(serializer.data)
        
    def edit(self, request):
        data = request.data
        id = request.data.get('id')
        queryset = Tag.objects.all()
        item = get_object_or_404(queryset, pk=id)
        serializer = TagSerializer(item, data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        serializer.save()
        return Response(serializer.data)
        
    def delete(self, request):
        id = request.data.get('id')
        item = get_object_or_404(Tag.objects, id=id)
        item.delete()
        return Response(True)
        
    def list(self, request):
        items = Tag.objects.all()
        serializer = TagSerializer(items, many=True)
        return Response(serializer.data)
        
class ArticleView(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in ('retrieve', 'retrieve_title', 'count', 'list', 'prev_list'):
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def create(self, request):
        data = request.data
        serializer = CreateArticleSerializer(data=data)
        tags = request.POST.getlist('tags[]')
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        new_item = serializer.save(tags=tags)
        return Response({"data": serializer.data, 'item_id': new_item.id})
    
    def edit(self, request, id):
        data = request.data
        item = get_object_or_404(Article.objects.all(), pk=id)
        if not request.user.is_superuser:
            return Response(status=403, data={'error': 'Нет прав'})
        serializer = CreateArticleSerializer(item, data=data)
        tags = request.POST.getlist('tags[]')
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        cover_deleting = data.get('cover_deleting')
        if cover_deleting == "true":
            item.cover.delete(save=True)
        new_item = serializer.save(tags=tags)
        return Response({"data": serializer.data, 'item_id': new_item.id})
       
    def retrieve(self, request, id):
        queryset = Article.objects.all()
        item = get_object_or_404(queryset, pk=id)
        serializer = FullArticleSerializer(item)
        return Response(serializer.data)
        
    def retrieve_title(self, request, id):
        queryset = Article.objects.all()
        item = get_object_or_404(queryset, pk=id)
        serializer = TitleArticleSerializer(item)
        return Response(serializer.data)
        
    def count(self, request):
        data = request.data
        search_str = data.get('searchStr')
        items = Article.objects.all()
        items = items.filter(Q(title__icontains=search_str))
        itemsCount = items.count()
        return Response(itemsCount)
        
    def list(self, request):
        data = request.data
        search_str = data.get('searchStr')
        loaded_count = int(data.get('loadedCount'))
        limit = int(data.get('limit'))
        tags = request.POST.getlist('tags[]')
        queryset = Article.objects.all().order_by('-created_at')
        queryset = queryset.filter(Q(title__icontains=search_str) | Q(description__icontains=search_str))
        if tags != []:
            queryset = queryset.filter(tags__in=(tags)).distinct()
        items = queryset[loaded_count:loaded_count+limit]
        serializer = CreateArticleSerializer(items, many=True)
        return Response(serializer.data)
    
    def prev_list(self, request):
        items = Article.objects.order_by('-id')[:5]
        serializer = CreateArticleSerializer(items, many=True)
        return Response(serializer.data)
        
    def delete(self, request):
        id = request.data.get('id')
        item = get_object_or_404(Article.objects, id=id)
        if not request.user.is_superuser:
            return Response(status=403, data={'error': 'Нет прав'})
        log_admin_action(request, 'delete_article', item)   # <-- здесь
        item.cover.delete(save=True)
        item.delete()
        return Response(True)

class ArticleCommentView(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in ('list', 'count'):
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def list(self, request, article_id, loadedItemsCount):
        comments = ArticleComment.objects.filter(article__id=article_id).order_by('-created_at')[loadedItemsCount:loadedItemsCount+30]
        serializer = ArticleCommentSerializer(comments, many=True)
        return Response(serializer.data)

    def count(self, request, article_id):
        items = ArticleComment.objects.all().filter(article__id=article_id)
        count = items.count()
        return Response(count)

    def create(self, request):
        data = request.data
        _mutable = data._mutable
        data._mutable = True
        data['author'] = request.user.pk
        data._mutable = _mutable
        serializer = ArticleCommentCreateSerializer(data=data)
        if not serializer.is_valid():
            return Response(status=400, data=serializer.errors)
        new_comment = serializer.save()
        show_data_serializer = ArticleCommentSerializer(new_comment)
        return Response(show_data_serializer.data)

    def delete(self, request):
        id = request.data.get('comment_id')
        item = get_object_or_404(ArticleComment.objects, id=id)
        if not request.user.is_superuser:
            return Response(status=403, data={'error': 'Нет прав'})
        log_admin_action(request, 'delete_article_comment', item)
        item.delete()
        return Response(True)
        