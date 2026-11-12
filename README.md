# fonarik — настраиваемый блог

Блог-платформа на Django + React, которую пользователь может настроить под себя: название сайта, логотип и список тегов задаются в админ-панели Django, интерфейс собирается через webpack.

## Технологический стек

**Backend**
- Python 3, Django (в `requirements.txt` указан `django==6.1.3` — см. примечание ниже)
- Django REST Framework
- Django Channels + Daphne + channels-redis (WebSocket)
- Redis (channel layer + кэш через django-redis)
- Pillow, django-cleanup, django-cors-headers, django-crontab
- python-dotenv (чтение `.env`)
- Gunicorn (WSGI) + Daphne (ASGI)
- SQLite (база данных)

**Frontend**
- React 18, Redux, Zustand, React Query, React Router
- Formik + Yup, axios
- CKEditor 4, react-dropzone, browser-image-compression
- Yandex Smart Captcha, Google reCAPTCHA
- Webpack 5 + Babel, Sass

**Инфраструктура (VPS)**
- Nginx (reverse proxy, статика/медиа, SSL через Certbot)
- Redis
- Gunicorn (systemd) + Daphne (systemd)
- SQLite

## Шаги локального запуска

### 1. Клонирование
```bash
git clone https://github.com/mwinter-cloud/fonarik.git
cd fonarik
```

### 2. Виртуальное окружение и зависимости
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
> В репозитории `requirements.txt` содержит `pip-cleanup`, `pipreqs`, `ipython`, `jupyter-*` и другие инструменты разработки — для продакшена их можно не ставить. Если при установке возникают конфликты версий, ставьте пакеты по одному и правьте версии.

Системные зависимости (нужны для сборки `cryptography`, `cffi`, `Pillow`):
```bash
sudo apt install -y build-essential libssl-dev libffi-dev python3-dev
```

### 3. Переменные окружения
Скопируйте пример и заполните значения:
```bash
cp .env.example .env
```
Список переменных — в разделе «Переменные окружения» ниже.

### 4. Настройка `settings.py`
В `blogProject/settings.py` проверьте:
- `ALLOWED_HOSTS` — добавьте `127.0.0.1`, `localhost` и адрес сервера;
- `DATABASES` — по умолчанию SQLite (`BASE_DIR / 'db.sqlite3'`);
- `CHANNEL_LAYERS` и `CACHES` — указывают на Redis (`redis://default:redispw@localhost:32768`). Для локального запуска либо поднимите Redis на этом порту, либо измените хост/порт/пароль на свои;
- `EMAIL_*` — читаются из `.env`;
- в `INSTALLED_APPS` раскомментируйте `django_crontab`, если нужна автоматическая очистка записей.

### 5. Миграции и суперпользователь
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic
```

### 6. Запуск в режиме разработки
```bash
python manage.py runserver
```
Сайт: `http://127.0.0.1:8000/`, админка: `http://127.0.0.1:8000/django-admin-page/` (см. `urls.py`; стандартный путь — `/admin/`).

### 7. Сборка фронтенда (опционально, если правите React)
```bash
cd src   # каталог с package.json
npm install
npm run dev     # development-сборка в ../frontend/static/frontend
npm run build   # production-сборка
```

### 8. Автоудаление материалов (опционально)
```bash
python manage.py crontab add
```

## Примечания по развёртыванию

Развёртывание — на VPS без Docker, с SQLite. Ниже — сжатая версия инструкции из репозитория.

### Системные зависимости
```bash
sudo apt update
sudo apt install -y nginx ufw redis-server build-essential libssl-dev libffi-dev python3-dev python3-venv
sudo apt install -y gunicorn daphne   # или через venv, см. ниже
```
В инструкции Gunicorn и Daphne ставятся в venv:
```bash
pip install gunicorn
# daphne уже в requirements.txt
```

### Пользователь и права
```bash
adduser tanya
usermod -aG sudo tanya
usermod -aG www-data tanya
sudo su - tanya
```

### Код и окружение
```bash
git clone https://github.com/mwinter-cloud/fonarik.git /var/www/fonarik
cd /var/www/fonarik
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

### Настройки Django для продакшена
В `settings.py`:
```python
ALLOWED_HOSTS = ['fonarik.ru', '31.129.108.254', '127.0.0.1']
CORS_ALLOW_CREDENTIALS = True
CORS_ORIGIN_ALLOW_ALL = True
CSRF_TRUSTED_ORIGINS = ['https://fonarik.ru']
CSRF_COOKIE_DOMAIN = 'fonarik.ru'
CORS_ORIGIN_WHITELIST = ('https://fonarik.ru',)
```
Также заполните настройки почты (через `.env`) и раскомментируйте `django_crontab` в `INSTALLED_APPS`, если нужен крон.

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic
```

### Gunicorn (systemd)
`/etc/systemd/system/gunicorn.service`:
```ini
[Unit]
Description=gunicorn daemon
Requires=gunicorn.socket
After=network.target

[Service]
User=root
WorkingDirectory=/var/www/fonarik
ExecStart=/var/www/fonarik/venv/bin/gunicorn --workers 5 --bind unix:/run/gunicorn.sock blogProject.wsgi:application

[Install]
WantedBy=multi-user.target
```
> В проекте WSGI-модуль называется `blogProject.wsgi:application` (см. `settings.py`: `ROOT_URLCONF = 'blogProject.urls'`, `WSGI_APPLICATION = 'blogProject.wsgi.application'`). Если структура переименована — поправьте путь.

`/etc/systemd/system/gunicorn.socket`:
```ini
[Unit]
Description=gunicorn socket

[Socket]
ListenStream=/run/gunicorn.sock

[Install]
WantedBy=sockets.target
```
Проверка и запуск:
```bash
systemd-analyze verify gunicorn.service
sudo systemctl enable gunicorn
sudo systemctl start gunicorn
sudo systemctl status gunicorn   # должно быть running
```

### Nginx
`/etc/nginx/sites-available/default`:
```nginx
server {
    server_name 127.0.0.1 fonarik.ru;

    location = /favicon.ico { access_log off; log_not_found off; }
    location /static/ { root /var/www/fonarik/frontend; }
    location /media/  { root /var/www/fonarik; }
    location /static/admin/ { root /var/www/fonarik/windmail; }

    location /ws/ {
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_redirect off;
        proxy_pass http://127.0.0.1:7002;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn.sock;
    }

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/fonarik.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/fonarik.ru/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    if ($host = fonarik.ru) {
        return 301 https://$host$request_uri;
    }
    listen 80;
    server_name 31.129.108.254 fonarik.ru;
    return 404;
}
```
> В блоке `location /static/admin/` путь `root /var/www/fonarik/windmail;` остался от старой структуры. Замените `windmail` на реальный каталог, где лежит статика админки (обычно `blogProject` или общий `static`). Проверьте по `STATIC_ROOT` в `settings.py`.

```bash
sudo ufw allow 'Nginx HTTP'
sudo systemctl restart nginx
```

### SSL (Certbot)
```bash
sudo apt install -y snapd
sudo snap install core
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot
sudo certbot certonly --nginx
sudo certbot install --nginx
sudo certbot renew --dry-run
sudo systemctl restart nginx
```

### Redis
```bash
sudo apt install redis-server
sudo sed -i 's/^supervised no/supervised systemd/' /etc/redis/redis.conf
sudo systemctl restart redis.service
sudo systemctl status redis
sudo netstat -lnp | grep redis
```
> В `settings.py` Redis указан на порту `32768` с паролем `redispw`. Стандартный Redis слушает `6379` без пароля — либо приведите `CHANNEL_LAYERS`/`CACHES` к стандартному порту, либо настройте Redis на `32768` с паролем в `redis.conf`.

### Daphne (WebSocket, systemd)
`/etc/systemd/system/daphne.service`:
```ini
[Unit]
Description=WebSocket Daphne Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/var/www/fonarik
ExecStart=/var/www/fonarik/venv/bin/daphne -b 0.0.0.0 -p 7002 blogProject.asgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl start daphne.service
sudo systemctl status daphne.service
```

### Перезапуск после изменений
```bash
sudo systemctl restart gunicorn
sudo systemctl restart daphne
sudo systemctl restart nginx
```

### Первичная настройка сайта
- Зайдите в админку Django (`/django-admin-page/`): задайте название сайта, список тегов, логотип.
- В `frontend/templates/frontend/index.py` (по инструкции) пропишите название сайта и ссылку на логотип, если шаблон это использует.
- Привяжите домен к IP сервера.

## Переменные окружения

Файл `.env` читается через `python-dotenv` (`load_dotenv(BASE_DIR / '.env')`). Пример — `.env.example`:

```dotenv
# Django
SECRET_KEY=change-me-to-a-long-random-string

# Email (используется в settings.py)
EMAIL_HOST=smtp.example.com
EMAIL_HOST_USER=user@example.com
EMAIL_HOST_PASSWORD=change-me
EMAIL_PORT=465
EMAIL_USE_TLS=False
EMAIL_USE_SSL=True
```

Обязательные переменные (при отсутствии `settings.py` упадёт с `KeyError`):
- `SECRET_KEY`
- `EMAIL_HOST`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`

Необязательные (есть значения по умолчанию):
- `EMAIL_PORT` (по умолчанию `465`)
- `EMAIL_USE_TLS` (по умолчанию `False`)
- `EMAIL_USE_SSL` (по умолчанию `True`)

> Redis-подключение (`redis://default:redispw@localhost:32768`) и `ALLOWED_HOSTS` сейчас заданы прямо в `settings.py`, не через `.env`. Если хотите вынести их в окружение — добавьте соответствующие `os.environ[...]`.

## Примечания и известные расхождения

1. **Имя WSGI/ASGI-модуля.** В `settings.py` используется `blogProject.wsgi` / `blogProject.asgi`. Если каталог проекта называется иначе — приведите пути в `gunicorn.service` и `daphne.service` в соответствие с реальной структурой.
2. **Версия Django.** В присланном `requirements.txt` указан `django==6.1.3`, а `settings.py` использует `USE_L10N` (удалён в Django 5.0). Проверьте, какая версия реально работает у вас, и зафиксируйте её в `requirements.txt`.
3. **`requirements.txt` содержит инструменты разработки** (`pip-cleanup`, `pipreqs`, `ipython`, `jupyter-*`, `nbconvert`). Для продакшена рекомендуется собрать отдельный `requirements.txt` только с рантайм-зависимостями (см. подход с `pip-tools` / `requirements.in`).
4. **SQLite** — база по умолчанию. Для продакшена при нагрузке стоит рассмотреть PostgreSQL, но текущая инструкция и `settings.py` настроены на SQLite.
5. **`DEBUG = True`** в `settings.py`. Перед публикацией на реальном домене установите `DEBUG = False` и заполните `ALLOWED_HOSTS`.
6. **Путь `/static/admin/` в Nginx** всё ещё содержит `windmail` — замените на реальный каталог со статикой админки (см. `STATIC_ROOT` в `settings.py`).
