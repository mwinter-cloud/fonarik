# fonarik — настраиваемый блог

Блог-платформа на Django + React, которую пользователь может настроить под себя: название сайта, логотип и список тегов задаются в админ-панели Django, интерфейс собирается через webpack.

## Технологический стек

**Backend**
- Python 3, Django 4.2
- Django REST Framework
- Django Channels + Daphne + channels-redis (WebSocket)
- Redis (channel layer + кэш через django-redis)
- Pillow, django-cleanup, django-cors-headers
- python-dotenv
- Gunicorn (WSGI) + Daphne (ASGI)
- SQLite

**Frontend**
- React 18, Redux, Zustand, React Query, React Router
- Formik + Yup, axios
- CKEditor 4, react-dropzone, browser-image-compression
- Webpack 5 + Babel, Sass

**Инфраструктура**
- Nginx (reverse proxy, статика/медиа, SSL через Certbot)
- Redis
- Gunicorn и Daphne под systemd
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

Системные зависимости для сборки `cryptography`, `cffi`, `Pillow`:

```bash
sudo apt install -y build-essential libssl-dev libffi-dev python3-dev
```

### 3. Переменные окружения

```bash
cp .env.example .env
```

Заполните `.env` (см. раздел «Переменные окружения»).

### 4. Настройка `settings.py`

Проверьте:
- `ALLOWED_HOSTS` — добавьте `127.0.0.1`, `localhost`;
- `DATABASES` — по умолчанию SQLite;
- `CHANNEL_LAYERS` и `CACHES` — указывают на Redis `127.0.0.1:6379`. Для локального запуска поднимите Redis (`sudo apt install redis-server`) или измените адрес на свой;
- `EMAIL_*` — читаются из `.env`.

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

Сайт: `http://127.0.0.1:8000/`. Админка: путь из `urls.py` (стандартный — `/admin/`).

### 7. Сборка фронтенда (если правите React)

```bash
cd src
npm install
npm run dev
npm run build
```

## Развёртывание на VPS

Без Docker, с SQLite.

### Системные зависимости

```bash
sudo apt update
sudo apt install -y nginx ufw redis-server build-essential libssl-dev libffi-dev python3-dev python3-venv
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
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = ['fonarik.ru', '31.129.108.254', '127.0.0.1', 'localhost']
```

В `.env` добавьте `DEBUG=False`.

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic
```

### Redis

```bash
sudo systemctl enable redis-server
sudo systemctl restart redis-server
redis-cli ping   # PONG
```

`settings.py` использует `redis://127.0.0.1:6379/0` для Channels и `/1` для кэша.

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

`/etc/systemd/system/gunicorn.socket`:

```ini
[Unit]
Description=gunicorn socket

[Socket]
ListenStream=/run/gunicorn.sock

[Install]
WantedBy=sockets.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl start gunicorn
sudo systemctl status gunicorn
```

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
ExecStart=/var/www/fonarik/venv/bin/daphne -b 127.0.0.1 -p 7002 blogProject.asgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable daphne
sudo systemctl start daphne
sudo systemctl status daphne
```

### Nginx

`/etc/nginx/sites-available/default`:

```nginx
server {
    listen 80;
    server_name fonarik.ru 31.129.108.254;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name fonarik.ru 31.129.108.254;

    ssl_certificate /etc/letsencrypt/live/fonarik.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/fonarik.ru/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        root /var/www/fonarik/frontend;
    }

    location /media/ {
        root /var/www/fonarik;
    }

    location /static/admin/ {
        root /var/www/fonarik/blogProject;
    }

    location /ws/ {
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_redirect off;
        proxy_pass http://127.0.0.1:7002;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn.sock;
    }
}
```

```bash
sudo ufw allow 'Nginx Full'
sudo nginx -t
sudo systemctl restart nginx
```

### SSL (Certbot)

```bash
sudo apt install -y snapd
sudo snap install core
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot
sudo certbot certonly --nginx -d fonarik.ru
sudo systemctl restart nginx
sudo certbot renew --dry-run
```

### Перезапуск после изменений

```bash
sudo systemctl restart gunicorn
sudo systemctl restart daphne
sudo systemctl restart nginx
```

### Первичная настройка сайта

- Зайдите в админку Django: задайте название сайта, список тегов, логотип.
- Привяжите домен к IP сервера.
- Проверьте `https://fonarik.ru` и подключение WebSocket (вкладка Network в DevTools, фильтр `WS`).

## Переменные окружения

Файл `.env` читается через `python-dotenv`. Пример — `.env.example`:

```dotenv
# Django
SECRET_KEY=change-me-to-a-long-random-string
DEBUG=False

# Email
EMAIL_HOST=smtp.example.com
EMAIL_HOST_USER=user@example.com
EMAIL_HOST_PASSWORD=change-me
EMAIL_PORT=465
EMAIL_USE_TLS=False
EMAIL_USE_SSL=True
```

Обязательные переменные (без них `settings.py` упадёт с `KeyError`):
- `SECRET_KEY`
- `EMAIL_HOST`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`

Необязательные:
- `DEBUG` (по умолчанию `False`)
- `EMAIL_PORT` (по умолчанию `465`)
- `EMAIL_USE_TLS` (по умолчанию `False`)
- `EMAIL_USE_SSL` (по умолчанию `True`)

## Известные ограничения

1. **Имя модуля.** `settings.py` использует `blogProject.wsgi` / `blogProject.asgi`. Если каталог проекта переименован, поправьте пути в `gunicorn.service` и `daphne.service`.
2. **Версия Django.** В `requirements.txt` указан `django==6.1.3`, но `settings.py` написан под Django 4.2 (использовались настройки, удалённые в 5.0). Зафиксируйте рабочую версию в `requirements.txt`.
3. **`requirements.txt` содержит dev-инструменты** (`pip-cleanup`, `pipreqs`, `ipython`, `jupyter-*`). Для продакшена соберите отдельный файл только с рантайм-зависимостями.
4. **SQLite** — база по умолчанию. При росте нагрузки рассмотрите PostgreSQL.
5. **`DEBUG=True`** в `settings.py` по умолчанию. На продакшене выставляйте `DEBUG=False` через `.env`.
