# 🛡️ StealthNET Admin Panel — Система управления VPN-бизнесом

Полнофункциональная система управления VPN-сервисом с административной панелью, клиентским личным кабинетом, Telegram ботом и интеграцией платежных систем.

![stealthnet](https://github.com/user-attachments/assets/e5c00d7c-58c1-447d-a539-6aa616856e0c)

## 🧪 [Тестовый сайт](https://panel.stealthnet.app/login) | 💬 **[Наш Чат](https://t.me/stealthnet_admin_panel)** - Для вопросов и предложений
🌎 **[VPN под ключ + Партнерка STEALTHNET ознакомиться](https://partners.stealthnet.app/)**
## 📋 Содержание

- [Описание](#-описание)
- [Основные компоненты](#-основные-компоненты)
- [Возможности](#-возможности)
- [Технологический стек](#-технологический-стек)
- [Установка через Docker](#-установка-через-docker-рекомендуется)
- [Структура проекта](#-структура-проекта)
- [Документация](#-документация)
- [Поддержка](#-поддержка)
- [Благодарности](#-благодарности)

---

## 🌟 Описание

**StealthNET VPN** — это комплексное решение для запуска и управления VPN-бизнесом. Система включает:

- 🏢 **Административная панель** — полный контроль над бизнесом
- 👤 **Клиентский личный кабинет** — удобный интерфейс для пользователей
- 🤖 **Telegram бот** — управление через Telegram
- 📱 **Telegram Mini-App** — веб-приложение в Telegram
- 💳 **Интеграция платежных систем** — CrystalPay, Heleket, Telegram Stars, YooKassa, Platega, Mulenpay, UrlPay, Monobank, BTCPayServer, Freekassa, Robokassa, Tribute
- 🌍 **Мультиязычность** — 4 языка (RU, UA, CN, EN)
- 💱 **Мультивалютность** — UAH, RUB, USD

---

## 🎯 Основные компоненты

### 1. Flask API (`app.py`)

Backend-сервер на Flask, предоставляющий RESTful API для всех компонентов системы.

**Основные функции:**
- Управление пользователями и авторизация (JWT)
- Управление тарифами и подписками
- Интеграция с платежными системами
- Реферальная программа
- Система промокодов
- Техническая поддержка (тикеты)
- Управление VPN-серверами (сквадами)
- Email-рассылки
- Брендинг и настройки

### 2. Admin Panel (`frontend/build/`)

React-приложение для администраторов с полным функционалом управления.

**Разделы:**
- 📊 Dashboard — статистика и аналитика
- 👥 Пользователи — управление клиентами
- 💎 Тарифы — создание и редактирование тарифов
- 🎫 Промокоды — управление промокодами
- 🎁 Рефералы — настройка реферальной программы
- 🛡️ Сквады — управление VPN-серверами
- ⚙️ Функции тарифов — настройка описаний
- 💰 Платежи — история транзакций (включая пополнения баланса)
- 💬 Поддержка — тикеты от клиентов
- 📧 Рассылки — email-уведомления
- 🎨 Брендинг — настройка логотипа и текстов
- ⚙️ Настройки — системные параметры

### 3. Telegram Bot (`client_bot.py`)

Telegram бот для клиентов с полным функционалом личного кабинета.

**Функции:**
- 📊 Статус подписки
- 💎 Просмотр и покупка тарифов
- 🌐 Список VPN-серверов
- 🎁 Реферальная программа
- 💬 Техническая поддержка
- 🎁 Активация триала (3 дня бесплатно)
- 📱 Web App (Mini-App)
- 🔐 Регистрация прямо в боте
- 💰 Пополнение баланса
- 📄 Пользовательское соглашение и публичная оферта

### 4. Telegram Mini-App (`frontend/build/miniapp/`)

Веб-приложение, встроенное в Telegram, с современным дизайном и полным функционалом.

**Возможности:**
- 📊 Обзор подписки и трафика
- 🌐 Список серверов
- 🔐 Доступ к учетным данным
- 📱 Адаптивный дизайн
- 🎨 Современный UI с эффектом стекла
- 🌙 Темная тема по умолчанию
- 💱 Мультивалютность

---

## ✨ Возможности

### Для администраторов

- ✅ Полная статистика бизнеса
- ✅ Управление пользователями и подписками
- ✅ Создание и редактирование тарифов
- ✅ Система промокодов и скидок
- ✅ Реферальная программа
- ✅ Управление VPN-серверами
- ✅ История платежей (включая пополнения баланса)
- ✅ Техническая поддержка клиентов
- ✅ Email-рассылки
- ✅ Настройка брендинга
- ✅ Мультиязычность и мультивалютность

### Для клиентов

- ✅ Личный кабинет с полным функционалом
- ✅ Просмотр статуса подписки и трафика
- ✅ Покупка тарифов с выбором способа оплаты
- ✅ Пополнение баланса
- ✅ Активация промокодов
- ✅ Активация триала (3 дня бесплатно)
- ✅ Список доступных VPN-серверов
- ✅ Реферальная программа
- ✅ Техническая поддержка
- ✅ Telegram бот для управления
- ✅ Telegram Mini-App

### Платежные системы

- 💳 **CrystalPay** — карты, электронные кошельки
- ₿ **Heleket** — криптовалюты
- ⭐ **Telegram Stars** — внутренняя валюта Telegram
- 💰 **YooKassa** — российская платежная система (RUB)
- 💳 **Platega** — платежная система
- 💳 **Mulenpay** — платежная система
- 💳 **UrlPay** — платежная система
- 💳 **Monobank** — украинский банк
- ₿ **BTCPayServer** — Bitcoin платежи
- 💳 **Freekassa** — платежная система
- 💳 **Robokassa** — платежная система
- 💳 **Tribute** — платежная система

---

## 🛠️ Технологический стек

### Backend

- **Python 3.11+**
- **Flask** — веб-фреймворк
- **SQLAlchemy** — ORM для работы с БД
- **SQLite** — база данных (по умолчанию)
- **JWT** — авторизация
- **Flask-Bcrypt** — хеширование паролей
- **Flask-Caching** — кэширование
- **Flask-Limiter** — rate limiting
- **Cryptography (Fernet)** — шифрование данных
- **Flask-Mail** — отправка email
- **Gunicorn** — WSGI сервер для продакшена
- **Docker** — контейнеризация

### Frontend (Admin Panel)

- **React 19**
- **React Router** — маршрутизация
- **i18next** — интернационализация
- **CSS3** — стилизация с переменными
- **React Icons** — иконки

### Telegram Bot

- **python-telegram-bot** — библиотека для работы с Telegram Bot API
- **asyncio** — асинхронное программирование

### Mini-App

- **HTML5/CSS3/JavaScript** — нативный веб
- **QRCode.js** — генерация QR-кодов
- **Современный дизайн** — glassmorphism эффекты

### Инфраструктура

- **Docker & Docker Compose** — контейнеризация и оркестрация
- **Nginx** — проксирование и статика
- **Gunicorn** — WSGI сервер

---

## 🐳 Установка через Docker (Рекомендуется) только на чистый сервер!

### Быстрый старт

1. **Установите Docker**:
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```

2. **Клонируйте проект**:
   ```bash
   cd /opt
   git clone https://github.com/GOFONCK/remnawave-STEALTHNET-Panel.git
   cd remnawave-STEALTHNET-Panel

   ```

3. **Настройте переменные окружения**:
   ```bash
   cp env.example .env
   nano .env  # Заполните все необходимые переменные
   ```

4. **Настройте Nginx**:
   ```bash
   # Редактируйте конфигурацию Nginx
   nano nginx/nginx.conf
   
   # Замените server_name _; на ваш домен или IP:
   # server_name panel.stealthnet.app;  # или ваш IP адрес
   
   # Для продакшена с HTTPS (после получения SSL сертификата):
   # 1. Раскомментируйте блок с HTTPS в nginx/nginx.conf
   # 2. Получите SSL сертификат (Let's Encrypt):
   #    certbot certonly --standalone -d panel.stealthnet.app --email your@email.com --agree-tos
   # 3. Скопируйте SSL сертификаты:
   #    cp /etc/letsencrypt/live/panel.stealthnet.app/fullchain.pem nginx/ssl/
   #    cp /etc/letsencrypt/live/panel.stealthnet.app/privkey.pem nginx/ssl/
   # 4. Перезапустите Nginx:
   #    docker compose restart nginx

   # Авто получение SSL ( Все делает автоматически и копирует сертификат в папку ) 
   #     chmod +x /opt/remnawave-STEALTHNET-Panel/scripts/ssl_issue_and_install.sh
   #     sudo /opt/remnawave-STEALTHNET-Panel/scripts/ssl_issue_and_install.sh -d panel.youdomain.com -e you@mail.com
   ```

5. **Запустите проект**:
   ```bash
   docker compose up -d
   ```

6. **Проверьте работу**:
   ```bash
   # Проверьте статус контейнеров
   docker compose ps
   
   # Проверьте логи
   docker compose logs -f
   
   # Проверьте API
   curl http://localhost:5000/api/public/health
   
   # Откройте в браузере
   # http://your-server-ip или https://your-domain
   ```

### Подробная инструкция

Полная подробная инструкция по установке находится в файле **[INSTALLATION.md](./INSTALLATION.md)**

Также доступна краткая инструкция: **[QUICK_START.md](./QUICK_START.md)**

---

## 📁 Структура проекта

```
remnawave-STEALTHNET-Panel/
├── app.py                          # Flask API сервер
├── client_bot.py                   # Telegram бот
├── requirements.txt                # Зависимости для API
├── client_bot_requirements.txt     # Зависимости для бота
├── Dockerfile                      # Образ для API
├── Dockerfile.bot                  # Образ для бота
├── docker-compose.yml              # Конфигурация Docker Compose
├── env.example                     # Пример переменных окружения
├── .dockerignore                   # Исключения для Docker
├── logo.png                        # Логотип для бота
├── start.sh                        # Скрипт быстрого запуска
├── generate_keys.sh                # Скрипт генерации ключей
├── nginx/
│   ├── nginx.conf                  # Конфигурация Nginx
│   └── ssl/                        # SSL сертификаты
├── frontend/
│   └── build/                      # Собранный React проект
│       ├── index.html
│       ├── static/
│       ├── locales/
│       └── miniapp/                # Telegram Mini-App
├── templates/                      # HTML шаблоны для email
│   ├── email_verification.html
│   └── email_broadcast.html
├── instance/                       # Экземпляр приложения
│   ├── stealthnet.db              # SQLite база данных
│   └── cache/                      # Кэш файлов
├── logs/                           # Логи приложения
└── INSTALLATION.md                 # Подробная инструкция
```

---

## 📝 Переменные окружения

Скопируйте `env.example` в `.env` и заполните все необходимые переменные:

**Основные:**
- `JWT_SECRET_KEY` - Секретный ключ для JWT токенов
- `API_URL` - URL внешнего API (RemnaWave)
- `ADMIN_TOKEN` - Токен администратора
- `CLIENT_BOT_TOKEN` - Токен Telegram бота
- `YOUR_SERVER_IP` - URL вашего сервера
- `SERVICE_NAME` - Название сервиса (отображается в боте)
- `FERNET_KEY` - Ключ для шифрования данных

**Платежные системы:**
- Настройте только те платежные системы, которые вам нужны
- См. полный список в `env.example`

**Генерация ключей:**
```bash
chmod +x generate_keys.sh
./generate_keys.sh
```

---

## 🐳 Docker Compose сервисы

- **api** - Flask API сервер (порт 5000)
- **bot** - Telegram бот
- **nginx** - Nginx для проксирования и статики (порты 80, 443)

---

## 📚 Документация

- **[INSTALLATION.md](./INSTALLATION.md)** - Полная подробная инструкция по установке (рекомендуется)
- **[QUICK_START.md](./QUICK_START.md)** - Быстрый старт за 5 минут
- **[DEPLOYMENT.md](./DEPLOYMENT.md)** - Развертывание на различных платформах (Railway, Fly.io, Render и др.)
- **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** - Решение проблем и ошибок
- **[nginx config examlpe.md](./nginx%20config%20examplpe.md)** - Пример конфигурации Nginx

---

## 🔄 Обновление проекта

```bash
cd /opt/remnawave-STEALTHNET-Panel
git pull  # Обновляем код из GitHub
docker compose down
docker compose build --no-cache
docker compose up -d  # База данных обновится автоматически при необходимости
```

---

## 🐛 Решение проблем

### Ошибки базы данных

База данных создается автоматически при первом запуске. Если возникают проблемы:

```bash
docker compose logs api
# База данных должна создаться автоматически через init_database()
```

### Проблемы с Telegram ботом

- Проверьте `CLIENT_BOT_TOKEN` в `.env`
- Убедитесь, что Flask API запущен и доступен
- Проверьте логи: `docker compose logs bot`

### Проблемы с платежами

- Проверьте настройки платежных систем в админ-панели
- Убедитесь, что webhook URL правильно настроен
- Проверьте логи: `docker compose logs api`

### Общие проблемы

- Проверьте логи: `docker compose logs -f`
- Проверьте статус контейнеров: `docker compose ps`
- Проверьте конфигурацию: `docker compose config`

---

## 📞 Поддержка

- **Email:** admin@stealthnet.app
- **Telegram:** [@StealthNet_Admin](https://t.me/stealthnet_admin_panel)

---

## 📄 Лицензия

Этот проект является частью StealthNET VPN системы.

---

## 🙏 Благодарности

Спасибо всем, кто использует и развивает этот проект!

---

**StealthNET VPN** — Ваша свобода в цифровом мире 🛡️

## 💰 Поддержка проекта

Мы принимаем донаты в криптовалюте. Пожалуйста, убедитесь, что вы отправляете средства в подходящей сети для каждого адреса.

**Адрес для (TRX/USDT-TRC20 и аналогичных):** `TY1ZATZ3Gtwz6hxv4j2mcgiZKc76o6V4Hp`



**Или звездами Telegram ⭐️**

Огромное вам спасибо за вашу веру в наш проект! Вместе мы сильнее! 💪
