import os
import json
from flask import Flask, request, jsonify, render_template, current_app, send_from_directory, send_file, redirect
from flask_cors import CORS 
import requests
from datetime import datetime, timedelta, timezone 
from sqlalchemy import func 

from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import jwt 
from functools import wraps
import click 
import random 
import string 
import threading 
from flask_caching import Cache 
from cryptography.fernet import Fernet
from flask_mail import Mail, Message 
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv 

# --- ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ---
load_dotenv()

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
API_URL = os.getenv("API_URL")
DEFAULT_SQUAD_ID = os.getenv("DEFAULT_SQUAD_ID")
YOUR_SERVER_IP_OR_DOMAIN = os.getenv("YOUR_SERVER_IP")
# Нормализуем URL - убеждаемся, что он с протоколом
if YOUR_SERVER_IP_OR_DOMAIN:
    YOUR_SERVER_IP_OR_DOMAIN = YOUR_SERVER_IP_OR_DOMAIN.strip()
    if not YOUR_SERVER_IP_OR_DOMAIN.startswith(('http://', 'https://')):
        YOUR_SERVER_IP_OR_DOMAIN = f"https://{YOUR_SERVER_IP_OR_DOMAIN}"
else:
    YOUR_SERVER_IP_OR_DOMAIN = "https://panel.stealthnet.app"  # Fallback
FERNET_KEY_STR = os.getenv("FERNET_KEY")
BOT_API_URL = os.getenv("BOT_API_URL", "")  # URL веб-API бота (например, http://localhost:8080)
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN", "")  # Токен для доступа к API бота
TELEGRAM_BOT_NAME = os.getenv("TELEGRAM_BOT_NAME", "")  # Имя бота для Telegram Login Widget
SERVICE_NAME = os.getenv("SERVICE_NAME", "StealthNET")  # Название сервиса для брендинга

# Cookies для Remnawave API (если панель требует cookies вместо/в дополнение к Bearer токену)
# Формат: COOKIES={"cookie_name":"cookie_value"} или COOKIES={"aEmFnBcC":"WbYWpixX"}
REMNAWAVE_COOKIES_STR = os.getenv("REMNAWAVE_COOKIES", "")
REMNAWAVE_COOKIES = {}
if REMNAWAVE_COOKIES_STR:
    try:
        REMNAWAVE_COOKIES = json.loads(REMNAWAVE_COOKIES_STR)
    except json.JSONDecodeError:
        print(f"⚠️ Warning: REMNAWAVE_COOKIES is not valid JSON, ignoring: {REMNAWAVE_COOKIES_STR}")
# Создаем необходимые директории ДО инициализации Flask
db_uri_env = os.getenv("SQLALCHEMY_DATABASE_URI", "sqlite:///instance/stealthnet.db")
if db_uri_env.startswith("sqlite:///") and not db_uri_env.startswith("sqlite:////"):
    db_path_env = db_uri_env.replace("sqlite:///", "")
    if not os.path.isabs(db_path_env):
        abs_db_path_env = os.path.abspath(db_path_env)
        db_dir_env = os.path.dirname(abs_db_path_env)
        if db_dir_env and not os.path.exists(db_dir_env):
            os.makedirs(db_dir_env, exist_ok=True)
            print(f"✅ Created database directory: {db_dir_env}")

app = Flask(__name__)

# CORS
CORS(app, resources={r"/api/.*": {
    "origins": [
        "http://localhost:5000", 
        "http://127.0.0.1:5000",
        "http://localhost:5001",
        "http://127.0.0.1:5001",
        YOUR_SERVER_IP_OR_DOMAIN,
        "https://stealthnet.app",
        "http://stealthnet.app"
    ]
}})

# База данных и Секреты
app.config['JWT_SECRET_KEY'] = os.getenv("JWT_SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("SQLALCHEMY_DATABASE_URI", "sqlite:///instance/stealthnet.db")
app.config['FERNET_KEY'] = FERNET_KEY_STR.encode() if FERNET_KEY_STR else None

# Кэширование
app.config['CACHE_TYPE'] = 'FileSystemCache'
app.config['CACHE_DIR'] = os.path.join(app.instance_path, 'cache')
cache = Cache(app)

# Почта
app.config['MAIL_SERVER'] = os.getenv("MAIL_SERVER")
app.config['MAIL_PORT'] = int(os.getenv("MAIL_PORT", 465))
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
# Устанавливаем отправителя только если MAIL_USERNAME настроен
if app.config['MAIL_USERNAME']:
    app.config['MAIL_DEFAULT_SENDER'] = ('StealthNET', app.config['MAIL_USERNAME'])
else:
    app.config['MAIL_DEFAULT_SENDER'] = ('StealthNET', 'noreply@stealthnet.app')

# Лимитер (Защита от спама запросами)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["2000 per day", "500 per hour"],
    storage_uri="memory://"
)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
# Инициализация Fernet только если ключ установлен
fernet = Fernet(app.config['FERNET_KEY']) if app.config.get('FERNET_KEY') else None
mail = Mail(app)


# ----------------------------------------------------
# ФУНКЦИИ КОНВЕРТАЦИИ ВАЛЮТ
# ----------------------------------------------------
def get_currency_rate(currency):
    """Получает курс валюты к USD из базы данных"""
    currency = currency.upper() if currency else 'USD'
    if currency == 'USD':
        return 1.0
    
    # Пытаемся получить курс из базы данных, но только если таблица существует
    try:
        rate_obj = CurrencyRate.query.filter_by(currency=currency).first()
        if rate_obj:
            return float(rate_obj.rate_to_usd)
    except:
        pass  # Если таблица еще не создана, используем значения по умолчанию
    
    # Значения по умолчанию, если курс не установлен
    default_rates = {
        'UAH': 40.0,
        'RUB': 100.0
    }
    return default_rates.get(currency, 1.0)

def convert_to_usd(amount, currency):
    """Конвертирует сумму из указанной валюты в USD"""
    currency = currency.upper() if currency else 'USD'
    if currency == 'USD':
        return float(amount)
    
    rate = get_currency_rate(currency)
    return float(amount) / rate

def convert_from_usd(amount_usd, target_currency):
    """Конвертирует сумму из USD в указанную валюту"""
    target_currency = target_currency.lower() if target_currency else 'usd'
    if target_currency == 'usd':
        return float(amount_usd)
    
    rate = get_currency_rate(target_currency.upper())
    return float(amount_usd) * rate

# ----------------------------------------------------
# МОДЕЛИ БАЗЫ ДАННЫХ
# ----------------------------------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True)  # Nullable для Telegram пользователей
    password_hash = db.Column(db.String(128), nullable=True)  # Nullable для Telegram пользователей
    encrypted_password = db.Column(db.Text, nullable=True)  # Зашифрованный пароль для бота (Fernet)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=True)  # Telegram ID пользователя
    telegram_username = db.Column(db.String(100), nullable=True)  # Telegram username
    remnawave_uuid = db.Column(db.String(128), unique=True, nullable=False)
    role = db.Column(db.String(10), nullable=False, default='CLIENT') 
    referral_code = db.Column(db.String(20), unique=True, nullable=True) 
    referrer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) 
    preferred_lang = db.Column(db.String(5), default='ru')
    preferred_currency = db.Column(db.String(5), default='uah')
    is_verified = db.Column(db.Boolean, nullable=False, default=True)  # Telegram пользователи считаются верифицированными
    verification_token = db.Column(db.String(100), unique=True, nullable=True)
    balance = db.Column(db.Float, nullable=False, default=0.0)  # Баланс пользователя
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

class Tariff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    price_uah = db.Column(db.Float, nullable=False)
    price_rub = db.Column(db.Float, nullable=False)
    price_usd = db.Column(db.Float, nullable=False)
    squad_id = db.Column(db.String(128), nullable=True)  # UUID сквада из внешнего API
    traffic_limit_bytes = db.Column(db.BigInteger, default=0)  # Лимит трафика в байтах (0 = безлимит)
    hwid_device_limit = db.Column(db.Integer, nullable=True, default=0)  # Лимит устройств (0 или NULL = безлимит)
    tier = db.Column(db.String(20), nullable=True)  # Уровень тарифа: 'basic', 'pro', 'elite' (если NULL - определяется автоматически)
    badge = db.Column(db.String(50), nullable=True)  # Бейдж тарифа (например, 'top_sale', NULL = без бейджа)
    bonus_days = db.Column(db.Integer, nullable=True, default=0)  # Бонусные дни (0 или NULL = без бонуса)

class PromoCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    promo_type = db.Column(db.String(20), nullable=False, default='PERCENT')
    value = db.Column(db.Integer, nullable=False) 
    uses_left = db.Column(db.Integer, nullable=False, default=1) 

class CurrencyRate(db.Model):
    """Модель для хранения курсов валют"""
    id = db.Column(db.Integer, primary_key=True)
    currency = db.Column(db.String(10), unique=True, nullable=False)  # 'UAH', 'RUB', 'USD'
    rate_to_usd = db.Column(db.Float, nullable=False)  # Курс к USD (например, 40.0 для UAH означает 1 USD = 40 UAH)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

class ReferralSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invitee_bonus_days = db.Column(db.Integer, default=7)
    referrer_bonus_days = db.Column(db.Integer, default=7) 
    trial_squad_id = db.Column(db.String(255), nullable=True)  # Сквад для триальной подписки

class TariffFeatureSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tier = db.Column(db.String(20), unique=True, nullable=False)  # 'basic', 'pro', 'elite'
    features = db.Column(db.Text, nullable=False)  # JSON массив строк с функциями 

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('tickets', lazy=True))
    subject = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='OPEN') 
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

class TicketMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    ticket = db.relationship('Ticket', backref=db.backref('messages', lazy=True))
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) 
    sender = db.relationship('User') 
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

class PaymentSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crystalpay_api_key = db.Column(db.Text, nullable=True)
    crystalpay_api_secret = db.Column(db.Text, nullable=True)
    heleket_api_key = db.Column(db.Text, nullable=True)
    telegram_bot_token = db.Column(db.Text, nullable=True)
    yookassa_api_key = db.Column(db.Text, nullable=True)  # Устаревшее поле, оставляем для совместимости
    yookassa_shop_id = db.Column(db.Text, nullable=True)  # Идентификатор магазина YooKassa
    yookassa_secret_key = db.Column(db.Text, nullable=True)  # Секретный ключ YooKassa
    cryptobot_api_key = db.Column(db.Text, nullable=True)
    platega_api_key = db.Column(db.Text, nullable=True)  # API ключ Platega
    platega_merchant_id = db.Column(db.Text, nullable=True)  # Merchant ID Platega
    mulenpay_api_key = db.Column(db.Text, nullable=True)  # API ключ Mulenpay
    mulenpay_secret_key = db.Column(db.Text, nullable=True)  # Secret ключ Mulenpay
    mulenpay_shop_id = db.Column(db.Text, nullable=True)  # Shop ID Mulenpay
    urlpay_api_key = db.Column(db.Text, nullable=True)  # API ключ UrlPay
    urlpay_secret_key = db.Column(db.Text, nullable=True)  # Secret ключ UrlPay
    urlpay_shop_id = db.Column(db.Text, nullable=True)  # Shop ID UrlPay
    monobank_token = db.Column(db.Text, nullable=True)  # Токен Monobank
    btcpayserver_url = db.Column(db.Text, nullable=True)  # URL BTCPayServer (например, https://btcpay.example.com)
    btcpayserver_api_key = db.Column(db.Text, nullable=True)  # API ключ BTCPayServer
    btcpayserver_store_id = db.Column(db.Text, nullable=True)  # Store ID BTCPayServer
    tribute_api_key = db.Column(db.Text, nullable=True)  # API ключ Tribute
    robokassa_merchant_login = db.Column(db.Text, nullable=True)  # Логин магазина Robokassa
    robokassa_password1 = db.Column(db.Text, nullable=True)  # Пароль #1 Robokassa (для подписания запросов)
    robokassa_password2 = db.Column(db.Text, nullable=True)  # Пароль #2 Robokassa (для проверки уведомлений)
    freekassa_shop_id = db.Column(db.Text, nullable=True)  # ID магазина Freekassa
    freekassa_secret = db.Column(db.Text, nullable=True)  # Секретное слово Freekassa (для подписания запросов)
    freekassa_secret2 = db.Column(db.Text, nullable=True)  # Секретное слово 2 Freekassa (для проверки уведомлений)

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    default_language = db.Column(db.String(10), default='ru', nullable=False)
    default_currency = db.Column(db.String(10), default='uah', nullable=False)
    show_language_currency_switcher = db.Column(db.Boolean, default=True, nullable=False)  # Показывать ли переключатели языка и валюты в Dashboard
    active_languages = db.Column(db.Text, default='["ru","ua","en","cn"]', nullable=False)  # JSON массив активных языков
    active_currencies = db.Column(db.Text, default='["uah","rub","usd"]', nullable=False)  # JSON массив активных валют
    # Настройки цветовой темы - светлая тема
    theme_primary_color = db.Column(db.String(20), default='#3f69ff', nullable=False)  # Акцентный цвет (светлая)
    theme_bg_primary = db.Column(db.String(20), default='#f8fafc', nullable=False)  # Основной фон (светлая)
    theme_bg_secondary = db.Column(db.String(20), default='#eef2ff', nullable=False)  # Вторичный фон (светлая)
    theme_text_primary = db.Column(db.String(20), default='#0f172a', nullable=False)  # Основной текст (светлая)
    theme_text_secondary = db.Column(db.String(20), default='#64748b', nullable=False)  # Вторичный текст (светлая)
    # Настройки цветовой темы - тёмная тема
    theme_primary_color_dark = db.Column(db.String(20), default='#6c7bff', nullable=False)  # Акцентный цвет (тёмная)
    theme_bg_primary_dark = db.Column(db.String(20), default='#050816', nullable=False)  # Основной фон (тёмная)
    theme_bg_secondary_dark = db.Column(db.String(20), default='#0f172a', nullable=False)  # Вторичный фон (тёмная)
    theme_text_primary_dark = db.Column(db.String(20), default='#e2e8f0', nullable=False)  # Основной текст (тёмная)
    theme_text_secondary_dark = db.Column(db.String(20), default='#94a3b8', nullable=False)  # Вторичный текст (тёмная)

class BrandingSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    logo_url = db.Column(db.String(500), nullable=True)  # URL логотипа
    site_name = db.Column(db.String(100), default=SERVICE_NAME, nullable=False)  # Название сайта
    site_subtitle = db.Column(db.String(200), nullable=True)  # Подзаголовок
    primary_color = db.Column(db.String(7), default='#3F69FF', nullable=False)  # Основной цвет (hex)
    secondary_color = db.Column(db.String(7), default='#ffffff', nullable=False)  # Вторичный цвет
    accent_color = db.Column(db.String(7), default='#3F69FF', nullable=False)  # Акцентный цвет
    login_welcome_text = db.Column(db.String(200), nullable=True)  # Текст приветствия на странице входа
    register_welcome_text = db.Column(db.String(200), nullable=True)  # Текст приветствия на странице регистрации
    footer_text = db.Column(db.String(200), nullable=True)  # Текст в футере
    dashboard_servers_title = db.Column(db.String(200), nullable=True)  # Заголовок страницы серверов в Dashboard
    dashboard_servers_description = db.Column(db.String(300), nullable=True)  # Описание страницы серверов
    dashboard_tariffs_title = db.Column(db.String(200), nullable=True)  # Заголовок страницы тарифов
    dashboard_tariffs_description = db.Column(db.String(300), nullable=True)  # Описание страницы тарифов
    dashboard_tagline = db.Column(db.String(100), nullable=True)  # Слоган в сайдбаре Dashboard (например, "Secure VPN")
    # Быстрое скачивание
    quick_download_enabled = db.Column(db.Boolean, default=True, nullable=False)  # Показывать блок быстрого скачивания
    quick_download_windows_url = db.Column(db.String(500), nullable=True)  # Ссылка на Windows клиент
    quick_download_android_url = db.Column(db.String(500), nullable=True)  # Ссылка на Android клиент
    quick_download_macos_url = db.Column(db.String(500), nullable=True)  # Ссылка на macOS клиент
    quick_download_ios_url = db.Column(db.String(500), nullable=True)  # Ссылка на iOS клиент
    quick_download_profile_deeplink = db.Column(db.String(200), nullable=True, default='stealthnet://install-config?url=')  # Deeplink схема для добавления профиля

class BotConfig(db.Model):
    """Конфигурация Telegram бота — все тексты, кнопки и настройки"""
    id = db.Column(db.Integer, primary_key=True)
    
    # Общие настройки
    service_name = db.Column(db.String(100), default='StealthNET', nullable=False)  # Название сервиса
    bot_username = db.Column(db.String(100), nullable=True)  # @username бота
    support_url = db.Column(db.String(500), nullable=True)  # Ссылка на поддержку
    support_bot_username = db.Column(db.String(100), nullable=True)  # @username бота поддержки
    
    # Настройки видимости кнопок
    show_webapp_button = db.Column(db.Boolean, default=True, nullable=False)  # Кнопка "Кабинет"
    show_trial_button = db.Column(db.Boolean, default=True, nullable=False)  # Кнопка "Активировать триал"
    show_referral_button = db.Column(db.Boolean, default=True, nullable=False)  # Кнопка "Рефералы"
    show_support_button = db.Column(db.Boolean, default=True, nullable=False)  # Кнопка "Поддержка"
    show_servers_button = db.Column(db.Boolean, default=True, nullable=False)  # Кнопка "Серверы"
    show_agreement_button = db.Column(db.Boolean, default=True, nullable=False)  # Кнопка "Соглашение"
    show_offer_button = db.Column(db.Boolean, default=True, nullable=False)  # Кнопка "Оферта"
    show_topup_button = db.Column(db.Boolean, default=True, nullable=False)  # Кнопка "Пополнить баланс"
    
    # Настройки триала
    trial_days = db.Column(db.Integer, default=3, nullable=False)  # Количество дней триала
    
    # Тексты переводов (JSON) — все тексты на всех языках
    translations_ru = db.Column(db.Text, nullable=True)  # JSON с русскими текстами
    translations_ua = db.Column(db.Text, nullable=True)  # JSON с украинскими текстами
    translations_en = db.Column(db.Text, nullable=True)  # JSON с английскими текстами
    translations_cn = db.Column(db.Text, nullable=True)  # JSON с китайскими текстами
    
    # Кастомные тексты (если заполнены — перезаписывают стандартные)
    welcome_message_ru = db.Column(db.Text, nullable=True)  # Приветственное сообщение (RU)
    welcome_message_ua = db.Column(db.Text, nullable=True)  # Приветственное сообщение (UA)
    welcome_message_en = db.Column(db.Text, nullable=True)  # Приветственное сообщение (EN)
    welcome_message_cn = db.Column(db.Text, nullable=True)  # Приветственное сообщение (CN)
    
    # Тексты документов
    user_agreement_ru = db.Column(db.Text, nullable=True)  # Пользовательское соглашение (RU)
    user_agreement_ua = db.Column(db.Text, nullable=True)  # Пользовательское соглашение (UA)
    user_agreement_en = db.Column(db.Text, nullable=True)  # Пользовательское соглашение (EN)
    user_agreement_cn = db.Column(db.Text, nullable=True)  # Пользовательское соглашение (CN)
    
    offer_text_ru = db.Column(db.Text, nullable=True)  # Публичная оферта (RU)
    offer_text_ua = db.Column(db.Text, nullable=True)  # Публичная оферта (UA)
    offer_text_en = db.Column(db.Text, nullable=True)  # Публичная оферта (EN)
    offer_text_cn = db.Column(db.Text, nullable=True)  # Публичная оферта (CN)
    
    # Кастомная структура меню (JSON)
    menu_structure = db.Column(db.Text, nullable=True)  # JSON со структурой кнопок меню
    
    # Проверка подписки на канал/группу при регистрации
    require_channel_subscription = db.Column(db.Boolean, default=False, nullable=False)  # Требовать подписку
    channel_id = db.Column(db.String(100), nullable=True)  # ID канала/группы (например: @channel или -1001234567890)
    channel_url = db.Column(db.String(500), nullable=True)  # Ссылка на канал для кнопки "Подписаться"
    channel_subscription_text_ru = db.Column(db.Text, nullable=True)  # Текст о необходимости подписки (RU)
    channel_subscription_text_ua = db.Column(db.Text, nullable=True)  # Текст о необходимости подписки (UA)
    channel_subscription_text_en = db.Column(db.Text, nullable=True)  # Текст о необходимости подписки (EN)
    channel_subscription_text_cn = db.Column(db.Text, nullable=True)  # Текст о необходимости подписки (CN)
    
    # Ссылка на бота для Mini App (для незарегистрированных пользователей)
    bot_link_for_miniapp = db.Column(db.String(500), nullable=True)  # https://t.me/BotName
    
    # Порядок кнопок в меню (JSON массив с ID кнопок)
    buttons_order = db.Column(db.Text, nullable=True)  # JSON: ["status", "tariffs", "topup", "servers", "referrals", "support", "settings", "agreement", "offer", "webapp"]
    
    # Дата обновления
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(100), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tariff_id = db.Column(db.Integer, db.ForeignKey('tariff.id'), nullable=True)  # Nullable для пополнения баланса
    status = db.Column(db.String(20), nullable=False, default='PENDING') 
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(5), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    payment_system_id = db.Column(db.String(100), nullable=True) 
    payment_provider = db.Column(db.String(20), nullable=True, default='crystalpay')  # 'crystalpay', 'heleket', 'yookassa', 'telegram_stars'
    promo_code_id = db.Column(db.Integer, db.ForeignKey('promo_code.id'), nullable=True)  # Промокод, использованный при оплате 


# ----------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ----------------------------------------------------
def parse_iso_datetime(iso_string):
    """
    Парсит ISO формат даты, поддерживая как стандартный формат, так и формат с 'Z' (UTC).
    Примеры:
    - '2025-11-29T09:56:35.745Z' -> datetime
    - '2025-11-29T09:56:35.745+00:00' -> datetime
    - '2025-11-29T09:56:35' -> datetime
    """
    if not iso_string:
        raise ValueError("Empty ISO string")
    
    # Заменяем 'Z' на '+00:00' для совместимости с fromisoformat
    if iso_string.endswith('Z'):
        iso_string = iso_string[:-1] + '+00:00'
    
    return datetime.fromisoformat(iso_string)

def create_local_jwt(user_id):
    payload = {'iat': datetime.now(timezone.utc), 'exp': datetime.now(timezone.utc) + timedelta(days=1), 'sub': str(user_id) }
    token = jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm="HS256")
    return token

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "): return jsonify({"message": "Auth required"}), 401
        try:
            local_token = auth_header.split(" ")[1]
            payload = jwt.decode(local_token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            user = db.session.get(User, int(payload['sub']))
            if not user or user.role != 'ADMIN': return jsonify({"message": "Forbidden"}), 403
            kwargs['current_admin'] = user 
        except Exception: return jsonify({"message": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated_function

def generate_referral_code(user_id):
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"REF-{user_id}-{random_part}"

def get_user_from_token():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "): return None
    try:
        local_token = auth_header.split(" ")[1]
        payload = jwt.decode(local_token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
        user = db.session.get(User, int(payload['sub']))
        return user
    except Exception: return None

def encrypt_key(key):
    if not fernet:
        raise ValueError("FERNET_KEY not configured. Cannot encrypt.")
    return fernet.encrypt(key.encode('utf-8'))

def decrypt_key(key):
    if not key: return ""
    if not fernet:
        return ""  # Если fernet не настроен, возвращаем пустую строку
    try: return fernet.decrypt(key).decode('utf-8')
    except Exception: return ""

def get_remnawave_headers(additional_headers=None):
    """
    Формирует заголовки для запросов к Remnawave API.
    Поддерживает как Bearer токен, так и cookies (если настроены).
    Возвращает кортеж (headers, cookies) для использования в requests.
    
    Args:
        additional_headers: Словарь с дополнительными заголовками, которые будут объединены с основными
    
    Returns:
        tuple: (headers_dict, cookies_dict) для использования в requests.get/post/patch/delete
    """
    headers = {}
    cookies = {}
    
    # Добавляем Bearer токен, если он настроен
    if ADMIN_TOKEN:
        headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"
    
    # Добавляем дополнительные заголовки, если они переданы
    if additional_headers:
        headers.update(additional_headers)
    
    # Добавляем cookies, если они настроены
    if REMNAWAVE_COOKIES:
        cookies.update(REMNAWAVE_COOKIES)
    
    return headers, cookies

def sync_subscription_to_bot_in_background(app_context, remnawave_uuid):
    """Синхронизирует подписку пользователя из RemnaWave в бота в фоновом режиме"""
    with app_context:
        try:
            if not BOT_API_URL or not BOT_API_TOKEN:
                print(f"⚠️ Bot API not configured, skipping sync for {remnawave_uuid}")
                return
            
            bot_api_url = BOT_API_URL.rstrip('/')
            sync_url = f"{bot_api_url}/remnawave/sync/from-panel"
            sync_headers = {"X-API-Key": BOT_API_TOKEN, "Content-Type": "application/json"}
            
            print(f"Background sync: Syncing subscription to bot for user {remnawave_uuid}...")
            # Увеличиваем таймаут до 60 секунд для синхронизации всех пользователей
            # Отправляем пустой JSON объект, так как эндпоинт требует body
            sync_response = requests.post(
                sync_url, 
                headers=sync_headers, 
                json={},  # Отправляем пустой JSON объект, так как эндпоинт требует body
                timeout=60
            )
            
            if sync_response.status_code == 200:
                print(f"✓ Background sync: Subscription synced to bot for user {remnawave_uuid}")
            else:
                print(f"⚠️ Background sync failed: Status {sync_response.status_code}")
                print(f"   Response: {sync_response.text[:200]}")
        except requests.Timeout:
            print(f"⚠️ Background sync timeout for user {remnawave_uuid} (sync takes too long)")
        except Exception as e:
            print(f"⚠️ Background sync error for user {remnawave_uuid}: {e}")
            import traceback
            traceback.print_exc()

def apply_referrer_bonus_in_background(app_context, referrer_uuid, bonus_days):
    with app_context: 
        try:
            admin_headers, admin_cookies = get_remnawave_headers()
            resp = requests.get(f"{API_URL}/api/users/{referrer_uuid}", headers=admin_headers, cookies=admin_cookies)
            if resp.ok:
                live_data = resp.json().get('response', {})
                curr = parse_iso_datetime(live_data.get('expireAt'))
                new_exp = max(datetime.now(timezone.utc), curr) + timedelta(days=bonus_days)
                requests.patch(f"{API_URL}/api/users", 
                             headers={"Content-Type": "application/json", **admin_headers}, 
                             json={ "uuid": referrer_uuid, "expireAt": new_exp.isoformat() })
                cache.delete(f'live_data_{referrer_uuid}')
        except Exception as e: print(f"[ФОН] ОШИБКА: {e}")

def send_email_in_background(app_context, recipient, subject, html_body):
    """Отправляет email в фоновом режиме"""
    print(f"[EMAIL] ========== НАЧАЛО ОТПРАВКИ EMAIL ==========")
    print(f"[EMAIL] Получатель: {recipient}")
    print(f"[EMAIL] Тема: {subject}")
    
    with app_context:
        try:
            from flask import current_app
            
            # Проверяем настройки email перед отправкой
            mail_server = current_app.config.get('MAIL_SERVER')
            mail_username = current_app.config.get('MAIL_USERNAME')
            mail_password = current_app.config.get('MAIL_PASSWORD')
            mail_port = current_app.config.get('MAIL_PORT', 465)
            mail_use_ssl = current_app.config.get('MAIL_USE_SSL', True)
            mail_use_tls = current_app.config.get('MAIL_USE_TLS', False)
            
            print(f"[EMAIL] Проверка настроек email:")
            print(f"   MAIL_SERVER: {mail_server if mail_server else '❌ НЕ НАСТРОЕН'}")
            print(f"   MAIL_PORT: {mail_port}")
            print(f"   MAIL_USE_SSL: {mail_use_ssl}")
            print(f"   MAIL_USE_TLS: {mail_use_tls}")
            print(f"   MAIL_USERNAME: {mail_username if mail_username else '❌ НЕ НАСТРОЕН'}")
            print(f"   MAIL_PASSWORD: {'✓ НАСТРОЕН' if mail_password else '❌ НЕ НАСТРОЕН'}")
            
            if not mail_server:
                print(f"[EMAIL] ❌ КРИТИЧЕСКАЯ ОШИБКА: MAIL_SERVER не настроен в .env")
                print(f"[EMAIL] Пожалуйста, установите переменную MAIL_SERVER в файле .env")
                return
            if not mail_username:
                print(f"[EMAIL] ❌ КРИТИЧЕСКАЯ ОШИБКА: MAIL_USERNAME не настроен в .env")
                print(f"[EMAIL] Пожалуйста, установите переменную MAIL_USERNAME в файле .env")
                return
            if not mail_password:
                print(f"[EMAIL] ❌ КРИТИЧЕСКАЯ ОШИБКА: MAIL_PASSWORD не настроен в .env")
                print(f"[EMAIL] Пожалуйста, установите переменную MAIL_PASSWORD в файле .env")
                return
            
            print(f"[EMAIL] ✓ Все настройки email проверены, начинаю отправку...")
            
            # Проверяем, что объект mail инициализирован
            if not mail:
                print(f"[EMAIL] ❌ КРИТИЧЕСКАЯ ОШИБКА: Объект mail не инициализирован!")
                return
            
            print(f"[EMAIL] Создание сообщения для {recipient}...")
            
            msg = Message(subject, recipients=[recipient])
            msg.html = html_body
            
            print(f"[EMAIL] Отправка сообщения через SMTP сервер {mail_server}:{mail_port}...")
            print(f"[EMAIL] Используется SSL: {mail_use_ssl}, TLS: {mail_use_tls}")
            
            mail.send(msg)
            
            print(f"[EMAIL] ✓✓✓ Письмо успешно отправлено на {recipient} ✓✓✓")
            print(f"[EMAIL] ========== EMAIL ОТПРАВЛЕН УСПЕШНО ==========")
            
        except Exception as e:
            print(f"[EMAIL] ❌❌❌ КРИТИЧЕСКАЯ ОШИБКА при отправке на {recipient} ❌❌❌")
            print(f"[EMAIL] Тип ошибки: {type(e).__name__}")
            print(f"[EMAIL] Сообщение об ошибке: {str(e)}")
            import traceback
            print(f"[EMAIL] Полный traceback:")
            traceback.print_exc()
            print(f"[EMAIL] ========== ОШИБКА ОТПРАВКИ EMAIL ==========")


# ----------------------------------------------------
# MIDDLEWARE - ЛОГИРОВАНИЕ ВСЕХ ЗАПРОСОВ
# ----------------------------------------------------
@app.before_request
def log_request_info():
    """Логирование всех входящих запросов для отладки"""
    if request.path.startswith('/api/public/forgot-password'):
        print(f"[MIDDLEWARE] ========== ЗАПРОС ДОШЕЛ ДО FLASK ==========")
        print(f"[MIDDLEWARE] Method: {request.method}")
        print(f"[MIDDLEWARE] Path: {request.path}")
        print(f"[MIDDLEWARE] Remote Address: {request.remote_addr}")
        print(f"[MIDDLEWARE] Headers: {dict(request.headers)}")
        print(f"[MIDDLEWARE] Data: {request.data}")
        print(f"[MIDDLEWARE] JSON: {request.json}")

# ----------------------------------------------------
# ЭНДПОИНТЫ
# ----------------------------------------------------

@app.route('/api/public/register', methods=['POST'])
@limiter.limit("5 per hour") 
def public_register():
    data = request.json
    email, password, ref_code = data.get('email'), data.get('password'), data.get('ref_code')
    
    # 🛡️ SECURITY FIX: Валидация типов
    if not isinstance(email, str) or not isinstance(password, str):
         return jsonify({"message": "Неверный формат ввода"}), 400
    if not email or not password: 
        return jsonify({"message": "Требуется адрес электронной почты и пароль"}), 400
        
    # Нормализуем email (приводим к нижнему регистру)
    email = email.strip().lower()
    
    # Проверяем существование пользователя по email (email обязателен для обычной регистрации)
    if User.query.filter_by(email=email).first(): return jsonify({"message": "User exists"}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    clean_username = email.replace("@", "_").replace(".", "_")
    
    referrer, bonus_days_new = None, 0
    if ref_code and isinstance(ref_code, str):
        referrer = User.query.filter_by(referral_code=ref_code).first()
        if referrer:
            s = ReferralSetting.query.first()
            bonus_days_new = s.invitee_bonus_days if s else 7
            
    expire_date = (datetime.now(timezone.utc) + timedelta(days=bonus_days_new)).isoformat()
    
    payload_create = { 
        "email": email, "password": password, "username": clean_username, 
        "expireAt": expire_date, 
        "activeInternalSquads": [DEFAULT_SQUAD_ID] if referrer else [] 
    }
    
    try:
        headers, cookies = get_remnawave_headers()
        resp = requests.post(f"{API_URL}/api/users", headers=headers, cookies=cookies, json=payload_create)
        resp.raise_for_status()
        remnawave_uuid = resp.json().get('response', {}).get('uuid')
        
        if not remnawave_uuid: return jsonify({"message": "Provider Error"}), 500
        
        verif_token = ''.join(random.choices(string.ascii_letters + string.digits, k=50))
        # Получаем дефолтные настройки
        sys_settings = SystemSetting.query.first() or SystemSetting(id=1)
        if not sys_settings.id: 
            db.session.add(sys_settings)
            db.session.flush()
        
        new_user = User(
            email=email, password_hash=hashed_password, remnawave_uuid=remnawave_uuid, 
            referrer_id=referrer.id if referrer else None, is_verified=False, 
            verification_token=verif_token, created_at=datetime.now(timezone.utc),
            preferred_lang=sys_settings.default_language,
            preferred_currency=sys_settings.default_currency
        )
        db.session.add(new_user)
        db.session.flush() 
        new_user.referral_code = generate_referral_code(new_user.id)
        db.session.commit()
        
        url = f"{YOUR_SERVER_IP_OR_DOMAIN}/verify?token={verif_token}"
        branding = BrandingSetting.query.first() or BrandingSetting(site_name=SERVICE_NAME, primary_color="#3F69FF", secondary_color="#ffffff", accent_color="#3F69FF")
        html = render_template('email_verification.html', verification_url=url, branding=branding, service_name=SERVICE_NAME)
        threading.Thread(target=send_email_in_background, args=(app.app_context(), email, "Подтвердите свой адрес электронной почты", html)).start()

        if referrer:
            s = ReferralSetting.query.first()
            days = s.referrer_bonus_days if s else 7
            threading.Thread(target=apply_referrer_bonus_in_background, args=(app.app_context(), referrer.remnawave_uuid, days)).start()
            
        return jsonify({"message": "Регистрация прошла успешно. Проверьте электронную почту."}), 201 
        
    except requests.exceptions.HTTPError as e: 
        print(f"HTTP Error: {e}")
        return jsonify({"message": "Provider error"}), 500 
    except Exception as e:
        print(f"Register Error: {e}")
        return jsonify({"message": "Internal Server Error"}), 500

@app.route('/api/public/forgot-password', methods=['POST', 'OPTIONS'])
@limiter.limit("5 per hour")  # Ограничение: 5 запросов в час
def forgot_password():
    """Восстановление пароля - отправка нового пароля на email"""
    print(f"[FORGOT PASSWORD] ========== ЗАПРОС ПОЛУЧЕН ==========")
    print(f"[FORGOT PASSWORD] Method: {request.method}")
    print(f"[FORGOT PASSWORD] Remote Address: {request.remote_addr}")
    print(f"[FORGOT PASSWORD] Headers: {dict(request.headers)}")
    
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        print(f"[FORGOT PASSWORD] OPTIONS запрос, возвращаем CORS headers")
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
    
    print(f"[FORGOT PASSWORD] POST запрос, продолжаем обработку")
    print(f"[FORGOT PASSWORD] Data: {request.data}")
    print(f"[FORGOT PASSWORD] Content-Type: {request.content_type}")
    try:
        data = request.json or {}
        print(f"[FORGOT PASSWORD] Данные запроса (JSON): {data}")
        email = data.get('email', '').strip().lower()
        print(f"[FORGOT PASSWORD] Email из запроса: {email}")
        
        if not email:
            print(f"[FORGOT PASSWORD] Email пустой, возвращаем 400")
            response = jsonify({"message": "Email is required"})
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
            response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
            return response, 400
        
        # Ищем пользователя по email (case-insensitive поиск)
        # Пробуем сначала точное совпадение, потом case-insensitive
        user = User.query.filter_by(email=email).first()
        if not user:
            # Если не нашли, пробуем case-insensitive поиск
            from sqlalchemy import func
            user = User.query.filter(func.lower(User.email) == email).first()
        print(f"[FORGOT PASSWORD] Пользователь найден: {user is not None}")
        if user:
            print(f"[FORGOT PASSWORD] Email пользователя в БД: {user.email}")
        
        # Всегда возвращаем успех для безопасности (чтобы не раскрывать, существует ли email)
        if not user:
            print(f"[FORGOT PASSWORD] Пользователь не найден, возвращаем успех (безопасность)")
            return jsonify({"message": "If this email exists, a password reset link has been sent"}), 200
        
        # Пытаемся получить существующий пароль из encrypted_password
        password_to_send = None
        password_source = None
        
        if fernet and user.encrypted_password:
            try:
                # Расшифровываем существующий пароль
                password_to_send = fernet.decrypt(user.encrypted_password.encode()).decode('utf-8')
                password_source = "existing"
                print(f"[FORGOT PASSWORD] Найден зашифрованный пароль, расшифрован: {password_to_send[:3]}***")
            except Exception as e:
                print(f"[FORGOT PASSWORD] Ошибка расшифровки encrypted_password: {e}")
                password_to_send = None
        
        # Если не удалось получить существующий пароль, генерируем новый
        if not password_to_send:
            import secrets
            import string
            password_to_send = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
            password_source = "new"
            print(f"[FORGOT PASSWORD] Новый пароль сгенерирован: {password_to_send[:3]}***")
            
            # Хешируем и сохраняем новый пароль
            hashed_password = bcrypt.generate_password_hash(password_to_send).decode('utf-8')
            user.password_hash = hashed_password
            
            # Сохраняем зашифрованный пароль для будущего использования
            if fernet:
                try:
                    user.encrypted_password = fernet.encrypt(password_to_send.encode()).decode()
                    print(f"[FORGOT PASSWORD] Новый пароль зашифрован и сохранен")
                except Exception as e:
                    print(f"[FORGOT PASSWORD] Ошибка шифрования нового пароля: {e}")
            
            db.session.commit()
            print(f"[FORGOT PASSWORD] Новый пароль сохранен в БД")
        
        # Отправляем пароль на email
        user_email = user.email  # Сохраняем email пользователя в отдельную переменную
        print(f"[FORGOT PASSWORD] Email пользователя для отправки: {user_email}")
        password_label = "Ваш пароль" if password_source == "existing" else "Ваш новый пароль"
        subject = f"Восстановление пароля {SERVICE_NAME}"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #4a90e2;">Восстановление пароля</h2>
                <p>Здравствуйте!</p>
                <p>Вы запросили восстановление пароля для вашего аккаунта {SERVICE_NAME}.</p>
                <p><strong>{password_label}:</strong></p>
                <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; font-family: monospace; font-size: 18px; text-align: center; letter-spacing: 2px;">
                    {password_to_send}
                </div>
                <p style="color: #666; font-size: 14px;">{"Используйте этот пароль для входа в систему." if password_source == "existing" else "Рекомендуем изменить этот пароль после входа в систему."}</p>
                <p style="color: #666; font-size: 14px;">Если вы не запрашивали восстановление пароля, проигнорируйте это письмо.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #999; font-size: 12px;">© 2025 {SERVICE_NAME}. Privacy First.</p>
            </div>
        </body>
        </html>
        """
        
        # Проверяем настройки email перед отправкой
        mail_server = app.config.get('MAIL_SERVER')
        mail_username = app.config.get('MAIL_USERNAME')
        mail_password = app.config.get('MAIL_PASSWORD')
        
        if not mail_server or not mail_username or not mail_password:
            print(f"[FORGOT PASSWORD] ❌ КРИТИЧЕСКАЯ ОШИБКА: Настройки email не полностью настроены!")
            print(f"   MAIL_SERVER: {'✓' if mail_server else '✗'} ({mail_server if mail_server else 'НЕ НАСТРОЕН'})")
            print(f"   MAIL_USERNAME: {'✓' if mail_username else '✗'} ({mail_username if mail_username else 'НЕ НАСТРОЕН'})")
            print(f"   MAIL_PASSWORD: {'✓' if mail_password else '✗'} ({'***' if mail_password else 'НЕ НАСТРОЕН'})")
            print(f"[FORGOT PASSWORD] ⚠️ Email НЕ БУДЕТ ОТПРАВЛЕН из-за отсутствия настроек!")
            # Продолжаем выполнение, но email не будет отправлен
        else:
            print(f"[FORGOT PASSWORD] ✓ Настройки email проверены:")
            print(f"   MAIL_SERVER: {mail_server}")
            print(f"   MAIL_USERNAME: {mail_username}")
            print(f"   MAIL_PASSWORD: {'***' if mail_password else 'НЕ НАСТРОЕН'}")
        
        # Отправляем email в фоновом режиме (используем тот же подход, что и при регистрации)
        print(f"[FORGOT PASSWORD] Подготовка отправки email на {user_email}")
        print(f"[FORGOT PASSWORD] Тема письма: {subject}")
        
        # Создаем поток для отправки email
        email_thread = threading.Thread(
            target=send_email_in_background,
            args=(app.app_context(), user_email, subject, html_body),
            daemon=True
        )
        email_thread.start()
        print(f"[FORGOT PASSWORD] Фоновый поток для отправки email запущен (thread ID: {email_thread.ident})")
        
        print(f"[FORGOT PASSWORD] Запрос на восстановление пароля для {user_email}, пароль {'найден' if password_source == 'existing' else 'сгенерирован'}: {password_to_send[:3]}***")
        
        response = jsonify({"message": "If this email exists, a password reset link has been sent"})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        print(f"[FORGOT PASSWORD] ✓✓✓ УСПЕШНО ЗАВЕРШЕНО, возвращаем ответ ✓✓✓")
        return response, 200
        
    except Exception as e:
        print(f"[FORGOT PASSWORD] ❌❌❌ ОШИБКА: {e} ❌❌❌")
        import traceback
        traceback.print_exc()
        # Все равно возвращаем успех для безопасности
        response = jsonify({"message": "If this email exists, a password reset link has been sent"})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200

@app.route('/api/public/login', methods=['POST'])
@limiter.limit("10 per minute")
def client_login():
    data = request.json
    email, password = data.get('email'), data.get('password')
    
    # 🛡️ SECURITY FIX
    if not isinstance(email, str) or not isinstance(password, str):
         return jsonify({"message": "Invalid input"}), 400
    
    try:
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"message": "Invalid credentials"}), 401
        # Проверяем, что у пользователя есть пароль (не Telegram пользователь)
        # Пустая строка также означает Telegram пользователя (для совместимости со старой БД)
        if not user.password_hash or user.password_hash == '':
            return jsonify({"message": "This account uses Telegram login"}), 401
        if not bcrypt.check_password_hash(user.password_hash, password):
            return jsonify({"message": "Invalid credentials"}), 401
        if not user.is_verified:
            return jsonify({"message": "Электронная почта не подтверждена", "code": "NOT_VERIFIED"}), 403 
        
        return jsonify({"token": create_local_jwt(user.id), "role": user.role}), 200
    except Exception as e: 
        print(f"Login Error: {e}")
        return jsonify({"message": "Internal Server Error"}), 500

@app.route('/api/public/telegram-login', methods=['POST'])
@limiter.limit("10 per minute")
def telegram_login():
    """
    Авторизация через Telegram.
    Принимает данные от Telegram Login Widget и проверяет их через API бота.
    """
    data = request.json
    telegram_id = data.get('id')
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    username = data.get('username', '')
    hash_value = data.get('hash')
    auth_date = data.get('auth_date')
    
    if not telegram_id or not hash_value:
        return jsonify({"message": "Invalid Telegram data"}), 400
    
    try:
        # Проверяем, существует ли пользователь с таким telegram_id
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            # Пытаемся найти пользователя через API бота
            if BOT_API_URL and BOT_API_TOKEN:
                try:
                    # Нормализуем URL - убираем лишние слэши
                    bot_api_url = BOT_API_URL.rstrip('/')
                    
                    # Пробуем оба формата заголовков (X-API-Key и Authorization: Bearer)
                    headers_list = [
                        {"X-API-Key": BOT_API_TOKEN},
                        {"Authorization": f"Bearer {BOT_API_TOKEN}"}
                    ]
                    
                    bot_resp = None
                    for headers in headers_list:
                        # Пробуем прямой запрос по telegram_id (GET /users/{telegram_id})
                        url = f"{bot_api_url}/users/{telegram_id}"
                        header_format = list(headers.keys())[0]
                        print(f"Requesting bot API (direct): {url} with {header_format}")
                        bot_resp = requests.get(url, headers=headers, timeout=10)
                        
                        if bot_resp.status_code == 200:
                            print(f"Success with {header_format}")
                            break
                        elif bot_resp.status_code == 401:
                            print(f"401 with {header_format}, trying next format...")
                            continue
                        else:
                            # Для других ошибок тоже продолжаем попытки
                            break
                    
                    # Если не получилось, пробуем через список с фильтром с тем же форматом заголовка
                    if not bot_resp or bot_resp.status_code != 200:
                        print(f"Direct request failed, trying list with filter...")
                        headers = headers_list[0]  # Используем первый формат
                        bot_resp = requests.get(
                            f"{bot_api_url}/users",
                            headers=headers,
                            params={"telegram_id": telegram_id},
                            timeout=10
                        )
                    
                    print(f"Bot API Response: Status {bot_resp.status_code}")
                    
                    if bot_resp.status_code == 200:
                        try:
                            bot_data = bot_resp.json()
                        except Exception as e:
                            print(f"Bot API JSON Parse Error: {e}")
                            print(f"Bot API Response: {bot_resp.text[:500]}")
                            return jsonify({"message": "Неверный формат ответа от API бота"}), 500
                        
                        # Обрабатываем ответ в зависимости от формата
                        bot_user = None
                        
                        # Формат 1: Прямой ответ с пользователем (GET /users/{id})
                        if isinstance(bot_data, dict) and 'response' in bot_data:
                            response_data = bot_data.get('response', {})
                            if isinstance(response_data, dict) and (response_data.get('telegram_id') == telegram_id or response_data.get('id') or response_data.get('uuid')):
                                bot_user = response_data
                        
                        # Формат 2: Объект пользователя напрямую
                        elif isinstance(bot_data, dict) and (bot_data.get('telegram_id') == telegram_id or bot_data.get('id') or bot_data.get('uuid')):
                            bot_user = bot_data
                        
                        # Формат 3: Список пользователей с фильтром
                        elif isinstance(bot_data, dict) and 'items' in bot_data:
                            for u in bot_data.get('items', []):
                                if isinstance(u, dict) and u.get('telegram_id') == telegram_id:
                                    bot_user = u
                                    break
                        
                        # Формат 4: Список пользователей в 'response'
                        elif isinstance(bot_data, dict) and 'response' in bot_data:
                            response_data = bot_data.get('response', {})
                            if isinstance(response_data, dict) and 'items' in response_data:
                                for u in response_data.get('items', []):
                                    if isinstance(u, dict) and u.get('telegram_id') == telegram_id:
                                        bot_user = u
                                        break
                            elif isinstance(response_data, list):
                                for u in response_data:
                                    if isinstance(u, dict) and u.get('telegram_id') == telegram_id:
                                        bot_user = u
                                        break
                        
                        # Формат 5: Список пользователей напрямую
                        elif isinstance(bot_data, list):
                            for u in bot_data:
                                if isinstance(u, dict) and u.get('telegram_id') == telegram_id:
                                    bot_user = u
                                    break
                        
                        if bot_user:
                            # Пытаемся получить remnawave_uuid из разных источников
                            remnawave_uuid = bot_user.get('remnawave_uuid') or bot_user.get('uuid')
                            
                            # Если UUID не найден напрямую, пробуем получить через RemnaWave API
                            if not remnawave_uuid:
                                print(f"Bot user found but no remnawave_uuid in response, trying to get from RemnaWave...")
                                
                                # Вариант 1: Получить данные пользователя через /users/{id} где id может быть telegram_id
                                # Согласно документации API бота: GET /users/{id} - ID может быть как внутренним (user.id), так и Telegram ID
                                try:
                                    print(f"Trying to get user data from bot API using telegram_id as id: {telegram_id}")
                                    for headers in headers_list:
                                        header_format = list(headers.keys())[0]
                                        bot_user_resp = requests.get(
                                            f"{bot_api_url}/users/{telegram_id}",
                                            headers=headers,
                                            timeout=10
                                        )
                                        if bot_user_resp.status_code == 200:
                                            bot_user_full = bot_user_resp.json()
                                            # Парсим ответ в зависимости от формата
                                            if isinstance(bot_user_full, dict):
                                                user_data = bot_user_full.get('response', {}) if 'response' in bot_user_full else bot_user_full
                                                # Пробуем найти стандартный UUID (не shortUUID)
                                                # UUID должен быть в формате: be7d4bb9-f083-4733-90e0-5dbab253335c
                                                potential_uuid = (user_data.get('remnawave_uuid') or 
                                                                 user_data.get('uuid') or
                                                                 user_data.get('remnawave_uuid') or
                                                                 user_data.get('user_uuid'))
                                                
                                                if potential_uuid and '-' in potential_uuid and len(potential_uuid) >= 36:
                                                    remnawave_uuid = potential_uuid
                                                    print(f"✓ Found standard UUID from bot API /users/{telegram_id}: {remnawave_uuid}")
                                                    break
                                                elif potential_uuid:
                                                    print(f"⚠️  Found non-standard UUID format from bot API: {potential_uuid[:20]}...")
                                        elif bot_user_resp.status_code == 401:
                                            print(f"401 with {header_format}, trying next format...")
                                            continue
                                        else:
                                            print(f"Bot API /users/{telegram_id} returned status {bot_user_resp.status_code}")
                                            break
                                except Exception as e:
                                    print(f"Failed to get UUID from bot API /users/{telegram_id}: {e}")
                                
                                # Вариант 1.1: Получить через эндпоинт /remnawave/users/{telegram_id}/traffic
                                if not remnawave_uuid:
                                    try:
                                        remnawave_resp = requests.get(
                                            f"{bot_api_url}/remnawave/users/{telegram_id}/traffic",
                                            headers=headers_list[0],  # Используем первый формат заголовка
                                            timeout=5
                                        )
                                        if remnawave_resp.status_code == 200:
                                            remnawave_data = remnawave_resp.json()
                                            # Пробуем найти UUID в ответе (проверяем формат)
                                            if isinstance(remnawave_data, dict):
                                                potential_uuid = remnawave_data.get('uuid') or remnawave_data.get('response', {}).get('uuid')
                                                if potential_uuid and '-' in potential_uuid and len(potential_uuid) >= 36:
                                                    remnawave_uuid = potential_uuid
                                                    print(f"✓ Found standard UUID from /remnawave/users/{telegram_id}/traffic: {remnawave_uuid}")
                                    except Exception as e:
                                        print(f"Failed to get UUID from RemnaWave endpoint: {e}")
                                
                                # Вариант 2: Получить UUID через подписку пользователя в боте
                                if not remnawave_uuid:
                                    subscription = bot_user.get('subscription', {})
                                    if subscription and isinstance(subscription, dict):
                                        # Попытка 2.1: Извлечь UUID из subscription_url (если там он есть)
                                        subscription_url = subscription.get('subscription_url', '')
                                        if subscription_url:
                                            # subscription_url имеет формат: https://admin.stealthnet.app/{UUID}
                                            # Пробуем извлечь UUID из URL
                                            import re
                                            url_parts = subscription_url.split('/')
                                            if len(url_parts) > 0:
                                                potential_uuid = url_parts[-1]  # Последняя часть URL
                                                # Проверяем, что это похоже на UUID (не пустой, не слишком короткий)
                                                if potential_uuid and len(potential_uuid) > 10:
                                                    # Проверяем, является ли это стандартным UUID (содержит дефисы) или shortUUID
                                                    # Стандартный UUID формат: be7d4bb9-f083-4733-90e0-5dbab253335c (с дефисами)
                                                    # ShortUUID формат: aBtzyf4hQgycgvN4 (без дефисов, короткий)
                                                    if '-' in potential_uuid and len(potential_uuid) > 30:
                                                        # Это стандартный UUID - используем напрямую
                                                        remnawave_uuid = potential_uuid
                                                        print(f"✓ Found standard UUID in subscription_url: {remnawave_uuid}")
                                                    else:
                                                        # Это shortUUID - сохраняем для поиска в RemnaWave API
                                                        short_uuid_from_url = potential_uuid
                                                        print(f"✓ Found shortUUID in subscription_url: {short_uuid_from_url}")
                                                        print(f"   Will search for user with this shortUUID in RemnaWave API...")
                                                        
                                                        # Получаем пользователя из RemnaWave API по shortUUID
                                                        # Согласно документации RemnaWave API: GET /api/users/by-short-uuid/{shortUuid}
                                                        if API_URL and ADMIN_TOKEN:
                                                            try:
                                                                print(f"Fetching user from RemnaWave API by shortUUID: {short_uuid_from_url}")
                                                                
                                                                # Используем прямой эндпоинт для получения пользователя по shortUUID
                                                                remnawave_short_uuid_resp = requests.get(
                                                                    f"{API_URL}/api/users/by-short-uuid/{short_uuid_from_url}",
                                                                    headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                                                                    timeout=10
                                                                )
                                                                
                                                                if remnawave_short_uuid_resp.status_code == 200:
                                                                    remnawave_short_uuid_data = remnawave_short_uuid_resp.json()
                                                                    
                                                                    # Парсим ответ в зависимости от формата
                                                                    user_data = remnawave_short_uuid_data.get('response', {}) if isinstance(remnawave_short_uuid_data, dict) and 'response' in remnawave_short_uuid_data else remnawave_short_uuid_data
                                                                    
                                                                    # Получаем стандартный UUID пользователя
                                                                    potential_uuid = user_data.get('uuid') if isinstance(user_data, dict) else None
                                                                    
                                                                    if potential_uuid and '-' in potential_uuid and len(potential_uuid) >= 36:
                                                                        remnawave_uuid = potential_uuid
                                                                        print(f"✓ Found remnawave_uuid by shortUUID endpoint: {remnawave_uuid}")
                                                                    else:
                                                                        print(f"⚠️  Invalid UUID format in RemnaWave API response: {potential_uuid}")
                                                                elif remnawave_short_uuid_resp.status_code == 404:
                                                                    print(f"⚠️  User with shortUUID {short_uuid_from_url} not found in RemnaWave API (404)")
                                                                else:
                                                                    print(f"⚠️  Failed to fetch user by shortUUID: Status {remnawave_short_uuid_resp.status_code}")
                                                                    print(f"   Falling back to fetching all users...")
                                                                    
                                                                    # Fallback: получаем всех пользователей, если прямой эндпоинт не сработал
                                                                    print(f"Fetching all users from RemnaWave API to find user with shortUUID: {short_uuid_from_url}")
                                                                    remnawave_all_resp = requests.get(
                                                                        f"{API_URL}/api/users",
                                                                        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                                                                        timeout=15
                                                                    )
                                                                    
                                                                    if remnawave_all_resp.status_code == 200:
                                                                        remnawave_all_data = remnawave_all_resp.json()
                                                                        # Парсим ответ в зависимости от формата
                                                                        all_users_list = []
                                                                        if isinstance(remnawave_all_data, dict):
                                                                            response_data = remnawave_all_data.get('response', {})
                                                                            if isinstance(response_data, dict):
                                                                                all_users_list = response_data.get('users', [])
                                                                            elif isinstance(response_data, list):
                                                                                all_users_list = response_data
                                                                        elif isinstance(remnawave_all_data, list):
                                                                            all_users_list = remnawave_all_data
                                                                    
                                                                    print(f"Searching in {len(all_users_list)} RemnaWave users for shortUUID: {short_uuid_from_url}")
                                                                    
                                                                    # Ищем пользователя, у которого shortUUID совпадает
                                                                    # shortUUID может быть в subscription_url, short_uuid, или других полях
                                                                    for rw_user in all_users_list:
                                                                        if isinstance(rw_user, dict):
                                                                            rw_uuid = rw_user.get('uuid')
                                                                            
                                                                            # Проверяем, что UUID в правильном формате
                                                                            if rw_uuid and '-' in rw_uuid and len(rw_uuid) >= 36:
                                                                                # Проверяем различные поля, где может быть shortUUID
                                                                                # 1. В subscription_url
                                                                                subscriptions = rw_user.get('subscriptions', []) or []
                                                                                for sub in subscriptions:
                                                                                    if isinstance(sub, dict):
                                                                                        sub_url = sub.get('url', '') or sub.get('subscription_url', '') or sub.get('link', '')
                                                                                        if short_uuid_from_url in sub_url:
                                                                                            remnawave_uuid = rw_uuid
                                                                                            print(f"✓ Found remnawave_uuid by shortUUID in subscription_url: {remnawave_uuid}")
                                                                                            break
                                                                                
                                                                                if remnawave_uuid:
                                                                                    break
                                                                                
                                                                                # 2. В поле short_uuid или shortUuid
                                                                                if (rw_user.get('short_uuid') == short_uuid_from_url or 
                                                                                    rw_user.get('shortUuid') == short_uuid_from_url or
                                                                                    rw_user.get('short_uuid') == short_uuid_from_url):
                                                                                    remnawave_uuid = rw_uuid
                                                                                    print(f"✓ Found remnawave_uuid by shortUUID field: {remnawave_uuid}")
                                                                                    break
                                                                                
                                                                                # 3. В metadata или customFields
                                                                                metadata = rw_user.get('metadata', {}) or {}
                                                                                custom_fields = rw_user.get('customFields', {}) or {}
                                                                                if (metadata.get('short_uuid') == short_uuid_from_url or
                                                                                    custom_fields.get('short_uuid') == short_uuid_from_url or
                                                                                    custom_fields.get('shortUuid') == short_uuid_from_url):
                                                                                    remnawave_uuid = rw_uuid
                                                                                    print(f"✓ Found remnawave_uuid by shortUUID in metadata/customFields: {remnawave_uuid}")
                                                                                    break
                                                                    
                                                                        if not remnawave_uuid:
                                                                            print(f"⚠️  User with shortUUID {short_uuid_from_url} not found in RemnaWave API")
                                                                            print(f"   Searched in {len(all_users_list)} users")
                                                                    else:
                                                                        print(f"Failed to fetch users from RemnaWave API: Status {remnawave_all_resp.status_code}")
                                                            except Exception as e:
                                                                print(f"Error searching for user by shortUUID in RemnaWave API: {e}")
                                                                import traceback
                                                                traceback.print_exc()
                                        
                                        # Попытка 2.2: Получить UUID через эндпоинт подписки
                                        if not remnawave_uuid:
                                            subscription_id = subscription.get('id')
                                            if subscription_id:
                                                try:
                                                    sub_resp = requests.get(
                                                        f"{bot_api_url}/subscriptions/{subscription_id}",
                                                        headers=headers_list[0],
                                                        timeout=5
                                                    )
                                                    if sub_resp.status_code == 200:
                                                        sub_data = sub_resp.json()
                                                        # Пробуем найти UUID в ответе
                                                        if isinstance(sub_data, dict):
                                                            response_data = sub_data.get('response', {}) if 'response' in sub_data else sub_data
                                                            remnawave_uuid = (response_data.get('uuid') or 
                                                                             response_data.get('remnawave_uuid') or
                                                                             response_data.get('user_uuid') or
                                                                             response_data.get('remnawave_user_uuid'))
                                                            if remnawave_uuid:
                                                                print(f"Found remnawave_uuid from subscription endpoint: {remnawave_uuid}")
                                                except Exception as e:
                                                    print(f"Failed to get UUID from subscription endpoint: {e}")
                            
                            # Вариант 3: Попробовать найти пользователя в RemnaWave API напрямую по telegram_id
                                # Согласно документации RemnaWave API: GET /api/users поддерживает фильтрацию
                                if not remnawave_uuid and API_URL and ADMIN_TOKEN:
                                    try:
                                        # Получаем список всех пользователей из RemnaWave
                                        remnawave_resp = requests.get(
                                            f"{API_URL}/api/users",
                                            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                                            timeout=10
                                        )
                                        if remnawave_resp.status_code == 200:
                                            remnawave_data = remnawave_resp.json()
                                            # Парсим ответ в зависимости от формата
                                            users_list = []
                                            if isinstance(remnawave_data, dict):
                                                response_data = remnawave_data.get('response', {})
                                                if isinstance(response_data, dict):
                                                    users_list = response_data.get('users', [])
                                                elif isinstance(response_data, list):
                                                    users_list = response_data
                                            elif isinstance(remnawave_data, list):
                                                users_list = remnawave_data
                                            
                                            print(f"Searching for user with telegram_id {telegram_id} in {len(users_list)} RemnaWave users...")
                                            
                                            # Ищем пользователя по telegram_id (если он есть в RemnaWave)
                                            # Согласно документации RemnaWave API, можно искать по разным полям
                                            bot_email = bot_user.get('email') or f"tg_{telegram_id}@telegram.local"
                                            bot_username = bot_user.get('username') or bot_user.get('first_name', '')
                                            
                                            print(f"Searching in {len(users_list)} RemnaWave users for telegram_id: {telegram_id}")
                                            
                                            for u in users_list:
                                                if isinstance(u, dict):
                                                    uuid_value = u.get('uuid')
                                                    
                                                    # Проверяем, что UUID в правильном формате (стандартный UUID с дефисами)
                                                    # Стандартный UUID: be7d4bb9-f083-4733-90e0-5dbab253335c (36 символов с дефисами)
                                                    # ShortUUID: aBtzyf4hQgycgvN4 (без дефисов, короткий)
                                                    if uuid_value and '-' in uuid_value and len(uuid_value) >= 36:
                                                        # Приоритет 1: Проверяем по telegram_id (если поле есть в RemnaWave)
                                                        # Согласно документации RemnaWave, telegram_id может быть в разных полях
                                                        user_telegram_id = (u.get('telegram_id') or 
                                                                           u.get('metadata', {}).get('telegram_id') or
                                                                           u.get('customFields', {}).get('telegram_id') or
                                                                           u.get('customFields', {}).get('telegramId'))
                                                        if user_telegram_id and str(user_telegram_id) == str(telegram_id):
                                                            remnawave_uuid = uuid_value
                                                            print(f"✓ Found remnawave_uuid by telegram_id: {remnawave_uuid}")
                                                            break
                                                        
                                                        # Приоритет 2: Проверяем по email
                                                        if u.get('email') and u.get('email') == bot_email:
                                                            remnawave_uuid = uuid_value
                                                            print(f"✓ Found remnawave_uuid by email: {remnawave_uuid}")
                                                            break
                                                        
                                                        # Приоритет 3: Проверяем по username (точное или частичное совпадение)
                                                        if bot_username and u.get('username'):
                                                            user_username = u.get('username', '').lower()
                                                            bot_username_lower = bot_username.lower()
                                                            if user_username == bot_username_lower or bot_username_lower in user_username:
                                                                remnawave_uuid = uuid_value
                                                                print(f"✓ Found remnawave_uuid by username: {remnawave_uuid}")
                                                                break
                                                    elif uuid_value:
                                                        # Если UUID в нестандартном формате, пропускаем его
                                                        print(f"⚠️  Skipping user with non-standard UUID format: {uuid_value[:20]}...")
                                            
                                            if not remnawave_uuid:
                                                print(f"⚠️  User not found in RemnaWave API by telegram_id ({telegram_id}), email, or username")
                                                print(f"   Searched in {len(users_list)} users")
                                                # Выводим несколько примеров для отладки
                                                if users_list:
                                                    print(f"   Sample users (first 3): {[{'uuid': u.get('uuid'), 'email': u.get('email'), 'username': u.get('username'), 'telegram_id': u.get('telegram_id')} for u in users_list[:3] if isinstance(u, dict)]}")
                                    except Exception as e:
                                        print(f"Failed to find user in RemnaWave API: {e}")
                                        import traceback
                                        traceback.print_exc()
                            
                            # Если UUID все еще не найден, возвращаем ошибку
                            if not remnawave_uuid:
                                print(f"Bot user found but no remnawave_uuid: {bot_user}")
                                return jsonify({
                                    "message": "Пользователь найден в боте, но не найден в RemnaWave. Обратитесь к администратору или синхронизируйте данные бота с RemnaWave.",
                                    "details": "Возможно, пользователь не был синхронизирован с RemnaWave панелью."
                                }), 404
                            
                            # Проверяем, не существует ли уже пользователь с таким remnawave_uuid
                            existing_user = User.query.filter_by(remnawave_uuid=remnawave_uuid).first()
                            if existing_user:
                                # Обновляем существующего пользователя
                                existing_user.telegram_id = telegram_id
                                existing_user.telegram_username = username
                                if not existing_user.email:
                                    existing_user.email = f"tg_{telegram_id}@telegram.local"  # Временный email
                                # Обновляем password_hash для совместимости, если это Telegram пользователь
                                if not existing_user.password_hash:
                                    existing_user.password_hash = ''  # Пустая строка для Telegram пользователей
                                db.session.commit()
                                user = existing_user
                                print(f"Telegram user linked to existing user: {user.id}")
                            else:
                                # Создаем нового пользователя
                                sys_settings = SystemSetting.query.first() or SystemSetting(id=1)
                                if not sys_settings.id:
                                    db.session.add(sys_settings)
                                    db.session.flush()
                                
                                # Для Telegram пользователей создаем пустой password_hash
                                # Если БД еще не обновлена (password_hash NOT NULL), используем пустую строку
                                # В идеале должно быть None, но для совместимости со старой структурой БД используем ''
                                user = User(
                                    telegram_id=telegram_id,
                                    telegram_username=username,
                                    email=f"tg_{telegram_id}@telegram.local",  # Временный email
                                    password_hash='',  # Telegram пользователи не используют пароль (используем '' для совместимости со старой БД)
                                    remnawave_uuid=remnawave_uuid,
                                    is_verified=True,  # Telegram пользователи считаются верифицированными
                                    preferred_lang=sys_settings.default_language,
                                    preferred_currency=sys_settings.default_currency
                                )
                                db.session.add(user)
                                db.session.flush()
                                user.referral_code = generate_referral_code(user.id)
                                db.session.commit()
                                
                                # Очищаем кэш для нового пользователя, чтобы данные загрузились сразу
                                cache.delete(f'live_data_{remnawave_uuid}')
                                cache.delete(f'nodes_{remnawave_uuid}')
                                cache.delete('all_live_users_map')  # Очищаем общий кэш
                                print(f"New Telegram user created: {user.id}, telegram_id: {telegram_id}, remnawave_uuid: {remnawave_uuid}")
                        else:
                            print(f"User with telegram_id {telegram_id} not found in bot response")
                            print(f"Bot API response structure: {type(bot_data)}")
                            if isinstance(bot_data, dict):
                                print(f"Bot API response keys: {list(bot_data.keys())}")
                            return jsonify({"message": "Пользователь не найден в боте. Убедитесь, что вы зарегистрированы через Telegram бота."}), 404
                    else:
                        error_text = bot_resp.text[:500] if hasattr(bot_resp, 'text') else 'No error details'
                        print(f"Bot API Error: Status {bot_resp.status_code}, Response: {error_text}")
                        
                        error_msg = "Ошибка подключения к API бота"
                        if bot_resp.status_code == 401:
                            error_msg = f"Неверный токен API бота (401). Проверьте BOT_API_TOKEN в .env файле. Ответ API: {error_text}"
                        elif bot_resp.status_code == 404:
                            error_msg = f"Пользователь не найден в API бота (404). Проверьте, что вы зарегистрированы через Telegram бота. Ответ API: {error_text}"
                        elif bot_resp.status_code == 403:
                            error_msg = "Доступ к API бота запрещен. Проверьте токен и права доступа."
                        else:
                            error_msg = f"Ошибка API бота (код {bot_resp.status_code}): {error_text}"
                        
                        return jsonify({"message": error_msg}), 500
                except requests.Timeout:
                    print(f"Bot API Timeout: {BOT_API_URL}")
                    return jsonify({"message": "Таймаут подключения к API бота. Проверьте доступность сервера."}), 500
                except requests.ConnectionError as e:
                    print(f"Bot API Connection Error: {e}")
                    return jsonify({"message": "Не удалось подключиться к API бота. Проверьте BOT_API_URL в настройках."}), 500
                except requests.RequestException as e:
                    print(f"Bot API Request Error: {e}")
                    return jsonify({"message": f"Ошибка запроса к API бота: {str(e)[:100]}"}), 500
            else:
                return jsonify({"message": "Bot API not configured"}), 500
        
        # Обновляем username если изменился
        if username and user.telegram_username != username:
            user.telegram_username = username
            db.session.commit()
        
        # Очищаем кэш для пользователя, чтобы данные обновились после входа
        cache.delete(f'live_data_{user.remnawave_uuid}')
        cache.delete(f'nodes_{user.remnawave_uuid}')
        
        return jsonify({"token": create_local_jwt(user.id), "role": user.role}), 200
        
    except Exception as e:
        print(f"Telegram Login Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Server Error"}), 500

@app.route('/api/client/me', methods=['GET'])
def get_client_me():
    user = get_user_from_token()
    if not user: return jsonify({"message": "Ошибка аутентификации"}), 401
    
    # Проверяем, является ли UUID shortUUID (без дефисов или слишком короткий)
    # Если это shortUUID, пытаемся найти стандартный UUID
    current_uuid = user.remnawave_uuid
    is_short_uuid = (not current_uuid or 
                     '-' not in current_uuid or 
                     len(current_uuid) < 36)
    
    if is_short_uuid and current_uuid:
        print(f"⚠️  User {user.id} has shortUUID: {current_uuid}")
        print(f"   Getting user with this shortUUID from RemnaWave API...")
        
        # Сохраняем оригинальный shortUUID для использования в fallback логике
        original_short_uuid = current_uuid
        
        # Получаем пользователя из RemnaWave API по shortUUID
        # Согласно документации RemnaWave API: GET /api/users/by-short-uuid/{shortUuid}
        found_uuid = None
        if API_URL and ADMIN_TOKEN:
            try:
                print(f"Fetching user from RemnaWave API by shortUUID: {original_short_uuid}")
                
                # Используем прямой эндпоинт для получения пользователя по shortUUID
                remnawave_short_uuid_resp = requests.get(
                    f"{API_URL}/api/users/by-short-uuid/{original_short_uuid}",
                    headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                    timeout=10
                )
                
                if remnawave_short_uuid_resp.status_code == 200:
                    remnawave_short_uuid_data = remnawave_short_uuid_resp.json()
                    
                    # Парсим ответ в зависимости от формата
                    user_data = remnawave_short_uuid_data.get('response', {}) if isinstance(remnawave_short_uuid_data, dict) and 'response' in remnawave_short_uuid_data else remnawave_short_uuid_data
                    
                    # Получаем стандартный UUID пользователя
                    found_uuid = user_data.get('uuid') if isinstance(user_data, dict) else None
                    
                    if found_uuid and '-' in found_uuid and len(found_uuid) >= 36:
                        # Обновляем UUID в базе данных
                        old_uuid = user.remnawave_uuid
                        user.remnawave_uuid = found_uuid
                        db.session.commit()
                        current_uuid = found_uuid
                        
                        # Очищаем старый кэш
                        if old_uuid:
                            cache.delete(f'live_data_{old_uuid}')
                            cache.delete(f'nodes_{old_uuid}')
                        
                        print(f"✓ Updated UUID for user {user.id}: {old_uuid} -> {current_uuid}")
                        # Выходим, так как UUID успешно обновлен
                        found_uuid = True  # Флаг успешного обновления
                    else:
                        print(f"⚠️  Invalid UUID format in RemnaWave API response: {found_uuid}")
                elif remnawave_short_uuid_resp.status_code == 404:
                    print(f"⚠️  User with shortUUID {original_short_uuid} not found in RemnaWave API (404)")
                else:
                    print(f"⚠️  Failed to fetch user by shortUUID: Status {remnawave_short_uuid_resp.status_code}")
                    print(f"   Response: {remnawave_short_uuid_resp.text[:200]}")
                
                # Если прямой эндпоинт не сработал, пробуем получить всех пользователей (fallback)
                # Используем оригинальный shortUUID, а не обновленный UUID
                if not found_uuid:
                    print(f"   Falling back to fetching all users from RemnaWave API to search for shortUUID: {original_short_uuid}...")
                    
                    # Получаем всех пользователей с учетом пагинации
                    all_users_list = []
                    page = 1
                    per_page = 100  # Запрашиваем больше пользователей за раз
                    has_more = True
                    
                    while has_more:
                        try:
                            # Формируем параметры запроса
                            params = {}
                            if page > 1:
                                params["page"] = page
                            if per_page != 100:
                                params["per_page"] = per_page
                            
                            remnawave_all_resp = requests.get(
                                f"{API_URL}/api/users",
                                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                                params=params if params else None,
                                timeout=20
                            )
                            
                            if remnawave_all_resp.status_code == 200:
                                remnawave_all_data = remnawave_all_resp.json()
                                
                                # Парсим ответ в зависимости от формата
                                page_users = []
                                total_users = 0
                                total_pages = 1
                                
                                if isinstance(remnawave_all_data, dict):
                                    response_data = remnawave_all_data.get('response', {})
                                    if isinstance(response_data, dict):
                                        # Проверяем, есть ли пагинация
                                        if 'users' in response_data:
                                            page_users = response_data.get('users', [])
                                        elif 'items' in response_data:
                                            page_users = response_data.get('items', [])
                                        else:
                                            page_users = []
                                        
                                        # Проверяем метаданные пагинации
                                        total_users = response_data.get('total', response_data.get('totalUsers', len(page_users)))
                                        total_pages = response_data.get('totalPages', response_data.get('pages', 1))
                                        current_page = response_data.get('page', response_data.get('currentPage', page))
                                    elif isinstance(response_data, list):
                                        page_users = response_data
                                        has_more = False  # Если это список, значит пагинации нет
                                elif isinstance(remnawave_all_data, list):
                                    page_users = remnawave_all_data
                                    has_more = False  # Если это список, значит пагинации нет
                                
                                if page_users:
                                    all_users_list.extend(page_users)
                                    print(f"Fetched page {page}: {len(page_users)} users (total so far: {len(all_users_list)})")
                                    
                                    # Проверяем, есть ли еще страницы
                                    # Если total_pages указан и мы не на последней странице - продолжаем
                                    if total_pages > 1 and page < total_pages:
                                        page += 1
                                        has_more = True
                                        print(f"   Continuing to page {page} (total pages: {total_pages})")
                                    elif len(page_users) < per_page:
                                        # Если получили меньше пользователей, чем запросили, значит это последняя страница
                                        has_more = False
                                        print(f"   Last page reached (got {len(page_users)} < {per_page})")
                                    elif len(page_users) == per_page:
                                        # Если получили ровно столько, сколько запросили, возможно есть еще страницы
                                        # Пробуем запросить следующую страницу
                                        page += 1
                                        has_more = True
                                        print(f"   Got full page ({len(page_users)} users), trying page {page}...")
                                    else:
                                        has_more = False
                                else:
                                    # Если не получили пользователей, прекращаем
                                    has_more = False
                                    print(f"   No users on page {page}, stopping")
                            else:
                                print(f"Failed to fetch page {page} from RemnaWave API: Status {remnawave_all_resp.status_code}")
                                has_more = False
                        except requests.RequestException as e:
                            print(f"Error fetching page {page} from RemnaWave API: {e}")
                            has_more = False
                
                    # Используем оригинальный shortUUID для поиска в fallback логике
                    print(f"Searching in {len(all_users_list)} RemnaWave users for shortUUID: {original_short_uuid}")
                    
                    # Ищем пользователя, у которого shortUUID совпадает
                    found_uuid_in_list = None
                    for rw_user in all_users_list:
                        if isinstance(rw_user, dict):
                            rw_uuid = rw_user.get('uuid')
                            
                            # Проверяем, что UUID в правильном формате
                            if rw_uuid and '-' in rw_uuid and len(rw_uuid) >= 36:
                                # Проверяем различные поля, где может быть shortUUID
                                # 1. В subscription_url
                                subscriptions = rw_user.get('subscriptions', []) or []
                                for sub in subscriptions:
                                    if isinstance(sub, dict):
                                        sub_url = sub.get('url', '') or sub.get('subscription_url', '') or sub.get('link', '')
                                        if original_short_uuid in sub_url:
                                            found_uuid_in_list = rw_uuid
                                            print(f"✓ Found remnawave_uuid by shortUUID in subscription_url: {found_uuid_in_list}")
                                            break
                                
                                if found_uuid_in_list:
                                    break
                                
                                # 2. В поле short_uuid или shortUuid
                                if (rw_user.get('short_uuid') == original_short_uuid or 
                                    rw_user.get('shortUuid') == original_short_uuid):
                                    found_uuid_in_list = rw_uuid
                                    print(f"✓ Found remnawave_uuid by shortUUID field: {found_uuid_in_list}")
                                    break
                                
                                # 3. В metadata или customFields
                                metadata = rw_user.get('metadata', {}) or {}
                                custom_fields = rw_user.get('customFields', {}) or {}
                                if (metadata.get('short_uuid') == original_short_uuid or
                                    custom_fields.get('short_uuid') == original_short_uuid or
                                    custom_fields.get('shortUuid') == original_short_uuid):
                                    found_uuid_in_list = rw_uuid
                                    print(f"✓ Found remnawave_uuid by shortUUID in metadata/customFields: {found_uuid_in_list}")
                                    break
                    
                    # Обновляем UUID только если нашли через fallback (если прямой эндпоинт не сработал)
                    if found_uuid_in_list:
                        # Обновляем UUID в базе данных
                        old_uuid = user.remnawave_uuid
                        user.remnawave_uuid = found_uuid_in_list
                        db.session.commit()
                        current_uuid = found_uuid_in_list
                        
                        # Очищаем старый кэш
                        if old_uuid:
                            cache.delete(f'live_data_{old_uuid}')
                            cache.delete(f'nodes_{old_uuid}')
                        
                        print(f"✓ Updated UUID for user {user.id} (fallback): {old_uuid} -> {current_uuid}")
                    else:
                        print(f"⚠️  User with shortUUID {original_short_uuid} not found in RemnaWave API")
                        print(f"   Searched in {len(all_users_list)} users")
            except Exception as e:
                print(f"Error searching for user by shortUUID in RemnaWave API: {e}")
                import traceback
                traceback.print_exc()
    
    cache_key = f'live_data_{current_uuid}'
    
    # Проверяем параметр force_refresh для принудительного обновления
    force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
    
    if not force_refresh:
        if cached := cache.get(cache_key):
            # ВСЕГДА обновляем preferred_lang и preferred_currency из БД, даже если данные из кэша
            # Это нужно, чтобы изменения настроек сразу отображались
            if isinstance(cached, dict):
                cached = cached.copy()  # Создаем копию, чтобы не изменять оригинал в кэше
                # Баланс хранится в USD, конвертируем в предпочитаемую валюту для бота
                balance_usd = float(user.balance) if user.balance else 0.0
                balance_converted = convert_from_usd(balance_usd, user.preferred_currency)
                cached.update({
                    'referral_code': user.referral_code, 
                    'preferred_lang': user.preferred_lang, 
                    'preferred_currency': user.preferred_currency,
                    'telegram_id': user.telegram_id,
                    'telegram_username': user.telegram_username,
                    'balance_usd': balance_usd,  # Баланс в USD для конвертации на фронтенде
                    'balance': balance_converted  # Баланс в предпочитаемой валюте для бота и обратной совместимости
                })
            return jsonify({"response": cached}), 200
    
    try:
        # Согласно документации RemnaWave API: GET /api/users/{uuid}
        # UUID должен быть стандартным (с дефисами)
        if is_short_uuid and current_uuid:
            return jsonify({
                "message": f"Некорректный UUID пользователя: {current_uuid}. Обратитесь к администратору.",
                "error": "INVALID_UUID_FORMAT"
            }), 400
        
        resp = requests.get(
            f"{API_URL}/api/users/{current_uuid}", 
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            timeout=10
        )
        
        if resp.status_code != 200:
            print(f"RemnaWave API Error for UUID {current_uuid}: Status {resp.status_code}")
            error_text = resp.text[:500] if hasattr(resp, 'text') else 'No error details'
            print(f"Error response: {error_text}")
            
            # Если пользователь не найден, возвращаем ошибку
            if resp.status_code == 404:
                return jsonify({"message": f"Пользователь не найден в RemnaWave (UUID: {current_uuid}). Обратитесь к администратору."}), 404
            
            # Если ошибка валидации UUID (400), возможно это shortUUID
            if resp.status_code == 400 and 'Invalid uuid' in error_text:
                return jsonify({
                    "message": f"Некорректный формат UUID: {current_uuid}. Обратитесь к администратору для исправления.",
                    "error": "INVALID_UUID_FORMAT"
                }), 400
            
            return jsonify({"message": f"Ошибка получения данных из RemnaWave: {resp.status_code}"}), 500
        
        response_data = resp.json()
        data = response_data.get('response', {}) if isinstance(response_data, dict) else response_data
        
        # Добавляем данные из локальной БД
        if isinstance(data, dict):
            # Баланс хранится в USD, конвертируем в предпочитаемую валюту для бота
            balance_usd = float(user.balance) if user.balance else 0.0
            balance_converted = convert_from_usd(balance_usd, user.preferred_currency)
            data.update({
                'referral_code': user.referral_code, 
                'preferred_lang': user.preferred_lang, 
                'preferred_currency': user.preferred_currency,
                'telegram_id': user.telegram_id,
                'telegram_username': user.telegram_username,
                'balance_usd': balance_usd,  # Баланс в USD для конвертации на фронтенде
                'balance': balance_converted  # Баланс в предпочитаемой валюте для бота и обратной совместимости
            })
        
        cache.set(cache_key, data, timeout=300)
        return jsonify({"response": data}), 200
    except requests.RequestException as e:
        print(f"Request Error in get_client_me: {e}")
        return jsonify({"message": f"Ошибка подключения к RemnaWave API: {str(e)}"}), 500
    except Exception as e: 
        print(f"Error in get_client_me: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Error"}), 500

@app.route('/api/client/activate-trial', methods=['POST'])
def activate_trial():
    user = get_user_from_token()
    if not user: return jsonify({"message": "Ошибка аутентификации"}), 401
    try:
        new_exp = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        
        # Получаем сквад для триала из настроек, если не указан - используем дефолтный
        referral_settings = ReferralSetting.query.first()
        trial_squad_id = DEFAULT_SQUAD_ID
        if referral_settings and referral_settings.trial_squad_id:
            trial_squad_id = referral_settings.trial_squad_id
        
        headers, cookies = get_remnawave_headers()
        requests.patch(f"{API_URL}/api/users", headers=headers, cookies=cookies, 
                       json={"uuid": user.remnawave_uuid, "expireAt": new_exp, "activeInternalSquads": [trial_squad_id]})
        cache.delete(f'live_data_{user.remnawave_uuid}')
        cache.delete('all_live_users_map')
        cache.delete(f'nodes_{user.remnawave_uuid}')  # Очищаем кэш серверов при изменении сквада
        return jsonify({"message": "Trial activated"}), 200
    except Exception as e: return jsonify({"message": "Internal Error"}), 500

@app.route('/miniapp/subscription', methods=['POST', 'OPTIONS'])
@limiter.limit("30 per minute")
def miniapp_subscription():
    """
    Эндпоинт для получения данных подписки в Telegram Mini App.
    Принимает initData от Telegram Web App и возвращает данные пользователя.
    """
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    print(f"[MINIAPP] POST /miniapp/subscription received")
    print(f"[MINIAPP] Content-Type: {request.content_type}")
    print(f"[MINIAPP] Method: {request.method}")
    
    try:
        # Пробуем получить данные из разных источников
        data = {}
        
        # 1. Пробуем JSON
        try:
            if request.is_json:
                data = request.json or {}
                print(f"[MINIAPP] Data from JSON: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
        except Exception as e:
            print(f"[MINIAPP] Error parsing JSON: {e}")
        
        # 2. Пробуем form-data
        if not data and request.form:
            data = dict(request.form)
            print(f"[MINIAPP] Data from form: {list(data.keys())}")
        
        # 3. Пробуем raw data
        if not data and request.data:
            try:
                import json as json_lib
                raw_data = request.data.decode('utf-8')
                print(f"[MINIAPP] Raw data preview: {raw_data[:200]}")
                # Пробуем распарсить как JSON
                if raw_data.strip().startswith('{') or raw_data.strip().startswith('['):
                    data = json_lib.loads(raw_data)
                    print(f"[MINIAPP] Data from raw JSON: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                else:
                    # Если не JSON, пробуем как URL-encoded
                    import urllib.parse
                    data = urllib.parse.parse_qs(raw_data)
                    # Преобразуем списки в строки
                    data = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in data.items()}
                    print(f"[MINIAPP] Data from URL-encoded: {list(data.keys())}")
            except Exception as e:
                print(f"[MINIAPP] Error parsing raw data: {e}")
        
        # Логируем входящие данные для отладки
        print(f"[MINIAPP] Final data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
        
        # Пробуем получить initData из разных возможных полей
        init_data = data.get('initData') or data.get('init_data') or data.get('data') or ''
        
        if not init_data:
            # Если initData отсутствует, логируем подробную информацию
            print(f"[MINIAPP] No initData found. Request details:")
            print(f"  - Content-Type: {request.content_type}")
            print(f"  - Has JSON: {request.is_json}")
            print(f"  - Has form: {bool(request.form)}")
            print(f"  - Has data: {bool(request.data)}")
            print(f"  - Data length: {len(request.data) if request.data else 0}")
            if request.data:
                try:
                    print(f"  - Data preview: {request.data.decode('utf-8')[:500]}")
                except:
                    print(f"  - Data (bytes): {request.data[:100]}")
            
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Missing initData. Please open the mini app from Telegram.",
                    "hint": "The mini app must be opened from Telegram to work properly."
                }
            }), 401
        
        # Парсим initData от Telegram Web App
        # Формат: user=%7B%22id%22%3A123456789%2C...%7D&auth_date=1234567890&hash=...
        import urllib.parse
        import json as json_lib
        
        parsed_data = urllib.parse.parse_qs(init_data)
        user_str = parsed_data.get('user', [''])[0]
        
        if not user_str:
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Invalid initData format. Please open the mini app from Telegram."
                }
            }), 401
        
        # Декодируем JSON из user параметра
        try:
            user_data = json_lib.loads(urllib.parse.unquote(user_str))
            telegram_id = user_data.get('id')
        except (json_lib.JSONDecodeError, KeyError):
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Invalid user data in initData."
                }
            }), 401
        
        if not telegram_id:
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Telegram ID not found in initData."
                }
            }), 401
        
        # Находим пользователя по telegram_id
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            return jsonify({
                "detail": {
                    "title": "User Not Found",
                    "message": "User not registered. Please register in the bot first.",
                    "code": "user_not_found"
                }
            }), 404
        
        # Вспомогательная функция для адаптации данных под miniapp
        def adapt_data_for_miniapp(data_dict, user_obj):
            """Адаптирует данные под формат, ожидаемый miniapp"""
            if not isinstance(data_dict, dict):
                return data_dict
            
            # Проверяем, есть ли активная подписка
            expire_at = data_dict.get('expireAt') or data_dict.get('expire_at')
            has_active_subscription = False
            if expire_at:
                try:
                    expire_dt = parse_iso_datetime(expire_at) if isinstance(expire_at, str) else expire_at
                    now = datetime.now(timezone.utc)
                    has_active_subscription = expire_dt > now if expire_dt else False
                except:
                    has_active_subscription = False
            
            # Формируем объект user, как ожидает miniapp
            username = user_obj.telegram_username or f"user_{user_obj.telegram_id}"
            display_name = user_obj.telegram_username or f"User {user_obj.telegram_id}"
            
            user_data = {
                'id': user_obj.telegram_id,
                'telegram_id': user_obj.telegram_id,
                'username': username,
                'display_name': display_name,
                'first_name': None,  # Можно добавить из initData, если нужно
                'last_name': None,   # Можно добавить из initData, если нужно
                'email': user_obj.email or f"tg_{user_obj.telegram_id}@telegram.local",
                'uuid': data_dict.get('uuid') or user_obj.remnawave_uuid,
                'has_active_subscription': has_active_subscription,
                'subscription_actual_status': 'active' if has_active_subscription else 'inactive',
                'subscription_status': 'active' if has_active_subscription else 'inactive',
                'subscription_type': None,  # Можно добавить, если есть в данных
                'expireAt': expire_at,
                'expires_at': expire_at,  # Для совместимости с miniapp
                'referral_code': user_obj.referral_code,
                'preferred_lang': user_obj.preferred_lang,
                'preferred_currency': user_obj.preferred_currency
            }
            
            # Добавляем данные о трафике
            used_traffic_bytes = data_dict.get('usedTrafficBytes') or data_dict.get('used_traffic_bytes') or data_dict.get('lifetimeUsedTrafficBytes') or 0
            traffic_limit_bytes = data_dict.get('trafficLimitBytes') or data_dict.get('traffic_limit_bytes') or 0
            
            # Конвертируем в ГБ для отображения
            def bytes_to_gb(bytes_val):
                if not bytes_val or bytes_val == 0:
                    return 0
                return round(bytes_val / (1024 ** 3), 2)
            
            user_data['traffic_used'] = used_traffic_bytes
            user_data['traffic_used_gb'] = bytes_to_gb(used_traffic_bytes)
            user_data['traffic_limit'] = traffic_limit_bytes
            user_data['traffic_limit_gb'] = bytes_to_gb(traffic_limit_bytes) if traffic_limit_bytes > 0 else None
            user_data['traffic_used_label'] = f"{bytes_to_gb(used_traffic_bytes)} ГБ" if used_traffic_bytes else "0.00 ГБ"
            user_data['traffic_limit_label'] = f"{bytes_to_gb(traffic_limit_bytes)} ГБ" if traffic_limit_bytes > 0 else "Безлимит"
            
            # Добавляем данные о серверах и устройствах
            user_data['connected_squads'] = data_dict.get('activeInternalSquads') or data_dict.get('active_internal_squads') or []
            user_data['servers_count'] = len(user_data['connected_squads'])
            user_data['devices_count'] = data_dict.get('hwidDeviceLimit') or data_dict.get('hwid_device_limit') or 0
            
            # Добавляем все остальные поля из data_dict в user_data
            for key, value in data_dict.items():
                if key not in user_data:
                    user_data[key] = value
            
            # Формируем финальный ответ в формате, ожидаемом miniapp
            result = {
                'user': user_data,
                'subscription_url': data_dict.get('subscriptionUrl') or data_dict.get('subscription_url'),
                'subscription_missing': not has_active_subscription,
                'subscriptionMissing': not has_active_subscription,
                'uuid': user_data['uuid'],
                'email': user_data['email'],
                'username': user_data['username'],
                'expireAt': expire_at
            }
            
            # Добавляем все остальные поля из data_dict в result (для обратной совместимости)
            for key, value in data_dict.items():
                if key not in result:
                    result[key] = value
            
            return result
        
        # Получаем данные пользователя из RemnaWave (аналогично get_client_me)
        current_uuid = user.remnawave_uuid
        
        # Проверяем кэш
        cache_key = f'live_data_{current_uuid}'
        if cached := cache.get(cache_key):
            # Адаптируем данные для miniapp
            response_data = adapt_data_for_miniapp(cached.copy(), user)
            response = jsonify(response_data)
            # Добавляем CORS заголовки для miniapp
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
            response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
            return response, 200
        
        # Получаем данные из RemnaWave API
        try:
            resp = requests.get(
                f"{API_URL}/api/users/{current_uuid}",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                timeout=10
            )
            
            if resp.status_code != 200:
                if resp.status_code == 404:
                    return jsonify({
                        "detail": {
                            "title": "Subscription Not Found",
                            "message": "User not found in VPN system. Please contact support."
                        }
                    }), 404
                return jsonify({
                    "detail": {
                        "title": "Subscription Not Found",
                        "message": f"Failed to fetch subscription data: {resp.status_code}"
                    }
                }), 500
            
            response_data = resp.json()
            data = response_data.get('response', {}) if isinstance(response_data, dict) else response_data
            
            # Адаптируем данные для miniapp
            if isinstance(data, dict):
                data = adapt_data_for_miniapp(data, user)
            
            # Кэшируем на 5 минут (сохраняем оригинальные данные без адаптации)
            cache_data = data.copy()
            # Убираем поля, которые мы добавили для miniapp, чтобы не дублировать в кэше
            cache_data.pop('subscription_missing', None)
            cache_data.pop('subscriptionMissing', None)
            cache.set(cache_key, cache_data, timeout=300)
            
            print(f"[MINIAPP] Successfully fetched subscription data for user {telegram_id}")
            print(f"[MINIAPP] Response keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
            if isinstance(data, dict):
                print(f"[MINIAPP] Sample fields: expireAt={data.get('expireAt')}, subscription_missing={data.get('subscription_missing')}, uuid={bool(data.get('uuid'))}")
            
            response = jsonify(data)
            # Добавляем CORS заголовки для miniapp
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
            response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
            return response, 200
            
        except requests.RequestException as e:
            print(f"Request Error in miniapp_subscription: {e}")
            return jsonify({
                "detail": {
                    "title": "Subscription Not Found",
                    "message": f"Failed to connect to VPN system: {str(e)}"
                }
            }), 500
        except Exception as e:
            print(f"Error in miniapp_subscription: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "detail": {
                    "title": "Subscription Not Found",
                    "message": "Internal server error"
                }
            }), 500
            
    except Exception as e:
        print(f"Error parsing initData: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "detail": {
                "title": "Authorization Error",
                "message": "Invalid initData format."
            }
        }), 401

def get_miniapp_path():
    """
    Получить путь к папке miniapp.
    Проверяет переменную окружения и стандартные пути.
    Учитывает различные варианты размещения miniapp.
    """
    import os
    
    # 1. Из переменной окружения (приоритет)
    miniapp_path = os.getenv("MINIAPP_PATH", "")
    if miniapp_path:
        # Убираем пробелы и проверяем
        miniapp_path = miniapp_path.strip()
        if miniapp_path and os.path.isdir(miniapp_path):
            index_path = os.path.join(miniapp_path, 'index.html')
            if os.path.exists(index_path):
                print(f"[MINIAPP] Using path from MINIAPP_PATH: {miniapp_path}")
                return miniapp_path
            else:
                print(f"[MINIAPP] MINIAPP_PATH set to {miniapp_path}, but index.html not found")
    
    # 2. Базовый путь от текущего файла
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 3. Стандартные пути (в порядке приоритета)
    possible_paths = [
        # Пользовательские пути (из сообщений)
        os.path.join('/var/www', 'stealthnet-client', 'build', 'miniapp'),
        os.path.join('/opt', 'admin-panel', 'build', 'miniapp'),
        
        # Относительно текущего файла
        os.path.join(base_dir, 'admin-panel', 'build', 'miniapp'),
        os.path.join(base_dir, 'miniapp'),
        
        # Стандартные системные пути
        os.path.join('/var/www', 'admin-panel', 'build', 'miniapp'),
        os.path.join('/var/www', 'miniapp'),
        os.path.join('/srv', 'admin-panel', 'build', 'miniapp'),
        os.path.join('/srv', 'miniapp'),
        os.path.join('/opt', 'miniapp'),
        os.path.join('/opt', 'stealthnet', 'admin-panel', 'build', 'miniapp'),
        os.path.join('/opt', 'stealthnet-client', 'build', 'miniapp'),
        os.path.join(os.path.expanduser('~'), 'admin-panel', 'build', 'miniapp'),
        os.path.join(os.path.expanduser('~'), 'miniapp'),
    ]
    
    # Убираем дубликаты, сохраняя порядок
    seen = set()
    unique_paths = []
    for path in possible_paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)
    
    # Проверяем каждый путь
    for path in unique_paths:
        if os.path.isdir(path):
            index_path = os.path.join(path, 'index.html')
            if os.path.exists(index_path):
                print(f"[MINIAPP] Found miniapp at: {path}")
                return path
            else:
                # Логируем, если директория существует, но index.html нет
                print(f"[MINIAPP] Directory exists but no index.html: {path}")
    
    # Если ничего не найдено, выводим список проверенных путей
    print(f"[MINIAPP] Miniapp directory not found in any of the checked paths:")
    for path in unique_paths:
        exists = os.path.exists(path)
        is_dir = os.path.isdir(path) if exists else False
        print(f"  - {path} {'(exists, dir)' if is_dir else '(exists, not dir)' if exists else '(not found)'}")
    
    return None

@app.route('/miniapp/app-config.json', methods=['GET'])
@app.route('/app-config.json', methods=['GET'])
def miniapp_app_config():
    """
    Эндпоинт для отдачи конфигурации miniapp (app-config.json).
    Поддерживает несколько путей для поиска файла.
    """
    import json
    import os
    
    # Возможные пути к файлу app-config.json
    # 1. Из переменной окружения (если указана)
    miniapp_path = os.getenv("MINIAPP_PATH", "")
    
    # 2. Базовый путь от текущего файла
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Список возможных путей для поиска
    possible_paths = []
    
    # Если указан путь в переменной окружения
    if miniapp_path:
        possible_paths.append(os.path.join(miniapp_path, 'app-config.json'))
        possible_paths.append(os.path.join(miniapp_path, 'miniapp', 'app-config.json'))
    
    # Стандартные пути относительно текущего файла
    possible_paths.extend([
        # Пользовательские пути (из сообщений)
        os.path.join('/var/www', 'stealthnet-client', 'build', 'miniapp', 'app-config.json'),
        os.path.join('/opt', 'admin-panel', 'build', 'miniapp', 'app-config.json'),
        
        # Относительно текущего файла
        os.path.join(base_dir, 'admin-panel', 'build', 'miniapp', 'app-config.json'),
        os.path.join(base_dir, 'miniapp', 'app-config.json'),
        os.path.join(base_dir, 'app-config.json'),
        
        # Стандартные системные пути
        os.path.join('/var/www', 'admin-panel', 'build', 'miniapp', 'app-config.json'),
        os.path.join('/var/www', 'miniapp', 'app-config.json'),
        os.path.join('/srv', 'admin-panel', 'build', 'miniapp', 'app-config.json'),
        os.path.join('/srv', 'miniapp', 'app-config.json'),
        os.path.join('/opt', 'miniapp', 'app-config.json'),
        os.path.join('/opt', 'stealthnet', 'admin-panel', 'build', 'miniapp', 'app-config.json'),
        os.path.join('/opt', 'stealthnet-client', 'build', 'miniapp', 'app-config.json'),
        os.path.join(os.path.expanduser('~'), 'admin-panel', 'build', 'miniapp', 'app-config.json'),
        os.path.join(os.path.expanduser('~'), 'miniapp', 'app-config.json'),
    ])
    
    # Убираем дубликаты, сохраняя порядок
    seen = set()
    unique_paths = []
    for path in possible_paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)
    
    config_data = None
    found_path = None
    
    # Пытаемся найти файл по одному из путей
    for config_path in unique_paths:
        try:
            if os.path.exists(config_path) and os.path.isfile(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                found_path = config_path
                print(f"[MINIAPP] Found app-config.json at: {config_path}")
                break
        except (FileNotFoundError, PermissionError) as e:
            continue
        except json.JSONDecodeError as e:
            print(f"[MINIAPP] Error parsing JSON from {config_path}: {e}")
            continue
        except Exception as e:
            print(f"[MINIAPP] Error reading {config_path}: {e}")
            continue
    
    # Если файл не найден, создаем базовую конфигурацию
    if config_data is None:
        print(f"[MINIAPP] app-config.json not found in any of the checked paths:")
        for path in unique_paths:
            print(f"  - {path}")
        print(f"[MINIAPP] Using default configuration")
        
        # Создаем базовую конфигурацию
        config_data = {
            "config": {
                "additionalLocales": ["ru", "zh", "fa"],
                "branding": {
                    "name": "StealthNET",
                    "logoUrl": "",
                    "supportUrl": "https://t.me"
                }
            },
            "platforms": {
                "ios": [],
                "android": [],
                "macos": [],
                "windows": [],
                "linux": [],
                "androidTV": [],
                "appleTV": []
            }
        }
    
    # Обновляем branding из базы данных, если есть
    try:
        branding = BrandingSetting.query.first()
        if branding:
            if 'config' not in config_data:
                config_data['config'] = {}
            if 'branding' not in config_data['config']:
                config_data['config']['branding'] = {}
            
            config_data['config']['branding']['name'] = branding.site_name or "StealthNET"
            if branding.logo_url:
                config_data['config']['branding']['logoUrl'] = branding.logo_url
            # supportUrl можно оставить как есть или добавить в BrandingSetting
    except Exception as e:
        print(f"[MINIAPP] Error updating branding from database: {e}")
    
    response = jsonify(config_data)
    # Добавляем CORS заголовки
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Content-Type', 'application/json')
    return response

@app.route('/miniapp/maintenance/status', methods=['POST', 'OPTIONS'])
@limiter.limit("30 per minute")
def miniapp_maintenance_status():
    """
    Эндпоинт для проверки статуса технического обслуживания в Telegram Mini App.
    """
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    print(f"[MINIAPP] POST /miniapp/maintenance/status received")
    try:
        # Просто возвращаем, что обслуживание не активно
        # В будущем можно добавить логику проверки статуса обслуживания
        return jsonify({
            "isActive": False,
            "is_active": False,
            "message": None
        }), 200
    except Exception as e:
        print(f"Error in miniapp_maintenance_status: {e}")
        return jsonify({
            "isActive": False,
            "is_active": False,
            "message": None
        }), 200

@app.route('/miniapp/subscription/trial', methods=['POST'])
@limiter.limit("10 per minute")
def miniapp_activate_trial():
    """
    Эндпоинт для активации триала через Telegram Mini App.
    """
    try:
        data = request.json
        init_data = data.get('initData', '')
        
        if not init_data:
            return jsonify({
                "success": False,
                "message": "Missing initData. Please open the mini app from Telegram."
            }), 401
        
        # Парсим initData
        import urllib.parse
        import json as json_lib
        
        parsed_data = urllib.parse.parse_qs(init_data)
        user_str = parsed_data.get('user', [''])[0]
        
        if not user_str:
            return jsonify({
                "success": False,
                "message": "Invalid initData format."
            }), 401
        
        try:
            user_data = json_lib.loads(urllib.parse.unquote(user_str))
            telegram_id = user_data.get('id')
        except (json_lib.JSONDecodeError, KeyError):
            return jsonify({
                "success": False,
                "message": "Invalid user data in initData."
            }), 401
        
        if not telegram_id:
            return jsonify({
                "success": False,
                "message": "Telegram ID not found in initData."
            }), 401
        
        # Находим пользователя
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            return jsonify({
                "success": False,
                "message": "User not registered. Please register in the bot first."
            }), 404
        
        # Активируем триал (аналогично activate_trial)
        new_exp = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        
        referral_settings = ReferralSetting.query.first()
        trial_squad_id = DEFAULT_SQUAD_ID
        if referral_settings and referral_settings.trial_squad_id:
            trial_squad_id = referral_settings.trial_squad_id
        
        patch_resp = requests.patch(
            f"{API_URL}/api/users",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            json={"uuid": user.remnawave_uuid, "expireAt": new_exp, "activeInternalSquads": [trial_squad_id]},
            timeout=10
        )
        
        if patch_resp.status_code != 200:
            return jsonify({
                "success": False,
                "message": "Failed to activate trial. Please try again later."
            }), 500
        
        # Очищаем кэш
        cache.delete(f'live_data_{user.remnawave_uuid}')
        cache.delete('all_live_users_map')
        cache.delete(f'nodes_{user.remnawave_uuid}')
        
        return jsonify({
            "success": True,
            "message": "Trial activated successfully. You received 3 days of premium access."
        }), 200
        
    except Exception as e:
        print(f"Error in miniapp_activate_trial: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": "Internal server error"
        }), 500

# --- MINIAPP PAYMENT ENDPOINTS ---
@app.route('/miniapp/payments/methods', methods=['POST', 'OPTIONS'])
@limiter.limit("30 per minute")
def miniapp_payment_methods():
    """Получить список доступных способов оплаты для miniapp"""
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    try:
        # Получаем доступные методы оплаты
        s = PaymentSetting.query.first()
        if not s:
            return jsonify({"methods": []}), 200
        
        available = []
        
        # CrystalPay
        crystalpay_key = decrypt_key(s.crystalpay_api_key) if s.crystalpay_api_key else None
        crystalpay_secret = decrypt_key(s.crystalpay_api_secret) if s.crystalpay_api_secret else None
        if crystalpay_key and crystalpay_secret and crystalpay_key != "DECRYPTION_ERROR" and crystalpay_secret != "DECRYPTION_ERROR":
            available.append({"id": "crystalpay", "name": "CrystalPay", "type": "redirect"})
        
        # Heleket
        heleket_key = decrypt_key(s.heleket_api_key) if s.heleket_api_key else None
        if heleket_key and heleket_key != "DECRYPTION_ERROR":
            available.append({"id": "heleket", "name": "Heleket", "type": "redirect"})
        
        # YooKassa
        yookassa_shop = decrypt_key(s.yookassa_shop_id) if s.yookassa_shop_id else None
        yookassa_secret = decrypt_key(s.yookassa_secret_key) if s.yookassa_secret_key else None
        if yookassa_shop and yookassa_secret and yookassa_shop != "DECRYPTION_ERROR" and yookassa_secret != "DECRYPTION_ERROR":
            available.append({"id": "yookassa", "name": "YooKassa", "type": "redirect"})
        
        # Platega
        platega_key = decrypt_key(s.platega_api_key) if s.platega_api_key else None
        platega_merchant = decrypt_key(s.platega_merchant_id) if s.platega_merchant_id else None
        if platega_key and platega_merchant and platega_key != "DECRYPTION_ERROR" and platega_merchant != "DECRYPTION_ERROR":
            available.append({"id": "platega", "name": "Platega", "type": "redirect"})
        
        # Mulenpay
        mulenpay_key = decrypt_key(s.mulenpay_api_key) if s.mulenpay_api_key else None
        mulenpay_secret = decrypt_key(s.mulenpay_secret_key) if s.mulenpay_secret_key else None
        mulenpay_shop = decrypt_key(s.mulenpay_shop_id) if s.mulenpay_shop_id else None
        if mulenpay_key and mulenpay_secret and mulenpay_shop and mulenpay_key != "DECRYPTION_ERROR" and mulenpay_secret != "DECRYPTION_ERROR" and mulenpay_shop != "DECRYPTION_ERROR":
            available.append({"id": "mulenpay", "name": "MulenPay", "type": "redirect"})
        
        # UrlPay
        urlpay_key = decrypt_key(s.urlpay_api_key) if s.urlpay_api_key else None
        urlpay_secret = decrypt_key(s.urlpay_secret_key) if s.urlpay_secret_key else None
        urlpay_shop = decrypt_key(s.urlpay_shop_id) if s.urlpay_shop_id else None
        if urlpay_key and urlpay_secret and urlpay_shop and urlpay_key != "DECRYPTION_ERROR" and urlpay_secret != "DECRYPTION_ERROR" and urlpay_shop != "DECRYPTION_ERROR":
            available.append({"id": "urlpay", "name": "UrlPay", "type": "redirect"})
        
        # Telegram Stars
        telegram_token = decrypt_key(s.telegram_bot_token) if s.telegram_bot_token else None
        if telegram_token and telegram_token != "DECRYPTION_ERROR":
            available.append({"id": "telegram_stars", "name": "Telegram Stars", "type": "telegram"})
        
        # Monobank
        monobank_token = decrypt_key(s.monobank_token) if s.monobank_token else None
        if monobank_token and monobank_token != "DECRYPTION_ERROR":
            available.append({"id": "monobank", "name": "Monobank", "type": "card"})
        
        # BTCPayServer
        btcpayserver_url = decrypt_key(s.btcpayserver_url) if s.btcpayserver_url else None
        btcpayserver_api_key = decrypt_key(s.btcpayserver_api_key) if s.btcpayserver_api_key else None
        btcpayserver_store_id = decrypt_key(s.btcpayserver_store_id) if s.btcpayserver_store_id else None
        if btcpayserver_url and btcpayserver_api_key and btcpayserver_store_id and btcpayserver_url != "DECRYPTION_ERROR" and btcpayserver_api_key != "DECRYPTION_ERROR" and btcpayserver_store_id != "DECRYPTION_ERROR":
            available.append({"id": "btcpayserver", "name": "BTCPayServer (Bitcoin)", "type": "redirect"})
        
        # Tribute
        tribute_api_key = decrypt_key(s.tribute_api_key) if s.tribute_api_key else None
        if tribute_api_key and tribute_api_key != "DECRYPTION_ERROR":
            available.append({"id": "tribute", "name": "Tribute", "type": "redirect"})
        
        # Robokassa
        robokassa_login = decrypt_key(s.robokassa_merchant_login) if s.robokassa_merchant_login else None
        robokassa_password1 = decrypt_key(s.robokassa_password1) if s.robokassa_password1 else None
        if robokassa_login and robokassa_password1 and robokassa_login != "DECRYPTION_ERROR" and robokassa_password1 != "DECRYPTION_ERROR":
            available.append({"id": "robokassa", "name": "Robokassa", "type": "redirect"})
        
        # Freekassa
        freekassa_shop_id = decrypt_key(s.freekassa_shop_id) if s.freekassa_shop_id else None
        freekassa_secret = decrypt_key(s.freekassa_secret) if s.freekassa_secret else None
        if freekassa_shop_id and freekassa_secret and freekassa_shop_id != "DECRYPTION_ERROR" and freekassa_secret != "DECRYPTION_ERROR":
            available.append({"id": "freekassa", "name": "Freekassa", "type": "redirect"})
        
        response = jsonify({"methods": available})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
    except Exception as e:
        print(f"Error in miniapp_payment_methods: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({"methods": []})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 200

@app.route('/miniapp/payments/create', methods=['POST', 'OPTIONS'])
@limiter.limit("10 per minute")
def miniapp_create_payment():
    """Создать платеж через miniapp"""
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    try:
        # Парсим initData для получения пользователя
        data = {}
        if request.is_json:
            data = request.json or {}
        elif request.form:
            data = dict(request.form)
        elif request.data:
            try:
                import json as json_lib
                data = json_lib.loads(request.data.decode('utf-8'))
            except:
                pass
        
        init_data = data.get('initData') or request.headers.get('X-Telegram-Init-Data') or request.headers.get('X-Init-Data') or request.args.get('initData')
        
        if not init_data:
            # Пробуем получить из initDataUnsafe
            init_data_unsafe = data.get('initDataUnsafe', {})
            if isinstance(init_data_unsafe, dict) and init_data_unsafe.get('user'):
                user_data = init_data_unsafe['user']
                telegram_id = user_data.get('id')
            else:
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Missing initData. Please open the mini app from Telegram."
                    }
                }), 401
        else:
            # Парсим initData
            import urllib.parse
            import json as json_lib
            
            if isinstance(init_data, dict):
                parsed_data = init_data
            else:
                parsed_data = urllib.parse.parse_qs(init_data)
            
            user_str = parsed_data.get('user', [''])[0] if isinstance(parsed_data, dict) and 'user' in parsed_data else None
            if not user_str and isinstance(parsed_data, dict):
                user_str = parsed_data.get('user')
            
            if not user_str:
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Invalid initData format."
                    }
                }), 401
            
            try:
                if isinstance(user_str, str):
                    user_data = json_lib.loads(urllib.parse.unquote(user_str))
                else:
                    user_data = user_str
                telegram_id = user_data.get('id')
            except (json_lib.JSONDecodeError, KeyError, TypeError):
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Invalid user data in initData."
                    }
                }), 401
        
        if not telegram_id:
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Telegram ID not found in initData."
                }
            }), 401
        
        # Находим пользователя
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            return jsonify({
                "detail": {
                    "title": "User Not Found",
                    "message": "User not registered. Please register in the bot first."
                }
            }), 404
        
        # Получаем параметры платежа
        tariff_id = data.get('tariff_id') or data.get('tariffId')
        payment_provider = data.get('payment_provider') or data.get('paymentProvider', 'crystalpay')
        promo_code_str = data.get('promo_code') or data.get('promoCode', '').strip().upper() if data.get('promo_code') or data.get('promoCode') else None
        
        if not tariff_id:
            return jsonify({
                "detail": {
                    "title": "Invalid Request",
                    "message": "tariff_id is required"
                }
            }), 400
        
        try:
            tariff_id = int(tariff_id)
        except (ValueError, TypeError):
            return jsonify({
                "detail": {
                    "title": "Invalid Request",
                    "message": "Invalid tariff_id"
                }
            }), 400
        
        # Получаем тариф
        t = db.session.get(Tariff, tariff_id)
        if not t:
            return jsonify({
                "detail": {
                    "title": "Not Found",
                    "message": "Tariff not found"
                }
            }), 404
        
        # Определяем цену в зависимости от валюты пользователя
        price_map = {"uah": {"a": t.price_uah, "c": "UAH"}, "rub": {"a": t.price_rub, "c": "RUB"}, "usd": {"a": t.price_usd, "c": "USD"}}
        info = price_map.get(user.preferred_currency, price_map['uah'])
        
        # Применяем промокод со скидкой, если указан
        promo_code_obj = None
        final_amount = info['a']
        if promo_code_str:
            promo = PromoCode.query.filter_by(code=promo_code_str).first()
            if not promo:
                return jsonify({
                    "detail": {
                        "title": "Invalid Promo Code",
                        "message": "Неверный промокод"
                    }
                }), 400
            if promo.uses_left <= 0:
                return jsonify({
                    "detail": {
                        "title": "Invalid Promo Code",
                        "message": "Промокод больше не действителен"
                    }
                }), 400
            if promo.promo_type == 'PERCENT':
                discount = (promo.value / 100.0) * final_amount
                final_amount = final_amount - discount
                if final_amount < 0:
                    final_amount = 0
                promo_code_obj = promo
            elif promo.promo_type == 'DAYS':
                return jsonify({
                    "detail": {
                        "title": "Invalid Promo Code",
                        "message": "Промокод на бесплатные дни активируется отдельно"
                    }
                }), 400
        
        # Создаем платеж (используем логику из create_payment)
        s = PaymentSetting.query.first()
        order_id = f"u{user.id}-t{t.id}-{int(datetime.now().timestamp())}"
        payment_url = None
        payment_system_id = None
        
        # Используем ту же логику создания платежа, что и в create_payment
        if payment_provider == 'heleket':
            # Heleket API
            heleket_key = decrypt_key(s.heleket_api_key) if s else None
            if not heleket_key or heleket_key == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "Heleket API key not configured"
                    }
                }), 500
            
            heleket_currency = info['c']
            to_currency = None
            
            if info['c'] == 'USD':
                heleket_currency = "USD"
            else:
                heleket_currency = "USD"
                to_currency = "USDT"
            
            payload = {
                "amount": f"{final_amount:.2f}",
                "currency": heleket_currency,
                "order_id": order_id,
                "url_return": f"{YOUR_SERVER_IP_OR_DOMAIN}/miniapp/",
                "url_callback": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/heleket"
            }
            
            if to_currency:
                payload["to_currency"] = to_currency
            
            headers = {
                "Authorization": f"Bearer {heleket_key}",
                "Content-Type": "application/json"
            }
            
            resp = requests.post("https://api.heleket.com/v1/payment", json=payload, headers=headers).json()
            if resp.get('state') != 0 or not resp.get('result'):
                error_msg = resp.get('message', 'Payment Provider Error')
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": error_msg
                    }
                }), 500
            
            result = resp.get('result', {})
            payment_url = result.get('url')
            payment_system_id = result.get('uuid')
            
        elif payment_provider == 'telegram_stars':
            # Telegram Stars API
            bot_token = decrypt_key(s.telegram_bot_token) if s else None
            if not bot_token or bot_token == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "Telegram Bot Token not configured"
                    }
                }), 500
            
            stars_amount = int(final_amount * 100)
            if info['c'] == 'UAH':
                stars_amount = int(final_amount * 2.7)
            elif info['c'] == 'RUB':
                stars_amount = int(final_amount * 1.1)
            elif info['c'] == 'USD':
                stars_amount = int(final_amount * 100)
            
            if stars_amount < 1:
                stars_amount = 1
            
            invoice_payload = {
                "title": f"Подписка StealthNET - {t.name}",
                "description": f"Подписка на {t.duration_days} дней",
                "payload": order_id,
                "provider_token": "",
                "currency": "XTR",
                "prices": [
                    {
                        "label": f"Подписка {t.duration_days} дней",
                        "amount": stars_amount
                    }
                ]
            }
            
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/createInvoiceLink",
                json=invoice_payload,
                headers={"Content-Type": "application/json"}
            ).json()
            
            if not resp.get('ok'):
                error_msg = resp.get('description', 'Telegram Bot API Error')
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": error_msg
                    }
                }), 500
            
            payment_url = resp.get('result')
            payment_system_id = order_id
            
        elif payment_provider == 'yookassa':
            # YooKassa API
            shop_id = decrypt_key(s.yookassa_shop_id) if s else None
            secret_key = decrypt_key(s.yookassa_secret_key) if s else None
            
            if not shop_id or not secret_key or shop_id == "DECRYPTION_ERROR" or secret_key == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "YooKassa credentials not configured"
                    }
                }), 500
            
            if info['c'] != 'RUB':
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "YooKassa supports only RUB currency"
                    }
                }), 400
            
            import uuid
            import base64
            idempotence_key = str(uuid.uuid4())
            
            payload = {
                "amount": {
                    "value": f"{final_amount:.2f}",
                    "currency": "RUB"
                },
                "capture": True,
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/miniapp/"
                },
                "description": f"Подписка StealthNET - {t.name} ({t.duration_days} дней)",
                "metadata": {
                    "order_id": order_id,
                    "user_id": str(user.id),
                    "tariff_id": str(t.id)
                }
            }
            
            auth_string = f"{shop_id}:{secret_key}"
            auth_b64 = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
            
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Idempotence-Key": idempotence_key,
                "Content-Type": "application/json"
            }
            
            try:
                resp = requests.post(
                    "https://api.yookassa.ru/v3/payments",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                payment_data = resp.json()
                
                if payment_data.get('status') != 'pending':
                    error_msg = payment_data.get('description', 'YooKassa payment creation failed')
                    return jsonify({
                        "detail": {
                            "title": "Payment Error",
                            "message": error_msg
                        }
                    }), 500
                
                confirmation = payment_data.get('confirmation', {})
                payment_url = confirmation.get('confirmation_url')
                payment_system_id = payment_data.get('id')
                
                if not payment_url:
                    return jsonify({
                        "detail": {
                            "title": "Payment Error",
                            "message": "Failed to get payment URL from YooKassa"
                        }
                    }), 500
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('description', str(e))
                    except:
                        pass
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": f"YooKassa API Error: {error_msg}"
                    }
                }), 500
        
        elif payment_provider == 'platega':
            # Platega API
            import uuid
            api_key = decrypt_key(s.platega_api_key) if s else None
            merchant_id = decrypt_key(s.platega_merchant_id) if s else None
            
            if not api_key or not merchant_id or api_key == "DECRYPTION_ERROR" or merchant_id == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "Platega credentials not configured"
                    }
                }), 500
            
            transaction_uuid = str(uuid.uuid4())
            
            # Формируем payload согласно документации Platega API
            payload = {
                "paymentMethod": 2,  # 2 - СБП/QR, 10 - CardRu, 12 - International
                "id": transaction_uuid,
                "paymentDetails": {
                    "amount": int(final_amount),
                    "currency": info['c']
                },
                "description": f"Payment for order {transaction_uuid}",
                "return": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription" if YOUR_SERVER_IP_OR_DOMAIN else "https://panel.stealthnet.app/dashboard/subscription",
                "failedUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription" if YOUR_SERVER_IP_OR_DOMAIN else "https://panel.stealthnet.app/dashboard/subscription"
            }
            
            # Заголовки согласно документации Platega API
            headers = {
                "Content-Type": "application/json",
                "X-MerchantId": merchant_id,
                "X-Secret": api_key
            }
            
            try:
                resp = requests.post(
                    "https://app.platega.io/transaction/process",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                payment_data = resp.json()
                
                payment_url = payment_data.get('redirect')
                payment_system_id = payment_data.get('transactionId') or transaction_uuid
                
                if not payment_url:
                    error_msg = payment_data.get('message', 'Failed to get payment URL from Platega')
                    return jsonify({
                        "detail": {
                            "title": "Payment Error",
                            "message": error_msg
                        }
                    }), 500
            except requests.exceptions.ConnectionError as e:
                # Обработка DNS ошибок и проблем с подключением
                error_msg = str(e)
                if "Name or service not known" in error_msg or "Failed to resolve" in error_msg:
                    print(f"Platega API DNS Error: {e}")
                    return jsonify({
                        "detail": {
                            "title": "Payment Error",
                            "message": "Platega API недоступен. Проверьте настройки DNS или свяжитесь с поддержкой."
                        }
                    }), 503  # Service Unavailable
                else:
                    print(f"Platega API Connection Error: {e}")
                    return jsonify({
                        "detail": {
                            "title": "Payment Error",
                            "message": "Не удалось подключиться к Platega API. Проверьте интернет-соединение."
                        }
                    }), 503
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message', str(e))
                    except:
                        pass
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": f"Platega API Error: {error_msg}"
                    }
                }), 500
        
        elif payment_provider == 'mulenpay':
            # Mulenpay API
            api_key = decrypt_key(s.mulenpay_api_key) if s else None
            secret_key = decrypt_key(s.mulenpay_secret_key) if s else None
            shop_id = decrypt_key(s.mulenpay_shop_id) if s else None
            
            if not api_key or not secret_key or not shop_id or api_key == "DECRYPTION_ERROR" or secret_key == "DECRYPTION_ERROR" or shop_id == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "Mulenpay credentials not configured"
                    }
                }), 500
            
            currency_map = {'RUB': 'rub', 'UAH': 'uah', 'USD': 'usd'}
            mulenpay_currency = currency_map.get(info['c'], info['c'].lower())
            
            try:
                shop_id_int = int(shop_id)
            except (ValueError, TypeError):
                shop_id_int = shop_id
            
            payload = {
                "currency": mulenpay_currency,
                "amount": str(final_amount),
                "uuid": order_id,
                "shopId": shop_id_int,
                "description": f"Подписка StealthNET - {t.name} ({t.duration_days} дней)",
                "subscribe": None,
                "holdTime": None
            }
            
            import base64
            auth_string = f"{api_key}:{secret_key}"
            auth_b64 = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
            
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/json"
            }
            
            try:
                resp = requests.post(
                    "https://api.mulenpay.ru/v2/payments",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                payment_data = resp.json()
                
                payment_url = payment_data.get('url') or payment_data.get('payment_url') or payment_data.get('redirect')
                payment_system_id = payment_data.get('id') or payment_data.get('payment_id') or order_id
                
                if not payment_url:
                    error_msg = payment_data.get('message') or payment_data.get('error') or 'Failed to get payment URL from Mulenpay'
                    return jsonify({
                        "detail": {
                            "title": "Payment Error",
                            "message": error_msg
                        }
                    }), 500
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('error') or str(e)
                    except:
                        pass
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": f"Mulenpay API Error: {error_msg}"
                    }
                }), 500
        
        elif payment_provider == 'urlpay':
            # UrlPay API
            api_key = decrypt_key(s.urlpay_api_key) if s else None
            secret_key = decrypt_key(s.urlpay_secret_key) if s else None
            shop_id = decrypt_key(s.urlpay_shop_id) if s else None
            
            if not api_key or not secret_key or not shop_id or api_key == "DECRYPTION_ERROR" or secret_key == "DECRYPTION_ERROR" or shop_id == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "UrlPay credentials not configured"
                    }
                }), 500
            
            currency_map = {'RUB': 'rub', 'UAH': 'uah', 'USD': 'usd'}
            urlpay_currency = currency_map.get(info['c'], info['c'].lower())
            
            try:
                shop_id_int = int(shop_id)
            except (ValueError, TypeError):
                shop_id_int = shop_id
            
            payload = {
                "currency": urlpay_currency,
                "amount": str(final_amount),
                "uuid": order_id,
                "shopId": shop_id_int,
                "description": f"Подписка StealthNET - {t.name} ({t.duration_days} дней)",
                "subscribe": None,
                "holdTime": None
            }
            
            import base64
            auth_string = f"{api_key}:{secret_key}"
            auth_b64 = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
            
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/json"
            }
            
            try:
                resp = requests.post(
                    "https://api.urlpay.io/v2/payments",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                payment_data = resp.json()
                
                payment_url = payment_data.get('url') or payment_data.get('payment_url') or payment_data.get('redirect')
                payment_system_id = payment_data.get('id') or payment_data.get('payment_id') or order_id
                
                if not payment_url:
                    error_msg = payment_data.get('message') or payment_data.get('error') or 'Failed to get payment URL from UrlPay'
                    return jsonify({
                        "detail": {
                            "title": "Payment Error",
                            "message": error_msg
                        }
                    }), 500
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('error') or str(e)
                    except:
                        pass
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": f"UrlPay API Error: {error_msg}"
                    }
                }), 500
        
        elif payment_provider == 'monobank':
            # Monobank API
            monobank_token = decrypt_key(s.monobank_token) if s else None
            if not monobank_token or monobank_token == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "Monobank token not configured"
                    }
                }), 500
            
            # Monobank принимает сумму в копейках (минимальных единицах)
            # Конвертируем сумму в копейки
            amount_in_kopecks = int(final_amount * 100)
            if info['c'] == 'UAH':
                amount_in_kopecks = int(final_amount * 100)  # UAH в копейках
            elif info['c'] == 'RUB':
                amount_in_kopecks = int(final_amount * 100)  # RUB в копейках
            elif info['c'] == 'USD':
                amount_in_kopecks = int(final_amount * 100)  # USD в центах
            
            # Код валюты по ISO 4217: 980 = UAH, 643 = RUB, 840 = USD
            currency_code = 980  # По умолчанию UAH
            if info['c'] == 'RUB':
                currency_code = 643
            elif info['c'] == 'USD':
                currency_code = 840
            
            # Создаем инвойс через Monobank API
            payload = {
                "amount": amount_in_kopecks,
                "ccy": currency_code,
                "merchantPaymInfo": {
                    "reference": order_id,
                    "destination": f"Подписка StealthNET - {t.name} ({t.duration_days} дней)",
                    "basketOrder": [
                        {
                            "name": f"Подписка {t.name}",
                            "qty": 1,
                            "sum": amount_in_kopecks,
                            "unit": "шт"
                        }
                    ]
                },
                "redirectUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/miniapp/",
                "webHookUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/monobank",
                "validity": 86400,  # 24 часа в секундах
                "paymentType": "debit"
            }
            
            headers = {
                "X-Token": monobank_token,
                "Content-Type": "application/json"
            }
            
            try:
                resp = requests.post(
                    "https://api.monobank.ua/api/merchant/invoice/create",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                payment_data = resp.json()
                
                payment_url = payment_data.get('pageUrl')
                payment_system_id = payment_data.get('invoiceId') or order_id
                
                if not payment_url:
                    error_msg = payment_data.get('errText') or 'Failed to get payment URL from Monobank'
                    return jsonify({
                        "detail": {
                            "title": "Payment Error",
                            "message": error_msg
                        }
                    }), 500
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('errText') or error_data.get('message') or str(e)
                    except:
                        pass
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": f"Monobank API Error: {error_msg}"
                    }
                }), 500
        
        elif payment_provider == 'btcpayserver':
            # BTCPayServer API
            btcpayserver_url = decrypt_key(s.btcpayserver_url) if s else None
            btcpayserver_api_key = decrypt_key(s.btcpayserver_api_key) if s else None
            btcpayserver_store_id = decrypt_key(s.btcpayserver_store_id) if s else None
            
            if not btcpayserver_url or not btcpayserver_api_key or not btcpayserver_store_id or btcpayserver_url == "DECRYPTION_ERROR" or btcpayserver_api_key == "DECRYPTION_ERROR" or btcpayserver_store_id == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "BTCPayServer credentials not configured"
                    }
                }), 500
            
            # Очищаем URL от завершающего слеша
            btcpayserver_url = btcpayserver_url.rstrip('/')
            
            # Формируем payload для создания инвойса согласно BTCPayServer API
            # BTCPayServer работает с криптовалютами, но может принимать фиат через конвертацию
            # Для простоты используем USD как базовую валюту, BTCPayServer конвертирует в BTC
            invoice_currency = info['c']
            
            # Формируем metadata с информацией о заказе
            metadata = {
                "orderId": order_id,
                "buyerEmail": user.email if user.email else None,
                "itemDesc": f"VPN Subscription - {t.name} ({t.duration_days} days)"
            }
            
            # Payload для создания инвойса
            # Добавляем checkout options с redirect URL и callback URL для webhook
            checkout_options = {
                "redirectURL": f"{YOUR_SERVER_IP_OR_DOMAIN}/miniapp/" if YOUR_SERVER_IP_OR_DOMAIN else "https://client.vpnborz.ru/miniapp/"
            }
            
            payload = {
                "amount": f"{final_amount:.2f}",
                "currency": invoice_currency,
                "metadata": metadata,
                "checkout": checkout_options
            }
            
            # URL для создания инвойса: POST /api/v1/stores/{storeId}/invoices
            invoice_url = f"{btcpayserver_url}/api/v1/stores/{btcpayserver_store_id}/invoices"
            
            # Заголовки для авторизации (BTCPayServer использует Basic Auth или API Key в заголовке)
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"token {btcpayserver_api_key}"
            }
            
            try:
                resp = requests.post(
                    invoice_url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                invoice_data = resp.json()
                
                # Получаем checkoutLink из ответа
                payment_url = invoice_data.get('checkoutLink')
                payment_system_id = invoice_data.get('id')  # Invoice ID
                
                if not payment_url:
                    error_msg = invoice_data.get('message') or 'Failed to get payment URL from BTCPayServer'
                    return jsonify({
                        "detail": {
                            "title": "Payment Error",
                            "message": error_msg
                        }
                    }), 500
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('error') or str(e)
                    except:
                        pass
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": f"BTCPayServer API Error: {error_msg}"
                    }
                }), 500
        
        elif payment_provider == 'tribute':
            # Tribute API
            tribute_api_key = decrypt_key(s.tribute_api_key) if s else None
            
            if not tribute_api_key or tribute_api_key == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "Tribute API key not configured"
                    }
                }), 500
            
            # Tribute принимает сумму в минимальных единицах валюты (копейки для RUB, центы для EUR)
            # Конвертируем валюту в формат Tribute (rub, eur)
            currency_map = {
                'RUB': 'rub',
                'UAH': 'rub',  # UAH не поддерживается, используем RUB
                'USD': 'eur'   # USD не поддерживается, используем EUR
            }
            tribute_currency = currency_map.get(info['c'], 'rub')
            
            # Конвертируем сумму в минимальные единицы (копейки/центы)
            # final_amount в рублях/гривнах/долларах, нужно умножить на 100
            amount_in_cents = int(final_amount * 100)
            
            # Формируем payload для создания заказа
            payload = {
                "amount": amount_in_cents,
                "currency": tribute_currency,
                "title": f"VPN Subscription - {t.name}"[:100],  # Макс 100 символов
                "description": f"VPN subscription for {t.duration_days} days"[:300],  # Макс 300 символов
                "successUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/miniapp/" if YOUR_SERVER_IP_OR_DOMAIN else "https://client.vpnborz.ru/miniapp/",
                "failUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/miniapp/" if YOUR_SERVER_IP_OR_DOMAIN else "https://client.vpnborz.ru/miniapp/"
            }
            
            # Добавляем email, если есть
            if user.email:
                payload["email"] = user.email
            
            # URL для создания заказа: POST /api/v1/shop/orders
            order_url = "https://tribute.tg/api/v1/shop/orders"
            
            # Заголовки для авторизации
            headers = {
                "Content-Type": "application/json",
                "Api-Key": tribute_api_key
            }
            
            try:
                resp = requests.post(
                    order_url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                order_data = resp.json()
                
                # Получаем paymentUrl и uuid из ответа
                payment_url = order_data.get('paymentUrl')
                payment_system_id = order_data.get('uuid')  # UUID заказа
                
                if not payment_url:
                    error_msg = order_data.get('message') or 'Failed to get payment URL from Tribute'
                    return jsonify({
                        "detail": {
                            "title": "Payment Error",
                            "message": error_msg
                        }
                    }), 500
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('error') or str(e)
                    except:
                        pass
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": f"Tribute API Error: {error_msg}"
                    }
                }), 500
        
        elif payment_provider == 'robokassa':
            # Robokassa API
            robokassa_login = decrypt_key(s.robokassa_merchant_login) if s else None
            robokassa_password1 = decrypt_key(s.robokassa_password1) if s else None
            
            if not robokassa_login or not robokassa_password1 or robokassa_login == "DECRYPTION_ERROR" or robokassa_password1 == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "Robokassa credentials not configured"
                    }
                }), 500
            
            # Robokassa работает только с RUB
            # Если валюта не RUB, конвертируем или используем RUB
            if info['c'] not in ['RUB', 'rub']:
                # Для других валют используем RUB (можно добавить конвертацию)
                robokassa_amount = final_amount  # Используем сумму как есть
            else:
                robokassa_amount = final_amount
            
            # Формируем описание платежа
            description = f"VPN Subscription - {t.name} ({t.duration_days} days)"[:100]  # Макс 100 символов
            
            # Создаем MD5 подпись: MD5(MerchantLogin:OutSum:InvId:Password#1)
            import hashlib
            signature_string = f"{robokassa_login}:{robokassa_amount}:{order_id}:{robokassa_password1}"
            signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest()
            
            # Формируем URL для оплаты
            import urllib.parse
            params = {
                'MerchantLogin': robokassa_login,
                'OutSum': str(robokassa_amount),
                'InvId': order_id,
                'Description': description,
                'SignatureValue': signature
            }
            
            # Добавляем параметры для редиректа
            success_url = f"{YOUR_SERVER_IP_OR_DOMAIN}/miniapp/" if YOUR_SERVER_IP_OR_DOMAIN else "https://client.vpnborz.ru/miniapp/"
            fail_url = f"{YOUR_SERVER_IP_OR_DOMAIN}/miniapp/" if YOUR_SERVER_IP_OR_DOMAIN else "https://client.vpnborz.ru/miniapp/"
            
            params['SuccessURL'] = success_url
            params['FailURL'] = fail_url
            
            # Формируем полный URL
            query_string = urllib.parse.urlencode(params)
            payment_url = f"https://auth.robokassa.ru/Merchant/Index.aspx?{query_string}"
            payment_system_id = order_id  # Используем order_id как идентификатор
        
        elif payment_provider == 'freekassa':
            # Freekassa API
            freekassa_shop_id = decrypt_key(s.freekassa_shop_id) if s else None
            freekassa_secret = decrypt_key(s.freekassa_secret) if s else None
            
            if not freekassa_shop_id or not freekassa_secret or freekassa_shop_id == "DECRYPTION_ERROR" or freekassa_secret == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "Freekassa credentials not configured"
                    }
                }), 500
            
            # Freekassa поддерживает валюты: RUB, USD, EUR, UAH, KZT
            # Конвертируем валюту в формат Freekassa
            currency_map = {
                'RUB': 'RUB',
                'UAH': 'UAH',
                'USD': 'USD',
                'EUR': 'EUR',
                'KZT': 'KZT'
            }
            freekassa_currency = currency_map.get(info['c'], 'RUB')
            
            # Генерируем nonce (уникальный ID запроса, должен быть больше предыдущего)
            import time
            nonce = int(time.time() * 1000)  # Используем timestamp в миллисекундах
            
            # Формируем подпись: MD5(shopId + amount + currency + paymentId + secret)
            import hashlib
            signature_string = f"{freekassa_shop_id}{final_amount}{freekassa_currency}{order_id}{freekassa_secret}"
            signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest()
            
            # Параметры для создания заказа через API
            api_params = {
                'shopId': freekassa_shop_id,
                'nonce': nonce,
                'signature': signature,
                'paymentId': order_id,
                'amount': str(final_amount),
                'currency': freekassa_currency
            }
            
            # URL для создания заказа: POST https://api.fk.life/v1/orders/create
            api_url = "https://api.fk.life/v1/orders/create"
            
            try:
                resp = requests.post(
                    api_url,
                    params=api_params,
                    timeout=30
                )
                resp.raise_for_status()
                order_data = resp.json()
                
                # Проверяем ответ
                if order_data.get('type') == 'success':
                    payment_url = order_data.get('data', {}).get('url')
                    payment_system_id = order_data.get('data', {}).get('orderId') or order_id
                    
                    if not payment_url:
                        error_msg = order_data.get('message') or 'Failed to get payment URL from Freekassa'
                        return jsonify({
                            "detail": {
                                "title": "Payment Error",
                                "message": error_msg
                            }
                        }), 500
                else:
                    error_msg = order_data.get('message') or 'Failed to create payment'
                    return jsonify({
                        "detail": {
                            "title": "Payment Error",
                            "message": error_msg
                        }
                    }), 500
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('error') or str(e)
                    except:
                        pass
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": f"Freekassa API Error: {error_msg}"
                    }
                }), 500
        
        else:
            # CrystalPay API (по умолчанию)
            login = decrypt_key(s.crystalpay_api_key) if s else None
            secret = decrypt_key(s.crystalpay_api_secret) if s else None
            
            if not login or not secret or login == "DECRYPTION_ERROR" or secret == "DECRYPTION_ERROR":
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "CrystalPay not configured"
                    }
                }), 500
            
            payload = {
                "auth_login": login, "auth_secret": secret,
                "amount": f"{final_amount:.2f}", "type": "purchase", "currency": info['c'],
                "lifetime": 60, "extra": order_id, 
                "callback_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/crystalpay",
                "redirect_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/miniapp/"
            }
            
            resp = requests.post("https://api.crystalpay.io/v3/invoice/create/", json=payload).json()
            if resp.get('errors'): 
                return jsonify({
                    "detail": {
                        "title": "Payment Error",
                        "message": "Failed to create payment"
                    }
                }), 500
            
            payment_url = resp.get('url')
            payment_system_id = resp.get('id')
        
        if not payment_url:
            return jsonify({
                "detail": {
                    "title": "Payment Error",
                    "message": "Failed to create payment"
                }
            }), 500
        
        # Создаем запись о платеже
        new_p = Payment(
            order_id=order_id, 
            user_id=user.id, 
            tariff_id=t.id, 
            status='PENDING', 
            amount=final_amount, 
            currency=info['c'], 
            payment_system_id=payment_system_id,
            payment_provider=payment_provider,
            promo_code_id=promo_code_obj.id if promo_code_obj else None
        )
        db.session.add(new_p)
        db.session.commit()
        
        response = jsonify({
            "payment_url": payment_url,
            "payment_id": payment_system_id,
            "order_id": order_id
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
        
    except Exception as e:
        print(f"Error in miniapp_create_payment: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            "detail": {
                "title": "Internal Server Error",
                "message": "An error occurred while processing the request."
            }
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/miniapp/payments/status', methods=['POST', 'OPTIONS'])
@limiter.limit("30 per minute")
def miniapp_payment_status():
    """Получить статус платежа для miniapp"""
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    try:
        data = {}
        if request.is_json:
            data = request.json or {}
        elif request.form:
            data = dict(request.form)
        elif request.data:
            try:
                import json as json_lib
                data = json_lib.loads(request.data.decode('utf-8'))
            except:
                pass
        
        payment_id = data.get('payment_id') or data.get('paymentId') or data.get('order_id') or data.get('orderId')
        
        if not payment_id:
            return jsonify({
                "detail": {
                    "title": "Invalid Request",
                    "message": "payment_id is required"
                }
            }), 400
        
        # Находим платеж
        p = Payment.query.filter_by(order_id=payment_id).first()
        if not p:
            p = Payment.query.filter_by(payment_system_id=payment_id).first()
        
        if not p:
            return jsonify({
                "status": "not_found",
                "paid": False
            }), 200
        
        response = jsonify({
            "status": p.status.lower(),
            "paid": p.status == 'PAID',
            "order_id": p.order_id,
            "amount": p.amount,
            "currency": p.currency
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
        
    except Exception as e:
        print(f"Error in miniapp_payment_status: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            "status": "error",
            "paid": False
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 200

@app.route('/miniapp/promo-codes/activate', methods=['POST', 'OPTIONS'])
@limiter.limit("10 per minute")
def miniapp_activate_promocode():
    """Активировать промокод через miniapp"""
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    try:
        # Парсим initData
        data = {}
        if request.is_json:
            data = request.json or {}
        elif request.form:
            data = dict(request.form)
        elif request.data:
            try:
                import json as json_lib
                data = json_lib.loads(request.data.decode('utf-8'))
            except:
                pass
        
        init_data = data.get('initData') or request.headers.get('X-Telegram-Init-Data') or request.headers.get('X-Init-Data') or request.args.get('initData')
        
        if not init_data:
            init_data_unsafe = data.get('initDataUnsafe', {})
            if isinstance(init_data_unsafe, dict) and init_data_unsafe.get('user'):
                user_data = init_data_unsafe['user']
                telegram_id = user_data.get('id')
            else:
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Missing initData. Please open the mini app from Telegram."
                    }
                }), 401
        else:
            import urllib.parse
            import json as json_lib
            
            if isinstance(init_data, dict):
                parsed_data = init_data
            else:
                parsed_data = urllib.parse.parse_qs(init_data)
            
            user_str = parsed_data.get('user', [''])[0] if isinstance(parsed_data, dict) and 'user' in parsed_data else None
            if not user_str and isinstance(parsed_data, dict):
                user_str = parsed_data.get('user')
            
            if not user_str:
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Invalid initData format."
                    }
                }), 401
            
            try:
                if isinstance(user_str, str):
                    user_data = json_lib.loads(urllib.parse.unquote(user_str))
                else:
                    user_data = user_str
                telegram_id = user_data.get('id')
            except (json_lib.JSONDecodeError, KeyError, TypeError):
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Invalid user data in initData."
                    }
                }), 401
        
        if not telegram_id:
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Telegram ID not found in initData."
                }
            }), 401
        
        # Находим пользователя
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            return jsonify({
                "detail": {
                    "title": "User Not Found",
                    "message": "User not registered. Please register in the bot first."
                }
            }), 404
        
        # Получаем промокод
        promo_code_str = data.get('promo_code') or data.get('promoCode', '').strip().upper()
        if not promo_code_str:
            return jsonify({
                "detail": {
                    "title": "Invalid Request",
                    "message": "promo_code is required"
                }
            }), 400
        
        # Активируем промокод (используем логику из activate_promocode)
        promo = PromoCode.query.filter_by(code=promo_code_str).first()
        if not promo:
            return jsonify({
                "detail": {
                    "title": "Invalid Promo Code",
                    "message": "Неверный промокод"
                }
            }), 400
        
        if promo.uses_left <= 0:
            return jsonify({
                "detail": {
                    "title": "Invalid Promo Code",
                    "message": "Промокод больше не действителен"
                }
            }), 400
        
        if promo.promo_type == 'DAYS':
            # Применяем бесплатные дни
            h, c = get_remnawave_headers()
            live = requests.get(f"{API_URL}/api/users/{user.remnawave_uuid}", headers=h, cookies=c).json().get('response', {})
            curr_exp = parse_iso_datetime(live.get('expireAt'))
            new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=promo.value)
            
            patch_resp = requests.patch(
                f"{API_URL}/api/users",
                headers={"Content-Type": "application/json", **h},
                json={"uuid": user.remnawave_uuid, "expireAt": new_exp.isoformat()},
                timeout=10
            )
            
            if not patch_resp.ok:
                return jsonify({
                    "detail": {
                        "title": "Internal Server Error",
                        "message": "Failed to activate promo code"
                    }
                }), 500
            
            # Списываем использование промокода
            promo.uses_left -= 1
            db.session.commit()
            
            cache.delete(f'live_data_{user.remnawave_uuid}')
            cache.delete('all_live_users_map')
            
            response = jsonify({
                "success": True,
                "message": f"Промокод активирован! Вы получили {promo.value} бесплатных дней."
            })
        elif promo.promo_type == 'PERCENT':
            # Процентные промокоды применяются при создании платежа
            response = jsonify({
                "success": True,
                "message": f"Промокод действителен! Скидка {promo.value}% будет применена при оплате."
            })
        else:
            return jsonify({
                "detail": {
                    "title": "Invalid Promo Code",
                    "message": "Неизвестный тип промокода"
                }
            }), 400
        
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
        
    except Exception as e:
        print(f"Error in miniapp_activate_promocode: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            "detail": {
                "title": "Internal Server Error",
                "message": "An error occurred while processing the request."
            }
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/miniapp/promo-offers/<offer_id>/claim', methods=['POST', 'OPTIONS'])
@limiter.limit("10 per minute")
def miniapp_claim_promo_offer(offer_id):
    """Активировать промо-оффер через miniapp (алиас для промокода)"""
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    # Перенаправляем на активацию промокода
    # offer_id может быть кодом промокода
    try:
        data = {}
        if request.is_json:
            data = request.json or {}
        elif request.form:
            data = dict(request.form)
        elif request.data:
            try:
                import json as json_lib
                data = json_lib.loads(request.data.decode('utf-8'))
            except:
                pass
        
        # Используем offer_id как код промокода
        data['promo_code'] = offer_id
        request.json = data
        
        # Вызываем функцию активации промокода
        return miniapp_activate_promocode()
        
    except Exception as e:
        print(f"Error in miniapp_claim_promo_offer: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            "detail": {
                "title": "Internal Server Error",
                "message": "An error occurred while processing the request."
            }
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/miniapp/nodes', methods=['POST', 'OPTIONS'])
@limiter.limit("30 per minute")
def miniapp_nodes():
    """Получить список серверов для miniapp"""
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    try:
        data = request.json or {}
        init_data = data.get('initData') or data.get('init_data') or data.get('data') or ''
        
        if not init_data:
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Missing initData"
                }
            }), 401
        
        # Парсим initData (используем ту же логику, что и в miniapp_subscription)
        import urllib.parse
        parsed_data = urllib.parse.parse_qs(init_data)
        user_str = parsed_data.get('user', [''])[0]
        
        if not user_str:
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Invalid initData format"
                }
            }), 401
        
        import json as json_lib
        user_data = json_lib.loads(user_str)
        telegram_id = user_data.get('id')
        
        if not telegram_id:
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "User ID not found in initData"
                }
            }), 401
        
        # Находим пользователя
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            return jsonify({
                "detail": {
                    "title": "User Not Found",
                    "message": "User not registered"
                }
            }), 404
        
        # Получаем серверы
        headers, cookies = get_remnawave_headers()
        resp = requests.get(f"{API_URL}/api/users/{user.remnawave_uuid}/accessible-nodes", headers=headers, cookies=cookies, timeout=10)
        
        if resp.status_code == 200:
            nodes_data = resp.json()
            response = jsonify(nodes_data)
            response.headers.add('Access-Control-Allow-Origin', '*')
            return response, 200
        else:
            return jsonify({
                "detail": {
                    "title": "Error",
                    "message": "Failed to fetch nodes"
                }
            }), 500
            
    except Exception as e:
        print(f"Error in miniapp_nodes: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            "detail": {
                "title": "Internal Server Error",
                "message": str(e)
            }
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/miniapp/tariffs', methods=['POST', 'OPTIONS'])
@limiter.limit("30 per minute")
def miniapp_tariffs():
    """Получить список тарифов для miniapp"""
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    try:
        tariffs = Tariff.query.all()
        tariffs_list = [{
            "id": t.id, 
            "name": t.name, 
            "duration_days": t.duration_days, 
            "price_uah": t.price_uah, 
            "price_rub": t.price_rub, 
            "price_usd": t.price_usd,
            "squad_id": t.squad_id,
            "traffic_limit_bytes": t.traffic_limit_bytes or 0,
            "tier": t.tier,
            "badge": t.badge
        } for t in tariffs]
        
        response = jsonify({"tariffs": tariffs_list})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
    except Exception as e:
        print(f"Error in miniapp_tariffs: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({"tariffs": []})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 200

@app.route('/miniapp/subscription/renewal/options', methods=['POST', 'OPTIONS'])
@limiter.limit("30 per minute")
def miniapp_subscription_renewal_options():
    """Получить опции продления подписки для miniapp"""
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    try:
        # Парсим initData для получения пользователя
        data = {}
        if request.is_json:
            data = request.json or {}
        elif request.form:
            data = dict(request.form)
        elif request.data:
            try:
                import json as json_lib
                data = json_lib.loads(request.data.decode('utf-8'))
            except:
                pass
        
        init_data = data.get('initData') or request.headers.get('X-Telegram-Init-Data') or request.headers.get('X-Init-Data') or request.args.get('initData')
        
        if not init_data:
            init_data_unsafe = data.get('initDataUnsafe', {})
            if isinstance(init_data_unsafe, dict) and init_data_unsafe.get('user'):
                user_data = init_data_unsafe['user']
                telegram_id = user_data.get('id')
            else:
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Missing initData. Please open the mini app from Telegram."
                    }
                }), 401
        else:
            import urllib.parse
            import json as json_lib
            
            if isinstance(init_data, dict):
                parsed_data = init_data
            else:
                parsed_data = urllib.parse.parse_qs(init_data)
            
            user_str = parsed_data.get('user', [''])[0] if isinstance(parsed_data, dict) and 'user' in parsed_data else None
            if not user_str and isinstance(parsed_data, dict):
                user_str = parsed_data.get('user')
            
            if not user_str:
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Invalid initData format."
                    }
                }), 401
            
            try:
                if isinstance(user_str, str):
                    user_data = json_lib.loads(urllib.parse.unquote(user_str))
                else:
                    user_data = user_str
                telegram_id = user_data.get('id')
            except (json_lib.JSONDecodeError, KeyError, TypeError):
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Invalid user data in initData."
                    }
                }), 401
        
        if not telegram_id:
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Telegram ID not found in initData."
                }
            }), 401
        
        # Находим пользователя
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            return jsonify({
                "detail": {
                    "title": "User Not Found",
                    "message": "User not registered. Please register in the bot first."
                }
            }), 404
        
        # Получаем данные подписки
        h, c = get_remnawave_headers()
        live = requests.get(f"{API_URL}/api/users/{user.remnawave_uuid}", headers=h, cookies=c).json().get('response', {})
        
        # Получаем тарифы для продления
        tariffs = Tariff.query.all()
        
        # Определяем валюту пользователя
        currency = user.preferred_currency.upper() if user.preferred_currency else 'UAH'
        currency_map = {'UAH': 'UAH', 'RUB': 'RUB', 'USD': 'USD'}
        currency = currency_map.get(currency, 'UAH')
        
        # Формируем опции продления
        periods = []
        for t in tariffs:
            price_map = {"uah": t.price_uah, "rub": t.price_rub, "usd": t.price_usd}
            price = price_map.get(currency.lower(), t.price_uah)
            
            periods.append({
                "id": t.id,
                "duration_days": t.duration_days,
                "price": price,
                "currency": currency,
                "name": t.name
            })
        
        # Получаем баланс пользователя (если есть)
        balance = 0.0  # Можно добавить поле balance в модель User
        
        response_data = {
            "renewal": {
                "periods": periods,
                "currency": currency,
                "balance": balance,
                "balance_kopeks": int(balance * 100) if currency == 'RUB' else int(balance * 100),
                "subscription_id": user.id  # Используем user.id как subscription_id
            }
        }
        
        response = jsonify(response_data)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
        
    except Exception as e:
        print(f"Error in miniapp_subscription_renewal_options: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            "detail": {
                "title": "Internal Server Error",
                "message": "An error occurred while processing the request."
            }
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/miniapp/subscription/settings', methods=['POST', 'OPTIONS'])
@limiter.limit("30 per minute")
def miniapp_subscription_settings():
    """Получить настройки подписки для miniapp"""
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    try:
        # Парсим initData для получения пользователя
        data = {}
        if request.is_json:
            data = request.json or {}
        elif request.form:
            data = dict(request.form)
        elif request.data:
            try:
                import json as json_lib
                data = json_lib.loads(request.data.decode('utf-8'))
            except:
                pass
        
        init_data = data.get('initData') or request.headers.get('X-Telegram-Init-Data') or request.headers.get('X-Init-Data') or request.args.get('initData')
        
        if not init_data:
            init_data_unsafe = data.get('initDataUnsafe', {})
            if isinstance(init_data_unsafe, dict) and init_data_unsafe.get('user'):
                user_data = init_data_unsafe['user']
                telegram_id = user_data.get('id')
            else:
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Missing initData. Please open the mini app from Telegram."
                    }
                }), 401
        else:
            import urllib.parse
            import json as json_lib
            
            if isinstance(init_data, dict):
                parsed_data = init_data
            else:
                parsed_data = urllib.parse.parse_qs(init_data)
            
            user_str = parsed_data.get('user', [''])[0] if isinstance(parsed_data, dict) and 'user' in parsed_data else None
            if not user_str and isinstance(parsed_data, dict):
                user_str = parsed_data.get('user')
            
            if not user_str:
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Invalid initData format."
                    }
                }), 401
            
            try:
                if isinstance(user_str, str):
                    user_data = json_lib.loads(urllib.parse.unquote(user_str))
                else:
                    user_data = user_str
                telegram_id = user_data.get('id')
            except (json_lib.JSONDecodeError, KeyError, TypeError):
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Invalid user data in initData."
                    }
                }), 401
        
        if not telegram_id:
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Telegram ID not found in initData."
                }
            }), 401
        
        # Находим пользователя
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            return jsonify({
                "detail": {
                    "title": "User Not Found",
                    "message": "User not registered. Please register in the bot first."
                }
            }), 404
        
        # Получаем данные подписки
        h, c = get_remnawave_headers()
        live = requests.get(f"{API_URL}/api/users/{user.remnawave_uuid}", headers=h, cookies=c).json().get('response', {})
        
        # Получаем доступные серверы (ноды)
        nodes_resp = requests.get(f"{API_URL}/api/users/{user.remnawave_uuid}/accessible-nodes", headers=h)
        nodes_data = []
        if nodes_resp.status_code == 200:
            nodes_json = nodes_resp.json()
            if isinstance(nodes_json, dict) and 'response' in nodes_json:
                nodes_list = nodes_json.get('response', [])
            elif isinstance(nodes_json, list):
                nodes_list = nodes_json
            else:
                nodes_list = []
            
            for node in nodes_list:
                if isinstance(node, dict):
                    nodes_data.append({
                        "uuid": node.get('uuid'),
                        "name": node.get('name') or node.get('location') or 'Unknown',
                        "country": node.get('country') or node.get('location') or 'Unknown',
                        "is_online": node.get('isOnline') or node.get('is_online') or False
                    })
        
        # Получаем текущие подключенные серверы
        current_servers = live.get('activeInternalSquads', []) or []
        
        # Получаем информацию о трафике
        traffic_limit_bytes = live.get('trafficLimitBytes') or 0
        used_traffic_bytes = live.get('usedTrafficBytes') or live.get('lifetimeUsedTrafficBytes') or 0
        
        # Получаем информацию об устройствах
        hwid_device_limit = live.get('hwidDeviceLimit') or 0
        
        # Формируем ответ
        response_data = {
            "settings": {
                "current": {
                    "servers": current_servers,
                    "connected_servers": current_servers
                },
                "servers": {
                    "available": nodes_data,
                    "countries": nodes_data
                },
                "traffic": {
                    "limit_bytes": traffic_limit_bytes,
                    "used_bytes": used_traffic_bytes,
                    "limit_gb": round(traffic_limit_bytes / (1024 ** 3), 2) if traffic_limit_bytes > 0 else 0,
                    "used_gb": round(used_traffic_bytes / (1024 ** 3), 2),
                    "unlimited": traffic_limit_bytes == 0
                },
                "devices": {
                    "limit": hwid_device_limit,
                    "current": 0  # Можно добавить отслеживание текущих устройств
                }
            }
        }
        
        response = jsonify(response_data)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
        
    except Exception as e:
        print(f"Error in miniapp_subscription_settings: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            "detail": {
                "title": "Internal Server Error",
                "message": "An error occurred while processing the request."
            }
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/api/client/nodes', methods=['GET'])
def get_client_nodes():
    user = get_user_from_token()
    if not user: return jsonify({"message": "Ошибка аутентификации"}), 401
    
    # Проверяем параметр force_refresh для принудительного обновления
    force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
    
    if not force_refresh:
        if cached := cache.get(f'nodes_{user.remnawave_uuid}'): 
            return jsonify(cached), 200
    
    try:
        headers, cookies = get_remnawave_headers()
        resp = requests.get(f"{API_URL}/api/users/{user.remnawave_uuid}/accessible-nodes", headers=headers, cookies=cookies)
        resp.raise_for_status()
        data = resp.json()
        cache.set(f'nodes_{user.remnawave_uuid}', data, timeout=600)
        return jsonify(data), 200
    except Exception as e: 
        print(f"Error fetching nodes: {e}")
        return jsonify({"message": "Internal Error"}), 500

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def get_all_users(current_admin):
    try:
        local_users = User.query.all()
        live_map = cache.get('all_live_users_map')
        if not live_map:
            headers, cookies = get_remnawave_headers()
            resp = requests.get(f"{API_URL}/api/users", headers=headers, cookies=cookies)
            data = resp.json().get('response', {})
            # Безопасный парсинг
            users_list = data.get('users', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            live_map = {u['uuid']: u for u in users_list if isinstance(u, dict) and 'uuid' in u}
            cache.set('all_live_users_map', live_map, timeout=60)
            
        combined = []
        for u in local_users:
            combined.append({
                "id": u.id, "email": u.email, "role": u.role, "remnawave_uuid": u.remnawave_uuid,
                "referral_code": u.referral_code, "referrer_id": u.referrer_id, "is_verified": u.is_verified,
                "balance": float(u.balance) if u.balance else 0.0,
                "preferred_currency": u.preferred_currency or 'uah',
                "live_data": {"response": live_map.get(u.remnawave_uuid)}
            })
        return jsonify(combined), 200
    except Exception as e: 
        print(e); return jsonify({"message": "Internal Error"}), 500

@app.route('/api/admin/sync-bot-users', methods=['POST'])
@admin_required
def sync_bot_users(current_admin):
    """
    Синхронизация пользователей из Telegram бота в веб-панель.
    Получает всех пользователей из бота и создает/обновляет их в веб-панели.
    """
    if not BOT_API_URL or not BOT_API_TOKEN:
        return jsonify({"message": "Bot API not configured"}), 500
    
    try:
        # Получаем всех пользователей из бота
        bot_resp = requests.get(
            f"{BOT_API_URL}/users",
            headers={"X-API-Key": BOT_API_TOKEN},
            params={"limit": 1000},  # Получаем до 1000 пользователей
            timeout=30
        )
        
        if bot_resp.status_code != 200:
            return jsonify({"message": f"Bot API error: {bot_resp.status_code}"}), 500
        
        bot_data = bot_resp.json()
        bot_users = []
        
        # Парсим ответ в зависимости от формата
        if isinstance(bot_data, dict):
            if 'items' in bot_data:
                bot_users = bot_data['items']
            elif 'response' in bot_data:
                if isinstance(bot_data['response'], list):
                    bot_users = bot_data['response']
                elif isinstance(bot_data['response'], dict) and 'items' in bot_data['response']:
                    bot_users = bot_data['response']['items']
        elif isinstance(bot_data, list):
            bot_users = bot_data
        
        if not bot_users:
            return jsonify({"message": "No users found in bot", "synced": 0, "created": 0, "updated": 0}), 200
        
        sys_settings = SystemSetting.query.first() or SystemSetting(id=1)
        if not sys_settings.id:
            db.session.add(sys_settings)
            db.session.flush()
        
        synced = 0
        created = 0
        updated = 0
        
        for bot_user in bot_users:
            telegram_id = bot_user.get('telegram_id')
            remnawave_uuid = bot_user.get('remnawave_uuid') or bot_user.get('uuid')
            
            if not remnawave_uuid:
                continue  # Пропускаем пользователей без remnawave_uuid
            
            # Ищем пользователя по telegram_id или remnawave_uuid
            user = None
            if telegram_id:
                user = User.query.filter_by(telegram_id=telegram_id).first()
            
            if not user:
                user = User.query.filter_by(remnawave_uuid=remnawave_uuid).first()
            
            telegram_username = bot_user.get('username') or bot_user.get('telegram_username')
            first_name = bot_user.get('first_name', '')
            last_name = bot_user.get('last_name', '')
            
            if user:
                # Обновляем существующего пользователя
                if telegram_id and not user.telegram_id:
                    user.telegram_id = telegram_id
                if telegram_username and user.telegram_username != telegram_username:
                    user.telegram_username = telegram_username
                if not user.email:
                    user.email = f"tg_{telegram_id}@telegram.local" if telegram_id else f"user_{user.id}@telegram.local"
                if not user.is_verified and telegram_id:
                    user.is_verified = True  # Telegram пользователи считаются верифицированными
                updated += 1
            else:
                # Создаем нового пользователя
                user = User(
                    telegram_id=telegram_id,
                    telegram_username=telegram_username,
                    email=f"tg_{telegram_id}@telegram.local" if telegram_id else f"user_{remnawave_uuid[:8]}@telegram.local",
                    password_hash=None,
                    remnawave_uuid=remnawave_uuid,
                    is_verified=True if telegram_id else False,
                    preferred_lang=sys_settings.default_language,
                    preferred_currency=sys_settings.default_currency
                )
                db.session.add(user)
                db.session.flush()
                user.referral_code = generate_referral_code(user.id)
                created += 1
            
            synced += 1
        
        db.session.commit()
        
        return jsonify({
            "message": "Sync completed",
            "synced": synced,
            "created": created,
            "updated": updated
        }), 200
        
    except requests.RequestException as e:
        print(f"Bot API Error: {e}")
        return jsonify({"message": f"Cannot connect to bot API: {str(e)}"}), 500
    except Exception as e:
        print(f"Sync Error: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({"message": f"Internal Server Error: {str(e)}"}), 500

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(current_admin, user_id):
    try:
        u = db.session.get(User, user_id)
        if not u: return jsonify({"message": "Not found"}), 404
        if u.id == current_admin.id: return jsonify({"message": "Cannot delete self"}), 400
        
        # Удаляем все связанные записи перед удалением пользователя
        
        # 1. Удаляем сообщения тикетов, где пользователь является отправителем
        TicketMessage.query.filter_by(sender_id=u.id).delete()
        
        # 2. Удаляем все тикеты пользователя и их сообщения
        user_tickets = Ticket.query.filter_by(user_id=u.id).all()
        for ticket in user_tickets:
            # Удаляем все сообщения тикета
            TicketMessage.query.filter_by(ticket_id=ticket.id).delete()
            # Удаляем сам тикет
            db.session.delete(ticket)
        
        # 3. Удаляем все платежи пользователя
        Payment.query.filter_by(user_id=u.id).delete()
        
        # 4. Обнуляем referrer_id у пользователей, которые ссылаются на удаляемого пользователя
        User.query.filter_by(referrer_id=u.id).update({User.referrer_id: None})
        
        try:
            headers, cookies = get_remnawave_headers()
            requests.delete(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=headers, cookies=cookies)
        except: pass
        cache.delete('all_live_users_map')
        db.session.delete(u)
        db.session.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception as e: 
        db.session.rollback()
        return jsonify({"message": str(e)}), 500

@app.route('/api/admin/users/<int:user_id>/balance', methods=['PUT', 'PATCH'])
@admin_required
def update_user_balance(current_admin, user_id):
    """Обновить баланс пользователя (добавить или установить)"""
    try:
        u = db.session.get(User, user_id)
        if not u:
            return jsonify({"message": "Пользователь не найден"}), 404
        
        data = request.json
        action = data.get('action', 'set')  # 'set' - установить, 'add' - добавить, 'subtract' - списать
        amount = data.get('amount', 0)
        description = data.get('description', 'Изменение баланса администратором')
        
        if amount < 0:
            return jsonify({"message": "Сумма не может быть отрицательной"}), 400
        
        # Получаем валюту из запроса или используем USD по умолчанию
        currency = data.get('currency', 'USD').upper()
        
        # Конвертируем сумму в USD (баланс всегда хранится в USD)
        amount_usd = convert_to_usd(float(amount), currency)
        
        current_balance_usd = float(u.balance) if u.balance else 0.0
        
        if action == 'set':
            new_balance_usd = amount_usd
        elif action == 'add':
            new_balance_usd = current_balance_usd + amount_usd
        elif action == 'subtract':
            new_balance_usd = current_balance_usd - amount_usd
            if new_balance_usd < 0:
                return jsonify({"message": "Недостаточно средств на балансе"}), 400
        else:
            return jsonify({"message": "Неверное действие. Используйте: set, add, subtract"}), 400
        
        u.balance = new_balance_usd
        db.session.commit()
        
        # Очищаем кэш пользователя
        cache.delete(f'live_data_{u.remnawave_uuid}')
        cache.delete('all_live_users_map')
        
        # Конвертируем баланс обратно в валюту пользователя для отображения
        balance_display = convert_from_usd(new_balance_usd, u.preferred_currency)
        previous_balance_display = convert_from_usd(current_balance_usd, u.preferred_currency)
        change_display = convert_from_usd(new_balance_usd - current_balance_usd, u.preferred_currency)
        
        return jsonify({
            "message": "Баланс успешно обновлен",
            "balance": balance_display,
            "previous_balance": previous_balance_display,
            "change": change_display,
            "balance_usd": float(new_balance_usd),
            "currency": u.preferred_currency
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Ошибка обновления баланса: {str(e)}"}), 500

@app.route('/api/admin/users/<int:user_id>/change-password', methods=['POST'])
@admin_required
def admin_change_user_password(current_admin, user_id):
    """Изменение пароля пользователя администратором"""
    try:
        u = db.session.get(User, user_id)
        if not u:
            return jsonify({"message": "Пользователь не найден"}), 404
        
        data = request.json
        new_password = data.get('new_password')
        
        if not new_password:
            return jsonify({"message": "Требуется новый пароль"}), 400
        
        if len(new_password) < 6:
            return jsonify({"message": "Пароль должен содержать минимум 6 символов"}), 400
        
        # Хешируем новый пароль
        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        u.password_hash = hashed_password
        
        # Сохраняем зашифрованный пароль для бота
        if fernet:
            try:
                u.encrypted_password = fernet.encrypt(new_password.encode()).decode()
            except Exception as e:
                print(f"[ADMIN CHANGE PASSWORD] Ошибка шифрования пароля: {e}")
        
        db.session.commit()
        
        return jsonify({
            "message": "Пароль успешно изменен",
            "user_email": u.email
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"[ADMIN CHANGE PASSWORD] Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": f"Ошибка: {str(e)}"}), 500

@app.route('/api/admin/users/<int:user_id>/update', methods=['POST'])
@admin_required
def admin_update_user(current_admin, user_id):
    """Обновление пользователя: выдача тарифа, триал, лимит устройств"""
    try:
        u = db.session.get(User, user_id)
        if not u:
            return jsonify({"message": "Пользователь не найден"}), 404
        
        data = request.json
        
        # Получаем текущие данные пользователя из RemnaWave
        headers, cookies = get_remnawave_headers()
        resp = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=headers, cookies=cookies)
        
        if not resp.ok:
            return jsonify({"message": "Не удалось получить данные пользователя из RemnaWave"}), 500
        
        live_data = resp.json().get('response', {})
        current_expire = parse_iso_datetime(live_data.get('expireAt')) if live_data.get('expireAt') else datetime.now(timezone.utc)
        
        # Формируем payload для обновления
        patch_payload = {"uuid": u.remnawave_uuid}
        
        # Обработка выдачи тарифа
        if 'tariff_id' in data and data['tariff_id']:
            tariff = db.session.get(Tariff, data['tariff_id'])
            if not tariff:
                return jsonify({"message": "Тариф не найден"}), 404
            
            # Вычисляем новую дату окончания
            new_exp = max(datetime.now(timezone.utc), current_expire) + timedelta(days=tariff.duration_days)
            patch_payload["expireAt"] = new_exp.isoformat()
            
            # Используем сквад из тарифа, если указан, иначе дефолтный
            squad_id = tariff.squad_id if tariff.squad_id else DEFAULT_SQUAD_ID
            patch_payload["activeInternalSquads"] = [squad_id]
            
            # Добавляем лимит трафика, если указан в тарифе
            if tariff.traffic_limit_bytes and tariff.traffic_limit_bytes > 0:
                patch_payload["trafficLimitBytes"] = tariff.traffic_limit_bytes
                patch_payload["trafficLimitStrategy"] = "NO_RESET"
            
            # Добавляем лимит устройств, если указан в тарифе
            if tariff.hwid_device_limit and tariff.hwid_device_limit > 0:
                patch_payload["hwidDeviceLimit"] = tariff.hwid_device_limit
        
        # Обработка триала
        elif 'trial_days' in data and data['trial_days']:
            trial_days = int(data['trial_days'])
            if trial_days <= 0:
                return jsonify({"message": "Количество дней триала должно быть больше 0"}), 400
            
            # Получаем настройки рефералов для триального сквада
            referral_settings = ReferralSetting.query.first()
            trial_squad_id = referral_settings.trial_squad_id if referral_settings and referral_settings.trial_squad_id else DEFAULT_SQUAD_ID
            
            new_exp = max(datetime.now(timezone.utc), current_expire) + timedelta(days=trial_days)
            patch_payload["expireAt"] = new_exp.isoformat()
            patch_payload["activeInternalSquads"] = [trial_squad_id]
        
        # Обработка лимита устройств
        if 'hwid_device_limit' in data:
            hwid_limit = data['hwid_device_limit']
            if hwid_limit is not None:
                hwid_limit = int(hwid_limit) if int(hwid_limit) >= 0 else None
            patch_payload["hwidDeviceLimit"] = hwid_limit
        
        # Отправляем обновление в RemnaWave
        patch_headers, patch_cookies = get_remnawave_headers({"Content-Type": "application/json"})
        patch_resp = requests.patch(f"{API_URL}/api/users", headers=patch_headers, cookies=patch_cookies, json=patch_payload)
        
        if not patch_resp.ok:
            error_text = patch_resp.text
            print(f"[ADMIN UPDATE USER] Ошибка обновления в RemnaWave: {patch_resp.status_code} - {error_text}")
            return jsonify({"message": f"Ошибка обновления в RemnaWave: {error_text}"}), 500
        
        # Очищаем кэш
        cache.delete(f'live_data_{u.remnawave_uuid}')
        cache.delete('all_live_users_map')
        
        return jsonify({
            "message": "Пользователь успешно обновлен",
            "user_email": u.email
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"[ADMIN UPDATE USER] Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": f"Ошибка: {str(e)}"}), 500

# --- SQUADS (Сквады) ---
@app.route('/api/admin/squads', methods=['GET'])
@admin_required
def get_squads(current_admin):
    """Получить список всех сквадов из внешнего API"""
    try:
        # Используем ADMIN_TOKEN для запроса к API
        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        
        # Запрос к API используя API_URL из переменных окружения
        resp = requests.get(f"{API_URL}/api/internal-squads", headers=headers, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        
        # Обрабатываем ответ согласно структуре API
        # Ответ приходит в формате: {"response": {"total": N, "internalSquads": [...]}}
        if isinstance(data, dict) and 'response' in data:
            response_data = data['response']
            if isinstance(response_data, dict) and 'internalSquads' in response_data:
                squads_list = response_data['internalSquads']
            else:
                # Если структура другая, пытаемся извлечь массив
                squads_list = response_data if isinstance(response_data, list) else []
        elif isinstance(data, list):
            squads_list = data
        else:
            squads_list = []
        
        # Кэшируем на 5 минут
        cache.set('squads_list', squads_list, timeout=300)
        return jsonify(squads_list), 200
    except requests.exceptions.RequestException as e:
        # Если внешний API недоступен, возвращаем кэш или пустой список
        cached = cache.get('squads_list')
        if cached:
            return jsonify(cached), 200
        return jsonify({"error": "Failed to fetch squads", "message": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Internal error", "message": str(e)}), 500

# --- NODES (Ноды) ---
@app.route('/api/admin/nodes', methods=['GET'])
@admin_required
def get_nodes(current_admin):
    """Получить список всех нод из внешнего API"""
    try:
        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        resp = requests.get(f"{API_URL}/api/nodes", headers=headers, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        
        # Обрабатываем ответ согласно структуре API
        if isinstance(data, dict) and 'response' in data:
            nodes_list = data['response']
            if isinstance(nodes_list, dict) and 'nodes' in nodes_list:
                nodes_list = nodes_list['nodes']
            elif not isinstance(nodes_list, list):
                nodes_list = []
        elif isinstance(data, list):
            nodes_list = data
        else:
            nodes_list = []
        
        # Логируем структуру для отладки (только первые несколько символов)
        if nodes_list and len(nodes_list) > 0:
            print(f"[NODES DEBUG] Получено {len(nodes_list)} нод")
            print(f"[NODES DEBUG] Первая нода (первые поля): {list(nodes_list[0].keys())[:10] if isinstance(nodes_list[0], dict) else 'not a dict'}")
            if isinstance(nodes_list[0], dict):
                sample_node = nodes_list[0]
                print(f"[NODES DEBUG] Пример полей: status={sample_node.get('status')}, isOnline={sample_node.get('isOnline')}, isActive={sample_node.get('isActive')}, state={sample_node.get('state')}, isConnected={sample_node.get('isConnected')}")
        
        # Кэшируем на 2 минуты (ноды могут часто меняться)
        cache.set('nodes_list', nodes_list, timeout=120)
        return jsonify(nodes_list), 200
    except requests.exceptions.RequestException as e:
        cached = cache.get('nodes_list')
        if cached:
            return jsonify(cached), 200
        return jsonify({"error": "Failed to fetch nodes", "message": str(e)}), 500
    except Exception as e:
        print(f"[NODES ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal error", "message": str(e)}), 500

@app.route('/api/admin/nodes/<uuid>/restart', methods=['POST'])
@admin_required
def restart_node(current_admin, uuid):
    """Перезапустить конкретную ноду"""
    try:
        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        resp = requests.post(
            f"{API_URL}/api/nodes/{uuid}/actions/restart",
            headers=headers,
            timeout=30
        )
        resp.raise_for_status()
        
        # Очищаем кэш нод после перезапуска
        cache.delete('nodes_list')
        
        data = resp.json()
        return jsonify({"message": "Node restart initiated", "response": data}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Failed to restart node", "message": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Internal error", "message": str(e)}), 500

@app.route('/api/admin/nodes/restart-all', methods=['POST'])
@admin_required
def restart_all_nodes(current_admin):
    """Перезапустить все ноды"""
    try:
        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        resp = requests.post(
            f"{API_URL}/api/nodes/actions/restart-all",
            headers=headers,
            timeout=60
        )
        resp.raise_for_status()
        
        # Очищаем кэш нод после перезапуска
        cache.delete('nodes_list')
        
        data = resp.json()
        return jsonify({"message": "All nodes restart initiated", "response": data}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Failed to restart all nodes", "message": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Internal error", "message": str(e)}), 500

@app.route('/api/admin/nodes/<uuid>/enable', methods=['POST'])
@admin_required
def enable_node(current_admin, uuid):
    """Включить конкретную ноду"""
    try:
        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        resp = requests.post(
            f"{API_URL}/api/nodes/{uuid}/actions/enable",
            headers=headers,
            timeout=30
        )
        resp.raise_for_status()
        
        # Очищаем кэш нод после изменения
        cache.delete('nodes_list')
        
        data = resp.json()
        return jsonify({"message": "Node enabled", "response": data}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Failed to enable node", "message": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Internal error", "message": str(e)}), 500

@app.route('/api/admin/nodes/<uuid>/disable', methods=['POST'])
@admin_required
def disable_node(current_admin, uuid):
    """Отключить конкретную ноду"""
    try:
        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        resp = requests.post(
            f"{API_URL}/api/nodes/{uuid}/actions/disable",
            headers=headers,
            timeout=30
        )
        resp.raise_for_status()
        
        # Очищаем кэш нод после изменения
        cache.delete('nodes_list')
        
        data = resp.json()
        return jsonify({"message": "Node disabled", "response": data}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Failed to disable node", "message": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Internal error", "message": str(e)}), 500

# --- TARIFFS ---
@app.route('/api/admin/tariffs', methods=['GET'])
@admin_required
def get_tariffs(current_admin):
    return jsonify([{
        "id": t.id, 
        "name": t.name, 
        "duration_days": t.duration_days, 
        "price_uah": t.price_uah, 
        "price_rub": t.price_rub, 
        "price_usd": t.price_usd,
        "squad_id": t.squad_id,
        "traffic_limit_bytes": t.traffic_limit_bytes or 0,
        "hwid_device_limit": t.hwid_device_limit if t.hwid_device_limit is not None else 0,
        "tier": t.tier,
        "badge": t.badge,
        "bonus_days": t.bonus_days if t.bonus_days is not None else 0
    } for t in Tariff.query.all()]), 200

@app.route('/api/admin/tariffs', methods=['POST'])
@admin_required
def create_tariff(current_admin):
    try:
        d = request.json
        traffic_limit = d.get('traffic_limit_bytes', 0)
        if traffic_limit:
            traffic_limit = int(traffic_limit)
        else:
            traffic_limit = 0
        
        # Валидация tier
        tier = d.get('tier', '').lower() if d.get('tier') else None
        if tier and tier not in ['basic', 'pro', 'elite']:
            tier = None
        
        # Валидация badge
        badge = d.get('badge', '').strip() if d.get('badge') else None
        if badge and badge not in ['top_sale']:  # Можно расширить список допустимых бейджей
            badge = None
        
        # Обработка лимита устройств (0 или NULL = безлимит)
        hwid_device_limit = d.get('hwid_device_limit')
        if hwid_device_limit is not None:
            hwid_device_limit = int(hwid_device_limit) if int(hwid_device_limit) > 0 else None
        else:
            hwid_device_limit = None
        
        # Обработка бонусных дней (0 или NULL = без бонуса)
        bonus_days = d.get('bonus_days')
        if bonus_days is not None:
            bonus_days = int(bonus_days) if int(bonus_days) > 0 else None
        else:
            bonus_days = None
        
        nt = Tariff(
            name=d['name'], 
            duration_days=int(d['duration_days']), 
            price_uah=float(d['price_uah']), 
            price_rub=float(d['price_rub']), 
            price_usd=float(d['price_usd']),
            squad_id=d.get('squad_id'),  # Опциональное поле
            traffic_limit_bytes=traffic_limit,
            hwid_device_limit=hwid_device_limit,
            tier=tier,
            badge=badge,
            bonus_days=bonus_days
        )
        db.session.add(nt); db.session.commit()
        cache.clear()  # Очищаем весь кэш
        # Дополнительно очищаем кэш публичного API тарифов
        try:
            cache.delete('view//api/public/tariffs')
            cache.delete_many(['view//api/public/tariffs'])
        except:
            pass
        return jsonify({"message": "Created", "response": {
            "id": nt.id,
            "name": nt.name,
            "duration_days": nt.duration_days,
            "price_uah": nt.price_uah,
            "price_rub": nt.price_rub,
            "price_usd": nt.price_usd,
            "squad_id": nt.squad_id,
            "traffic_limit_bytes": nt.traffic_limit_bytes or 0,
            "hwid_device_limit": nt.hwid_device_limit if nt.hwid_device_limit is not None else 0,
            "tier": nt.tier,
            "badge": nt.badge,
            "bonus_days": nt.bonus_days if nt.bonus_days is not None else 0
        }}), 201
    except Exception as e: return jsonify({"message": str(e)}), 500

@app.route('/api/admin/tariffs/<int:id>', methods=['PATCH'])
@admin_required
def update_tariff(current_admin, id):
    try:
        t = db.session.get(Tariff, id)
        if not t: return jsonify({"message": "Not found"}), 404
        
        d = request.json
        if 'name' in d: t.name = d['name']
        if 'duration_days' in d: t.duration_days = int(d['duration_days'])
        if 'price_uah' in d: t.price_uah = float(d['price_uah'])
        if 'price_rub' in d: t.price_rub = float(d['price_rub'])
        if 'price_usd' in d: t.price_usd = float(d['price_usd'])
        if 'squad_id' in d: t.squad_id = d.get('squad_id') or None
        if 'traffic_limit_bytes' in d:
            traffic_limit = d.get('traffic_limit_bytes', 0)
            t.traffic_limit_bytes = int(traffic_limit) if traffic_limit else 0
        if 'hwid_device_limit' in d:
            hwid_device_limit = d.get('hwid_device_limit')
            if hwid_device_limit is not None:
                t.hwid_device_limit = int(hwid_device_limit) if int(hwid_device_limit) > 0 else None
            else:
                t.hwid_device_limit = None
        if 'tier' in d:
            tier = d.get('tier', '').lower() if d.get('tier') else None
            if tier and tier not in ['basic', 'pro', 'elite']:
                tier = None
            t.tier = tier
        if 'badge' in d:
            badge = d.get('badge', '').strip() if d.get('badge') else None
            if badge and badge not in ['top_sale']:  # Можно расширить список допустимых бейджей
                badge = None
            t.badge = badge
        if 'bonus_days' in d:
            bonus_days = d.get('bonus_days')
            if bonus_days is not None:
                t.bonus_days = int(bonus_days) if int(bonus_days) > 0 else None
            else:
                t.bonus_days = None
        
        db.session.commit()
        cache.clear()  # Очищаем весь кэш
        # Дополнительно очищаем кэш публичного API тарифов
        try:
            cache.delete('view//api/public/tariffs')
            cache.delete_many(['view//api/public/tariffs'])
        except:
            pass
        return jsonify({
            "message": "Updated",
            "response": {
                "id": t.id,
                "name": t.name,
                "duration_days": t.duration_days,
                "price_uah": t.price_uah,
                "price_rub": t.price_rub,
                "price_usd": t.price_usd,
                "squad_id": t.squad_id,
                "traffic_limit_bytes": t.traffic_limit_bytes or 0,
                "hwid_device_limit": t.hwid_device_limit if t.hwid_device_limit is not None else 0,
                "tier": t.tier,
                "badge": t.badge,
                "bonus_days": t.bonus_days if t.bonus_days is not None else 0
            }
        }), 200
    except Exception as e: return jsonify({"message": str(e)}), 500

@app.route('/api/admin/tariffs/<int:id>', methods=['DELETE'])
@admin_required
def del_tariff(current_admin, id):
    t = db.session.get(Tariff, id)
    if t: db.session.delete(t); db.session.commit(); cache.clear()
    return jsonify({"message": "Deleted"}), 200

# --- EMAIL BROADCAST ---
@app.route('/api/admin/broadcast', methods=['POST'])
@admin_required
def send_broadcast(current_admin):
    try:
        data = request.json
        subject = data.get('subject', '').strip()
        message = data.get('message', '').strip()
        recipient_type = data.get('recipient_type', 'all')  # 'all', 'active', 'inactive', 'custom'
        custom_emails = data.get('custom_emails', [])  # Массив email для 'custom'
        
        if not subject or not message:
            return jsonify({"message": "Subject and message are required"}), 400
        
        # Определяем получателей
        recipients = []
        if recipient_type == 'all':
            recipients = [u.email for u in User.query.filter_by(role='CLIENT').all()]
        elif recipient_type == 'active':
            # Активные пользователи (с remnawave_uuid - зарегистрированы в VPN системе)
            from sqlalchemy import and_
            active_users = User.query.filter(and_(User.role == 'CLIENT', User.remnawave_uuid != None)).all()
            recipients = [u.email for u in active_users]
        elif recipient_type == 'inactive':
            # Неактивные пользователи (без remnawave_uuid)
            inactive_users = User.query.filter_by(role='CLIENT').filter(User.remnawave_uuid == None).all()
            recipients = [u.email for u in inactive_users]
        elif recipient_type == 'custom':
            if not custom_emails or not isinstance(custom_emails, list):
                return jsonify({"message": "Custom emails list is required"}), 400
            recipients = [email.strip() for email in custom_emails if email.strip()]
        
        if not recipients:
            return jsonify({"message": "No recipients found"}), 400
        
        # Формируем HTML письма используя шаблон
        branding = BrandingSetting.query.first() or BrandingSetting(site_name=SERVICE_NAME, primary_color="#3F69FF", secondary_color="#ffffff", accent_color="#3F69FF")
        html_body = render_template('email_broadcast.html', subject=subject, message=message, branding=branding, service_name=SERVICE_NAME)
        
        # Отправляем письма в фоновом режиме
        sent_count = 0
        failed_count = 0
        failed_emails = []
        
        for recipient in recipients:
            try:
                threading.Thread(
                    target=send_email_in_background,
                    args=(app.app_context(), recipient, subject, html_body)
                ).start()
                sent_count += 1
            except Exception as e:
                failed_count += 1
                failed_emails.append(recipient)
                print(f"[BROADCAST] Ошибка отправки на {recipient}: {e}")
        
        return jsonify({
            "message": "Broadcast started",
            "total_recipients": len(recipients),
            "sent": sent_count,
            "failed": failed_count,
            "failed_emails": failed_emails[:10]  # Первые 10 для примера
        }), 200
        
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route('/api/admin/users/emails', methods=['GET'])
@admin_required
def get_users_emails(current_admin):
    """Получить список email всех пользователей для рассылки"""
    try:
        users = User.query.filter_by(role='CLIENT').all()
        emails = [{"email": u.email, "is_verified": u.is_verified} for u in users]
        return jsonify(emails), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

# --- PROMOCODES ---
@app.route('/api/admin/promocodes', methods=['GET', 'POST'])
@admin_required
def handle_promos(current_admin):
    if request.method == 'GET':
        return jsonify([{
            "id": c.id, 
            "code": c.code, 
            "promo_type": c.promo_type,
            "value": c.value,
            "uses_left": c.uses_left
        } for c in PromoCode.query.all()]), 200
    try:
        d = request.json
        nc = PromoCode(code=d['code'], promo_type=d['promo_type'], value=int(d['value']), uses_left=int(d['uses_left']))
        db.session.add(nc); db.session.commit()
        return jsonify({
            "message": "Created",
            "response": {
                "id": nc.id,
                "code": nc.code,
                "promo_type": nc.promo_type,
                "value": nc.value,
                "uses_left": nc.uses_left
            }
        }), 201
    except Exception as e: return jsonify({"message": str(e)}), 500

@app.route('/api/admin/promocodes/<int:id>', methods=['DELETE'])
@admin_required
def del_promo(current_admin, id):
    c = db.session.get(PromoCode, id)
    if c: db.session.delete(c); db.session.commit()
    return jsonify({"message": "Deleted"}), 200

# --- SETTINGS ---
@app.route('/api/admin/referral-settings', methods=['GET', 'POST'])
@admin_required
def ref_settings(current_admin):
    s = ReferralSetting.query.first() or ReferralSetting()
    if not s.id: db.session.add(s); db.session.commit()
    if request.method == 'POST':
        s.invitee_bonus_days = int(request.json['invitee_bonus_days'])
        s.referrer_bonus_days = int(request.json['referrer_bonus_days'])
        s.trial_squad_id = request.json.get('trial_squad_id') or None
        db.session.commit()
    return jsonify({
        "invitee_bonus_days": s.invitee_bonus_days, 
        "referrer_bonus_days": s.referrer_bonus_days,
        "trial_squad_id": s.trial_squad_id
    }), 200

# --- TARIFF FEATURES SETTINGS ---
@app.route('/api/admin/tariff-features', methods=['GET', 'POST'])
@admin_required
def tariff_features_settings(current_admin):
    import json
    
    # Дефолтные функции
    default_features = {
        'basic': ['Безлимитный трафик', 'До 5 устройств', 'Базовый анти-DPI'],
        'pro': ['Приоритетная скорость', 'До 10 устройств', 'Ротация IP-адресов'],
        'elite': ['VIP-поддержка 24/7', 'Статический IP по запросу', 'Автообновление ключей']
    }
    
    if request.method == 'GET':
        result = {}
        for tier in ['basic', 'pro', 'elite']:
            setting = TariffFeatureSetting.query.filter_by(tier=tier).first()
            if setting:
                try:
                    result[tier] = json.loads(setting.features)
                except:
                    result[tier] = default_features[tier]
            else:
                result[tier] = default_features[tier]
        return jsonify(result), 200
    
    # POST - обновление
    try:
        data = request.json
        for tier, features in data.items():
            if tier not in ['basic', 'pro', 'elite']:
                continue
            if not isinstance(features, list):
                continue
            
            setting = TariffFeatureSetting.query.filter_by(tier=tier).first()
            if setting:
                setting.features = json.dumps(features, ensure_ascii=False)
            else:
                setting = TariffFeatureSetting(tier=tier, features=json.dumps(features, ensure_ascii=False))
                db.session.add(setting)
        
        db.session.commit()
        cache.clear()  # Очищаем кэш публичного API
        return jsonify({"message": "Updated"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route('/api/public/telegram-auth-enabled', methods=['GET'])
def telegram_auth_enabled():
    """Проверка доступности авторизации через Telegram"""
    enabled = bool(BOT_API_URL and BOT_API_TOKEN and TELEGRAM_BOT_NAME)
    return jsonify({
        "enabled": enabled,
        "bot_name": TELEGRAM_BOT_NAME if enabled else None
    }), 200

@app.route('/api/public/server-domain', methods=['GET'])
def server_domain():
    """Получить домен сервера из переменной окружения"""
    domain = YOUR_SERVER_IP_OR_DOMAIN or request.host_url.rstrip('/')
    # Убираем протокол, если он есть
    if domain and (domain.startswith('http://') or domain.startswith('https://')):
        domain = domain.split('://', 1)[1]
    # Убираем слэш в конце
    if domain:
        domain = domain.rstrip('/')
    else:
        # Если домен не задан, используем текущий хост
        domain = request.host
    
    # Формируем полный URL (всегда HTTPS для продакшена)
    if domain.startswith('http'):
        full_url = domain
    else:
        full_url = f"https://{domain}"
    
    return jsonify({
        "domain": domain,
        "full_url": full_url
    }), 200

@app.route('/api/public/tariff-features', methods=['GET'])
@cache.cached(timeout=3600)
def get_public_tariff_features():
    import json
    
    # Дефолтные функции
    default_features = {
        'basic': ['Безлимитный трафик', 'До 5 устройств', 'Базовый анти-DPI'],
        'pro': ['Приоритетная скорость', 'До 10 устройств', 'Ротация IP-адресов'],
        'elite': ['VIP-поддержка 24/7', 'Статический IP по запросу', 'Автообновление ключей']
    }
    
    result = {}
    for tier in ['basic', 'pro', 'elite']:
        setting = TariffFeatureSetting.query.filter_by(tier=tier).first()
        if setting:
            try:
                parsed_features = json.loads(setting.features)
                # Убеждаемся, что это список и не пустой
                if isinstance(parsed_features, list) and len(parsed_features) > 0:
                    result[tier] = parsed_features
                else:
                    result[tier] = default_features[tier]
            except Exception as e:
                result[tier] = default_features[tier]
        else:
            result[tier] = default_features[tier]
    
    return jsonify(result), 200

@app.route('/api/public/tariffs', methods=['GET'])
@cache.cached(timeout=3600)
def get_public_tariffs():
    return jsonify([{
        "id": t.id, 
        "name": t.name, 
        "duration_days": t.duration_days, 
        "price_uah": t.price_uah, 
        "price_rub": t.price_rub, 
        "price_usd": t.price_usd,
        "squad_id": t.squad_id,
        "traffic_limit_bytes": t.traffic_limit_bytes or 0,
        "tier": t.tier,
        "badge": t.badge,
        "bonus_days": t.bonus_days if t.bonus_days is not None else 0
    } for t in Tariff.query.all()]), 200

@app.route('/api/public/nodes', methods=['GET'])
@cache.cached(timeout=300)  # Кэш на 5 минут
def get_public_nodes():
    """Публичный endpoint для получения списка серверов (для лендинга)"""
    try:
        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        resp = requests.get(f"{API_URL}/api/nodes", headers=headers, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        
        # Обрабатываем ответ согласно структуре API
        if isinstance(data, dict) and 'response' in data:
            nodes_list = data['response']
            if isinstance(nodes_list, dict) and 'nodes' in nodes_list:
                nodes_list = nodes_list['nodes']
            elif not isinstance(nodes_list, list):
                nodes_list = []
        elif isinstance(data, list):
            nodes_list = data
        else:
            nodes_list = []
        
        # Фильтруем только активные серверы и возвращаем только нужные поля
        public_nodes = []
        for node in nodes_list:
            if isinstance(node, dict):
                # Проверяем, активен ли сервер
                is_active = (
                    node.get('isOnline') or 
                    node.get('is_online') or 
                    node.get('status') == 'online' or
                    node.get('state') == 'active'
                )
                
                if is_active:
                    public_nodes.append({
                        "uuid": node.get('uuid'),
                        "name": node.get('name') or node.get('location') or 'Unknown',
                        "location": node.get('location') or node.get('name') or 'Unknown',
                        "regionName": node.get('regionName') or node.get('region') or node.get('countryCode'),
                        "countryCode": node.get('countryCode') or node.get('country'),
                        "isOnline": True
                    })
        
        return jsonify(public_nodes), 200
    except Exception as e:
        print(f"Error in get_public_nodes: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Failed to fetch nodes", "nodes": []}), 500

@app.route('/api/client/settings', methods=['POST'])
def set_settings():
    user = get_user_from_token()
    if not user: return jsonify({"message": "Auth Error"}), 401
    d = request.json
    if 'lang' in d: user.preferred_lang = d['lang']
    if 'currency' in d: user.preferred_currency = d['currency']
    db.session.commit()
    # Очищаем кэш пользователя, чтобы новые настройки сразу отобразились
    cache.delete(f'live_data_{user.remnawave_uuid}')
    return jsonify({"message": "OK"}), 200

@app.route('/api/client/change-password', methods=['POST'])
def change_password():
    """Изменение пароля текущего пользователя"""
    user = get_user_from_token()
    if not user: return jsonify({"message": "Auth Error"}), 401
    
    try:
        data = request.json
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({"message": "Требуется текущий и новый пароль"}), 400
        
        if len(new_password) < 6:
            return jsonify({"message": "Новый пароль должен содержать минимум 6 символов"}), 400
        
        # Проверяем текущий пароль
        if not user.password_hash:
            return jsonify({"message": "У вас нет пароля. Используйте восстановление пароля."}), 400
        
        if not bcrypt.check_password_hash(user.password_hash, current_password):
            return jsonify({"message": "Неверный текущий пароль"}), 400
        
        # Хешируем новый пароль
        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        user.password_hash = hashed_password
        
        # Сохраняем зашифрованный пароль для бота
        if fernet:
            try:
                user.encrypted_password = fernet.encrypt(new_password.encode()).decode()
            except Exception as e:
                print(f"[CHANGE PASSWORD] Ошибка шифрования пароля: {e}")
        
        db.session.commit()
        
        return jsonify({"message": "Пароль успешно изменен"}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"[CHANGE PASSWORD] Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": f"Ошибка: {str(e)}"}), 500

# --- SYSTEM SETTINGS (Default Language & Currency) ---
@app.route('/api/admin/system-settings', methods=['GET', 'POST'])
@admin_required
def system_settings(current_admin):
    import json
    s = SystemSetting.query.first() or SystemSetting(id=1)
    if not s.id: 
        db.session.add(s)
        db.session.commit()
        # Устанавливаем значения по умолчанию
        if s.show_language_currency_switcher is None:
            s.show_language_currency_switcher = True
        if not s.active_languages or s.active_languages.strip() == '':
            s.active_languages = '["ru","ua","en","cn"]'
        if not s.active_currencies or s.active_currencies.strip() == '':
            s.active_currencies = '["uah","rub","usd"]'
        db.session.commit()
    
    if request.method == 'GET':
        # Парсим JSON массивы
        try:
            active_languages = json.loads(s.active_languages) if s.active_languages else ["ru", "ua", "en", "cn"]
        except:
            active_languages = ["ru", "ua", "en", "cn"]
        
        try:
            active_currencies = json.loads(s.active_currencies) if s.active_currencies else ["uah", "rub", "usd"]
        except:
            active_currencies = ["uah", "rub", "usd"]
        
        # Автозаполнение NULL значений в БД
        needs_save = False
        if not s.active_languages:
            s.active_languages = '["ru","ua","en","cn"]'
            needs_save = True
        if not s.active_currencies:
            s.active_currencies = '["uah","rub","usd"]'
            needs_save = True
        if needs_save:
            try:
                db.session.commit()
            except:
                db.session.rollback()
        
        return jsonify({
            "default_language": s.default_language,
            "default_currency": s.default_currency,
            "show_language_currency_switcher": s.show_language_currency_switcher if s.show_language_currency_switcher is not None else True,
            "active_languages": active_languages,
            "active_currencies": active_currencies,
            # Цвета светлой темы
            "theme_primary_color": getattr(s, 'theme_primary_color', '#3f69ff') or '#3f69ff',
            "theme_bg_primary": getattr(s, 'theme_bg_primary', '#f8fafc') or '#f8fafc',
            "theme_bg_secondary": getattr(s, 'theme_bg_secondary', '#eef2ff') or '#eef2ff',
            "theme_text_primary": getattr(s, 'theme_text_primary', '#0f172a') or '#0f172a',
            "theme_text_secondary": getattr(s, 'theme_text_secondary', '#64748b') or '#64748b',
            # Цвета тёмной темы
            "theme_primary_color_dark": getattr(s, 'theme_primary_color_dark', '#6c7bff') or '#6c7bff',
            "theme_bg_primary_dark": getattr(s, 'theme_bg_primary_dark', '#050816') or '#050816',
            "theme_bg_secondary_dark": getattr(s, 'theme_bg_secondary_dark', '#0f172a') or '#0f172a',
            "theme_text_primary_dark": getattr(s, 'theme_text_primary_dark', '#e2e8f0') or '#e2e8f0',
            "theme_text_secondary_dark": getattr(s, 'theme_text_secondary_dark', '#94a3b8') or '#94a3b8'
        }), 200
    
    # POST - обновление
    try:
        import json
        data = request.json
        if 'default_language' in data:
            if data['default_language'] not in ['ru', 'ua', 'cn', 'en']:
                return jsonify({"message": "Invalid language"}), 400
            s.default_language = data['default_language']
        if 'default_currency' in data:
            if data['default_currency'] not in ['uah', 'rub', 'usd']:
                return jsonify({"message": "Invalid currency"}), 400
            s.default_currency = data['default_currency']
        if 'show_language_currency_switcher' in data:
            s.show_language_currency_switcher = bool(data['show_language_currency_switcher'])
        if 'active_languages' in data:
            # Валидация: должен быть массив строк
            if isinstance(data['active_languages'], list):
                valid_langs = ['ru', 'ua', 'en', 'cn']
                filtered_langs = [lang for lang in data['active_languages'] if lang in valid_langs]
                if len(filtered_langs) == 0:
                    return jsonify({"message": "At least one language must be active"}), 400
                s.active_languages = json.dumps(filtered_langs)
            else:
                return jsonify({"message": "active_languages must be an array"}), 400
        if 'active_currencies' in data:
            # Валидация: должен быть массив строк
            if isinstance(data['active_currencies'], list):
                valid_currs = ['uah', 'rub', 'usd']
                filtered_currs = [curr for curr in data['active_currencies'] if curr in valid_currs]
                if len(filtered_currs) == 0:
                    return jsonify({"message": "At least one currency must be active"}), 400
                s.active_currencies = json.dumps(filtered_currs)
            else:
                return jsonify({"message": "active_currencies must be an array"}), 400
        # Обработка цветов темы - хелпер для валидации
        def is_valid_hex(color):
            return color and color.startswith('#') and len(color) in [4, 7]
        
        # Светлая тема
        if 'theme_primary_color' in data and is_valid_hex(data['theme_primary_color']):
            s.theme_primary_color = data['theme_primary_color']
        if 'theme_bg_primary' in data and is_valid_hex(data['theme_bg_primary']):
            s.theme_bg_primary = data['theme_bg_primary']
        if 'theme_bg_secondary' in data and is_valid_hex(data['theme_bg_secondary']):
            s.theme_bg_secondary = data['theme_bg_secondary']
        if 'theme_text_primary' in data and is_valid_hex(data['theme_text_primary']):
            s.theme_text_primary = data['theme_text_primary']
        if 'theme_text_secondary' in data and is_valid_hex(data['theme_text_secondary']):
            s.theme_text_secondary = data['theme_text_secondary']
        # Тёмная тема
        if 'theme_primary_color_dark' in data and is_valid_hex(data['theme_primary_color_dark']):
            s.theme_primary_color_dark = data['theme_primary_color_dark']
        if 'theme_bg_primary_dark' in data and is_valid_hex(data['theme_bg_primary_dark']):
            s.theme_bg_primary_dark = data['theme_bg_primary_dark']
        if 'theme_bg_secondary_dark' in data and is_valid_hex(data['theme_bg_secondary_dark']):
            s.theme_bg_secondary_dark = data['theme_bg_secondary_dark']
        if 'theme_text_primary_dark' in data and is_valid_hex(data['theme_text_primary_dark']):
            s.theme_text_primary_dark = data['theme_text_primary_dark']
        if 'theme_text_secondary_dark' in data and is_valid_hex(data['theme_text_secondary_dark']):
            s.theme_text_secondary_dark = data['theme_text_secondary_dark']
        db.session.commit()
        cache.clear()  # Очищаем весь кэш
        return jsonify({"message": "Updated"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route('/api/public/currency-rates', methods=['GET'])
def public_currency_rates():
    """Публичный endpoint для получения курсов валют (для фронтенда)"""
    try:
        rates = CurrencyRate.query.all()
    except:
        rates = []
    
    rates_dict = {}
    for rate in rates:
        rates_dict[rate.currency] = float(rate.rate_to_usd)
    
    # Добавляем значения по умолчанию для валют, которых нет в БД
    default_rates = {
        'UAH': 40.0,
        'RUB': 100.0,
        'USD': 1.0
    }
    for currency, default_rate in default_rates.items():
        if currency not in rates_dict:
            rates_dict[currency] = default_rate
    
    return jsonify({"rates": rates_dict}), 200

@app.route('/api/admin/currency-rates', methods=['GET', 'POST'])
@admin_required
def currency_rates(current_admin):
    """Управление курсами валют"""
    if request.method == 'GET':
        # Получаем все курсы валют
        try:
            rates = CurrencyRate.query.all()
        except:
            # Если таблица еще не создана, возвращаем значения по умолчанию
            rates = []
        
        rates_dict = {}
        for rate in rates:
            rates_dict[rate.currency] = {
                'rate_to_usd': float(rate.rate_to_usd),
                'updated_at': rate.updated_at.isoformat() if rate.updated_at else None
            }
        
        # Добавляем значения по умолчанию для валют, которых нет в БД
        default_rates = {
            'UAH': 40.0,
            'RUB': 100.0,
            'USD': 1.0
        }
        for currency, default_rate in default_rates.items():
            if currency not in rates_dict:
                rates_dict[currency] = {
                    'rate_to_usd': default_rate,
                    'updated_at': None
                }
        
        return jsonify({"rates": rates_dict}), 200
    
    # POST - обновление курсов
    try:
        data = request.json
        rates_data = data.get('rates', {})
        
        for currency, rate_info in rates_data.items():
            currency = currency.upper()
            if currency == 'USD':
                continue  # USD всегда равен 1.0
            
            rate_value = float(rate_info.get('rate_to_usd', rate_info) if isinstance(rate_info, dict) else rate_info)
            
            if rate_value <= 0:
                return jsonify({"message": f"Курс для {currency} должен быть больше 0"}), 400
            
            # Ищем существующий курс или создаем новый
            rate_obj = CurrencyRate.query.filter_by(currency=currency).first()
            if rate_obj:
                rate_obj.rate_to_usd = rate_value
                rate_obj.updated_at = datetime.now(timezone.utc)
            else:
                rate_obj = CurrencyRate(currency=currency, rate_to_usd=rate_value)
                db.session.add(rate_obj)
        
        db.session.commit()
        
        # Очищаем кэш, чтобы новые курсы сразу применялись
        cache.clear()
        
        return jsonify({"message": "Курсы валют успешно обновлены"}), 200
    except ValueError as e:
        return jsonify({"message": f"Неверное значение курса: {str(e)}"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": str(e)}), 500

@app.route('/api/admin/branding', methods=['GET', 'POST'])
@admin_required
def branding_settings(current_admin):
    """Управление настройками брендинга"""
    b = BrandingSetting.query.first() or BrandingSetting(id=1)
    if not b.id: 
        db.session.add(b)
        db.session.commit()
    
    if request.method == 'GET':
        return jsonify({
            "logo_url": b.logo_url or "",
            "site_name": b.site_name or SERVICE_NAME,
            "site_subtitle": b.site_subtitle or "",
            "primary_color": b.primary_color or "#3F69FF",
            "secondary_color": b.secondary_color or "#ffffff",
            "accent_color": b.accent_color or "#3F69FF",
            "login_welcome_text": b.login_welcome_text or "",
            "register_welcome_text": b.register_welcome_text or "",
            "footer_text": b.footer_text or "",
            "dashboard_servers_title": b.dashboard_servers_title or "",
            "dashboard_servers_description": b.dashboard_servers_description or "",
            "dashboard_tariffs_title": b.dashboard_tariffs_title or "",
            "dashboard_tariffs_description": b.dashboard_tariffs_description or "",
            "dashboard_tagline": b.dashboard_tagline or "",
            # Быстрое скачивание
            "quick_download_enabled": b.quick_download_enabled if hasattr(b, 'quick_download_enabled') and b.quick_download_enabled is not None else True,
            "quick_download_windows_url": getattr(b, 'quick_download_windows_url', '') or "",
            "quick_download_android_url": getattr(b, 'quick_download_android_url', '') or "",
            "quick_download_macos_url": getattr(b, 'quick_download_macos_url', '') or "",
            "quick_download_ios_url": getattr(b, 'quick_download_ios_url', '') or "",
            "quick_download_profile_deeplink": getattr(b, 'quick_download_profile_deeplink', '') or "stealthnet://install-config?url="
        }), 200
    
    # POST - обновление
    try:
        data = request.json
        if 'logo_url' in data:
            b.logo_url = data['logo_url'] or None
        if 'site_name' in data:
            b.site_name = data['site_name'] or SERVICE_NAME
        if 'site_subtitle' in data:
            b.site_subtitle = data['site_subtitle'] or None
        if 'primary_color' in data:
            b.primary_color = data['primary_color'] or "#3F69FF"
        if 'secondary_color' in data:
            b.secondary_color = data['secondary_color'] or "#ffffff"
        if 'accent_color' in data:
            b.accent_color = data['accent_color'] or "#3F69FF"
        if 'login_welcome_text' in data:
            b.login_welcome_text = data['login_welcome_text'] or None
        if 'register_welcome_text' in data:
            b.register_welcome_text = data['register_welcome_text'] or None
        if 'footer_text' in data:
            b.footer_text = data['footer_text'] or None
        if 'dashboard_servers_title' in data:
            b.dashboard_servers_title = data['dashboard_servers_title'] or None
        if 'dashboard_servers_description' in data:
            b.dashboard_servers_description = data['dashboard_servers_description'] or None
        if 'dashboard_tariffs_title' in data:
            b.dashboard_tariffs_title = data['dashboard_tariffs_title'] or None
        if 'dashboard_tariffs_description' in data:
            b.dashboard_tariffs_description = data['dashboard_tariffs_description'] or None
        if 'dashboard_tagline' in data:
            b.dashboard_tagline = data['dashboard_tagline'] or None
        # Быстрое скачивание
        if 'quick_download_enabled' in data:
            b.quick_download_enabled = bool(data['quick_download_enabled'])
        if 'quick_download_windows_url' in data:
            b.quick_download_windows_url = data['quick_download_windows_url'] or None
        if 'quick_download_android_url' in data:
            b.quick_download_android_url = data['quick_download_android_url'] or None
        if 'quick_download_macos_url' in data:
            b.quick_download_macos_url = data['quick_download_macos_url'] or None
        if 'quick_download_ios_url' in data:
            b.quick_download_ios_url = data['quick_download_ios_url'] or None
        if 'quick_download_profile_deeplink' in data:
            b.quick_download_profile_deeplink = data['quick_download_profile_deeplink'] or 'stealthnet://install-config?url='
        db.session.commit()
        return jsonify({"message": "Branding settings updated"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route('/api/public/branding', methods=['GET'])
def public_branding():
    """Публичный эндпоинт для получения настроек брендинга"""
    b = BrandingSetting.query.first() or BrandingSetting(id=1)
    if not b.id: 
        db.session.add(b)
        db.session.commit()
    
    return jsonify({
        "logo_url": b.logo_url or "",
        "site_name": b.site_name or SERVICE_NAME,
        "site_subtitle": b.site_subtitle or "",
        "primary_color": b.primary_color or "#3F69FF",
        "secondary_color": b.secondary_color or "#ffffff",
        "accent_color": b.accent_color or "#3F69FF",
        "login_welcome_text": b.login_welcome_text or "",
        "register_welcome_text": b.register_welcome_text or "",
        "footer_text": b.footer_text or "",
        "dashboard_servers_title": b.dashboard_servers_title or "",
        "dashboard_servers_description": b.dashboard_servers_description or "",
        "dashboard_tariffs_title": b.dashboard_tariffs_title or "",
        "dashboard_tariffs_description": b.dashboard_tariffs_description or "",
        "dashboard_tagline": b.dashboard_tagline or "",
        # Быстрое скачивание
        "quick_download_enabled": b.quick_download_enabled if hasattr(b, 'quick_download_enabled') and b.quick_download_enabled is not None else True,
        "quick_download_windows_url": getattr(b, 'quick_download_windows_url', '') or "",
        "quick_download_android_url": getattr(b, 'quick_download_android_url', '') or "",
        "quick_download_macos_url": getattr(b, 'quick_download_macos_url', '') or "",
        "quick_download_ios_url": getattr(b, 'quick_download_ios_url', '') or "",
        "quick_download_profile_deeplink": getattr(b, 'quick_download_profile_deeplink', '') or "stealthnet://install-config?url="
    }), 200

# ═══════════════════════════════════════════════════════════════════════════════
# КОНСТРУКТОР БОТА
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/admin/bot-config', methods=['GET', 'POST'])
@admin_required
def admin_bot_config(current_admin):
    """Управление конфигурацией Telegram бота"""
    import json
    
    # Получаем или создаём конфиг
    config = BotConfig.query.first()
    if not config:
        config = BotConfig(id=1)
        db.session.add(config)
        db.session.commit()
    
    if request.method == 'GET':
        # Получаем все настройки
        return jsonify({
            # Общие настройки
            "service_name": config.service_name or "StealthNET",
            "bot_username": config.bot_username or "",
            "support_url": config.support_url or "",
            "support_bot_username": config.support_bot_username or "",
            
            # Настройки видимости кнопок
            "show_webapp_button": config.show_webapp_button if config.show_webapp_button is not None else True,
            "show_trial_button": config.show_trial_button if config.show_trial_button is not None else True,
            "show_referral_button": config.show_referral_button if config.show_referral_button is not None else True,
            "show_support_button": config.show_support_button if config.show_support_button is not None else True,
            "show_servers_button": config.show_servers_button if config.show_servers_button is not None else True,
            "show_agreement_button": config.show_agreement_button if config.show_agreement_button is not None else True,
            "show_offer_button": config.show_offer_button if config.show_offer_button is not None else True,
            "show_topup_button": config.show_topup_button if config.show_topup_button is not None else True,
            
            # Настройки триала
            "trial_days": config.trial_days or 3,
            
            # Переводы (JSON -> dict)
            "translations_ru": json.loads(config.translations_ru) if config.translations_ru else {},
            "translations_ua": json.loads(config.translations_ua) if config.translations_ua else {},
            "translations_en": json.loads(config.translations_en) if config.translations_en else {},
            "translations_cn": json.loads(config.translations_cn) if config.translations_cn else {},
            
            # Кастомные сообщения
            "welcome_message_ru": config.welcome_message_ru or "",
            "welcome_message_ua": config.welcome_message_ua or "",
            "welcome_message_en": config.welcome_message_en or "",
            "welcome_message_cn": config.welcome_message_cn or "",
            
            # Документы
            "user_agreement_ru": config.user_agreement_ru or "",
            "user_agreement_ua": config.user_agreement_ua or "",
            "user_agreement_en": config.user_agreement_en or "",
            "user_agreement_cn": config.user_agreement_cn or "",
            
            "offer_text_ru": config.offer_text_ru or "",
            "offer_text_ua": config.offer_text_ua or "",
            "offer_text_en": config.offer_text_en or "",
            "offer_text_cn": config.offer_text_cn or "",
            
            # Структура меню
            "menu_structure": json.loads(config.menu_structure) if config.menu_structure else None,
            
            # Проверка подписки на канал
            "require_channel_subscription": config.require_channel_subscription if hasattr(config, 'require_channel_subscription') and config.require_channel_subscription is not None else False,
            "channel_id": getattr(config, 'channel_id', '') or "",
            "channel_url": getattr(config, 'channel_url', '') or "",
            "channel_subscription_text_ru": getattr(config, 'channel_subscription_text_ru', '') or "",
            "channel_subscription_text_ua": getattr(config, 'channel_subscription_text_ua', '') or "",
            "channel_subscription_text_en": getattr(config, 'channel_subscription_text_en', '') or "",
            "channel_subscription_text_cn": getattr(config, 'channel_subscription_text_cn', '') or "",
            
            # Ссылка на бота для Mini App
            "bot_link_for_miniapp": getattr(config, 'bot_link_for_miniapp', '') or "",
            
            # Порядок кнопок
            "buttons_order": json.loads(config.buttons_order) if hasattr(config, 'buttons_order') and config.buttons_order else ["connect", "trial", "status", "tariffs", "topup", "servers", "referrals", "support", "settings", "agreement", "offer", "webapp"],
            
            "updated_at": config.updated_at.isoformat() if config.updated_at else None
        }), 200
    
    # POST - обновление
    try:
        data = request.json
        
        # Общие настройки
        if 'service_name' in data:
            config.service_name = data['service_name'] or "StealthNET"
        if 'bot_username' in data:
            config.bot_username = data['bot_username'] or None
        if 'support_url' in data:
            config.support_url = data['support_url'] or None
        if 'support_bot_username' in data:
            config.support_bot_username = data['support_bot_username'] or None
        
        # Настройки видимости кнопок
        if 'show_webapp_button' in data:
            config.show_webapp_button = bool(data['show_webapp_button'])
        if 'show_trial_button' in data:
            config.show_trial_button = bool(data['show_trial_button'])
        if 'show_referral_button' in data:
            config.show_referral_button = bool(data['show_referral_button'])
        if 'show_support_button' in data:
            config.show_support_button = bool(data['show_support_button'])
        if 'show_servers_button' in data:
            config.show_servers_button = bool(data['show_servers_button'])
        if 'show_agreement_button' in data:
            config.show_agreement_button = bool(data['show_agreement_button'])
        if 'show_offer_button' in data:
            config.show_offer_button = bool(data['show_offer_button'])
        if 'show_topup_button' in data:
            config.show_topup_button = bool(data['show_topup_button'])
        
        # Настройки триала
        if 'trial_days' in data:
            config.trial_days = int(data['trial_days']) if data['trial_days'] else 3
        
        # Переводы (dict -> JSON)
        if 'translations_ru' in data:
            config.translations_ru = json.dumps(data['translations_ru'], ensure_ascii=False) if data['translations_ru'] else None
        if 'translations_ua' in data:
            config.translations_ua = json.dumps(data['translations_ua'], ensure_ascii=False) if data['translations_ua'] else None
        if 'translations_en' in data:
            config.translations_en = json.dumps(data['translations_en'], ensure_ascii=False) if data['translations_en'] else None
        if 'translations_cn' in data:
            config.translations_cn = json.dumps(data['translations_cn'], ensure_ascii=False) if data['translations_cn'] else None
        
        # Кастомные сообщения
        if 'welcome_message_ru' in data:
            config.welcome_message_ru = data['welcome_message_ru'] or None
        if 'welcome_message_ua' in data:
            config.welcome_message_ua = data['welcome_message_ua'] or None
        if 'welcome_message_en' in data:
            config.welcome_message_en = data['welcome_message_en'] or None
        if 'welcome_message_cn' in data:
            config.welcome_message_cn = data['welcome_message_cn'] or None
        
        # Документы
        if 'user_agreement_ru' in data:
            config.user_agreement_ru = data['user_agreement_ru'] or None
        if 'user_agreement_ua' in data:
            config.user_agreement_ua = data['user_agreement_ua'] or None
        if 'user_agreement_en' in data:
            config.user_agreement_en = data['user_agreement_en'] or None
        if 'user_agreement_cn' in data:
            config.user_agreement_cn = data['user_agreement_cn'] or None
        
        if 'offer_text_ru' in data:
            config.offer_text_ru = data['offer_text_ru'] or None
        if 'offer_text_ua' in data:
            config.offer_text_ua = data['offer_text_ua'] or None
        if 'offer_text_en' in data:
            config.offer_text_en = data['offer_text_en'] or None
        if 'offer_text_cn' in data:
            config.offer_text_cn = data['offer_text_cn'] or None
        
        # Структура меню
        if 'menu_structure' in data:
            config.menu_structure = json.dumps(data['menu_structure'], ensure_ascii=False) if data['menu_structure'] else None
        
        # Проверка подписки на канал
        if 'require_channel_subscription' in data:
            config.require_channel_subscription = bool(data['require_channel_subscription'])
        if 'channel_id' in data:
            config.channel_id = data['channel_id'] or None
        if 'channel_url' in data:
            config.channel_url = data['channel_url'] or None
        if 'channel_subscription_text_ru' in data:
            config.channel_subscription_text_ru = data['channel_subscription_text_ru'] or None
        if 'channel_subscription_text_ua' in data:
            config.channel_subscription_text_ua = data['channel_subscription_text_ua'] or None
        if 'channel_subscription_text_en' in data:
            config.channel_subscription_text_en = data['channel_subscription_text_en'] or None
        if 'channel_subscription_text_cn' in data:
            config.channel_subscription_text_cn = data['channel_subscription_text_cn'] or None
        
        # Ссылка на бота для Mini App
        if 'bot_link_for_miniapp' in data:
            config.bot_link_for_miniapp = data['bot_link_for_miniapp'] or None
        
        # Порядок кнопок
        if 'buttons_order' in data:
            config.buttons_order = json.dumps(data['buttons_order'], ensure_ascii=False) if data['buttons_order'] else None
        
        db.session.commit()
        return jsonify({"message": "Bot config updated successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": str(e)}), 500


@app.route('/api/public/bot-config', methods=['GET'])
def public_bot_config():
    """Публичный эндпоинт для получения конфигурации бота (для самого бота)"""
    import json
    
    config = BotConfig.query.first()
    if not config:
        # Возвращаем дефолтные значения
        return jsonify({
            "service_name": "StealthNET",
            "show_webapp_button": True,
            "show_trial_button": True,
            "show_referral_button": True,
            "show_support_button": True,
            "show_servers_button": True,
            "show_agreement_button": True,
            "show_offer_button": True,
            "show_topup_button": True,
            "trial_days": 3,
            "translations": {},
            "welcome_messages": {},
            "user_agreements": {},
            "offer_texts": {},
            "menu_structure": None,
            "require_channel_subscription": False,
            "channel_id": "",
            "channel_url": "",
            "channel_subscription_texts": {"ru": "", "ua": "", "en": "", "cn": ""},
            "bot_link_for_miniapp": "",
            "buttons_order": ["connect", "trial", "status", "tariffs", "topup", "servers", "referrals", "support", "settings", "agreement", "offer", "webapp"]
        }), 200
    
    return jsonify({
        "service_name": config.service_name or "StealthNET",
        "bot_username": config.bot_username or "",
        "support_url": config.support_url or "",
        "support_bot_username": config.support_bot_username or "",
        
        "show_webapp_button": config.show_webapp_button if config.show_webapp_button is not None else True,
        "show_trial_button": config.show_trial_button if config.show_trial_button is not None else True,
        "show_referral_button": config.show_referral_button if config.show_referral_button is not None else True,
        "show_support_button": config.show_support_button if config.show_support_button is not None else True,
        "show_servers_button": config.show_servers_button if config.show_servers_button is not None else True,
        "show_agreement_button": config.show_agreement_button if config.show_agreement_button is not None else True,
        "show_offer_button": config.show_offer_button if config.show_offer_button is not None else True,
        "show_topup_button": config.show_topup_button if config.show_topup_button is not None else True,
        "trial_days": config.trial_days or 3,
        
        # Все переводы в одном объекте
        "translations": {
            "ru": json.loads(config.translations_ru) if config.translations_ru else {},
            "ua": json.loads(config.translations_ua) if config.translations_ua else {},
            "en": json.loads(config.translations_en) if config.translations_en else {},
            "cn": json.loads(config.translations_cn) if config.translations_cn else {}
        },
        
        # Приветственные сообщения
        "welcome_messages": {
            "ru": config.welcome_message_ru or "",
            "ua": config.welcome_message_ua or "",
            "en": config.welcome_message_en or "",
            "cn": config.welcome_message_cn or ""
        },
        
        # Документы
        "user_agreements": {
            "ru": config.user_agreement_ru or "",
            "ua": config.user_agreement_ua or "",
            "en": config.user_agreement_en or "",
            "cn": config.user_agreement_cn or ""
        },
        "offer_texts": {
            "ru": config.offer_text_ru or "",
            "ua": config.offer_text_ua or "",
            "en": config.offer_text_en or "",
            "cn": config.offer_text_cn or ""
        },
        
        "menu_structure": json.loads(config.menu_structure) if config.menu_structure else None,
        
        # Проверка подписки на канал
        "require_channel_subscription": getattr(config, 'require_channel_subscription', False) or False,
        "channel_id": getattr(config, 'channel_id', '') or "",
        "channel_url": getattr(config, 'channel_url', '') or "",
        "channel_subscription_texts": {
            "ru": getattr(config, 'channel_subscription_text_ru', '') or "",
            "ua": getattr(config, 'channel_subscription_text_ua', '') or "",
            "en": getattr(config, 'channel_subscription_text_en', '') or "",
            "cn": getattr(config, 'channel_subscription_text_cn', '') or ""
        },
        
        # Ссылка на бота для Mini App
        "bot_link_for_miniapp": getattr(config, 'bot_link_for_miniapp', '') or "",
        
        # Порядок кнопок
        "buttons_order": json.loads(config.buttons_order) if hasattr(config, 'buttons_order') and config.buttons_order else ["connect", "trial", "status", "tariffs", "topup", "servers", "referrals", "support", "settings", "agreement", "offer", "webapp"]
    }), 200


@app.route('/api/admin/bot-config/default-translations', methods=['GET'])
@admin_required
def get_default_translations(current_admin):
    """Получить дефолтные переводы бота для редактирования"""
    # Эти переводы можно загрузить из client_bot.py или определить здесь
    default_translations = {
        "ru": {
            "main_menu": "Главное меню",
            "welcome_bot": "Добро пожаловать в {SERVICE_NAME} VPN Bot!",
            "welcome_user": "Добро пожаловать",
            "stealthnet_bot": "{SERVICE_NAME} VPN Bot",
            "not_registered_text": "Вы еще не зарегистрированы в системе.",
            "register_here": "Вы можете зарегистрироваться прямо здесь в боте или на сайте.",
            "after_register": "После регистрации вы получите логин и пароль для входа на сайте.",
            "subscription_status_title": "Статус подписки",
            "active": "Активна",
            "inactive": "Не активна",
            "balance": "Баланс",
            "traffic_title": "Трафик",
            "unlimited_traffic": "Безлимитный",
            "days": "дней",
            "connect_button": "Подключиться",
            "activate_trial_button": "Активировать триал",
            "status_button": "Статус подписки",
            "tariffs_button": "Тарифы",
            "servers_button": "Серверы",
            "referrals_button": "Рефералы",
            "support_button": "Поддержка",
            "settings_button": "Настройки",
            "top_up_balance": "Пополнить баланс",
            "cabinet_button": "Кабинет",
            "user_agreement_button": "Соглашение",
            "offer_button": "Оферта",
            "main_menu_button": "Главное меню",
            "back": "Назад",
            "register": "Зарегистрироваться",
            "on_site": "на сайте",
            "error": "Ошибка",
            "auth_error": "Ошибка авторизации",
            "failed_to_load": "Не удалось загрузить данные",
            "trial_activated_title": "Триал активирован!",
            "trial_days_received": "Вы получили {DAYS} дней премиум доступа.",
            "enjoy_vpn": "Наслаждайтесь VPN без ограничений!",
            "referral_program": "Реферальная программа",
            "invite_friends": "Приглашайте друзей и получайте бонусы!",
            "your_referral_link": "Ваша реферальная ссылка",
            "your_code": "Ваш код",
            "copy_link": "Копировать ссылку",
            "support_title": "Поддержка",
            "create_ticket_button": "Создать тикет",
            "currency": "Валюта",
            "language": "Язык",
            "select_currency": "Выберите валюту:",
            "select_language": "Выберите язык:",
            "settings_saved": "Настройки сохранены"
        },
        "ua": {
            "main_menu": "Головне меню",
            "welcome_bot": "Ласкаво просимо в {SERVICE_NAME} VPN Bot!",
            "welcome_user": "Ласкаво просимо",
            "stealthnet_bot": "{SERVICE_NAME} VPN Bot",
            "not_registered_text": "Ви ще не зареєстровані в системі.",
            "register_here": "Ви можете зареєструватися прямо тут в боті або на сайті.",
            "after_register": "Після реєстрації ви отримаєте логін і пароль для входу на сайті.",
            "subscription_status_title": "Статус підписки",
            "active": "Активна",
            "inactive": "Не активна",
            "balance": "Баланс",
            "traffic_title": "Трафік",
            "unlimited_traffic": "Безлімітний",
            "days": "днів",
            "connect_button": "Підключитися",
            "activate_trial_button": "Активувати триал",
            "status_button": "Статус підписки",
            "tariffs_button": "Тарифи",
            "servers_button": "Сервери",
            "referrals_button": "Реферали",
            "support_button": "Підтримка",
            "settings_button": "Налаштування",
            "top_up_balance": "Поповнити баланс",
            "cabinet_button": "Кабінет",
            "user_agreement_button": "Угода",
            "offer_button": "Оферта",
            "main_menu_button": "Головне меню",
            "back": "Назад",
            "register": "Зареєструватися",
            "on_site": "на сайті",
            "error": "Помилка",
            "auth_error": "Помилка авторизації",
            "failed_to_load": "Не вдалося завантажити дані",
            "trial_activated_title": "Триал активовано!",
            "trial_days_received": "Ви отримали {DAYS} днів преміум доступу.",
            "enjoy_vpn": "Насолоджуйтесь VPN без обмежень!",
            "referral_program": "Реферальна програма",
            "invite_friends": "Запрошуйте друзів і отримуйте бонуси!",
            "your_referral_link": "Ваше реферальне посилання",
            "your_code": "Ваш код",
            "copy_link": "Копіювати посилання",
            "support_title": "Підтримка",
            "create_ticket_button": "Створити тікет",
            "currency": "Валюта",
            "language": "Мова",
            "select_currency": "Виберіть валюту:",
            "select_language": "Виберіть мову:",
            "settings_saved": "Налаштування збережено"
        },
        "en": {
            "main_menu": "Main Menu",
            "welcome_bot": "Welcome to {SERVICE_NAME} VPN Bot!",
            "welcome_user": "Welcome",
            "stealthnet_bot": "{SERVICE_NAME} VPN Bot",
            "not_registered_text": "You are not registered yet.",
            "register_here": "You can register right here in the bot or on the website.",
            "after_register": "After registration, you will receive login credentials for the website.",
            "subscription_status_title": "Subscription Status",
            "active": "Active",
            "inactive": "Inactive",
            "balance": "Balance",
            "traffic_title": "Traffic",
            "unlimited_traffic": "Unlimited",
            "days": "days",
            "connect_button": "Connect",
            "activate_trial_button": "Activate Trial",
            "status_button": "Subscription Status",
            "tariffs_button": "Tariffs",
            "servers_button": "Servers",
            "referrals_button": "Referrals",
            "support_button": "Support",
            "settings_button": "Settings",
            "top_up_balance": "Top Up Balance",
            "cabinet_button": "Dashboard",
            "user_agreement_button": "Agreement",
            "offer_button": "Terms",
            "main_menu_button": "Main Menu",
            "back": "Back",
            "register": "Register",
            "on_site": "on site",
            "error": "Error",
            "auth_error": "Authorization error",
            "failed_to_load": "Failed to load data",
            "trial_activated_title": "Trial Activated!",
            "trial_days_received": "You received {DAYS} days of premium access.",
            "enjoy_vpn": "Enjoy VPN without limits!",
            "referral_program": "Referral Program",
            "invite_friends": "Invite friends and get bonuses!",
            "your_referral_link": "Your referral link",
            "your_code": "Your code",
            "copy_link": "Copy link",
            "support_title": "Support",
            "create_ticket_button": "Create ticket",
            "currency": "Currency",
            "language": "Language",
            "select_currency": "Select currency:",
            "select_language": "Select language:",
            "settings_saved": "Settings saved"
        },
        "cn": {
            "main_menu": "主菜单",
            "welcome_bot": "欢迎使用 {SERVICE_NAME} VPN Bot!",
            "welcome_user": "欢迎",
            "stealthnet_bot": "{SERVICE_NAME} VPN Bot",
            "not_registered_text": "您尚未注册。",
            "register_here": "您可以在此机器人中或在网站上注册。",
            "after_register": "注册后，您将获得网站登录凭据。",
            "subscription_status_title": "订阅状态",
            "active": "活跃",
            "inactive": "不活跃",
            "balance": "余额",
            "traffic_title": "流量",
            "unlimited_traffic": "无限",
            "days": "天",
            "connect_button": "连接",
            "activate_trial_button": "激活试用",
            "status_button": "订阅状态",
            "tariffs_button": "套餐",
            "servers_button": "服务器",
            "referrals_button": "推荐",
            "support_button": "支持",
            "settings_button": "设置",
            "top_up_balance": "充值余额",
            "cabinet_button": "仪表板",
            "user_agreement_button": "协议",
            "offer_button": "条款",
            "main_menu_button": "主菜单",
            "back": "返回",
            "register": "注册",
            "on_site": "在网站上",
            "error": "错误",
            "auth_error": "授权错误",
            "failed_to_load": "加载数据失败",
            "trial_activated_title": "试用已激活！",
            "trial_days_received": "您获得了 {DAYS} 天的高级访问权限。",
            "enjoy_vpn": "享受无限制的VPN！",
            "referral_program": "推荐计划",
            "invite_friends": "邀请朋友并获得奖励！",
            "your_referral_link": "您的推荐链接",
            "your_code": "您的代码",
            "copy_link": "复制链接",
            "support_title": "支持",
            "create_ticket_button": "创建工单",
            "currency": "货币",
            "language": "语言",
            "select_currency": "选择货币：",
            "select_language": "选择语言：",
            "settings_saved": "设置已保存"
        }
    }
    
    return jsonify(default_translations), 200


@app.route('/api/public/system-settings', methods=['GET'])
def public_system_settings():
    """Публичный эндпоинт для получения публичных системных настроек"""
    import json
    s = SystemSetting.query.first() or SystemSetting(id=1)
    if not s.id: 
        db.session.add(s)
        db.session.commit()
        if s.show_language_currency_switcher is None:
            s.show_language_currency_switcher = True
        if not s.active_languages or s.active_languages.strip() == '':
            s.active_languages = '["ru","ua","en","cn"]'
        if not s.active_currencies or s.active_currencies.strip() == '':
            s.active_currencies = '["uah","rub","usd"]'
        db.session.commit()
    
    # Автозаполнение NULL значений
    needs_save = False
    if not s.active_languages or s.active_languages.strip() == '':
        s.active_languages = '["ru","ua","en","cn"]'
        needs_save = True
    if not s.active_currencies or s.active_currencies.strip() == '':
        s.active_currencies = '["uah","rub","usd"]'
        needs_save = True
    if needs_save:
        try:
            db.session.commit()
        except:
            db.session.rollback()
    
    # Парсим JSON массивы
    try:
        active_languages = json.loads(s.active_languages) if s.active_languages else ["ru", "ua", "en", "cn"]
    except:
        active_languages = ["ru", "ua", "en", "cn"]
    
    try:
        active_currencies = json.loads(s.active_currencies) if s.active_currencies else ["uah", "rub", "usd"]
    except:
        active_currencies = ["uah", "rub", "usd"]
    
    print(f"[PUBLIC SYSTEM SETTINGS] active_languages={active_languages}, active_currencies={active_currencies}")
    
    return jsonify({
        "show_language_currency_switcher": s.show_language_currency_switcher if s.show_language_currency_switcher is not None else True,
        "active_languages": active_languages,
        "active_currencies": active_currencies,
        # Цвета светлой темы
        "theme_primary_color": getattr(s, 'theme_primary_color', '#3f69ff') or '#3f69ff',
        "theme_bg_primary": getattr(s, 'theme_bg_primary', '#f8fafc') or '#f8fafc',
        "theme_bg_secondary": getattr(s, 'theme_bg_secondary', '#eef2ff') or '#eef2ff',
        "theme_text_primary": getattr(s, 'theme_text_primary', '#0f172a') or '#0f172a',
        "theme_text_secondary": getattr(s, 'theme_text_secondary', '#64748b') or '#64748b',
        # Цвета тёмной темы
        "theme_primary_color_dark": getattr(s, 'theme_primary_color_dark', '#6c7bff') or '#6c7bff',
        "theme_bg_primary_dark": getattr(s, 'theme_bg_primary_dark', '#050816') or '#050816',
        "theme_bg_secondary_dark": getattr(s, 'theme_bg_secondary_dark', '#0f172a') or '#0f172a',
        "theme_text_primary_dark": getattr(s, 'theme_text_primary_dark', '#e2e8f0') or '#e2e8f0',
        "theme_text_secondary_dark": getattr(s, 'theme_text_secondary_dark', '#94a3b8') or '#94a3b8'
    }), 200

# --- PAYMENT & SUPPORT ---

@app.route('/api/public/available-payment-methods', methods=['GET'])
def available_payment_methods():
    """
    Возвращает список доступных способов оплаты (те, у которых настроены ключи).
    Публичный endpoint, доступен без авторизации.
    """
    s = PaymentSetting.query.first()
    if not s:
        return jsonify({"available_methods": []}), 200
    
    available = []
    
    # CrystalPay - нужны api_key и api_secret
    crystalpay_key = decrypt_key(s.crystalpay_api_key) if s.crystalpay_api_key else None
    crystalpay_secret = decrypt_key(s.crystalpay_api_secret) if s.crystalpay_api_secret else None
    if crystalpay_key and crystalpay_secret and crystalpay_key != "DECRYPTION_ERROR" and crystalpay_secret != "DECRYPTION_ERROR":
        available.append('crystalpay')
    
    # Heleket - нужен api_key
    heleket_key = decrypt_key(s.heleket_api_key) if s.heleket_api_key else None
    if heleket_key and heleket_key != "DECRYPTION_ERROR":
        available.append('heleket')
    
    # YooKassa - нужны shop_id и secret_key
    yookassa_shop = decrypt_key(s.yookassa_shop_id) if s.yookassa_shop_id else None
    yookassa_secret = decrypt_key(s.yookassa_secret_key) if s.yookassa_secret_key else None
    if yookassa_shop and yookassa_secret and yookassa_shop != "DECRYPTION_ERROR" and yookassa_secret != "DECRYPTION_ERROR":
        available.append('yookassa')
    
    # Platega - нужны api_key и merchant_id
    platega_key = decrypt_key(s.platega_api_key) if s.platega_api_key else None
    platega_merchant = decrypt_key(s.platega_merchant_id) if s.platega_merchant_id else None
    if platega_key and platega_merchant and platega_key != "DECRYPTION_ERROR" and platega_merchant != "DECRYPTION_ERROR":
        available.append('platega')
    
    # Mulenpay - нужны api_key, secret_key и shop_id
    mulenpay_key = decrypt_key(s.mulenpay_api_key) if s.mulenpay_api_key else None
    mulenpay_secret = decrypt_key(s.mulenpay_secret_key) if s.mulenpay_secret_key else None
    mulenpay_shop = decrypt_key(s.mulenpay_shop_id) if s.mulenpay_shop_id else None
    if mulenpay_key and mulenpay_secret and mulenpay_shop and mulenpay_key != "DECRYPTION_ERROR" and mulenpay_secret != "DECRYPTION_ERROR" and mulenpay_shop != "DECRYPTION_ERROR":
        available.append('mulenpay')
    
    # UrlPay - нужны api_key, secret_key и shop_id
    urlpay_key = decrypt_key(s.urlpay_api_key) if s.urlpay_api_key else None
    urlpay_secret = decrypt_key(s.urlpay_secret_key) if s.urlpay_secret_key else None
    urlpay_shop = decrypt_key(s.urlpay_shop_id) if s.urlpay_shop_id else None
    if urlpay_key and urlpay_secret and urlpay_shop and urlpay_key != "DECRYPTION_ERROR" and urlpay_secret != "DECRYPTION_ERROR" and urlpay_shop != "DECRYPTION_ERROR":
        available.append('urlpay')
    
    # Telegram Stars - нужен bot_token
    telegram_token = decrypt_key(s.telegram_bot_token) if s.telegram_bot_token else None
    if telegram_token and telegram_token != "DECRYPTION_ERROR":
        available.append('telegram_stars')
    
    # Monobank - нужен token
    monobank_token = decrypt_key(s.monobank_token) if s.monobank_token else None
    if monobank_token and monobank_token != "DECRYPTION_ERROR":
        available.append('monobank')
    
    # BTCPayServer - нужны url, api_key и store_id
    btcpayserver_url = decrypt_key(s.btcpayserver_url) if s.btcpayserver_url else None
    btcpayserver_api_key = decrypt_key(s.btcpayserver_api_key) if s.btcpayserver_api_key else None
    btcpayserver_store_id = decrypt_key(s.btcpayserver_store_id) if s.btcpayserver_store_id else None
    if btcpayserver_url and btcpayserver_api_key and btcpayserver_store_id and btcpayserver_url != "DECRYPTION_ERROR" and btcpayserver_api_key != "DECRYPTION_ERROR" and btcpayserver_store_id != "DECRYPTION_ERROR":
        available.append('btcpayserver')
    
    # Tribute - нужен api_key
    tribute_api_key = decrypt_key(s.tribute_api_key) if s.tribute_api_key else None
    if tribute_api_key and tribute_api_key != "DECRYPTION_ERROR":
        available.append('tribute')
    
    # Robokassa - нужны merchant_login и password1
    robokassa_login = decrypt_key(s.robokassa_merchant_login) if s.robokassa_merchant_login else None
    robokassa_password1 = decrypt_key(s.robokassa_password1) if s.robokassa_password1 else None
    if robokassa_login and robokassa_password1 and robokassa_login != "DECRYPTION_ERROR" and robokassa_password1 != "DECRYPTION_ERROR":
        available.append('robokassa')
    
    # Freekassa - нужны shop_id и secret
    freekassa_shop_id = decrypt_key(s.freekassa_shop_id) if s.freekassa_shop_id else None
    freekassa_secret = decrypt_key(s.freekassa_secret) if s.freekassa_secret else None
    if freekassa_shop_id and freekassa_secret and freekassa_shop_id != "DECRYPTION_ERROR" and freekassa_secret != "DECRYPTION_ERROR":
        available.append('freekassa')
    
    return jsonify({"available_methods": available}), 200

@app.route('/api/admin/payment-settings', methods=['GET', 'POST'])
@admin_required
def pay_settings(current_admin):
    try:
        s = PaymentSetting.query.first() or PaymentSetting()
        if not s.id: db.session.add(s); db.session.commit()
    except Exception as e:
        # Если ошибка связана с отсутствующими колонками, пытаемся их добавить
        error_str = str(e)
        if "no such column" in error_str.lower():
            print(f"⚠️  Обнаружены отсутствующие колонки в payment_setting, добавляем их...")
            try:
                import sqlite3
                db_path = app.config.get('SQLALCHEMY_DATABASE_URI', '').replace('sqlite:///', '')
                if not db_path:
                    db_path = 'stealthnet.db'
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Проверяем существующие колонки
                cursor.execute("PRAGMA table_info(payment_setting)")
                existing_columns = [col[1] for col in cursor.fetchall()]
                
                # Добавляем все недостающие колонки из required_columns
                required_columns = {
                    'platega_api_key': 'TEXT',
                    'platega_merchant_id': 'TEXT',
                    'mulenpay_api_key': 'TEXT',
                    'mulenpay_secret_key': 'TEXT',
                    'mulenpay_shop_id': 'TEXT',
                    'urlpay_api_key': 'TEXT',
                    'urlpay_secret_key': 'TEXT',
                    'urlpay_shop_id': 'TEXT',
                    'monobank_token': 'TEXT',
                    'btcpayserver_url': 'TEXT',
                    'btcpayserver_api_key': 'TEXT',
                    'btcpayserver_store_id': 'TEXT',
                    'tribute_api_key': 'TEXT',
                    'robokassa_merchant_login': 'TEXT',
                    'robokassa_password1': 'TEXT',
                    'robokassa_password2': 'TEXT'
                }
                
                for col_name, col_type in required_columns.items():
                    if col_name not in existing_columns:
                        try:
                            cursor.execute(f"ALTER TABLE payment_setting ADD COLUMN {col_name} {col_type}")
                            print(f"✓ Колонка {col_name} добавлена")
                        except sqlite3.OperationalError as alter_e:
                            if "duplicate column name" not in str(alter_e).lower():
                                print(f"⚠️  Ошибка при добавлении колонки {col_name}: {alter_e}")
                
                conn.commit()
                conn.close()
                
                # Повторяем запрос после миграции
                s = PaymentSetting.query.first() or PaymentSetting()
                if not s.id: db.session.add(s); db.session.commit()
            except Exception as migration_error:
                print(f"❌ Ошибка при миграции: {migration_error}")
                import traceback
                traceback.print_exc()
                # Возвращаем пустые настройки, чтобы не сломать интерфейс
                s = PaymentSetting()
        else:
            # Другая ошибка - пробрасываем дальше
            raise
    if request.method == 'POST':
        d = request.json
        s.crystalpay_api_key = encrypt_key(d.get('crystalpay_api_key', ''))
        s.crystalpay_api_secret = encrypt_key(d.get('crystalpay_api_secret', ''))
        s.heleket_api_key = encrypt_key(d.get('heleket_api_key', ''))
        s.telegram_bot_token = encrypt_key(d.get('telegram_bot_token', ''))
        s.yookassa_shop_id = encrypt_key(d.get('yookassa_shop_id', ''))
        s.yookassa_secret_key = encrypt_key(d.get('yookassa_secret_key', ''))
        s.platega_api_key = encrypt_key(d.get('platega_api_key', ''))
        s.platega_merchant_id = encrypt_key(d.get('platega_merchant_id', ''))
        s.mulenpay_api_key = encrypt_key(d.get('mulenpay_api_key', ''))
        s.mulenpay_secret_key = encrypt_key(d.get('mulenpay_secret_key', ''))
        s.mulenpay_shop_id = encrypt_key(d.get('mulenpay_shop_id', ''))
        s.urlpay_api_key = encrypt_key(d.get('urlpay_api_key', ''))
        s.urlpay_secret_key = encrypt_key(d.get('urlpay_secret_key', ''))
        s.urlpay_shop_id = encrypt_key(d.get('urlpay_shop_id', ''))
        s.monobank_token = encrypt_key(d.get('monobank_token', ''))
        s.btcpayserver_url = encrypt_key(d.get('btcpayserver_url', ''))
        s.btcpayserver_api_key = encrypt_key(d.get('btcpayserver_api_key', ''))
        s.btcpayserver_store_id = encrypt_key(d.get('btcpayserver_store_id', ''))
        s.tribute_api_key = encrypt_key(d.get('tribute_api_key', ''))
        s.robokassa_merchant_login = encrypt_key(d.get('robokassa_merchant_login', ''))
        s.robokassa_password1 = encrypt_key(d.get('robokassa_password1', ''))
        s.robokassa_password2 = encrypt_key(d.get('robokassa_password2', ''))
        s.freekassa_shop_id = encrypt_key(d.get('freekassa_shop_id', ''))
        s.freekassa_secret = encrypt_key(d.get('freekassa_secret', ''))
        s.freekassa_secret2 = encrypt_key(d.get('freekassa_secret2', ''))
        db.session.commit()
    return jsonify({
        "crystalpay_api_key": decrypt_key(s.crystalpay_api_key), 
        "crystalpay_api_secret": decrypt_key(s.crystalpay_api_secret),
        "heleket_api_key": decrypt_key(s.heleket_api_key),
        "telegram_bot_token": decrypt_key(s.telegram_bot_token),
        "yookassa_shop_id": decrypt_key(s.yookassa_shop_id),
        "yookassa_secret_key": decrypt_key(s.yookassa_secret_key),
        "platega_api_key": decrypt_key(s.platega_api_key),
        "platega_merchant_id": decrypt_key(s.platega_merchant_id),
        "mulenpay_api_key": decrypt_key(s.mulenpay_api_key),
        "mulenpay_secret_key": decrypt_key(s.mulenpay_secret_key),
        "mulenpay_shop_id": decrypt_key(s.mulenpay_shop_id),
        "urlpay_api_key": decrypt_key(s.urlpay_api_key), 
        "urlpay_secret_key": decrypt_key(s.urlpay_secret_key),
        "urlpay_shop_id": decrypt_key(s.urlpay_shop_id),
        "monobank_token": decrypt_key(s.monobank_token),
        "btcpayserver_url": decrypt_key(s.btcpayserver_url),
        "btcpayserver_api_key": decrypt_key(s.btcpayserver_api_key),
        "btcpayserver_store_id": decrypt_key(s.btcpayserver_store_id),
        "tribute_api_key": decrypt_key(s.tribute_api_key),
        "robokassa_merchant_login": decrypt_key(s.robokassa_merchant_login),
        "robokassa_password1": decrypt_key(s.robokassa_password1),
        "robokassa_password2": decrypt_key(s.robokassa_password2),
        "freekassa_shop_id": decrypt_key(s.freekassa_shop_id),
        "freekassa_secret": decrypt_key(s.freekassa_secret),
        "freekassa_secret2": decrypt_key(s.freekassa_secret2)
    }), 200

@app.route('/api/client/purchase-with-balance', methods=['POST'])
@limiter.limit("10 per minute")
def purchase_with_balance():
    """Покупка тарифа с баланса пользователя"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Auth Error"}), 401
    
    try:
        data = request.json
        tariff_id = data.get('tariff_id')
        promo_code_str = data.get('promo_code', '').strip().upper() if data.get('promo_code') else None
        
        if not tariff_id:
            return jsonify({"message": "tariff_id is required"}), 400
        
        # Получаем тариф
        t = db.session.get(Tariff, tariff_id)
        if not t:
            return jsonify({"message": "Тариф не найден"}), 404
        
        # Определяем цену в валюте пользователя
        price_map = {"uah": {"a": t.price_uah, "c": "UAH"}, "rub": {"a": t.price_rub, "c": "RUB"}, "usd": {"a": t.price_usd, "c": "USD"}}
        info = price_map.get(user.preferred_currency, price_map['uah'])
        
        # Применяем промокод, если указан
        promo_code_obj = None
        final_amount = info['a']
        if promo_code_str:
            promo = PromoCode.query.filter_by(code=promo_code_str).first()
            if not promo:
                return jsonify({"message": "Неверный промокод"}), 400
            if promo.uses_left <= 0:
                return jsonify({"message": "Промокод больше не действителен"}), 400
            if promo.promo_type == 'PERCENT':
                discount = (promo.value / 100.0) * final_amount
                final_amount = final_amount - discount
                if final_amount < 0:
                    final_amount = 0
                promo_code_obj = promo
            elif promo.promo_type == 'DAYS':
                return jsonify({"message": "Промокод на бесплатные дни активируется отдельно"}), 400
        
        # Проверяем баланс пользователя
        # Баланс хранится в USD, конвертируем цену тарифа в USD
        current_balance_usd = float(user.balance) if user.balance else 0.0
        final_amount_usd = convert_to_usd(final_amount, info['c'])
        
        if current_balance_usd < final_amount_usd:
            # Для сообщения об ошибке конвертируем баланс обратно в валюту пользователя
            current_balance_display = convert_from_usd(current_balance_usd, user.preferred_currency)
            return jsonify({
                "message": f"Недостаточно средств на балансе. Требуется: {final_amount:.2f} {info['c']}, доступно: {current_balance_display:.2f} {info['c']}"
            }), 400
        
        # Списываем средства с баланса (в USD)
        user.balance = current_balance_usd - final_amount_usd
        
        # Активируем тариф
        h, c = get_remnawave_headers()
        live = requests.get(f"{API_URL}/api/users/{user.remnawave_uuid}", headers=h, cookies=c).json().get('response', {})
        curr_exp = parse_iso_datetime(live.get('expireAt'))
        new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
        
        # Используем сквад из тарифа, если указан, иначе дефолтный
        squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
        
        # Формируем payload для обновления пользователя
        patch_payload = {
            "uuid": user.remnawave_uuid,
            "expireAt": new_exp.isoformat(),
            "activeInternalSquads": [squad_id]
        }
        
        # Добавляем лимит трафика, если указан в тарифе
        if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
            patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
            patch_payload["trafficLimitStrategy"] = "NO_RESET"
        
        h, c = get_remnawave_headers({"Content-Type": "application/json"})
        patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
        if not patch_resp.ok:
            # Откатываем списание баланса
            user.balance = current_balance_usd
            db.session.rollback()
            return jsonify({"message": "Ошибка активации тарифа"}), 500
        
        # Списываем использование промокода, если он был использован
        if promo_code_obj:
            if promo_code_obj.uses_left > 0:
                promo_code_obj.uses_left -= 1
        
        # Создаем запись о платеже
        order_id = f"u{user.id}-t{t.id}-balance-{int(datetime.now().timestamp())}"
        new_p = Payment(
            order_id=order_id,
            user_id=user.id,
            tariff_id=t.id,
            status='PAID',
            amount=final_amount,
            currency=info['c'],
            payment_provider='balance',
            promo_code_id=promo_code_obj.id if promo_code_obj else None
        )
        db.session.add(new_p)
        db.session.commit()
        
        # Очищаем кэш
        cache.delete(f'live_data_{user.remnawave_uuid}')
        cache.delete(f'nodes_{user.remnawave_uuid}')
        cache.delete('all_live_users_map')
        
        # Конвертируем баланс обратно в валюту пользователя для отображения
        balance_display = convert_from_usd(float(user.balance), user.preferred_currency)
        
        return jsonify({
            "message": "Тариф успешно активирован",
            "balance": balance_display,
            "tariff_id": t.id,
            "tariff_name": t.name
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Purchase with balance error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Error"}), 500

@app.route('/api/client/create-payment', methods=['POST'])
def create_payment():
    user = get_user_from_token()
    if not user: return jsonify({"message": "Auth Error"}), 401
    try:
        # Проверяем, это пополнение баланса или покупка тарифа
        payment_type = request.json.get('type', 'tariff')
        tid = request.json.get('tariff_id')
        
        # Если это пополнение баланса, обрабатываем отдельно
        if payment_type == 'balance_topup' or tid is None:
            amount = request.json.get('amount', 0)
            currency = request.json.get('currency', user.preferred_currency or 'uah')
            payment_provider = request.json.get('payment_provider', 'crystalpay')
            
            if not amount or amount <= 0:
                return jsonify({"message": "Неверная сумма"}), 400
            
            # Создаем платеж для пополнения баланса
            s = PaymentSetting.query.first()
            order_id = f"u{user.id}-balance-{int(datetime.now().timestamp())}"
            payment_url = None
            payment_system_id = None
            
            # Используем ту же логику создания платежа, что и для тарифов
            # но без тарифа
            currency_code_map = {"uah": "UAH", "rub": "RUB", "usd": "USD"}
            cp_currency = currency_code_map.get(currency.lower(), "UAH")
            
            if payment_provider == 'crystalpay':
                crystalpay_key = decrypt_key(s.crystalpay_api_key) if s else None
                crystalpay_secret = decrypt_key(s.crystalpay_api_secret) if s else None
                if not crystalpay_key or crystalpay_key == "DECRYPTION_ERROR" or not crystalpay_secret or crystalpay_secret == "DECRYPTION_ERROR":
                    return jsonify({"message": "CrystalPay не настроен"}), 500
                
                # Используем v3 API для создания платежа (как в обычной покупке тарифа)
                payload = {
                    "auth_login": crystalpay_key,
                    "auth_secret": crystalpay_secret,
                    "amount": f"{float(amount):.2f}",
                    "type": "purchase",
                    "currency": cp_currency,
                    "lifetime": 60,
                    "extra": order_id,
                    "callback_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/crystalpay",
                    "redirect_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
                }
                
                resp = requests.post("https://api.crystalpay.io/v3/invoice/create/", json=payload, timeout=10)
                if resp.ok:
                    data = resp.json()
                    if not data.get('errors'):
                        payment_url = data.get('url')
                        payment_system_id = data.get('id')
                    else:
                        print(f"CrystalPay Error for balance topup: {data.get('errors')}")
                else:
                    print(f"CrystalPay API Error: {resp.status_code} - {resp.text}")
            
            elif payment_provider == 'heleket':
                heleket_key = decrypt_key(s.heleket_api_key) if s else None
                if not heleket_key or heleket_key == "DECRYPTION_ERROR":
                    return jsonify({"message": "Heleket API key not configured"}), 500
                
                # Heleket поддерживает USD напрямую, для других валют используем конвертацию через to_currency
                heleket_currency = cp_currency
                to_currency = None
                
                if cp_currency == 'USD':
                    heleket_currency = "USD"
                else:
                    heleket_currency = "USD"
                    to_currency = "USDT"
                
                payload = {
                    "amount": f"{float(amount):.2f}",
                    "currency": heleket_currency,
                    "order_id": order_id,
                    "url_return": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                    "url_callback": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/heleket"
                }
                
                if to_currency:
                    payload["to_currency"] = to_currency
                
                headers = {
                    "Authorization": f"Bearer {heleket_key}",
                    "Content-Type": "application/json"
                }
                
                resp = requests.post("https://api.heleket.com/v1/payment", json=payload, headers=headers, timeout=10)
                if resp.ok:
                    data = resp.json()
                    if data.get('state') == 0 and data.get('result'):
                        result = data.get('result', {})
                        payment_url = result.get('url')
                        payment_system_id = result.get('uuid')
                    else:
                        print(f"Heleket Error for balance topup: {data.get('message')}")
                else:
                    print(f"Heleket API Error: {resp.status_code} - {resp.text}")
            
            elif payment_provider == 'yookassa':
                yookassa_shop = decrypt_key(s.yookassa_shop_id) if s else None
                yookassa_secret = decrypt_key(s.yookassa_secret_key) if s else None
                if not yookassa_shop or not yookassa_secret or yookassa_shop == "DECRYPTION_ERROR" or yookassa_secret == "DECRYPTION_ERROR":
                    return jsonify({"message": "YooKassa credentials not configured"}), 500
                
                if cp_currency != 'RUB':
                    return jsonify({"message": "YooKassa поддерживает только валюту RUB. Пожалуйста, выберите другую платежную систему или измените валюту на RUB."}), 400
                
                import uuid
                import base64
                idempotence_key = str(uuid.uuid4())
                
                payload = {
                    "amount": {
                        "value": f"{float(amount):.2f}",
                        "currency": "RUB"
                    },
                    "capture": True,
                    "confirmation": {
                        "type": "redirect",
                        "return_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
                    },
                    "description": f"Пополнение баланса на сумму {float(amount):.2f} RUB",
                    "metadata": {
                        "order_id": order_id
                    }
                }
                
                auth_string = f"{yookassa_shop}:{yookassa_secret}"
                auth_bytes = auth_string.encode('ascii')
                auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
                
                headers = {
                    "Authorization": f"Basic {auth_b64}",
                    "Idempotence-Key": idempotence_key,
                    "Content-Type": "application/json"
                }
                
                try:
                    resp = requests.post("https://api.yookassa.ru/v3/payments", json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get('status') != 'pending':
                        error_msg = data.get('description', 'YooKassa payment creation failed')
                        print(f"YooKassa Error: {error_msg}")
                    else:
                        confirmation = data.get('confirmation', {})
                        payment_url = confirmation.get('confirmation_url')
                        payment_system_id = data.get('id')
                        if not payment_url:
                            print(f"YooKassa Error: No confirmation URL")
                except requests.exceptions.RequestException as e:
                    print(f"YooKassa API Error: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get('description', str(e))
                        except:
                            error_msg = str(e)
                    else:
                        error_msg = str(e)
                    print(f"YooKassa Error: {error_msg}")
            
            elif payment_provider == 'platega':
                import uuid
                platega_key = decrypt_key(s.platega_api_key) if s else None
                platega_merchant = decrypt_key(s.platega_merchant_id) if s else None
                if not platega_key or not platega_merchant or platega_key == "DECRYPTION_ERROR" or platega_merchant == "DECRYPTION_ERROR":
                    return jsonify({"message": "Platega credentials not configured"}), 500
                
                transaction_uuid = str(uuid.uuid4())
                
                payload = {
                    "paymentMethod": 2,  # 2 - СБП/QR, 10 - CardRu, 12 - International
                    "id": transaction_uuid,
                    "paymentDetails": {
                        "amount": int(float(amount)),
                        "currency": cp_currency
                    },
                    "description": f"Пополнение баланса на сумму {float(amount):.2f} {cp_currency}",
                    "return": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                    "failedUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
                }
                
                headers = {
                    "Content-Type": "application/json",
                    "X-MerchantId": platega_merchant,
                    "X-Secret": platega_key
                }
                
                try:
                    resp = requests.post("https://app.platega.io/transaction/process", json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    payment_url = data.get('redirect')
                    payment_system_id = data.get('transactionId') or transaction_uuid
                    if not payment_url:
                        print(f"Platega Error for balance topup: {data.get('message', 'No redirect URL')}")
                except requests.exceptions.RequestException as e:
                    print(f"Platega API Error: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get('message', str(e))
                        except:
                            error_msg = str(e)
                    else:
                        error_msg = str(e)
                    print(f"Platega Error: {error_msg}")
            
            elif payment_provider == 'mulenpay':
                mulenpay_key = decrypt_key(s.mulenpay_api_key) if s else None
                mulenpay_secret = decrypt_key(s.mulenpay_secret_key) if s else None
                mulenpay_shop = decrypt_key(s.mulenpay_shop_id) if s else None
                if not mulenpay_key or not mulenpay_secret or not mulenpay_shop or mulenpay_key == "DECRYPTION_ERROR" or mulenpay_secret == "DECRYPTION_ERROR" or mulenpay_shop == "DECRYPTION_ERROR":
                    return jsonify({"message": "Mulenpay credentials not configured"}), 500
                
                currency_map = {
                    'RUB': 'rub',
                    'UAH': 'uah',
                    'USD': 'usd'
                }
                mulenpay_currency = currency_map.get(cp_currency, cp_currency.lower())
                
                try:
                    shop_id_int = int(mulenpay_shop)
                except (ValueError, TypeError):
                    shop_id_int = mulenpay_shop
                
                payload = {
                    "currency": mulenpay_currency,
                    "amount": str(float(amount)),
                    "uuid": order_id,
                    "shopId": shop_id_int,
                    "description": f"Пополнение баланса на сумму {float(amount):.2f} {cp_currency}",
                    "subscribe": None,
                    "holdTime": None
                }
                
                import base64
                auth_string = f"{mulenpay_key}:{mulenpay_secret}"
                auth_bytes = auth_string.encode('ascii')
                auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
                
                headers = {
                    "Authorization": f"Basic {auth_b64}",
                    "Content-Type": "application/json"
                }
                
                try:
                    resp = requests.post("https://api.mulenpay.ru/v2/payments", json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    payment_url = data.get('url') or data.get('payment_url') or data.get('redirect')
                    payment_system_id = data.get('id') or data.get('payment_id') or order_id
                    if not payment_url:
                        print(f"Mulenpay Error for balance topup: {data.get('message', 'No payment URL')}")
                except requests.exceptions.RequestException as e:
                    print(f"Mulenpay API Error: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get('message') or error_data.get('error') or str(e)
                        except:
                            error_msg = str(e)
                    else:
                        error_msg = str(e)
                    print(f"Mulenpay Error: {error_msg}")
            
            elif payment_provider == 'urlpay':
                urlpay_key = decrypt_key(s.urlpay_api_key) if s else None
                urlpay_secret = decrypt_key(s.urlpay_secret_key) if s else None
                urlpay_shop = decrypt_key(s.urlpay_shop_id) if s else None
                if not urlpay_key or not urlpay_secret or not urlpay_shop or urlpay_key == "DECRYPTION_ERROR" or urlpay_secret == "DECRYPTION_ERROR" or urlpay_shop == "DECRYPTION_ERROR":
                    return jsonify({"message": "UrlPay credentials not configured"}), 500
                
                currency_map = {
                    'RUB': 'rub',
                    'UAH': 'uah',
                    'USD': 'usd'
                }
                urlpay_currency = currency_map.get(cp_currency, cp_currency.lower())
                
                try:
                    shop_id_int = int(urlpay_shop)
                except (ValueError, TypeError):
                    shop_id_int = urlpay_shop
                
                payload = {
                    "currency": urlpay_currency,
                    "amount": str(float(amount)),
                    "uuid": order_id,
                    "shopId": shop_id_int,
                    "description": f"Пополнение баланса на сумму {float(amount):.2f} {cp_currency}",
                    "subscribe": None,
                    "holdTime": None
                }
                
                import base64
                auth_string = f"{urlpay_key}:{urlpay_secret}"
                auth_bytes = auth_string.encode('ascii')
                auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
                
                headers = {
                    "Authorization": f"Basic {auth_b64}",
                    "Content-Type": "application/json"
                }
                
                try:
                    resp = requests.post("https://api.urlpay.io/v2/payments", json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    payment_url = data.get('url') or data.get('payment_url') or data.get('redirect')
                    payment_system_id = data.get('id') or data.get('payment_id') or order_id
                    if not payment_url:
                        print(f"UrlPay Error for balance topup: {data.get('message', 'No payment URL')}")
                except requests.exceptions.RequestException as e:
                    print(f"UrlPay API Error: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get('message') or error_data.get('error') or str(e)
                        except:
                            error_msg = str(e)
                    else:
                        error_msg = str(e)
                    print(f"UrlPay Error: {error_msg}")
            
            elif payment_provider == 'monobank':
                monobank_token = decrypt_key(s.monobank_token) if s else None
                if not monobank_token or monobank_token == "DECRYPTION_ERROR":
                    return jsonify({"message": "Monobank token not configured"}), 500
                
                # Monobank принимает сумму в копейках (минимальных единицах)
                # Конвертируем сумму в копейки
                amount_in_kopecks = int(float(amount) * 100)
                if cp_currency == 'UAH':
                    amount_in_kopecks = int(float(amount) * 100)  # UAH в копейках
                elif cp_currency == 'RUB':
                    amount_in_kopecks = int(float(amount) * 100)  # RUB в копейках
                elif cp_currency == 'USD':
                    amount_in_kopecks = int(float(amount) * 100)  # USD в центах
                
                # Код валюты по ISO 4217: 980 = UAH, 643 = RUB, 840 = USD
                currency_code = 980  # По умолчанию UAH
                if cp_currency == 'RUB':
                    currency_code = 643
                elif cp_currency == 'USD':
                    currency_code = 840
                
                payload = {
                    "amount": amount_in_kopecks,
                    "ccy": currency_code,
                    "merchantPaymInfo": {
                        "reference": order_id,
                        "destination": f"Пополнение баланса на сумму {float(amount):.2f} {cp_currency}",
                        "basketOrder": [
                            {
                                "name": "Пополнение баланса",
                                "qty": 1,
                                "sum": amount_in_kopecks,
                                "unit": "шт"
                            }
                        ]
                    },
                    "redirectUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                    "webHookUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/monobank",
                    "validity": 86400,  # 24 часа в секундах
                    "paymentType": "debit"
                }
                
                headers = {
                    "X-Token": monobank_token,
                    "Content-Type": "application/json"
                }
                
                try:
                    resp = requests.post("https://api.monobank.ua/api/merchant/invoice/create", json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    payment_url = data.get('pageUrl')
                    payment_system_id = data.get('invoiceId') or order_id
                    if not payment_url:
                        print(f"Monobank Error for balance topup: {data.get('errText', 'No payment URL')}")
                except requests.exceptions.RequestException as e:
                    print(f"Monobank API Error: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get('errText') or error_data.get('message') or str(e)
                        except:
                            error_msg = str(e)
                    else:
                        error_msg = str(e)
                    print(f"Monobank Error: {error_msg}")
            
            elif payment_provider == 'btcpayserver':
                btcpayserver_url = decrypt_key(s.btcpayserver_url) if s else None
                btcpayserver_api_key = decrypt_key(s.btcpayserver_api_key) if s else None
                btcpayserver_store_id = decrypt_key(s.btcpayserver_store_id) if s else None
                if not btcpayserver_url or not btcpayserver_api_key or not btcpayserver_store_id or btcpayserver_url == "DECRYPTION_ERROR" or btcpayserver_api_key == "DECRYPTION_ERROR" or btcpayserver_store_id == "DECRYPTION_ERROR":
                    return jsonify({"message": "BTCPayServer credentials not configured"}), 500
                
                btcpayserver_url = btcpayserver_url.rstrip('/')
                invoice_currency = cp_currency
                
                metadata = {
                    "orderId": order_id,
                    "buyerEmail": user.email if user.email else None,
                    "itemDesc": f"Пополнение баланса на сумму {float(amount):.2f} {cp_currency}"
                }
                
                checkout_options = {
                    "redirectURL": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
                }
                
                payload = {
                    "amount": f"{float(amount):.2f}",
                    "currency": invoice_currency,
                    "metadata": metadata,
                    "checkout": checkout_options
                }
                
                invoice_url = f"{btcpayserver_url}/api/v1/stores/{btcpayserver_store_id}/invoices"
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"token {btcpayserver_api_key}"
                }
                
                try:
                    resp = requests.post(invoice_url, json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    invoice_data = resp.json()
                    payment_url = invoice_data.get('checkoutLink')
                    payment_system_id = invoice_data.get('id')
                    if not payment_url:
                        print(f"BTCPayServer Error for balance topup: No checkoutLink in response")
                except requests.exceptions.RequestException as e:
                    print(f"BTCPayServer API Error: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get('message') or error_data.get('error') or str(e)
                        except:
                            error_msg = str(e)
                    else:
                        error_msg = str(e)
                    print(f"BTCPayServer Error: {error_msg}")
            
            elif payment_provider == 'tribute':
                tribute_api_key = decrypt_key(s.tribute_api_key) if s else None
                if not tribute_api_key or tribute_api_key == "DECRYPTION_ERROR":
                    return jsonify({"message": "Tribute API key not configured"}), 500
                
                currency_map = {
                    'RUB': 'rub',
                    'UAH': 'rub',  # UAH не поддерживается, используем RUB
                    'USD': 'eur'   # USD не поддерживается, используем EUR
                }
                tribute_currency = currency_map.get(cp_currency, 'rub')
                
                amount_in_cents = int(float(amount) * 100)
                
                payload = {
                    "amount": amount_in_cents,
                    "currency": tribute_currency,
                    "title": f"Пополнение баланса StealthNET"[:100],
                    "description": f"Пополнение баланса на сумму {float(amount):.2f} {cp_currency}"[:300],
                    "successUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                    "failUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
                }
                
                if user.email:
                    payload["email"] = user.email
                
                headers = {
                    "Content-Type": "application/json",
                    "Api-Key": tribute_api_key
                }
                
                try:
                    resp = requests.post("https://tribute.tg/api/v1/shop/orders", json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    payment_url = data.get('paymentUrl')
                    payment_system_id = data.get('uuid')
                    if not payment_url:
                        print(f"Tribute Error for balance topup: {data.get('message', 'No payment URL')}")
                except requests.exceptions.RequestException as e:
                    print(f"Tribute API Error: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get('message') or error_data.get('error') or str(e)
                        except:
                            error_msg = str(e)
                    else:
                        error_msg = str(e)
                    print(f"Tribute Error: {error_msg}")
            
            elif payment_provider == 'robokassa':
                robokassa_login = decrypt_key(s.robokassa_merchant_login) if s else None
                robokassa_password1 = decrypt_key(s.robokassa_password1) if s else None
                if not robokassa_login or not robokassa_password1 or robokassa_login == "DECRYPTION_ERROR" or robokassa_password1 == "DECRYPTION_ERROR":
                    return jsonify({"message": "Robokassa credentials not configured"}), 500
                
                import hashlib
                signature_string = f"{robokassa_login}:{float(amount)}:{order_id}:{robokassa_password1}"
                signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest()
                
                payment_url = f"https://auth.robokassa.ru/Merchant/Index.aspx?MerchantLogin={robokassa_login}&OutSum={float(amount)}&InvId={order_id}&SignatureValue={signature}&Description=Пополнение баланса&Culture=ru&IsTest=0"
                payment_system_id = order_id
            
            elif payment_provider == 'freekassa':
                freekassa_shop_id = decrypt_key(s.freekassa_shop_id) if s else None
                freekassa_secret = decrypt_key(s.freekassa_secret) if s else None
                if not freekassa_shop_id or not freekassa_secret or freekassa_shop_id == "DECRYPTION_ERROR" or freekassa_secret == "DECRYPTION_ERROR":
                    return jsonify({"message": "Freekassa credentials not configured"}), 500
                
                # Freekassa поддерживает валюты: RUB, USD, EUR, UAH, KZT
                freekassa_currency_map = {"RUB": "RUB", "USD": "USD", "EUR": "EUR", "UAH": "UAH", "KZT": "KZT"}
                freekassa_currency = freekassa_currency_map.get(cp_currency, "RUB")
                
                import hashlib
                signature_string = f"{freekassa_shop_id}:{float(amount)}:{freekassa_secret}:{order_id}"
                signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest()
                
                payment_url = f"https://pay.freekassa.ru/?m={freekassa_shop_id}&oa={float(amount)}&o={order_id}&s={signature}&currency={freekassa_currency}"
                payment_system_id = order_id
            
            elif payment_provider == 'telegram_stars':
                # Telegram Stars API
                bot_token = decrypt_key(s.telegram_bot_token) if s else None
                if not bot_token or bot_token == "DECRYPTION_ERROR":
                    return jsonify({"message": "Telegram Bot Token not configured"}), 500
                
                # Конвертируем сумму в Telegram Stars (примерно 1 USD = 100 Stars)
                # Для других валют используем примерный курс
                stars_amount = int(float(amount) * 100)  # Предполагаем, что суммы в USD
                if cp_currency == 'UAH':
                    # 1 UAH ≈ 0.027 USD, значит примерно 2.7 Stars за 1 UAH
                    stars_amount = int(float(amount) * 2.7)
                elif cp_currency == 'RUB':
                    # 1 RUB ≈ 0.011 USD, значит примерно 1.1 Stars за 1 RUB
                    stars_amount = int(float(amount) * 1.1)
                elif cp_currency == 'USD':
                    # 1 USD = 100 Stars (примерно)
                    stars_amount = int(float(amount) * 100)
                
                # Минимальная сумма - 1 звезда
                if stars_amount < 1:
                    stars_amount = 1
                
                # Создаем инвойс через Telegram Bot API
                invoice_payload = {
                    "title": "Пополнение баланса StealthNET",
                    "description": f"Пополнение баланса на сумму {float(amount):.2f} {cp_currency}",
                    "payload": order_id,
                    "provider_token": "",  # Пустой для Stars
                    "currency": "XTR",  # XTR - валюта Telegram Stars
                    "prices": [
                        {
                            "label": f"Пополнение баланса {float(amount):.2f} {cp_currency}",
                            "amount": stars_amount
                        }
                    ]
                }
                
                headers = {
                    "Content-Type": "application/json"
                }
                
                # Создаем ссылку на инвойс
                resp = requests.post(
                    f"https://api.telegram.org/bot{bot_token}/createInvoiceLink",
                    json=invoice_payload,
                    headers=headers,
                    timeout=10
                )
                if resp.ok:
                    data = resp.json()
                    if data.get('ok'):
                        payment_url = data.get('result')
                        payment_system_id = order_id
                        print(f"Telegram Stars: Invoice link created for balance topup, order_id={order_id}, user_id={user.id}, amount={amount} {cp_currency}")
                    else:
                        print(f"Telegram Stars Error for balance topup: {data.get('description')}")
                else:
                    print(f"Telegram Stars API Error: {resp.status_code} - {resp.text}")
            
            else:
                return jsonify({"message": f"Неподдерживаемый способ оплаты: {payment_provider}"}), 400
            
            if not payment_url:
                return jsonify({"message": "Не удалось создать платеж"}), 500
            
            # Создаем запись о платеже
            currency_code_map = {"uah": "UAH", "rub": "RUB", "usd": "USD"}
            new_p = Payment(
                order_id=order_id,
                user_id=user.id,
                tariff_id=None,
                status='PENDING',
                amount=float(amount),
                currency=currency_code_map.get(currency.lower(), "UAH"),
                payment_system_id=str(payment_system_id) if payment_system_id else order_id,  # Используем order_id как fallback
                payment_provider=payment_provider
            )
            db.session.add(new_p)
            try:
                db.session.commit()
                print(f"Telegram Stars: Payment record created for balance topup, payment_id={new_p.id}, order_id={order_id}, user_id={user.id}, amount={float(amount)} {currency_code_map.get(currency.lower(), 'UAH')}")
            except Exception as e:
                print(f"Telegram Stars: Error creating payment record: {e}")
                db.session.rollback()
                return jsonify({"message": "Ошибка создания платежа"}), 500
            
            return jsonify({"payment_url": payment_url, "order_id": order_id}), 200
        
        # Обычная покупка тарифа
        # 🛡️ TYPE CHECK
        if not isinstance(tid, int): return jsonify({"message": "Invalid ID"}), 400
        
        promo_code_str = request.json.get('promo_code', '').strip().upper() if request.json.get('promo_code') else None
        payment_provider = request.json.get('payment_provider', 'crystalpay')  # По умолчанию CrystalPay
        
        t = db.session.get(Tariff, tid)
        if not t: return jsonify({"message": "Not found"}), 404
        
        price_map = {"uah": {"a": t.price_uah, "c": "UAH"}, "rub": {"a": t.price_rub, "c": "RUB"}, "usd": {"a": t.price_usd, "c": "USD"}}
        info = price_map.get(user.preferred_currency, price_map['uah'])
        
        # Применяем промокод со скидкой, если указан
        promo_code_obj = None
        final_amount = info['a']
        if promo_code_str:
            promo = PromoCode.query.filter_by(code=promo_code_str).first()
            if not promo:
                return jsonify({"message": "Неверный промокод"}), 400
            if promo.uses_left <= 0:
                return jsonify({"message": "Промокод больше не действителен"}), 400
            if promo.promo_type == 'PERCENT':
                # Применяем процентную скидку
                discount = (promo.value / 100.0) * final_amount
                final_amount = final_amount - discount
                if final_amount < 0:
                    final_amount = 0
                promo_code_obj = promo
            elif promo.promo_type == 'DAYS':
                # Для бесплатных дней промокод применяется отдельно через activate-promocode
                return jsonify({"message": "Промокод на бесплатные дни активируется отдельно"}), 400
        
        s = PaymentSetting.query.first()
        order_id = f"u{user.id}-t{t.id}-{int(datetime.now().timestamp())}"
        payment_url = None
        payment_system_id = None
        
        if payment_provider == 'heleket':
            # Heleket API
            heleket_key = decrypt_key(s.heleket_api_key)
            if not heleket_key or heleket_key == "DECRYPTION_ERROR":
                return jsonify({"message": "Heleket API key not configured"}), 500
            
            # Heleket поддерживает USD напрямую, для других валют используем конвертацию через to_currency
            # Если валюта USD - используем USD, иначе конвертируем в USDT
            heleket_currency = info['c']  # Используем исходную валюту
            to_currency = None
            
            if info['c'] == 'USD':
                # USD поддерживается напрямую
                heleket_currency = "USD"
            else:
                # Для UAH и RUB конвертируем в USDT
                heleket_currency = "USD"  # Указываем исходную валюту
                to_currency = "USDT"  # Конвертируем в USDT
            
            payload = {
                "amount": f"{final_amount:.2f}",
                "currency": heleket_currency,
                "order_id": order_id,
                "url_return": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                "url_callback": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/heleket"
            }
            
            # Добавляем to_currency если нужна конвертация
            if to_currency:
                payload["to_currency"] = to_currency
            
            headers = {
                "Authorization": f"Bearer {heleket_key}",
                "Content-Type": "application/json"
            }
            
            resp = requests.post("https://api.heleket.com/v1/payment", json=payload, headers=headers).json()
            if resp.get('state') != 0 or not resp.get('result'):
                error_msg = resp.get('message', 'Payment Provider Error')
                print(f"Heleket Error: {error_msg}")
                return jsonify({"message": error_msg}), 500
            
            result = resp.get('result', {})
            payment_url = result.get('url')
            payment_system_id = result.get('uuid')
            
            if not payment_url:
                return jsonify({"message": "Failed to create payment"}), 500
            
        elif payment_provider == 'telegram_stars':
            # Telegram Stars API
            bot_token = decrypt_key(s.telegram_bot_token)
            if not bot_token or bot_token == "DECRYPTION_ERROR":
                return jsonify({"message": "Telegram Bot Token not configured"}), 500
            
            # Конвертируем сумму в Telegram Stars (примерно 1 USD = 100 Stars)
            # Для других валют используем примерный курс
            stars_amount = int(final_amount * 100)  # Предполагаем, что суммы в USD, UAH, RUB уже конвертированы
            if info['c'] == 'UAH':
                # 1 UAH ≈ 0.027 USD, значит примерно 2.7 Stars за 1 UAH
                stars_amount = int(final_amount * 2.7)
            elif info['c'] == 'RUB':
                # 1 RUB ≈ 0.011 USD, значит примерно 1.1 Stars за 1 RUB
                stars_amount = int(final_amount * 1.1)
            elif info['c'] == 'USD':
                # 1 USD = 100 Stars (примерно)
                stars_amount = int(final_amount * 100)
            
            # Минимальная сумма - 1 звезда
            if stars_amount < 1:
                stars_amount = 1
            
            # Создаем инвойс через Telegram Bot API
            invoice_payload = {
                "title": f"Подписка StealthNET - {t.name}",
                "description": f"Подписка на {t.duration_days} дней",
                "payload": order_id,
                "provider_token": "",  # Пустой для Stars
                "currency": "XTR",  # XTR - валюта Telegram Stars
                "prices": [
                    {
                        "label": f"Подписка {t.duration_days} дней",
                        "amount": stars_amount
                    }
                ]
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            
            # Создаем ссылку на инвойс
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/createInvoiceLink",
                json=invoice_payload,
                headers=headers
            ).json()
            
            if not resp.get('ok'):
                error_msg = resp.get('description', 'Telegram Bot API Error')
                print(f"Telegram Stars Error: {error_msg}")
                return jsonify({"message": error_msg}), 500
            
            payment_url = resp.get('result')
            payment_system_id = order_id  # Используем order_id как идентификатор
            
            if not payment_url:
                return jsonify({"message": "Failed to create payment"}), 500
        
        elif payment_provider == 'yookassa':
            # YooKassa API
            shop_id = decrypt_key(s.yookassa_shop_id)
            secret_key = decrypt_key(s.yookassa_secret_key)
            
            if not shop_id or not secret_key or shop_id == "DECRYPTION_ERROR" or secret_key == "DECRYPTION_ERROR":
                return jsonify({"message": "YooKassa credentials not configured"}), 500
            
            # YooKassa поддерживает только RUB
            if info['c'] != 'RUB':
                return jsonify({"message": "YooKassa supports only RUB currency"}), 400
            
            # Генерируем ключ идемпотентности (любое случайное значение)
            import uuid
            idempotence_key = str(uuid.uuid4())
            
            # Формируем payload для создания платежа
            payload = {
                "amount": {
                    "value": f"{final_amount:.2f}",
                    "currency": "RUB"
                },
                "capture": True,  # Автоматически списываем деньги после оплаты
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
                },
                "description": f"Подписка StealthNET - {t.name} ({t.duration_days} дней)",
                "metadata": {
                    "order_id": order_id,
                    "user_id": str(user.id),
                    "tariff_id": str(t.id)
                }
            }
            
            # Аутентификация через Basic Auth
            import base64
            auth_string = f"{shop_id}:{secret_key}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Idempotence-Key": idempotence_key,
                "Content-Type": "application/json"
            }
            
            try:
                resp = requests.post(
                    "https://api.yookassa.ru/v3/payments",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                payment_data = resp.json()
                
                if payment_data.get('status') != 'pending':
                    error_msg = payment_data.get('description', 'YooKassa payment creation failed')
                    print(f"YooKassa Error: {error_msg}")
                    return jsonify({"message": error_msg}), 500
                
                confirmation = payment_data.get('confirmation', {})
                payment_url = confirmation.get('confirmation_url')
                payment_system_id = payment_data.get('id')  # ID платежа в YooKassa
                
                if not payment_url:
                    return jsonify({"message": "Failed to get payment URL from YooKassa"}), 500
                    
            except requests.exceptions.RequestException as e:
                print(f"YooKassa API Error: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('description', str(e))
                    except:
                        error_msg = str(e)
                else:
                    error_msg = str(e)
                return jsonify({"message": f"YooKassa API Error: {error_msg}"}), 500
        
        elif payment_provider == 'platega':
            # Platega API
            import uuid
            api_key = decrypt_key(s.platega_api_key)
            merchant_id = decrypt_key(s.platega_merchant_id)
            
            if not api_key or not merchant_id or api_key == "DECRYPTION_ERROR" or merchant_id == "DECRYPTION_ERROR":
                return jsonify({"message": "Platega credentials not configured"}), 500
            
            # Генерируем UUID для транзакции
            transaction_uuid = str(uuid.uuid4())
            
            # Формируем payload согласно документации Platega API
            payload = {
                "paymentMethod": 2,  # 2 - СБП/QR, 10 - CardRu, 12 - International
                "id": transaction_uuid,
                "paymentDetails": {
                    "amount": int(final_amount),
                    "currency": info['c']
                },
                "description": f"Payment for order {transaction_uuid}",
                "return": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                "failedUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
            }
            
            # Заголовки согласно документации Platega API
            headers = {
                "Content-Type": "application/json",
                "X-MerchantId": merchant_id,
                "X-Secret": api_key
            }
            
            try:
                resp = requests.post(
                    "https://app.platega.io/transaction/process",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                payment_data = resp.json()
                
                payment_url = payment_data.get('redirect')
                payment_system_id = payment_data.get('transactionId') or transaction_uuid
                
                if not payment_url:
                    error_msg = payment_data.get('message', 'Failed to get payment URL from Platega')
                    print(f"Platega Error: {error_msg}")
                    return jsonify({"message": error_msg}), 500
                    
            except requests.exceptions.ConnectionError as e:
                # Обработка DNS ошибок и проблем с подключением
                error_msg = str(e)
                if "Name or service not known" in error_msg or "Failed to resolve" in error_msg:
                    print(f"Platega API DNS Error: {e}")
                    return jsonify({
                        "message": "Platega API недоступен. Проверьте настройки DNS или свяжитесь с поддержкой."
                    }), 503  # Service Unavailable
                else:
                    print(f"Platega API Connection Error: {e}")
                    return jsonify({
                        "message": "Не удалось подключиться к Platega API. Проверьте интернет-соединение."
                    }), 503
            except requests.exceptions.RequestException as e:
                print(f"Platega API Error: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message', str(e))
                    except:
                        error_msg = str(e)
                else:
                    error_msg = str(e)
                return jsonify({"message": f"Platega API Error: {error_msg}"}), 500
        
        elif payment_provider == 'mulenpay':
            # Mulenpay API
            api_key = decrypt_key(s.mulenpay_api_key)
            secret_key = decrypt_key(s.mulenpay_secret_key)
            shop_id = decrypt_key(s.mulenpay_shop_id)
            
            if not api_key or not secret_key or not shop_id or api_key == "DECRYPTION_ERROR" or secret_key == "DECRYPTION_ERROR" or shop_id == "DECRYPTION_ERROR":
                return jsonify({"message": "Mulenpay credentials not configured"}), 500
            
            # Конвертируем валюту в формат Mulenpay (rub, uah, usd)
            currency_map = {
                'RUB': 'rub',
                'UAH': 'uah',
                'USD': 'usd'
            }
            mulenpay_currency = currency_map.get(info['c'], info['c'].lower())
            
            # Формируем payload для создания платежа
            # shopId может быть числом или строкой, пробуем преобразовать в int если возможно
            try:
                shop_id_int = int(shop_id)
            except (ValueError, TypeError):
                shop_id_int = shop_id
            
            payload = {
                "currency": mulenpay_currency,
                "amount": str(final_amount),
                "uuid": order_id,
                "shopId": shop_id_int,
                "description": f"Подписка StealthNET - {t.name} ({t.duration_days} дней)",
                "subscribe": None,
                "holdTime": None
            }
            
            # Mulenpay использует Basic Auth с api_key:secret_key
            import base64
            auth_string = f"{api_key}:{secret_key}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/json"
            }
            
            try:
                resp = requests.post(
                    "https://api.mulenpay.ru/v2/payments",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                payment_data = resp.json()
                
                # Mulenpay возвращает URL для оплаты в поле "url" или "payment_url"
                payment_url = payment_data.get('url') or payment_data.get('payment_url') or payment_data.get('redirect')
                payment_system_id = payment_data.get('id') or payment_data.get('payment_id') or order_id
                
                if not payment_url:
                    error_msg = payment_data.get('message') or payment_data.get('error') or 'Failed to get payment URL from Mulenpay'
                    print(f"Mulenpay Error: {error_msg}")
                    return jsonify({"message": error_msg}), 500
                    
            except requests.exceptions.RequestException as e:
                print(f"Mulenpay API Error: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('error') or str(e)
                    except:
                        error_msg = str(e)
                else:
                    error_msg = str(e)
                return jsonify({"message": f"Mulenpay API Error: {error_msg}"}), 500
        
        elif payment_provider == 'monobank':
            # Monobank API
            monobank_token = decrypt_key(s.monobank_token) if s else None
            if not monobank_token or monobank_token == "DECRYPTION_ERROR":
                return jsonify({"message": "Monobank token not configured"}), 500
            
            # Monobank принимает сумму в копейках (минимальных единицах)
            amount_in_kopecks = int(final_amount * 100)
            if info['c'] == 'UAH':
                amount_in_kopecks = int(final_amount * 100)  # UAH в копейках
            elif info['c'] == 'RUB':
                amount_in_kopecks = int(final_amount * 100)  # RUB в копейках
            elif info['c'] == 'USD':
                amount_in_kopecks = int(final_amount * 100)  # USD в центах
            
            # Код валюты по ISO 4217: 980 = UAH, 643 = RUB, 840 = USD
            currency_code = 980  # По умолчанию UAH
            if info['c'] == 'RUB':
                currency_code = 643
            elif info['c'] == 'USD':
                currency_code = 840
            
            # Создаем инвойс через Monobank API
            payload = {
                "amount": amount_in_kopecks,
                "ccy": currency_code,
                "merchantPaymInfo": {
                    "reference": order_id,
                    "destination": f"Подписка StealthNET - {t.name} ({t.duration_days} дней)",
                    "basketOrder": [
                        {
                            "name": f"Подписка {t.name}",
                            "qty": 1,
                            "sum": amount_in_kopecks,
                            "unit": "шт"
                        }
                    ]
                },
                "redirectUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                "webHookUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/monobank",
                "validity": 86400,  # 24 часа в секундах
                "paymentType": "debit"
            }
            
            headers = {
                "X-Token": monobank_token,
                "Content-Type": "application/json"
            }
            
            try:
                resp = requests.post(
                    "https://api.monobank.ua/api/merchant/invoice/create",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                payment_data = resp.json()
                
                payment_url = payment_data.get('pageUrl')
                payment_system_id = payment_data.get('invoiceId') or order_id
                
                if not payment_url:
                    error_msg = payment_data.get('errText') or 'Failed to get payment URL from Monobank'
                    print(f"Monobank Error: {error_msg}")
                    return jsonify({"message": error_msg}), 500
                    
            except requests.exceptions.RequestException as e:
                print(f"Monobank API Error: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('errText') or error_data.get('message') or str(e)
                    except:
                        error_msg = str(e)
                else:
                    error_msg = str(e)
                return jsonify({"message": f"Monobank API Error: {error_msg}"}), 500
        
        elif payment_provider == 'btcpayserver':
            # BTCPayServer API
            btcpayserver_url = decrypt_key(s.btcpayserver_url) if s else None
            btcpayserver_api_key = decrypt_key(s.btcpayserver_api_key) if s else None
            btcpayserver_store_id = decrypt_key(s.btcpayserver_store_id) if s else None
            
            if not btcpayserver_url or not btcpayserver_api_key or not btcpayserver_store_id or btcpayserver_url == "DECRYPTION_ERROR" or btcpayserver_api_key == "DECRYPTION_ERROR" or btcpayserver_store_id == "DECRYPTION_ERROR":
                return jsonify({"message": "BTCPayServer credentials not configured"}), 500
            
            # Очищаем URL от завершающего слеша
            btcpayserver_url = btcpayserver_url.rstrip('/')
            
            # Формируем payload для создания инвойса
            invoice_currency = info['c']
            
            metadata = {
                "orderId": order_id,
                "buyerEmail": user.email if user.email else None,
                "itemDesc": f"VPN Subscription - {t.name} ({t.duration_days} days)"
            }
            
            # Добавляем checkout options с redirect URL
            checkout_options = {
                "redirectURL": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
            }
            
            payload = {
                "amount": f"{final_amount:.2f}",
                "currency": invoice_currency,
                "metadata": metadata,
                "checkout": checkout_options
            }
            
            invoice_url = f"{btcpayserver_url}/api/v1/stores/{btcpayserver_store_id}/invoices"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"token {btcpayserver_api_key}"
            }
            
            try:
                resp = requests.post(
                    invoice_url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                invoice_data = resp.json()
                
                payment_url = invoice_data.get('checkoutLink')
                payment_system_id = invoice_data.get('id')
                
                if not payment_url:
                    return jsonify({"message": "Failed to create payment"}), 500
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('error') or str(e)
                    except:
                        pass
                return jsonify({"message": f"BTCPayServer API Error: {error_msg}"}), 500
        
        elif payment_provider == 'tribute':
            # Tribute API
            tribute_api_key = decrypt_key(s.tribute_api_key) if s else None
            
            if not tribute_api_key or tribute_api_key == "DECRYPTION_ERROR":
                return jsonify({"message": "Tribute API key not configured"}), 500
            
            # Конвертируем валюту в формат Tribute (rub, eur)
            currency_map = {
                'RUB': 'rub',
                'UAH': 'rub',  # UAH не поддерживается, используем RUB
                'USD': 'eur'   # USD не поддерживается, используем EUR
            }
            tribute_currency = currency_map.get(info['c'], 'rub')
            
            # Конвертируем сумму в минимальные единицы (копейки/центы)
            amount_in_cents = int(final_amount * 100)
            
            payload = {
                "amount": amount_in_cents,
                "currency": tribute_currency,
                "title": f"VPN Subscription - {t.name}"[:100],
                "description": f"VPN subscription for {t.duration_days} days"[:300],
                "successUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                "failUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
            }
            
            if user.email:
                payload["email"] = user.email
            
            order_url = "https://tribute.tg/api/v1/shop/orders"
            
            headers = {
                "Content-Type": "application/json",
                "Api-Key": tribute_api_key
            }
            
            try:
                resp = requests.post(
                    order_url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                order_data = resp.json()
                
                payment_url = order_data.get('paymentUrl')
                payment_system_id = order_data.get('uuid')
                
                if not payment_url:
                    return jsonify({"message": "Failed to create payment"}), 500
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('error') or str(e)
                    except:
                        pass
                return jsonify({"message": f"Tribute API Error: {error_msg}"}), 500
        
        elif payment_provider == 'robokassa':
            # Robokassa API
            robokassa_login = decrypt_key(s.robokassa_merchant_login) if s else None
            robokassa_password1 = decrypt_key(s.robokassa_password1) if s else None
            
            if not robokassa_login or not robokassa_password1 or robokassa_login == "DECRYPTION_ERROR" or robokassa_password1 == "DECRYPTION_ERROR":
                return jsonify({"message": "Robokassa credentials not configured"}), 500
            
            # Robokassa работает только с RUB
            if info['c'] not in ['RUB', 'rub']:
                robokassa_amount = final_amount
            else:
                robokassa_amount = final_amount
            
            description = f"VPN Subscription - {t.name} ({t.duration_days} days)"[:100]
            
            # Создаем MD5 подпись: MD5(MerchantLogin:OutSum:InvId:Password#1)
            import hashlib
            signature_string = f"{robokassa_login}:{robokassa_amount}:{order_id}:{robokassa_password1}"
            signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest()
            
            # Формируем URL для оплаты
            import urllib.parse
            params = {
                'MerchantLogin': robokassa_login,
                'OutSum': str(robokassa_amount),
                'InvId': order_id,
                'Description': description,
                'SignatureValue': signature,
                'SuccessURL': f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                'FailURL': f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
            }
            
            query_string = urllib.parse.urlencode(params)
            payment_url = f"https://auth.robokassa.ru/Merchant/Index.aspx?{query_string}"
            payment_system_id = order_id
        
        elif payment_provider == 'freekassa':
            # Freekassa API
            freekassa_shop_id = decrypt_key(s.freekassa_shop_id) if s else None
            freekassa_secret = decrypt_key(s.freekassa_secret) if s else None
            
            if not freekassa_shop_id or not freekassa_secret or freekassa_shop_id == "DECRYPTION_ERROR" or freekassa_secret == "DECRYPTION_ERROR":
                return jsonify({"message": "Freekassa credentials not configured"}), 500
            
            # Freekassa поддерживает валюты: RUB, USD, EUR, UAH, KZT
            currency_map = {
                'RUB': 'RUB',
                'UAH': 'UAH',
                'USD': 'USD',
                'EUR': 'EUR',
                'KZT': 'KZT'
            }
            freekassa_currency = currency_map.get(info['c'], 'RUB')
            
            # Генерируем nonce
            import time
            nonce = int(time.time() * 1000)
            
            # Формируем подпись: MD5(shopId + amount + currency + paymentId + secret)
            import hashlib
            signature_string = f"{freekassa_shop_id}{final_amount}{freekassa_currency}{order_id}{freekassa_secret}"
            signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest()
            
            api_params = {
                'shopId': freekassa_shop_id,
                'nonce': nonce,
                'signature': signature,
                'paymentId': order_id,
                'amount': str(final_amount),
                'currency': freekassa_currency
            }
            
            api_url = "https://api.fk.life/v1/orders/create"
            
            try:
                resp = requests.post(
                    api_url,
                    params=api_params,
                    timeout=30
                )
                resp.raise_for_status()
                order_data = resp.json()
                
                if order_data.get('type') == 'success':
                    payment_url = order_data.get('data', {}).get('url')
                    payment_system_id = order_data.get('data', {}).get('orderId') or order_id
                    
                    if not payment_url:
                        return jsonify({"message": "Failed to create payment"}), 500
                else:
                    return jsonify({"message": "Failed to create payment"}), 500
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('error') or str(e)
                    except:
                        pass
                return jsonify({"message": f"Freekassa API Error: {error_msg}"}), 500
        
        elif payment_provider == 'urlpay':
            # UrlPay API (аналогично Mulenpay)
            api_key = decrypt_key(s.urlpay_api_key)
            secret_key = decrypt_key(s.urlpay_secret_key)
            shop_id = decrypt_key(s.urlpay_shop_id)
            
            if not api_key or not secret_key or not shop_id or api_key == "DECRYPTION_ERROR" or secret_key == "DECRYPTION_ERROR" or shop_id == "DECRYPTION_ERROR":
                return jsonify({"message": "UrlPay credentials not configured"}), 500
            
            # Конвертируем валюту в формат UrlPay (rub, uah, usd)
            currency_map = {
                'RUB': 'rub',
                'UAH': 'uah',
                'USD': 'usd'
            }
            urlpay_currency = currency_map.get(info['c'], info['c'].lower())
            
            # Формируем payload для создания платежа
            # shopId может быть числом или строкой, пробуем преобразовать в int если возможно
            try:
                shop_id_int = int(shop_id)
            except (ValueError, TypeError):
                shop_id_int = shop_id
            
            payload = {
                "currency": urlpay_currency,
                "amount": str(final_amount),
                "uuid": order_id,
                "shopId": shop_id_int,
                "description": f"Подписка StealthNET - {t.name} ({t.duration_days} дней)",
                "subscribe": None,
                "holdTime": None
            }
            
            # UrlPay использует Basic Auth с api_key:secret_key
            import base64
            auth_string = f"{api_key}:{secret_key}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/json"
            }
            
            try:
                resp = requests.post(
                    "https://api.urlpay.io/v2/payments",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                payment_data = resp.json()
                
                # UrlPay возвращает URL для оплаты в поле "url" или "payment_url"
                payment_url = payment_data.get('url') or payment_data.get('payment_url') or payment_data.get('redirect')
                payment_system_id = payment_data.get('id') or payment_data.get('payment_id') or order_id
                
                if not payment_url:
                    error_msg = payment_data.get('message') or payment_data.get('error') or 'Failed to get payment URL from UrlPay'
                    print(f"UrlPay Error: {error_msg}")
                    return jsonify({"message": error_msg}), 500
                    
            except requests.exceptions.RequestException as e:
                print(f"UrlPay API Error: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('error') or str(e)
                    except:
                        error_msg = str(e)
                else:
                    error_msg = str(e)
                return jsonify({"message": f"UrlPay API Error: {error_msg}"}), 500
        
        else:
            # CrystalPay API (по умолчанию)
            login = decrypt_key(s.crystalpay_api_key)
            secret = decrypt_key(s.crystalpay_api_secret)
            
            if not login or not secret or login == "DECRYPTION_ERROR" or secret == "DECRYPTION_ERROR":
                return jsonify({"message": "CrystalPay credentials not configured"}), 500
            
            payload = {
                "auth_login": login, "auth_secret": secret,
                "amount": f"{final_amount:.2f}", "type": "purchase", "currency": info['c'],
                "lifetime": 60, "extra": order_id, 
                "callback_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/crystalpay",
                "redirect_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
            }
            
            resp = requests.post("https://api.crystalpay.io/v3/invoice/create/", json=payload).json()
            if resp.get('errors'): 
                print(f"CrystalPay Error: {resp.get('errors')}")
                return jsonify({"message": "Payment Provider Error"}), 500
            
            payment_url = resp.get('url')
            payment_system_id = resp.get('id')
            
            if not payment_url:
                return jsonify({"message": "Failed to create payment"}), 500
        
        # Проверяем, что payment_url был установлен
        if not payment_url:
            return jsonify({"message": "Ошибка создания платежа"}), 500
        
        new_p = Payment(
            order_id=order_id, 
            user_id=user.id, 
            tariff_id=t.id, 
            status='PENDING', 
            amount=final_amount, 
            currency=info['c'], 
            payment_system_id=payment_system_id,
            payment_provider=payment_provider,
            promo_code_id=promo_code_obj.id if promo_code_obj else None
        )
        db.session.add(new_p); db.session.commit()
        return jsonify({"payment_url": payment_url}), 200
    except Exception as e: 
        print(f"Payment Exception: {e}")
        return jsonify({"message": "Internal Error"}), 500

@app.route('/api/webhook/crystalpay', methods=['POST'])
def crystal_webhook():
    d = request.json
    if d.get('state') != 'payed': return jsonify({"error": False}), 200
    p = Payment.query.filter_by(order_id=d.get('extra')).first()
    if not p or p.status == 'PAID': return jsonify({"error": False}), 200
    
    u = db.session.get(User, p.user_id)
    if not u: return jsonify({"error": False}), 200
    
    # Если это пополнение баланса (tariff_id == None)
    if p.tariff_id is None:
        # Пополняем баланс пользователя
        # Конвертируем сумму пополнения в USD перед добавлением к балансу
        current_balance_usd = float(u.balance) if u.balance else 0.0
        amount_usd = convert_to_usd(p.amount, p.currency)
        u.balance = current_balance_usd + amount_usd
        p.status = 'PAID'
        db.session.commit()
        
        # Очищаем кэш
        cache.delete(f'live_data_{u.remnawave_uuid}')
        cache.delete('all_live_users_map')
        
        return jsonify({"error": False}), 200
    
    # Обычная покупка тарифа
    t = db.session.get(Tariff, p.tariff_id)
    if not t: return jsonify({"error": False}), 200
    
    h, c = get_remnawave_headers()
    live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h, cookies=c).json().get('response', {})
    curr_exp = parse_iso_datetime(live.get('expireAt'))
    new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
    
    # Используем сквад из тарифа, если указан, иначе дефолтный
    squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
    
    # Формируем payload для обновления пользователя
    patch_payload = {
        "uuid": u.remnawave_uuid,
        "expireAt": new_exp.isoformat(),
        "activeInternalSquads": [squad_id]
    }
    
    # Добавляем лимит трафика, если указан в тарифе
    if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
        patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
        patch_payload["trafficLimitStrategy"] = "NO_RESET"
    
    h, c = get_remnawave_headers({"Content-Type": "application/json"})
    patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
    if not patch_resp.ok:
        print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
        return jsonify({"error": False}), 200  # Все равно возвращаем успех, чтобы вебхук не повторялся
    
    # Списываем использование промокода, если он был использован
    if p.promo_code_id:
        promo = db.session.get(PromoCode, p.promo_code_id)
        if promo and promo.uses_left > 0:
            promo.uses_left -= 1
    
    p.status = 'PAID'
    db.session.commit()
    cache.delete(f'live_data_{u.remnawave_uuid}')
    cache.delete(f'nodes_{u.remnawave_uuid}')  # Очищаем кэш серверов при изменении сквада
    
    # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
    # Это не блокирует ответ вебхука, так как синхронизация может занимать много времени
    if BOT_API_URL and BOT_API_TOKEN:
        app_context = app.app_context()
        import threading
        sync_thread = threading.Thread(
            target=sync_subscription_to_bot_in_background,
            args=(app_context, u.remnawave_uuid),
            daemon=True
        )
        sync_thread.start()
        print(f"Started background sync thread for user {u.remnawave_uuid}")
    
    return jsonify({"error": False}), 200

@app.route('/api/webhook/heleket', methods=['POST'])
def heleket_webhook():
    d = request.json
    # Heleket отправляет данные в формате: {"state": 0, "result": {...}}
    # Статус платежа: "paid" означает оплачен
    result = d.get('result', {})
    if not result:
        return jsonify({"error": False}), 200
    
    payment_status = result.get('payment_status', '')
    order_id = result.get('order_id')
    
    # Проверяем, что платеж оплачен
    if payment_status != 'paid':
        return jsonify({"error": False}), 200
    
    p = Payment.query.filter_by(order_id=order_id).first()
    if not p or p.status == 'PAID':
        return jsonify({"error": False}), 200
    
    u = db.session.get(User, p.user_id)
    t = db.session.get(Tariff, p.tariff_id)
    
    h, c = get_remnawave_headers()
    live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h, cookies=c).json().get('response', {})
    curr_exp = parse_iso_datetime(live.get('expireAt'))
    new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
    
    # Используем сквад из тарифа, если указан, иначе дефолтный
    squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
    
    # Формируем payload для обновления пользователя
    patch_payload = {
        "uuid": u.remnawave_uuid,
        "expireAt": new_exp.isoformat(),
        "activeInternalSquads": [squad_id]
    }
    
    # Добавляем лимит трафика, если указан в тарифе
    if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
        patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
        patch_payload["trafficLimitStrategy"] = "NO_RESET"
    
    h, c = get_remnawave_headers({"Content-Type": "application/json"})
    patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
    if not patch_resp.ok:
        print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
        return jsonify({"error": False}), 200  # Все равно возвращаем успех, чтобы вебхук не повторялся
    
    # Списываем использование промокода, если он был использован
    if p.promo_code_id:
        promo = db.session.get(PromoCode, p.promo_code_id)
        if promo and promo.uses_left > 0:
            promo.uses_left -= 1
    
    p.status = 'PAID'
    db.session.commit()
    cache.delete(f'live_data_{u.remnawave_uuid}')
    cache.delete(f'nodes_{u.remnawave_uuid}')  # Очищаем кэш серверов при изменении сквада
    
    # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
    # Это не блокирует ответ вебхука, так как синхронизация может занимать много времени
    if BOT_API_URL and BOT_API_TOKEN:
        app_context = app.app_context()
        import threading
        sync_thread = threading.Thread(
            target=sync_subscription_to_bot_in_background,
            args=(app_context, u.remnawave_uuid),
            daemon=True
        )
        sync_thread.start()
        print(f"Started background sync thread for user {u.remnawave_uuid}")
        try:
            bot_api_url = BOT_API_URL.rstrip('/')
            # Обновляем подписку пользователя в боте, передавая новые данные из RemnaWave
            update_url = f"{bot_api_url}/users/{u.telegram_id}"
            update_headers = {"X-API-Key": BOT_API_TOKEN, "Content-Type": "application/json"}
            
            # Получаем актуальные данные из RemnaWave для передачи в бот
            live_after_update = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h, timeout=5)
            if live_after_update.ok:
                live_data = live_after_update.json().get('response', {})
                # Формируем payload для обновления в боте
                bot_update_payload = {
                    "remnawave_uuid": u.remnawave_uuid,
                    "expire_at": live_data.get('expireAt'),
                    "subscription": {
                        "url": live_data.get('subscription_url', ''),
                        "expire_at": live_data.get('expireAt')
                    }
                }
                
                print(f"Updating user subscription in bot for telegram_id {u.telegram_id}...")
                bot_update_response = requests.patch(update_url, headers=update_headers, json=bot_update_payload, timeout=10)
                if bot_update_response.status_code == 200:
                    print(f"✓ User subscription updated in bot for telegram_id {u.telegram_id}")
                elif bot_update_response.status_code == 404:
                    print(f"⚠️ User with telegram_id {u.telegram_id} not found in bot, skipping update")
                else:
                    print(f"⚠️ Failed to update user in bot: Status {bot_update_response.status_code}")
                    print(f"   Response: {bot_update_response.text[:200]}")
            else:
                print(f"⚠️ Failed to get updated user data from RemnaWave for bot sync")
        except Exception as e:
            print(f"⚠️ Error updating user subscription in bot: {e}")
            import traceback
            traceback.print_exc()
    elif BOT_API_URL and BOT_API_TOKEN and not u.telegram_id:
        print(f"⚠️ User {u.remnawave_uuid} has no telegram_id, cannot sync to bot")
    else:
        print(f"⚠️ Bot API not configured (BOT_API_URL or BOT_API_TOKEN missing), skipping sync")
    
    return jsonify({"error": False}), 200

@app.route('/api/admin/telegram-webhook-status', methods=['GET'])
@admin_required
def telegram_webhook_status(current_admin):
    """Проверка статуса webhook для Telegram бота"""
    try:
        s = PaymentSetting.query.first()
        bot_token = decrypt_key(s.telegram_bot_token) if s else None
        
        if not bot_token or bot_token == "DECRYPTION_ERROR":
            return jsonify({"error": "Bot token not configured"}), 400
        
        # Получаем информацию о webhook
        resp = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getWebhookInfo",
            timeout=5
        ).json()
        
        if resp.get('ok'):
            webhook_info = resp.get('result', {})
            return jsonify({
                "url": webhook_info.get('url'),
                "has_custom_certificate": webhook_info.get('has_custom_certificate', False),
                "pending_update_count": webhook_info.get('pending_update_count', 0),
                "last_error_date": webhook_info.get('last_error_date'),
                "last_error_message": webhook_info.get('last_error_message'),
                "max_connections": webhook_info.get('max_connections'),
                "allowed_updates": webhook_info.get('allowed_updates', [])
            }), 200
        else:
            return jsonify({"error": resp.get('description', 'Unknown error')}), 500
            
    except Exception as e:
        print(f"Telegram webhook status error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/telegram-set-webhook', methods=['POST'])
@admin_required
def telegram_set_webhook(current_admin):
    """Настройка webhook для Telegram бота"""
    try:
        s = PaymentSetting.query.first()
        bot_token = decrypt_key(s.telegram_bot_token) if s else None
        
        if not bot_token or bot_token == "DECRYPTION_ERROR":
            return jsonify({"error": "Bot token not configured"}), 400
        
        webhook_url = f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/telegram"
        
        # Устанавливаем webhook
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/setWebhook",
            json={
                "url": webhook_url,
                "allowed_updates": ["pre_checkout_query", "message"]
            },
            timeout=5
        ).json()
        
        if resp.get('ok'):
            return jsonify({"success": True, "url": webhook_url, "message": "Webhook установлен успешно"}), 200
        else:
            return jsonify({"error": resp.get('description', 'Unknown error')}), 500
            
    except Exception as e:
        print(f"Telegram set webhook error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/webhook/yookassa', methods=['GET', 'POST'])
def yookassa_webhook():
    """Webhook для обработки уведомлений от YooKassa"""
    # YooKassa может отправлять GET запрос для проверки доступности webhook
    if request.method == 'GET':
        return jsonify({"status": "ok", "message": "YooKassa webhook is available"}), 200
    
    try:
        # YooKassa отправляет уведомления в формате JSON
        event_data = request.json
        
        # Проверяем тип события
        event_type = event_data.get('event')
        payment_object = event_data.get('object', {})
        
        # Нас интересуют только события payment.succeeded и payment.canceled
        if event_type not in ['payment.succeeded', 'payment.canceled']:
            return jsonify({"error": False}), 200
        
        payment_id = payment_object.get('id')
        payment_status = payment_object.get('status')
        metadata = payment_object.get('metadata', {})
        order_id = metadata.get('order_id')
        
        if not order_id:
            print("YooKassa webhook: order_id not found in metadata")
            return jsonify({"error": False}), 200
        
        # Находим платеж по order_id
        p = Payment.query.filter_by(order_id=order_id).first()
        if not p:
            print(f"YooKassa webhook: Payment not found for order_id {order_id}")
            return jsonify({"error": False}), 200
        
        # Если платеж уже обработан, игнорируем
        if p.status == 'PAID':
            return jsonify({"error": False}), 200
        
        # Обрабатываем только успешные платежи
        if payment_status == 'succeeded' and event_type == 'payment.succeeded':
            u = db.session.get(User, p.user_id)
            t = db.session.get(Tariff, p.tariff_id)
            
            if not u or not t:
                print(f"YooKassa webhook: User or Tariff not found for payment {order_id}")
                return jsonify({"error": False}), 200
            
            h = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
            live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h).json().get('response', {})
            curr_exp = parse_iso_datetime(live.get('expireAt'))
            new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
            
            # Используем сквад из тарифа, если указан, иначе дефолтный
            squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
            
            # Формируем payload для обновления пользователя
            patch_payload = {
                "uuid": u.remnawave_uuid,
                "expireAt": new_exp.isoformat(),
                "activeInternalSquads": [squad_id]
            }
            
            # Добавляем лимит трафика, если указан в тарифе
            if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
                patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
                patch_payload["trafficLimitStrategy"] = "NO_RESET"
            
            h, c = get_remnawave_headers({"Content-Type": "application/json"})
            patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
            if not patch_resp.ok:
                print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
                return jsonify({"error": False}), 200  # Все равно возвращаем успех, чтобы вебхук не повторялся
            
            # Списываем использование промокода, если он был использован
            if p.promo_code_id:
                promo = db.session.get(PromoCode, p.promo_code_id)
                if promo and promo.uses_left > 0:
                    promo.uses_left -= 1
            
            p.status = 'PAID'
            db.session.commit()
            cache.delete(f'live_data_{u.remnawave_uuid}')
            cache.delete(f'nodes_{u.remnawave_uuid}')
            
            # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
            if BOT_API_URL and BOT_API_TOKEN:
                app_context = app.app_context()
                import threading
                sync_thread = threading.Thread(
                    target=sync_subscription_to_bot_in_background,
                    args=(app_context, u.remnawave_uuid),
                    daemon=True
                )
                sync_thread.start()
                print(f"Started background sync thread for user {u.remnawave_uuid}")
        
        return jsonify({"error": False}), 200
        
    except Exception as e:
        print(f"YooKassa webhook error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": False}), 200  # Всегда возвращаем 200, чтобы YooKassa не повторял запрос

@app.route('/api/webhook/telegram', methods=['POST'])
def telegram_webhook():
    """Webhook для обработки платежей Telegram Stars"""
    try:
        update = request.json
        print(f"Telegram webhook received: {update}")
        if not update:
            print("Telegram webhook: Empty update received")
            return jsonify({"ok": True}), 200
        
        # Обработка PreCheckoutQuery (подтверждение оплаты)
        if 'pre_checkout_query' in update:
            pre_checkout = update['pre_checkout_query']
            order_id = pre_checkout.get('invoice_payload')
            query_id = pre_checkout.get('id')
            
            print(f"Telegram PreCheckoutQuery received: order_id={order_id}, query_id={query_id}")
            
            # Получаем Bot Token один раз
            s = PaymentSetting.query.first()
            bot_token = decrypt_key(s.telegram_bot_token) if s else None
            
            if not bot_token or bot_token == "DECRYPTION_ERROR":
                print(f"Telegram Bot Token not configured or invalid")
                return jsonify({"ok": True}), 200
            
            # Проверяем, что платеж существует и не оплачен
            p = Payment.query.filter_by(order_id=order_id).first()
            if p and p.status == 'PENDING':
                # Подтверждаем оплату
                try:
                    answer_resp = requests.post(
                        f"https://api.telegram.org/bot{bot_token}/answerPreCheckoutQuery",
                        json={"pre_checkout_query_id": query_id, "ok": True},
                        timeout=5
                    )
                    answer_data = answer_resp.json()
                    if answer_data.get('ok'):
                        print(f"Telegram PreCheckoutQuery confirmed successfully for order_id={order_id}")
                    else:
                        print(f"Telegram answerPreCheckoutQuery error: {answer_data}")
                except Exception as e:
                    print(f"Telegram answerPreCheckoutQuery exception: {e}")
            else:
                error_msg = "Payment not found" if not p else "Payment already processed"
                print(f"Telegram PreCheckoutQuery: {error_msg}. order_id={order_id}")
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{bot_token}/answerPreCheckoutQuery",
                        json={
                            "pre_checkout_query_id": query_id,
                            "ok": False,
                            "error_message": error_msg
                        },
                        timeout=5
                    )
                except Exception as e:
                    print(f"Telegram answerPreCheckoutQuery (error) exception: {e}")
            
            return jsonify({"ok": True}), 200
        
        # Обработка успешного платежа
        if 'message' in update:
            message = update['message']
            if 'successful_payment' in message:
                successful_payment = message['successful_payment']
                order_id = successful_payment.get('invoice_payload')
                
                print(f"Telegram successful payment received: order_id={order_id}")
                
                p = Payment.query.filter_by(order_id=order_id).first()
                if not p:
                    print(f"Telegram successful payment: Payment not found for order_id={order_id}")
                    # Попробуем найти по payment_system_id (может быть использован order_id)
                    p = Payment.query.filter_by(payment_system_id=order_id).first()
                    if not p:
                        print(f"Telegram successful payment: Payment not found by payment_system_id either: {order_id}")
                        return jsonify({"ok": True}), 200
                    else:
                        print(f"Telegram successful payment: Found payment by payment_system_id: {p.id}, order_id={p.order_id}")
                
                if p.status == 'PAID':
                    print(f"Telegram successful payment: Payment already paid for order_id={order_id}, payment_id={p.id}")
                    return jsonify({"ok": True}), 200
                
                u = db.session.get(User, p.user_id)
                if not u:
                    print(f"Telegram successful payment: User not found for payment {p.id}, user_id={p.user_id}")
                    return jsonify({"ok": True}), 200
                
                print(f"Telegram successful payment: Processing payment {p.id}, user_id={u.id}, tariff_id={p.tariff_id}, amount={p.amount}, currency={p.currency}")
                
                # Если это пополнение баланса (tariff_id == None)
                if p.tariff_id is None:
                    # Пополняем баланс пользователя
                    # Конвертируем сумму пополнения в USD перед добавлением к балансу
                    current_balance_usd = float(u.balance) if u.balance else 0.0
                    amount_usd = convert_to_usd(p.amount, p.currency)
                    new_balance = current_balance_usd + amount_usd
                    u.balance = new_balance
                    p.status = 'PAID'
                    
                    try:
                        db.session.commit()
                        print(f"Telegram Stars: Balance top-up successful for user {u.id} (email: {u.email}), amount: {p.amount} {p.currency} = {amount_usd} USD, old balance: {current_balance_usd}, new balance: {new_balance}")
                    except Exception as e:
                        print(f"Telegram Stars: Error committing balance top-up: {e}")
                        db.session.rollback()
                        return jsonify({"ok": True}), 200
                    
                    # Очищаем кэш
                    cache.delete(f'live_data_{u.remnawave_uuid}')
                    cache.delete('all_live_users_map')
                    
                    return jsonify({"ok": True}), 200
                
                # Обычная покупка тарифа
                t = db.session.get(Tariff, p.tariff_id)
                if not t:
                    print(f"Telegram successful payment: Tariff not found for payment {p.order_id}")
                    return jsonify({"ok": True}), 200
                
                h = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
                live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h).json().get('response', {})
                curr_exp = datetime.fromisoformat(live.get('expireAt'))
                new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
                
                # Используем сквад из тарифа, если указан, иначе дефолтный
                squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
                
                # Формируем payload для обновления пользователя
                patch_payload = {
                    "uuid": u.remnawave_uuid,
                    "expireAt": new_exp.isoformat(),
                    "activeInternalSquads": [squad_id]
                }
                
                # Добавляем лимит трафика, если указан в тарифе
                if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
                    patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
                    patch_payload["trafficLimitStrategy"] = "NO_RESET"
                
                h, c = get_remnawave_headers({"Content-Type": "application/json"})
                patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
                if not patch_resp.ok:
                    print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
                    return jsonify({"ok": True}), 200  # Все равно возвращаем успех
                
                # Списываем использование промокода, если он был использован
                if p.promo_code_id:
                    promo = db.session.get(PromoCode, p.promo_code_id)
                    if promo and promo.uses_left > 0:
                        promo.uses_left -= 1
                
                p.status = 'PAID'
                db.session.commit()
                cache.delete(f'live_data_{u.remnawave_uuid}')
                cache.delete(f'nodes_{u.remnawave_uuid}')
                
                # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
                # Это не блокирует ответ вебхука, так как синхронизация может занимать много времени
                if BOT_API_URL and BOT_API_TOKEN:
                    app_context = app.app_context()
                    import threading
                    sync_thread = threading.Thread(
                        target=sync_subscription_to_bot_in_background,
                        args=(app_context, u.remnawave_uuid),
                        daemon=True
                    )
                    sync_thread.start()
                    print(f"Started background sync thread for user {u.remnawave_uuid}")
        
        return jsonify({"ok": True}), 200
    except Exception as e:
        print(f"Telegram webhook error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"ok": True}), 200  # Всегда возвращаем успех, чтобы Telegram не повторял запрос

@app.route('/api/webhook/platega', methods=['POST'])
def platega_webhook():
    """Webhook для обработки уведомлений от Platega"""
    try:
        webhook_data = request.json
        
        # Проверяем статус платежа
        status = webhook_data.get('status', '').lower()
        transaction = webhook_data.get('transaction', {})
        
        # Нас интересуют только успешные платежи
        if status not in ['paid', 'success', 'completed']:
            return jsonify({}), 200
        
        # Получаем ID транзакции из webhook
        transaction_id = transaction.get('id')
        invoice_id = transaction.get('invoiceId')
        
        # Ищем платеж по transaction_id или invoice_id
        p = None
        if transaction_id:
            p = Payment.query.filter_by(payment_system_id=transaction_id).first()
        if not p and invoice_id:
            p = Payment.query.filter_by(order_id=invoice_id).first()
        
        if not p:
            print(f"Platega webhook: Payment not found for transaction_id={transaction_id}, invoice_id={invoice_id}")
            return jsonify({}), 200
        
        # Если платеж уже обработан, игнорируем
        if p.status == 'PAID':
            return jsonify({}), 200
        
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id)
        
        if not u or not t:
            print(f"Platega webhook: User or Tariff not found for payment {p.order_id}")
            return jsonify({}), 200
        
        h = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h).json().get('response', {})
        curr_exp = datetime.fromisoformat(live.get('expireAt'))
        new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
        
        # Используем сквад из тарифа, если указан, иначе дефолтный
        squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
        
        # Формируем payload для обновления пользователя
        patch_payload = {
            "uuid": u.remnawave_uuid,
            "expireAt": new_exp.isoformat(),
            "activeInternalSquads": [squad_id]
        }
        
        # Добавляем лимит трафика, если указан в тарифе
        if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
            patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
            patch_payload["trafficLimitStrategy"] = "NO_RESET"
        
        h, c = get_remnawave_headers({"Content-Type": "application/json"})
        patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
        if not patch_resp.ok:
            print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
            return jsonify({}), 200  # Все равно возвращаем успех, чтобы вебхук не повторялся
        
        # Списываем использование промокода, если он был использован
        if p.promo_code_id:
            promo = db.session.get(PromoCode, p.promo_code_id)
            if promo and promo.uses_left > 0:
                promo.uses_left -= 1
        
        p.status = 'PAID'
        db.session.commit()
        cache.delete(f'live_data_{u.remnawave_uuid}')
        cache.delete(f'nodes_{u.remnawave_uuid}')
        
        # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
        if BOT_API_URL and BOT_API_TOKEN:
            app_context = app.app_context()
            import threading
            sync_thread = threading.Thread(
                target=sync_subscription_to_bot_in_background,
                args=(app_context, u.remnawave_uuid),
                daemon=True
            )
            sync_thread.start()
            print(f"Started background sync thread for user {u.remnawave_uuid}")
        
        return jsonify({}), 200
        
    except Exception as e:
        print(f"Platega webhook error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({}), 200  # Всегда возвращаем 200, чтобы Platega не повторял запрос

@app.route('/api/webhook/mulenpay', methods=['POST'])
def mulenpay_webhook():
    """Webhook для обработки уведомлений от Mulenpay"""
    try:
        webhook_data = request.json
        
        # Mulenpay отправляет данные о платеже
        # Проверяем статус платежа
        status = webhook_data.get('status', '').lower()
        payment_id = webhook_data.get('id') or webhook_data.get('payment_id')
        uuid = webhook_data.get('uuid')  # Это наш order_id
        
        # Нас интересуют только успешные платежи
        if status not in ['paid', 'success', 'completed', 'successful']:
            return jsonify({}), 200
        
        # Ищем платеж по uuid (order_id) или payment_id
        p = None
        if uuid:
            p = Payment.query.filter_by(order_id=uuid).first()
        if not p and payment_id:
            p = Payment.query.filter_by(payment_system_id=str(payment_id)).first()
        
        if not p:
            print(f"Mulenpay webhook: Payment not found for uuid={uuid}, payment_id={payment_id}")
            return jsonify({}), 200
        
        # Если платеж уже обработан, игнорируем
        if p.status == 'PAID':
            return jsonify({}), 200
        
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id)
        
        if not u or not t:
            print(f"Mulenpay webhook: User or Tariff not found for payment {p.order_id}")
            return jsonify({}), 200
        
        h = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h).json().get('response', {})
        curr_exp = datetime.fromisoformat(live.get('expireAt'))
        new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
        
        # Используем сквад из тарифа, если указан, иначе дефолтный
        squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
        
        # Формируем payload для обновления пользователя
        patch_payload = {
            "uuid": u.remnawave_uuid,
            "expireAt": new_exp.isoformat(),
            "activeInternalSquads": [squad_id]
        }
        
        # Добавляем лимит трафика, если указан в тарифе
        if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
            patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
            patch_payload["trafficLimitStrategy"] = "NO_RESET"
        
        h, c = get_remnawave_headers({"Content-Type": "application/json"})
        patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
        if not patch_resp.ok:
            print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
            return jsonify({}), 200  # Все равно возвращаем успех, чтобы вебхук не повторялся
        
        # Списываем использование промокода, если он был использован
        if p.promo_code_id:
            promo = db.session.get(PromoCode, p.promo_code_id)
            if promo and promo.uses_left > 0:
                promo.uses_left -= 1
        
        p.status = 'PAID'
        db.session.commit()
        cache.delete(f'live_data_{u.remnawave_uuid}')
        cache.delete(f'nodes_{u.remnawave_uuid}')
        
        # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
        if BOT_API_URL and BOT_API_TOKEN:
            app_context = app.app_context()
            import threading
            sync_thread = threading.Thread(
                target=sync_subscription_to_bot_in_background,
                args=(app_context, u.remnawave_uuid),
                daemon=True
            )
            sync_thread.start()
            print(f"Started background sync thread for user {u.remnawave_uuid}")
        
        return jsonify({}), 200
        
    except Exception as e:
        print(f"Mulenpay webhook error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({}), 200  # Всегда возвращаем 200, чтобы Mulenpay не повторял запрос

@app.route('/api/webhook/urlpay', methods=['POST'])
def urlpay_webhook():
    """Webhook для обработки уведомлений от UrlPay"""
    try:
        webhook_data = request.json
        
        # UrlPay отправляет данные о платеже
        # Проверяем статус платежа
        status = webhook_data.get('status', '').lower()
        payment_id = webhook_data.get('id') or webhook_data.get('payment_id')
        uuid = webhook_data.get('uuid')  # Это наш order_id
        
        # Нас интересуют только успешные платежи
        if status not in ['paid', 'success', 'completed', 'successful']:
            return jsonify({}), 200
        
        # Ищем платеж по uuid (order_id) или payment_id
        p = None
        if uuid:
            p = Payment.query.filter_by(order_id=uuid).first()
        if not p and payment_id:
            p = Payment.query.filter_by(payment_system_id=str(payment_id)).first()
        
        if not p:
            print(f"UrlPay webhook: Payment not found for uuid={uuid}, payment_id={payment_id}")
            return jsonify({}), 200
        
        # Если платеж уже обработан, игнорируем
        if p.status == 'PAID':
            return jsonify({}), 200
        
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id)
        
        if not u or not t:
            print(f"UrlPay webhook: User or Tariff not found for payment {p.order_id}")
            return jsonify({}), 200
        
        h = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h).json().get('response', {})
        curr_exp = datetime.fromisoformat(live.get('expireAt'))
        new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
        
        # Используем сквад из тарифа, если указан, иначе дефолтный
        squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
        
        # Формируем payload для обновления пользователя
        patch_payload = {
            "uuid": u.remnawave_uuid,
            "expireAt": new_exp.isoformat(),
            "activeInternalSquads": [squad_id]
        }
        
        # Добавляем лимит трафика, если указан в тарифе
        if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
            patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
            patch_payload["trafficLimitStrategy"] = "NO_RESET"
        
        h, c = get_remnawave_headers({"Content-Type": "application/json"})
        patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
        if not patch_resp.ok:
            print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
            return jsonify({}), 200  # Все равно возвращаем успех, чтобы вебхук не повторялся
        
        # Списываем использование промокода, если он был использован
        if p.promo_code_id:
            promo = db.session.get(PromoCode, p.promo_code_id)
            if promo and promo.uses_left > 0:
                promo.uses_left -= 1
        
        p.status = 'PAID'
        db.session.commit()
        cache.delete(f'live_data_{u.remnawave_uuid}')
        cache.delete(f'nodes_{u.remnawave_uuid}')
        
        # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
        if BOT_API_URL and BOT_API_TOKEN:
            app_context = app.app_context()
            import threading
            sync_thread = threading.Thread(
                target=sync_subscription_to_bot_in_background,
                args=(app_context, u.remnawave_uuid),
                daemon=True
            )
            sync_thread.start()
            print(f"Started background sync thread for user {u.remnawave_uuid}")
        
        return jsonify({}), 200
        
    except Exception as e:
        print(f"UrlPay webhook error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({}), 200  # Всегда возвращаем 200, чтобы UrlPay не повторял запрос

@app.route('/api/webhook/btcpayserver', methods=['POST'])
def btcpayserver_webhook():
    """
    Webhook для обработки событий BTCPayServer
    
    В настройках BTCPayServer Store нужно указать webhook URL:
    {YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/btcpayserver
    
    BTCPayServer отправляет события в формате:
    {
        "type": "InvoiceSettled",  // или InvoiceReceivedPayment, InvoiceInvalid, InvoiceExpired
        "data": {
            "id": "invoice_id",
            "status": "Settled",
            ...
        }
    }
    """
    try:
        # BTCPayServer отправляет события в формате JSON
        # Типы событий: InvoiceSettled, InvoiceReceivedPayment, InvoiceInvalid, InvoiceExpired и т.д.
        data = request.json
        if not data:
            return jsonify({"error": "No data"}), 400
        
        event_type = data.get('type')
        invoice_data = data.get('data', {})
        
        # Нас интересует только событие InvoiceSettled (инвойс оплачен)
        if event_type != 'InvoiceSettled':
            return jsonify({"error": False}), 200
        
        # Получаем invoice ID из данных
        invoice_id = invoice_data.get('id')
        if not invoice_id:
            return jsonify({"error": "No invoice ID"}), 400
        
        # Ищем платеж по payment_system_id (invoice ID)
        p = Payment.query.filter_by(payment_system_id=invoice_id).first()
        if not p or p.status == 'PAID':
            return jsonify({"error": False}), 200
        
        # Проверяем статус инвойса
        invoice_status = invoice_data.get('status')
        if invoice_status != 'Settled':
            return jsonify({"error": False}), 200
        
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id)
        
        h, c = get_remnawave_headers()
        live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h, cookies=c).json().get('response', {})
        curr_exp = parse_iso_datetime(live.get('expireAt'))
        new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
        
        # Используем сквад из тарифа, если указан, иначе дефолтный
        squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
        
        # Формируем payload для обновления пользователя
        patch_payload = {
            "uuid": u.remnawave_uuid,
            "expireAt": new_exp.isoformat(),
            "activeInternalSquads": [squad_id]
        }
        
        # Добавляем лимит трафика, если указан в тарифе
        if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
            patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
            patch_payload["trafficLimitStrategy"] = "NO_RESET"
        
        h, c = get_remnawave_headers({"Content-Type": "application/json"})
        patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
        if not patch_resp.ok:
            print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
            return jsonify({"error": False}), 200
        
        # Списываем использование промокода, если он был использован
        if p.promo_code_id:
            promo = db.session.get(PromoCode, p.promo_code_id)
            if promo and promo.uses_left > 0:
                promo.uses_left -= 1
        
        p.status = 'PAID'
        db.session.commit()
        cache.delete(f'live_data_{u.remnawave_uuid}')
        cache.delete(f'nodes_{u.remnawave_uuid}')
        
        # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
        if BOT_API_URL and BOT_API_TOKEN:
            app_context = app.app_context()
            import threading
            sync_thread = threading.Thread(
                target=sync_subscription_to_bot_in_background,
                args=(app_context, u.remnawave_uuid),
                daemon=True
            )
            sync_thread.start()
            print(f"Started background sync thread for user {u.remnawave_uuid}")
        
        return jsonify({"error": False}), 200
    except Exception as e:
        print(f"Error in btcpayserver_webhook: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": False}), 200  # Возвращаем успех, чтобы BTCPayServer не повторял запрос

@app.route('/api/webhook/tribute', methods=['POST'])
def tribute_webhook():
    """
    Webhook для обработки уведомлений от Tribute
    
    Tribute может отправлять уведомления о статусе заказа.
    Также можно проверять статус через API: GET /api/v1/shop/orders/{orderUuid}/status
    """
    try:
        webhook_data = request.json
        if not webhook_data:
            return jsonify({}), 200
        
        # Tribute может отправлять UUID заказа или данные о заказе
        order_uuid = webhook_data.get('uuid') or webhook_data.get('orderUuid')
        status = webhook_data.get('status', '').lower()
        
        if not order_uuid:
            print("Tribute webhook: order UUID not found")
            return jsonify({}), 200
        
        # Ищем платеж по payment_system_id (UUID заказа)
        p = Payment.query.filter_by(payment_system_id=order_uuid).first()
        if not p:
            print(f"Tribute webhook: Payment not found for UUID {order_uuid}")
            return jsonify({}), 200
        
        # Если платеж уже обработан, игнорируем
        if p.status == 'PAID':
            return jsonify({}), 200
        
        # Если статус не указан в webhook, проверяем через API
        if not status or status not in ['paid', 'success', 'completed']:
            # Проверяем статус через API Tribute
            s = PaymentSetting.query.first()
            if not s:
                return jsonify({}), 200
            
            tribute_api_key = decrypt_key(s.tribute_api_key) if s.tribute_api_key else None
            if not tribute_api_key or tribute_api_key == "DECRYPTION_ERROR":
                return jsonify({}), 200
            
            try:
                status_url = f"https://tribute.tg/api/v1/shop/orders/{order_uuid}/status"
                headers = {"Api-Key": tribute_api_key}
                status_resp = requests.get(status_url, headers=headers, timeout=10)
                
                if status_resp.ok:
                    status_data = status_resp.json()
                    status = status_data.get('status', '').lower()
                else:
                    return jsonify({}), 200
            except:
                return jsonify({}), 200
        
        # Обрабатываем только успешные платежи
        if status in ['paid', 'success', 'completed']:
            u = db.session.get(User, p.user_id)
            t = db.session.get(Tariff, p.tariff_id)
            
            if not u or not t:
                print(f"Tribute webhook: User or Tariff not found for payment {p.order_id}")
                return jsonify({}), 200
            
            h, c = get_remnawave_headers()
            live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h, cookies=c).json().get('response', {})
            curr_exp = parse_iso_datetime(live.get('expireAt'))
            new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
            
            # Используем сквад из тарифа, если указан, иначе дефолтный
            squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
            
            # Формируем payload для обновления пользователя
            patch_payload = {
                "uuid": u.remnawave_uuid,
                "expireAt": new_exp.isoformat(),
                "activeInternalSquads": [squad_id]
            }
            
            # Добавляем лимит трафика, если указан в тарифе
            if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
                patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
                patch_payload["trafficLimitStrategy"] = "NO_RESET"
            
            h, c = get_remnawave_headers({"Content-Type": "application/json"})
            patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
            if not patch_resp.ok:
                print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
                return jsonify({}), 200
            
            # Списываем использование промокода, если он был использован
            if p.promo_code_id:
                promo = db.session.get(PromoCode, p.promo_code_id)
                if promo and promo.uses_left > 0:
                    promo.uses_left -= 1
            
            p.status = 'PAID'
            db.session.commit()
            cache.delete(f'live_data_{u.remnawave_uuid}')
            cache.delete(f'nodes_{u.remnawave_uuid}')
            
            # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
            if BOT_API_URL and BOT_API_TOKEN:
                app_context = app.app_context()
                import threading
                sync_thread = threading.Thread(
                    target=sync_subscription_to_bot_in_background,
                    args=(app_context, u.remnawave_uuid),
                    daemon=True
                )
                sync_thread.start()
                print(f"Started background sync thread for user {u.remnawave_uuid}")
        
        return jsonify({}), 200
    except Exception as e:
        print(f"Error in tribute_webhook: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({}), 200  # Возвращаем успех, чтобы Tribute не повторял запрос

@app.route('/api/webhook/robokassa', methods=['POST'])
def robokassa_webhook():
    """
    Webhook для обработки уведомлений от Robokassa (ResultURL)
    
    Robokassa отправляет POST запрос с параметрами:
    - OutSum - сумма платежа
    - InvId - номер счета (order_id)
    - SignatureValue - подпись для проверки
    
    Формула проверки подписи: MD5(OutSum:InvId:Password#2)
    
    В настройках магазина Robokassa нужно указать ResultURL:
    {YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/robokassa
    """
    try:
        # Robokassa отправляет данные через POST (form-data или query string)
        # Пробуем получить из form или args
        out_sum = request.form.get('OutSum') or request.args.get('OutSum')
        inv_id = request.form.get('InvId') or request.args.get('InvId')
        signature = request.form.get('SignatureValue') or request.args.get('SignatureValue')
        
        if not out_sum or not inv_id or not signature:
            print("Robokassa webhook: Missing required parameters")
            return "OK", 200  # Robokassa требует ответ "OK" в случае ошибки
        
        # Получаем настройки для проверки подписи
        s = PaymentSetting.query.first()
        if not s:
            return "OK", 200
        
        robokassa_password2 = decrypt_key(s.robokassa_password2) if s.robokassa_password2 else None
        if not robokassa_password2 or robokassa_password2 == "DECRYPTION_ERROR":
            print("Robokassa webhook: Password #2 not configured")
            return "OK", 200
        
        # Проверяем подпись: MD5(OutSum:InvId:Password#2)
        import hashlib
        expected_signature = hashlib.md5(f"{out_sum}:{inv_id}:{robokassa_password2}".encode('utf-8')).hexdigest()
        
        if signature.lower() != expected_signature.lower():
            print(f"Robokassa webhook: Invalid signature. Expected: {expected_signature}, Got: {signature}")
            return "OK", 200
        
        # Ищем платеж по order_id (InvId)
        p = Payment.query.filter_by(order_id=inv_id).first()
        if not p:
            print(f"Robokassa webhook: Payment not found for InvId {inv_id}")
            return "OK", 200
        
        # Если платеж уже обработан, игнорируем
        if p.status == 'PAID':
            return "OK", 200
        
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id)
        
        if not u or not t:
            print(f"Robokassa webhook: User or Tariff not found for payment {p.order_id}")
            return "OK", 200
        
        h, c = get_remnawave_headers()
        live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h, cookies=c).json().get('response', {})
        curr_exp = parse_iso_datetime(live.get('expireAt'))
        new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
        
        # Используем сквад из тарифа, если указан, иначе дефолтный
        squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
        
        # Формируем payload для обновления пользователя
        patch_payload = {
            "uuid": u.remnawave_uuid,
            "expireAt": new_exp.isoformat(),
            "activeInternalSquads": [squad_id]
        }
        
        # Добавляем лимит трафика, если указан в тарифе
        if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
            patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
            patch_payload["trafficLimitStrategy"] = "NO_RESET"
        
        h, c = get_remnawave_headers({"Content-Type": "application/json"})
        patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
        if not patch_resp.ok:
            print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
            return "OK", 200
        
        # Списываем использование промокода, если он был использован
        if p.promo_code_id:
            promo = db.session.get(PromoCode, p.promo_code_id)
            if promo and promo.uses_left > 0:
                promo.uses_left -= 1
        
        p.status = 'PAID'
        db.session.commit()
        cache.delete(f'live_data_{u.remnawave_uuid}')
        cache.delete(f'nodes_{u.remnawave_uuid}')
        
        # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
        if BOT_API_URL and BOT_API_TOKEN:
            app_context = app.app_context()
            import threading
            sync_thread = threading.Thread(
                target=sync_subscription_to_bot_in_background,
                args=(app_context, u.remnawave_uuid),
                daemon=True
            )
            sync_thread.start()
            print(f"Started background sync thread for user {u.remnawave_uuid}")
        
        # Robokassa требует ответ "OK" при успешной обработке
        return "OK", 200
    except Exception as e:
        print(f"Error in robokassa_webhook: {e}")
        import traceback
        traceback.print_exc()
        return "OK", 200  # Всегда возвращаем "OK", чтобы Robokassa не повторял запрос

@app.route('/api/webhook/freekassa', methods=['GET', 'POST'])
def freekassa_webhook():
    """
    Webhook для обработки уведомлений от Freekassa (Result URL)
    
    Freekassa отправляет данные на URL оповещения с параметрами:
    - MERCHANT_ID - ID магазина
    - AMOUNT - сумма платежа
    - MERCHANT_ORDER_ID - номер заказа (paymentId)
    - P_EMAIL - email плательщика (опционально)
    - P_PHONE - телефон плательщика (опционально)
    - SIGN - подпись для проверки
    
    Формула проверки подписи: MD5(AMOUNT + MERCHANT_ORDER_ID + Secret2)
    
    В настройках магазина Freekassa нужно указать URL оповещения:
    {YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/freekassa
    
    Для подтверждения получения уведомления нужно вернуть "YES"
    """
    try:
        # Freekassa может отправлять данные через GET или POST
        # Пробуем получить из form, args или json
        merchant_id = request.form.get('MERCHANT_ID') or request.args.get('MERCHANT_ID')
        amount = request.form.get('AMOUNT') or request.args.get('AMOUNT')
        merchant_order_id = request.form.get('MERCHANT_ORDER_ID') or request.args.get('MERCHANT_ORDER_ID')
        sign = request.form.get('SIGN') or request.args.get('SIGN')
        
        if not merchant_id or not amount or not merchant_order_id or not sign:
            print("Freekassa webhook: Missing required parameters")
            return "YES", 200  # Freekassa требует ответ "YES" даже при ошибке
        
        # Получаем настройки для проверки подписи
        s = PaymentSetting.query.first()
        if not s:
            return "YES", 200
        
        freekassa_secret2 = decrypt_key(s.freekassa_secret2) if s.freekassa_secret2 else None
        if not freekassa_secret2 or freekassa_secret2 == "DECRYPTION_ERROR":
            print("Freekassa webhook: Secret2 not configured")
            return "YES", 200
        
        # Проверяем подпись: MD5(AMOUNT + MERCHANT_ORDER_ID + Secret2)
        import hashlib
        expected_signature = hashlib.md5(f"{amount}{merchant_order_id}{freekassa_secret2}".encode('utf-8')).hexdigest()
        
        if sign.upper() != expected_signature.upper():
            print(f"Freekassa webhook: Invalid signature. Expected: {expected_signature.upper()}, Got: {sign.upper()}")
            return "YES", 200
        
        # Ищем платеж по order_id (MERCHANT_ORDER_ID)
        p = Payment.query.filter_by(order_id=merchant_order_id).first()
        if not p:
            print(f"Freekassa webhook: Payment not found for MERCHANT_ORDER_ID {merchant_order_id}")
            return "YES", 200
        
        # Если платеж уже обработан, игнорируем
        if p.status == 'PAID':
            return "YES", 200
        
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id)
        
        if not u or not t:
            print(f"Freekassa webhook: User or Tariff not found for payment {p.order_id}")
            return "YES", 200
        
        h, c = get_remnawave_headers()
        live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h, cookies=c).json().get('response', {})
        curr_exp = parse_iso_datetime(live.get('expireAt'))
        new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
        
        # Используем сквад из тарифа, если указан, иначе дефолтный
        squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
        
        # Формируем payload для обновления пользователя
        patch_payload = {
            "uuid": u.remnawave_uuid,
            "expireAt": new_exp.isoformat(),
            "activeInternalSquads": [squad_id]
        }
        
        # Добавляем лимит трафика, если указан в тарифе
        if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
            patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
            patch_payload["trafficLimitStrategy"] = "NO_RESET"
        
        h, c = get_remnawave_headers({"Content-Type": "application/json"})
        patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
        if not patch_resp.ok:
            print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
            return "YES", 200
        
        # Списываем использование промокода, если он был использован
        if p.promo_code_id:
            promo = db.session.get(PromoCode, p.promo_code_id)
            if promo and promo.uses_left > 0:
                promo.uses_left -= 1
        
        p.status = 'PAID'
        db.session.commit()
        cache.delete(f'live_data_{u.remnawave_uuid}')
        cache.delete(f'nodes_{u.remnawave_uuid}')
        
        # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
        if BOT_API_URL and BOT_API_TOKEN:
            app_context = app.app_context()
            import threading
            sync_thread = threading.Thread(
                target=sync_subscription_to_bot_in_background,
                args=(app_context, u.remnawave_uuid),
                daemon=True
            )
            sync_thread.start()
            print(f"Started background sync thread for user {u.remnawave_uuid}")
        
        # Freekassa требует ответ "YES" при успешной обработке
        return "YES", 200
    except Exception as e:
        print(f"Error in freekassa_webhook: {e}")
        import traceback
        traceback.print_exc()
        return "YES", 200  # Всегда возвращаем "YES", чтобы Freekassa не повторял запрос

@app.route('/api/webhook/monobank', methods=['POST'])
def monobank_webhook():
    """Webhook для обработки уведомлений от Monobank"""
    try:
        webhook_data = request.json
        if not webhook_data:
            return jsonify({}), 200
        
        # Monobank отправляет данные о статусе инвойса
        invoice_id = webhook_data.get('invoiceId')
        status = webhook_data.get('status')
        
        if not invoice_id:
            print("Monobank webhook: invoiceId not found")
            return jsonify({}), 200
        
        # Ищем платеж по invoiceId (payment_system_id) или order_id
        p = Payment.query.filter_by(payment_system_id=invoice_id).first()
        if not p:
            # Пробуем найти по order_id, если invoiceId совпадает с order_id
            p = Payment.query.filter_by(order_id=invoice_id).first()
        
        if not p:
            print(f"Monobank webhook: Payment not found for invoiceId {invoice_id}")
            return jsonify({}), 200
        
        # Если платеж уже обработан, игнорируем
        if p.status == 'PAID':
            return jsonify({}), 200
        
        # Обрабатываем только успешные платежи (status = 'success' или 'paid')
        if status in ['success', 'paid', 'successful']:
            u = db.session.get(User, p.user_id)
            t = db.session.get(Tariff, p.tariff_id)
            
            if not u or not t:
                print(f"Monobank webhook: User or Tariff not found for payment {p.order_id}")
                return jsonify({}), 200
            
            h = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
            live = requests.get(f"{API_URL}/api/users/{u.remnawave_uuid}", headers=h).json().get('response', {})
            curr_exp = datetime.fromisoformat(live.get('expireAt'))
            new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
            
            # Используем сквад из тарифа, если указан, иначе дефолтный
            squad_id = t.squad_id if t.squad_id else DEFAULT_SQUAD_ID
            
            # Формируем payload для обновления пользователя
            patch_payload = {
                "uuid": u.remnawave_uuid,
                "expireAt": new_exp.isoformat(),
                "activeInternalSquads": [squad_id]
            }
            
            # Добавляем лимит трафика, если указан в тарифе
            if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
                patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
                patch_payload["trafficLimitStrategy"] = "NO_RESET"
            
            h, c = get_remnawave_headers({"Content-Type": "application/json"})
            patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
            if not patch_resp.ok:
                print(f"⚠️ Failed to update user in RemnaWave: Status {patch_resp.status_code}")
                return jsonify({}), 200  # Все равно возвращаем успех, чтобы вебхук не повторялся
            
            # Списываем использование промокода, если он был использован
            if p.promo_code_id:
                promo = db.session.get(PromoCode, p.promo_code_id)
                if promo and promo.uses_left > 0:
                    promo.uses_left -= 1
            
            p.status = 'PAID'
            db.session.commit()
            cache.delete(f'live_data_{u.remnawave_uuid}')
            cache.delete(f'nodes_{u.remnawave_uuid}')
            
            # Синхронизируем обновленную подписку из RemnaWave в бота в фоновом режиме
            if BOT_API_URL and BOT_API_TOKEN:
                app_context = app.app_context()
                import threading
                sync_thread = threading.Thread(
                    target=sync_subscription_to_bot_in_background,
                    args=(app_context, u.remnawave_uuid),
                    daemon=True
                )
                sync_thread.start()
                print(f"Started background sync thread for user {u.remnawave_uuid}")
        
        return jsonify({}), 200
        
    except Exception as e:
        print(f"Monobank webhook error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({}), 200  # Всегда возвращаем 200, чтобы Monobank не повторял запрос

@app.route('/api/client/support-tickets', methods=['GET', 'POST'])
def client_tickets():
    user = get_user_from_token()
    if not user: return jsonify({"message": "Auth Error"}), 401
    if request.method == 'GET':
        ts = Ticket.query.filter_by(user_id=user.id).order_by(Ticket.created_at.desc()).all()
        return jsonify([{"id": t.id, "subject": t.subject, "status": t.status, "created_at": t.created_at.isoformat()} for t in ts]), 200
    
    # 🛡️ TYPE CHECK
    d = request.json
    subj, msg = d.get('subject'), d.get('message')
    if not isinstance(subj, str) or not isinstance(msg, str): return jsonify({"message": "Invalid input"}), 400
    
    nt = Ticket(user_id=user.id, subject=subj, status='OPEN')
    db.session.add(nt); db.session.flush()
    nm = TicketMessage(ticket_id=nt.id, sender_id=user.id, message=msg)
    db.session.add(nm); db.session.commit()
    return jsonify({"message": "Created", "ticket_id": nt.id}), 201

@app.route('/api/admin/support-tickets', methods=['GET'])
@admin_required
def admin_tickets(current_admin):
    ts = db.session.query(Ticket, User.email).join(User).order_by(Ticket.created_at.desc()).all()
    return jsonify([{"id": t.id, "user_email": e, "subject": t.subject, "status": t.status, "created_at": t.created_at.isoformat()} for t, e in ts]), 200

@app.route('/api/admin/support-tickets/<int:id>', methods=['PATCH'])
@admin_required
def admin_ticket_update(current_admin, id):
    t = db.session.get(Ticket, id)
    if t: t.status = request.json.get('status'); db.session.commit()
    return jsonify({"message": "Updated"}), 200

@app.route('/api/support-tickets/<int:id>', methods=['GET'])
def get_ticket_msgs(id):
    user = get_user_from_token()
    t = db.session.get(Ticket, id)
    if not t or (user.role != 'ADMIN' and t.user_id != user.id): return jsonify({"message": "Forbidden"}), 403
    msgs = db.session.query(TicketMessage, User.email, User.role).join(User).filter(TicketMessage.ticket_id == id).order_by(TicketMessage.created_at.asc()).all()
    return jsonify({"subject": t.subject, "status": t.status, "user_email": t.user.email, "messages": [{"id": m.id, "message": m.message, "sender_email": e, "sender_id": m.sender_id, "sender_role": r, "created_at": m.created_at.isoformat()} for m, e, r in msgs]}), 200

@app.route('/api/support-tickets/<int:id>/reply', methods=['POST'])
def reply_ticket(id):
    user = get_user_from_token()
    t = db.session.get(Ticket, id)
    if not t or (user.role != 'ADMIN' and t.user_id != user.id): return jsonify({"message": "Forbidden"}), 403
    
    # 🛡️ TYPE CHECK
    msg = request.json.get('message')
    if not isinstance(msg, str) or not msg: return jsonify({"message": "Invalid message"}), 400

    nm = TicketMessage(ticket_id=id, sender_id=user.id, message=msg)
    t.status = 'OPEN'
    db.session.add(nm); db.session.commit()
    return jsonify({"id": nm.id, "message": nm.message, "sender_email": user.email, "sender_id": user.id, "sender_role": user.role, "created_at": nm.created_at.isoformat()}), 201

@app.route('/api/admin/statistics', methods=['GET'])
@admin_required
def stats(current_admin):
    now = datetime.now(timezone.utc)
    total = db.session.query(Payment.currency, func.sum(Payment.amount)).filter(Payment.status == 'PAID').group_by(Payment.currency).all()
    month = db.session.query(Payment.currency, func.sum(Payment.amount)).filter(Payment.status == 'PAID', Payment.created_at >= now.replace(day=1, hour=0, minute=0)).group_by(Payment.currency).all()
    today = db.session.query(Payment.currency, func.sum(Payment.amount)).filter(Payment.status == 'PAID', Payment.created_at >= now.replace(hour=0, minute=0)).group_by(Payment.currency).all()
    
    return jsonify({
        "total_revenue": {c: a for c, a in total},
        "month_revenue": {c: a for c, a in month},
        "today_revenue": {c: a for c, a in today},
        "total_sales_count": db.session.query(func.count(Payment.id)).filter(Payment.status == 'PAID').scalar(),
        "total_users": db.session.query(func.count(User.id)).scalar()
    }), 200

@app.route('/api/admin/sales', methods=['GET'])
@admin_required
def get_sales(current_admin):
    """Получить список всех продаж с информацией о пользователе и тарифе"""
    try:
        limit = request.args.get('limit', type=int) or 50
        offset = request.args.get('offset', type=int) or 0
        
        # Получаем платежи с информацией о пользователе и тарифе (включая пополнения баланса)
        payments = db.session.query(
            Payment,
            User,
            Tariff,
            PromoCode
        ).join(
            User, Payment.user_id == User.id
        ).outerjoin(
            Tariff, Payment.tariff_id == Tariff.id
        ).outerjoin(
            PromoCode, Payment.promo_code_id == PromoCode.id
        ).filter(
            Payment.status == 'PAID'
        ).order_by(
            Payment.created_at.desc()
        ).limit(limit).offset(offset).all()
        
        sales_list = []
        for payment, user, tariff, promo in payments:
            # Если это пополнение баланса (tariff_id == None)
            if payment.tariff_id is None:
                sales_list.append({
                    "id": payment.id,
                    "order_id": payment.order_id,
                    "date": payment.created_at.isoformat() if payment.created_at else None,
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "status": payment.status,
                    "payment_provider": payment.payment_provider or 'crystalpay',
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "telegram_id": user.telegram_id,
                        "telegram_username": user.telegram_username
                    },
                    "tariff": None,  # Пополнение баланса
                    "is_balance_topup": True,  # Флаг пополнения баланса
                    "promo_code": promo.code if promo else None
                })
            else:
                # Обычная покупка тарифа
                sales_list.append({
                    "id": payment.id,
                    "order_id": payment.order_id,
                    "date": payment.created_at.isoformat() if payment.created_at else None,
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "status": payment.status,
                    "payment_provider": payment.payment_provider or 'crystalpay',
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "telegram_id": user.telegram_id,
                        "telegram_username": user.telegram_username
                    },
                    "tariff": {
                        "id": tariff.id,
                        "name": tariff.name,
                        "duration_days": tariff.duration_days
                    },
                    "is_balance_topup": False,
                    "promo_code": promo.code if promo else None
                })
        
        return jsonify(sales_list), 200
    except Exception as e:
        print(f"Error getting sales: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Failed to get sales", "message": str(e)}), 500

@app.route('/api/public/verify-email', methods=['POST'])
@limiter.limit("10 per minute")
def verify_email():
    token = request.json.get('token')
    if not isinstance(token, str): return jsonify({"message": "Invalid token"}), 400
    u = User.query.filter_by(verification_token=token).first()
    if not u: return jsonify({"message": "Invalid or expired token"}), 404
    u.is_verified = True; u.verification_token = None; db.session.commit()
    # Возвращаем токен для автоматической авторизации
    jwt_token = create_local_jwt(u.id)
    return jsonify({"message": "OK", "token": jwt_token, "role": u.role}), 200

@app.route('/api/public/resend-verification', methods=['POST'])
@limiter.limit("3 per minute")
def resend_verif():
    email = request.json.get('email')
    if not isinstance(email, str): return jsonify({"message": "Invalid email"}), 400
    u = User.query.filter_by(email=email).first()
    if u and not u.is_verified and u.verification_token:
        url = f"{YOUR_SERVER_IP_OR_DOMAIN}/verify?token={u.verification_token}"
        branding = BrandingSetting.query.first() or BrandingSetting(site_name=SERVICE_NAME, primary_color="#3F69FF", secondary_color="#ffffff", accent_color="#3F69FF")
        html = render_template('email_verification.html', verification_url=url, branding=branding, service_name=SERVICE_NAME)
        threading.Thread(target=send_email_in_background, args=(app.app_context(), u.email, "Verify Email", html)).start()
    return jsonify({"message": "Sent"}), 200

@app.cli.command("clean-unverified")
def clean():
    d = datetime.now(timezone.utc) - timedelta(hours=24)
    [db.session.delete(u) for u in User.query.filter(User.is_verified == False, User.created_at < d).all()]
    db.session.commit()
    print("Cleaned.")

@app.cli.command("make-admin")
@click.argument("email")
def make_admin(email):
    user = User.query.filter_by(email=email).first()
    if user: user.role = 'ADMIN'; db.session.commit(); print(f"User {email} is now ADMIN.")
    else: print(f"User {email} not found.")

@app.cli.command("migrate-yookassa-fields")
def migrate_yookassa_fields():
    """Добавляет поля yookassa_shop_id и yookassa_secret_key в таблицу payment_setting"""
    try:
        # Проверяем существующие колонки через SQL
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('payment_setting')]
        
        changes_made = False
        
        # Добавляем yookassa_shop_id, если его нет
        if 'yookassa_shop_id' not in columns:
            print("➕ Добавляем колонку yookassa_shop_id...")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE payment_setting ADD COLUMN yookassa_shop_id TEXT"))
                conn.commit()
            print("✓ Колонка yookassa_shop_id добавлена")
            changes_made = True
        else:
            print("✓ Колонка yookassa_shop_id уже существует")
        
        # Добавляем yookassa_secret_key, если его нет
        if 'yookassa_secret_key' not in columns:
            print("➕ Добавляем колонку yookassa_secret_key...")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE payment_setting ADD COLUMN yookassa_secret_key TEXT"))
                conn.commit()
            print("✓ Колонка yookassa_secret_key добавлена")
            changes_made = True
        else:
            print("✓ Колонка yookassa_secret_key уже существует")
        
        if changes_made:
            print("\n✅ Миграция успешно завершена!")
        else:
            print("\n✅ Все необходимые колонки уже существуют. Миграция не требуется.")
            
    except Exception as e:
        print(f"❌ Ошибка при выполнении миграции: {e}")
        import traceback
        traceback.print_exc()
        raise

# ❗️❗️❗️ ЭНДПОИНТ №29: ПРОВЕРКА ПРОМОКОДА (КЛИЕНТ) ❗️❗️❗️
@app.route('/api/client/check-promocode', methods=['POST'])
def check_promocode():
    user = get_user_from_token()
    if not user: return jsonify({"message": "Auth Error"}), 401
    
    code_str = request.json.get('code', '').strip().upper() if request.json.get('code') else None
    if not code_str:
        return jsonify({"message": "Введите код"}), 400
    
    promo = PromoCode.query.filter_by(code=code_str).first()
    if not promo:
        return jsonify({"message": "Неверный промокод"}), 404
        
    if promo.uses_left <= 0:
        return jsonify({"message": "Промокод больше не действителен"}), 400
    
    return jsonify({
        "code": promo.code,
        "promo_type": promo.promo_type,
        "value": promo.value,
        "uses_left": promo.uses_left
    }), 200

# ❗️❗️❗️ ЭНДПОИНТ ДЛЯ БОТА: ПОЛУЧЕНИЕ JWT ТОКЕНА ПО TELEGRAM_ID ❗️❗️❗️
@app.route('/api/bot/get-token', methods=['POST'])
@limiter.limit("20 per minute")
def bot_get_token():
    """
    Эндпоинт для получения JWT токена по telegram_id.
    Используется Telegram ботом для авторизации пользователей.
    
    Логика:
    1. Ищет пользователя в локальной БД по telegram_id
    2. Если не найден - пытается найти через RemnaWave API (BOT_API_URL)
    3. Если найден в RemnaWave - создает запись в локальной БД
    4. Если не найден - возвращает ошибку с инструкцией
    """
    data = request.json
    telegram_id = data.get('telegram_id')
    
    if not telegram_id:
        return jsonify({"message": "telegram_id is required"}), 400
    
    try:
        # Шаг 1: Ищем пользователя в локальной БД
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if user:
            # Пользователь найден - возвращаем токен
            token = create_local_jwt(user.id)
            return jsonify({"token": token}), 200
        
        # Шаг 2: Пользователь не найден в БД - пытаемся найти через RemnaWave API
        if BOT_API_URL and BOT_API_TOKEN:
            try:
                bot_api_url = BOT_API_URL.rstrip('/')
                headers_list = [
                    {"X-API-Key": BOT_API_TOKEN},
                    {"Authorization": f"Bearer {BOT_API_TOKEN}"}
                ]
                
                bot_user = None
                remnawave_uuid = None
                
                # Пробуем получить пользователя из RemnaWave API
                for headers in headers_list:
                    try:
                        bot_resp = requests.get(
                            f"{bot_api_url}/users/{telegram_id}",
                            headers=headers,
                            timeout=10
                        )
                        
                        if bot_resp.status_code == 200:
                            bot_data = bot_resp.json()
                            
                            # Парсим ответ
                            if isinstance(bot_data, dict):
                                user_data = bot_data.get('response', {}) if 'response' in bot_data else bot_data
                                remnawave_uuid = (user_data.get('remnawave_uuid') or 
                                                 user_data.get('uuid') or
                                                 user_data.get('user_uuid'))
                                bot_user = user_data
                                break
                    except Exception as e:
                        print(f"Error fetching from bot API: {e}")
                        continue
                
                # Если нашли пользователя в RemnaWave API
                if bot_user and remnawave_uuid:
                    print(f"Found user in RemnaWave API, creating local record for telegram_id: {telegram_id}")
                    
                    # Создаем запись в локальной БД
                    sys_settings = SystemSetting.query.first() or SystemSetting(id=1)
                    if not sys_settings.id:
                        db.session.add(sys_settings)
                        db.session.flush()
                    
                    # Получаем username из bot_user или используем пустую строку
                    telegram_username = bot_user.get('telegram_username') or bot_user.get('username') or ''
                    
                    # Создаем нового пользователя
                    user = User(
                        telegram_id=telegram_id,
                        telegram_username=telegram_username,
                        email=f"tg_{telegram_id}@telegram.local",
                        password_hash='',
                        remnawave_uuid=remnawave_uuid,
                        is_verified=True,
                        preferred_lang=sys_settings.default_language,
                        preferred_currency=sys_settings.default_currency
                    )
                    db.session.add(user)
                    db.session.flush()
                    user.referral_code = generate_referral_code(user.id)
                    db.session.commit()
                    
                    print(f"✓ Created local user record for telegram_id: {telegram_id}, UUID: {remnawave_uuid}")
                    
                    # Возвращаем токен
                    token = create_local_jwt(user.id)
                    return jsonify({"token": token}), 200
            
            except Exception as e:
                print(f"Error checking RemnaWave API: {e}")
                # Продолжаем - вернем ошибку ниже
        
        # Шаг 3: Пользователь не найден ни в БД, ни в RemnaWave API
        return jsonify({
            "message": "User not found. Please register via web panel first.",
            "register_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/register" if YOUR_SERVER_IP_OR_DOMAIN else "https://client.chrnet.ru/register",
            "error_code": "USER_NOT_FOUND"
        }), 404
    
    except Exception as e:
        print(f"Bot get token error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Server Error"}), 500

# ❗️❗️❗️ ЭНДПОИНТ ДЛЯ БОТА: РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ ❗️❗️❗️
@app.route('/api/bot/register', methods=['POST'])
@limiter.limit("5 per hour")
def bot_register():
    """
    Регистрация пользователя через Telegram бота.
    Автоматически генерирует логин (email) и пароль.
    Возвращает логин и пароль для входа на сайте.
    """
    data = request.json
    telegram_id = data.get('telegram_id')
    telegram_username = data.get('telegram_username', '')
    ref_code = data.get('ref_code')
    preferred_lang = data.get('preferred_lang')
    preferred_currency = data.get('preferred_currency')
    
    if not telegram_id:
        return jsonify({"message": "telegram_id is required"}), 400
    
    try:
        # Проверяем, не зарегистрирован ли уже пользователь
        existing_user = User.query.filter_by(telegram_id=telegram_id).first()
        if existing_user:
            # Если пользователь уже зарегистрирован, возвращаем его данные
            email = existing_user.email
            # Если у пользователя есть пароль, мы не можем его вернуть (хеширован)
            # Но можем сказать, что он уже зарегистрирован
            return jsonify({
                "message": "User already registered",
                "email": email,
                "has_password": bool(existing_user.password_hash and existing_user.password_hash != '')
            }), 400
        
        # Генерируем логин (email) и пароль
        # Логин: tg_{telegram_id}@stealthnet.local
        email = f"tg_{telegram_id}@stealthnet.local"
        
        # Проверяем, не занят ли email (маловероятно, но на всякий случай)
        if User.query.filter_by(email=email).first():
            # Если занят, добавляем случайную часть
            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            email = f"tg_{telegram_id}_{random_suffix}@stealthnet.local"
        
        # Генерируем пароль: 12 символов (буквы + цифры)
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # Обрабатываем реферальный код
        referrer, bonus_days_new = None, 0
        if ref_code and isinstance(ref_code, str):
            referrer = User.query.filter_by(referral_code=ref_code).first()
            if referrer:
                s = ReferralSetting.query.first()
                bonus_days_new = s.invitee_bonus_days if s else 7
        
        expire_date = (datetime.now(timezone.utc) + timedelta(days=bonus_days_new)).isoformat()
        clean_username = email.replace("@", "_").replace(".", "_")
        
        # Создаем пользователя в RemnaWave API
        payload_create = {
            "email": email,
            "password": password,
            "username": clean_username,
            "expireAt": expire_date,
            "activeInternalSquads": [DEFAULT_SQUAD_ID] if referrer else []
        }
        
        try:
            resp = requests.post(
                f"{API_URL}/api/users",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                json=payload_create,
                timeout=30
            )
            resp.raise_for_status()
            remnawave_uuid = resp.json().get('response', {}).get('uuid')
            
            if not remnawave_uuid:
                return jsonify({"message": "Provider Error: Failed to create user"}), 500
            
        except requests.exceptions.HTTPError as e:
            print(f"RemnaWave API HTTP Error: {e}")
            print(f"Response: {resp.text if 'resp' in locals() else 'No response'}")
            return jsonify({"message": "Provider error: Failed to create user in RemnaWave"}), 500
        except Exception as e:
            print(f"RemnaWave API Error: {e}")
            return jsonify({"message": "Provider error"}), 500
        
        # Создаем запись в локальной БД
        sys_settings = SystemSetting.query.first() or SystemSetting(id=1)
        if not sys_settings.id:
            db.session.add(sys_settings)
            db.session.flush()
        
        # Используем переданные язык и валюту, или значения по умолчанию из настроек
        final_lang = preferred_lang if preferred_lang in ['ru', 'ua', 'en', 'cn'] else sys_settings.default_language
        final_currency = preferred_currency if preferred_currency in ['uah', 'rub', 'usd'] else sys_settings.default_currency
        
        # Шифруем пароль для хранения (чтобы можно было показать пользователю)
        encrypted_password_str = None
        if app.config.get('FERNET_KEY') and fernet:
            try:
                encrypted_password_str = fernet.encrypt(password.encode()).decode()
            except Exception as e:
                print(f"Error encrypting password: {e}")
                encrypted_password_str = None
        
        new_user = User(
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            email=email,
            password_hash=hashed_password,
            encrypted_password=encrypted_password_str,  # Сохраняем зашифрованный пароль
            remnawave_uuid=remnawave_uuid,
            referrer_id=referrer.id if referrer else None,
            is_verified=True,  # Telegram пользователи считаются верифицированными
            created_at=datetime.now(timezone.utc),
            preferred_lang=final_lang,
            preferred_currency=final_currency
        )
        db.session.add(new_user)
        db.session.flush()
        new_user.referral_code = generate_referral_code(new_user.id)
        db.session.commit()
        
        # Применяем бонус рефереру в фоне
        if referrer:
            s = ReferralSetting.query.first()
            days = s.referrer_bonus_days if s else 7
            threading.Thread(
                target=apply_referrer_bonus_in_background,
                args=(app.app_context(), referrer.remnawave_uuid, days)
            ).start()
        
        print(f"✓ User registered via bot: telegram_id={telegram_id}, email={email}")
        
        # Возвращаем логин и пароль
        return jsonify({
            "message": "Registration successful",
            "email": email,
            "password": password,  # Возвращаем пароль только один раз при регистрации
            "token": create_local_jwt(new_user.id)
        }), 201
        
    except Exception as e:
        print(f"Bot register error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Server Error"}), 500

# ❗️❗️❗️ ЭНДПОИНТ ДЛЯ БОТА: ПОЛУЧЕНИЕ ЛОГИНА И ПАРОЛЯ ❗️❗️❗️
@app.route('/api/bot/get-credentials', methods=['POST'])
@limiter.limit("10 per minute")
def bot_get_credentials():
    """
    Получить логин (email) и пароль пользователя для входа на сайте.
    Пароль возвращается из зашифрованного хранилища, если доступен.
    """
    data = request.json
    telegram_id = data.get('telegram_id')
    
    if not telegram_id:
        return jsonify({"message": "telegram_id is required"}), 400
    
    try:
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            return jsonify({"message": "User not found"}), 404
        
        if not user.email:
            return jsonify({"message": "User has no email/login"}), 404
        
        # Проверяем, есть ли пароль
        has_password = bool(user.password_hash and user.password_hash != '')
        
        # Пытаемся расшифровать пароль, если он сохранен
        password = None
        if user.encrypted_password and app.config.get('FERNET_KEY') and fernet:
            try:
                password = fernet.decrypt(user.encrypted_password.encode()).decode()
            except Exception as e:
                print(f"Error decrypting password: {e}")
                password = None
        
        result = {
            "email": user.email,
            "has_password": has_password
        }
        
        if password:
            result["password"] = password
        elif not has_password:
            result["message"] = "No password set"
        else:
            result["message"] = "Password not available (contact support to reset)"
        
        return jsonify(result), 200
    
    except Exception as e:
        print(f"Bot get credentials error: {e}")
        return jsonify({"message": "Internal Server Error"}), 500

# ❗️❗️❗️ ЭНДПОИНТ №30: АКТИВАЦИЯ ПРОМОКОДА (КЛИЕНТ) ❗️❗️❗️
@app.route('/api/client/activate-promocode', methods=['POST'])
def activate_promocode():
    user = get_user_from_token()
    if not user: return jsonify({"message": "Auth Error"}), 401
    
    code_str = request.json.get('code')
    if not code_str: return jsonify({"message": "Введите код"}), 400
    
    # 1. Ищем код
    promo = PromoCode.query.filter_by(code=code_str).first()
    if not promo:
        return jsonify({"message": "Неверный промокод"}), 404
        
    if promo.uses_left <= 0:
        return jsonify({"message": "Промокод больше не действителен"}), 400

    # 2. Применяем (Пока поддерживаем только DAYS)
    if promo.promo_type == 'DAYS':
        try:
            admin_headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
            # Получаем текущую дату истечения
            resp_user = requests.get(f"{API_URL}/api/users/{user.remnawave_uuid}", headers=admin_headers)
            if not resp_user.ok: return jsonify({"message": "Ошибка API провайдера"}), 500
            
            live_data = resp_user.json().get('response', {})
            current_expire_at = parse_iso_datetime(live_data.get('expireAt'))
            now = datetime.now(timezone.utc)
            
            # Если подписка истекла, добавляем к "сейчас". Если активна — продлеваем.
            base_date = max(now, current_expire_at)
            new_expire_date = base_date + timedelta(days=promo.value)
            
            patch_payload = { 
                "uuid": user.remnawave_uuid, 
                "expireAt": new_expire_date.isoformat(),
                "activeInternalSquads": [DEFAULT_SQUAD_ID] 
            }
            requests.patch(f"{API_URL}/api/users", headers={"Content-Type": "application/json", **admin_headers}, json=patch_payload)
            
            # 3. Списываем использование
            promo.uses_left -= 1
            db.session.commit()
            
            # 4. Чистим кэш
            cache.delete(f'live_data_{user.remnawave_uuid}')
            cache.delete(f'nodes_{user.remnawave_uuid}')  # Очищаем кэш серверов
            
            return jsonify({"message": f"Успешно! Добавлено {promo.value} дней."}), 200
            
        except Exception as e:
            return jsonify({"message": str(e)}), 500
    
    return jsonify({"message": "Этот тип кода нужно использовать во вкладке Тарифы"}), 400
# ----------------------------------------------------

def init_database():
    """
    Инициализирует базу данных при первом запуске.
    Создает все таблицы и дефолтные настройки, если БД не существует.
    Для миграции существующих БД используйте скрипт migrate_payment_systems.py
    """
    import os
    import json
    import sqlite3
    
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    db_exists = os.path.exists(db_path) if db_path else False
    
    # Флаг для отслеживания миграции payment_setting
    payment_migration_performed = False
    
    # Откатываем любые незавершенные транзакции
    try:
        db.session.rollback()
    except:
        pass
    
    # ВСЕГДА создаем все таблицы (если их нет, они будут созданы)
    # Это гарантирует, что все таблицы существуют перед проверкой записей
    db.create_all()
    
    # Проверяем, что все необходимые таблицы созданы и имеют все колонки
    # Если таблиц нет, создаем их явно через raw SQL
    # Если таблицы есть, но не хватает колонок, добавляем их
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем наличие ключевых таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_setting'")
        payment_table_exists = cursor.fetchone() is not None
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_setting'")
        system_table_exists = cursor.fetchone() is not None
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='currency_rate'")
        currency_rate_table_exists = cursor.fetchone() is not None
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
        user_table_exists = cursor.fetchone() is not None
        
        # Проверяем и добавляем поле balance в таблицу user, если его нет
        if user_table_exists:
            cursor.execute("PRAGMA table_info(user)")
            user_columns = [col[1] for col in cursor.fetchall()]
            if 'balance' not in user_columns:
                print("⚠️  Добавление колонки balance в user...")
                try:
                    cursor.execute("ALTER TABLE user ADD COLUMN balance REAL NOT NULL DEFAULT 0.0")
                    cursor.execute("UPDATE user SET balance = 0.0 WHERE balance IS NULL")
                    conn.commit()
                    print("✓ Колонка balance добавлена в user")
                except Exception as e:
                    print(f"⚠️  Ошибка при добавлении колонки balance: {e}")
                    conn.rollback()
        
        # Проверяем наличие таблицы tariff
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tariff'")
        tariff_table_exists = cursor.fetchone() is not None
        
        # Проверяем и добавляем поле hwid_device_limit в таблицу tariff, если его нет
        if tariff_table_exists:
            cursor.execute("PRAGMA table_info(tariff)")
            tariff_columns = [col[1] for col in cursor.fetchall()]
            if 'hwid_device_limit' not in tariff_columns:
                print("⚠️  Добавление колонки hwid_device_limit в tariff...")
                try:
                    cursor.execute("ALTER TABLE tariff ADD COLUMN hwid_device_limit INTEGER DEFAULT 0")
                    cursor.execute("UPDATE tariff SET hwid_device_limit = 0 WHERE hwid_device_limit IS NULL")
                    conn.commit()
                    print("✓ Колонка hwid_device_limit добавлена в tariff")
                except Exception as e:
                    print(f"⚠️  Ошибка при добавлении колонки hwid_device_limit: {e}")
                    conn.rollback()
            
            # Обновляем список колонок после возможного добавления
            cursor.execute("PRAGMA table_info(tariff)")
            tariff_columns = [col[1] for col in cursor.fetchall()]
            
            if 'bonus_days' not in tariff_columns:
                print("⚠️  Добавление колонки bonus_days в tariff...")
                try:
                    cursor.execute("ALTER TABLE tariff ADD COLUMN bonus_days INTEGER DEFAULT 0")
                    conn.commit()
                    print("✓ Колонка bonus_days добавлена в tariff")
                except Exception as e:
                    print(f"⚠️  Ошибка при добавлении колонки bonus_days: {e}")
                    conn.rollback()
        
        # Проверяем наличие таблицы system_setting
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_setting'")
        system_setting_table_exists = cursor.fetchone() is not None
        
        # Проверяем и добавляем поля active_languages и active_currencies в таблицу system_setting, если их нет
        if system_setting_table_exists:
            cursor.execute("PRAGMA table_info(system_setting)")
            system_setting_columns = [col[1] for col in cursor.fetchall()]
            default_languages = '["ru","ua","en","cn"]'
            default_currencies = '["uah","rub","usd"]'
            
            if 'active_languages' not in system_setting_columns:
                print("⚠️  Добавление колонки active_languages в system_setting...")
                try:
                    # В SQLite нельзя использовать параметризованные запросы в ALTER TABLE с DEFAULT
                    cursor.execute("ALTER TABLE system_setting ADD COLUMN active_languages TEXT")
                    cursor.execute("UPDATE system_setting SET active_languages = ?", (default_languages,))
                    conn.commit()
                    print("✓ Колонка active_languages добавлена в system_setting")
                except Exception as e:
                    print(f"⚠️  Ошибка при добавлении колонки active_languages: {e}")
                    conn.rollback()
            
            if 'active_currencies' not in system_setting_columns:
                print("⚠️  Добавление колонки active_currencies в system_setting...")
                try:
                    # В SQLite нельзя использовать параметризованные запросы в ALTER TABLE с DEFAULT
                    cursor.execute("ALTER TABLE system_setting ADD COLUMN active_currencies TEXT")
                    cursor.execute("UPDATE system_setting SET active_currencies = ?", (default_currencies,))
                    conn.commit()
                    print("✓ Колонка active_currencies добавлена в system_setting")
                except Exception as e:
                    print(f"⚠️  Ошибка при добавлении колонки active_currencies: {e}")
                    conn.rollback()
            
            # Обновляем список колонок для проверки полей темы
            cursor.execute("PRAGMA table_info(system_setting)")
            system_setting_columns = [col[1] for col in cursor.fetchall()]
            
            # Колонки для настройки темы
            theme_columns = [
                ('theme_primary_color', '#3f69ff'),
                ('theme_bg_primary', '#f8fafc'),
                ('theme_bg_secondary', '#eef2ff'),
                ('theme_text_primary', '#0f172a'),
                ('theme_text_secondary', '#64748b'),
                ('theme_primary_color_dark', '#6c7bff'),
                ('theme_bg_primary_dark', '#050816'),
                ('theme_bg_secondary_dark', '#0f172a'),
                ('theme_text_primary_dark', '#e2e8f0'),
                ('theme_text_secondary_dark', '#94a3b8'),
            ]
            
            for col_name, default_value in theme_columns:
                # Обновляем список колонок перед каждой проверкой
                cursor.execute("PRAGMA table_info(system_setting)")
                system_setting_columns = [col[1] for col in cursor.fetchall()]
                
                if col_name not in system_setting_columns:
                    print(f"⚠️  Добавление колонки {col_name} в system_setting...")
                    try:
                        cursor.execute(f"ALTER TABLE system_setting ADD COLUMN {col_name} VARCHAR(20) DEFAULT '{default_value}'")
                        cursor.execute(f"UPDATE system_setting SET {col_name} = '{default_value}' WHERE {col_name} IS NULL")
                        conn.commit()
                        print(f"✓ Колонка {col_name} добавлена в system_setting")
                    except Exception as e:
                        print(f"⚠️  Ошибка при добавлении колонки {col_name}: {e}")
                        conn.rollback()
        
        # Если таблица payment_setting не существует, создаем её явно
        if not payment_table_exists:
            print("⚠️  Таблица payment_setting не найдена, создаем её...")
            cursor.execute("""
                CREATE TABLE payment_setting (
                    id INTEGER PRIMARY KEY,
                    crystalpay_api_key TEXT,
                    crystalpay_api_secret TEXT,
                    heleket_api_key TEXT,
                    telegram_bot_token TEXT,
                    yookassa_api_key TEXT,
                    yookassa_shop_id TEXT,
                    yookassa_secret_key TEXT,
                    cryptobot_api_key TEXT,
                    platega_api_key TEXT,
                    platega_merchant_id TEXT,
                    mulenpay_api_key TEXT,
                    mulenpay_secret_key TEXT,
                    mulenpay_shop_id TEXT,
                    urlpay_api_key TEXT,
                    urlpay_secret_key TEXT,
                    urlpay_shop_id TEXT,
                    monobank_token TEXT,
                    btcpayserver_url TEXT,
                    btcpayserver_api_key TEXT,
                    btcpayserver_store_id TEXT,
                    tribute_api_key TEXT,
                    robokassa_merchant_login TEXT,
                    robokassa_password1 TEXT,
                    robokassa_password2 TEXT,
                    freekassa_shop_id TEXT,
                    freekassa_secret TEXT,
                    freekassa_secret2 TEXT
                )
            """)
            conn.commit()
            print("✓ Таблица payment_setting создана")
        else:
            # Таблица существует - проверяем, есть ли все необходимые колонки
            # Если колонок не хватает, помечаем, что нужно использовать raw SQL
            # (миграцию колонок выполняет отдельный скрипт migrate_payment_systems.py)
            cursor.execute("PRAGMA table_info(payment_setting)")
            existing_columns = [col[1] for col in cursor.fetchall()]
            
            # Список всех необходимых колонок (включая новые)
            required_columns = [
                'platega_api_key', 'platega_merchant_id', 
                'mulenpay_api_key', 'mulenpay_secret_key', 'mulenpay_shop_id', 
                'urlpay_api_key', 'urlpay_secret_key', 'urlpay_shop_id', 
                'monobank_token',
                'btcpayserver_url', 'btcpayserver_api_key', 'btcpayserver_store_id',
                'tribute_api_key',
                'robokassa_merchant_login', 'robokassa_password1', 'robokassa_password2',
                'freekassa_shop_id', 'freekassa_secret', 'freekassa_secret2'
            ]
            
            # Проверяем, какие колонки отсутствуют
            missing_columns = [col for col in required_columns if col not in existing_columns]
            
            # Если есть недостающие колонки, добавляем их автоматически
            if missing_columns:
                payment_migration_performed = True
                print(f"⚠️  В таблице payment_setting отсутствуют {len(missing_columns)} колонок")
                print("   Добавляем недостающие колонки автоматически...")
                
                # Маппинг колонок и их типов
                column_types = {
                    'platega_api_key': 'TEXT',
                    'platega_merchant_id': 'TEXT',
                    'mulenpay_api_key': 'TEXT',
                    'mulenpay_secret_key': 'TEXT',
                    'mulenpay_shop_id': 'TEXT',
                    'urlpay_api_key': 'TEXT',
                    'urlpay_secret_key': 'TEXT',
                    'urlpay_shop_id': 'TEXT',
                    'monobank_token': 'TEXT',
                    'btcpayserver_url': 'TEXT',
                    'btcpayserver_api_key': 'TEXT',
                    'btcpayserver_store_id': 'TEXT',
                    'tribute_api_key': 'TEXT',
                    'robokassa_merchant_login': 'TEXT',
                    'robokassa_password1': 'TEXT',
                    'robokassa_password2': 'TEXT',
                    'freekassa_shop_id': 'TEXT',
                    'freekassa_secret': 'TEXT',
                    'freekassa_secret2': 'TEXT'
                }
                
                # Добавляем каждую недостающую колонку
                for col_name in missing_columns:
                    if col_name in column_types:
                        try:
                            cursor.execute(f"ALTER TABLE payment_setting ADD COLUMN {col_name} {column_types[col_name]}")
                            print(f"✓ Колонка {col_name} добавлена")
                        except sqlite3.OperationalError as e:
                            if "duplicate column name" in str(e).lower():
                                print(f"✓ Колонка {col_name} уже существует")
                            else:
                                print(f"⚠️  Ошибка при добавлении колонки {col_name}: {e}")
                
                conn.commit()
                print("✓ Недостающие колонки добавлены")
            else:
                payment_migration_performed = False
        
        # Если таблица system_setting не существует, создаем её явно
        if not system_table_exists:
            print("⚠️  Таблица system_setting не найдена, создаем её...")
            cursor.execute("""
                CREATE TABLE system_setting (
                    id INTEGER PRIMARY KEY,
                    default_language VARCHAR(10) NOT NULL DEFAULT 'ru',
                    default_currency VARCHAR(10) NOT NULL DEFAULT 'uah',
                    show_language_currency_switcher BOOLEAN DEFAULT 1 NOT NULL
                )
            """)
            conn.commit()
            print("✓ Таблица system_setting создана (с колонкой show_language_currency_switcher)")
        else:
            # Таблица существует - проверяем наличие колонки show_language_currency_switcher
            cursor.execute("PRAGMA table_info(system_setting)")
            existing_columns = [col[1] for col in cursor.fetchall()]
            
            if 'show_language_currency_switcher' not in existing_columns:
                print("⚠️  Добавление колонки show_language_currency_switcher в system_setting...")
                try:
                    cursor.execute("""
                        ALTER TABLE system_setting 
                        ADD COLUMN show_language_currency_switcher BOOLEAN DEFAULT 1 NOT NULL
                    """)
                    # Устанавливаем значение по умолчанию для существующих записей
                    cursor.execute("""
                        UPDATE system_setting 
                        SET show_language_currency_switcher = 1 
                        WHERE show_language_currency_switcher IS NULL
                    """)
                    conn.commit()
                    print("✓ Колонка show_language_currency_switcher добавлена")
                except Exception as e:
                    print(f"⚠️  Ошибка при добавлении колонки: {e}")
                    conn.rollback()
        
        # Если таблица currency_rate не существует, создаем её явно
        if not currency_rate_table_exists:
            print("⚠️  Таблица currency_rate не найдена, создаем её...")
            cursor.execute("""
                CREATE TABLE currency_rate (
                    id INTEGER PRIMARY KEY,
                    currency VARCHAR(10) NOT NULL UNIQUE,
                    rate_to_usd REAL NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            print("✓ Таблица currency_rate создана")
        
        conn.close()
    except Exception as e:
        print(f"⚠️  Ошибка при проверке/создании таблиц: {e}")
        import traceback
        traceback.print_exc()
    
    # Если БД не существовала, выводим сообщение
    if not db_exists:
        print("📦 Создание новой базы данных...")
        print("✓ Все таблицы созданы")
        should_init = True
    else:
        # БД существует - проверяем, нужно ли инициализировать настройки
        # Используем ORM, так как таблицы уже должны быть созданы
        try:
            system_count = SystemSetting.query.count()
            payment_count = PaymentSetting.query.count()
            should_init = (system_count == 0 or payment_count == 0)
        except Exception as e:
            # Если ORM не работает, пробуем через raw SQL
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM system_setting")
                system_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM payment_setting")
                payment_count = cursor.fetchone()[0]
                conn.close()
                should_init = (system_count == 0 or payment_count == 0)
            except Exception as sql_error:
                print(f"⚠️  Ошибка при проверке БД: {sql_error}")
                should_init = False
    
    if should_init:
        print("📦 Инициализация дефолтных настроек...")
    
    if should_init:
        # 1. SystemSetting
        try:
            system_exists = SystemSetting.query.first() is not None
        except:
            system_exists = False
        
        if not system_exists:
            system_setting = SystemSetting(
                id=1,
                default_language='ru',
                default_currency='uah',
                show_language_currency_switcher=True
            )
            db.session.add(system_setting)
            db.session.commit()
            print("✓ SystemSetting инициализирован")
        
        # 2. ReferralSetting
        try:
            referral_exists = ReferralSetting.query.first() is not None
        except:
            referral_exists = False
        
        if not referral_exists:
            referral_setting = ReferralSetting(
                invitee_bonus_days=7,
                referrer_bonus_days=7,
                trial_squad_id=None
            )
            db.session.add(referral_setting)
            db.session.commit()
            print("✓ ReferralSetting инициализирован")
        
        # 3. PaymentSetting
        # Если колонок не хватает, ВСЕГДА используем raw SQL (не пытаемся ORM)
        # чтобы избежать ошибок из-за несоответствия схемы
        try:
            if payment_migration_performed:
                # Используем raw SQL, если колонок не хватает
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM payment_setting WHERE id = 1")
                payment_exists = cursor.fetchone()[0] > 0
                conn.close()
            else:
                # Используем ORM, если все колонки на месте
                payment_exists = PaymentSetting.query.first() is not None
        except:
            # Если ORM не работает, пробуем через raw SQL
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM payment_setting WHERE id = 1")
                payment_exists = cursor.fetchone()[0] > 0
                conn.close()
            except:
                payment_exists = False
        
        if not payment_exists:
            # Если колонок не хватает, используем ТОЛЬКО raw SQL
            if payment_migration_performed:
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    # Проверяем еще раз перед вставкой
                    cursor.execute("SELECT COUNT(*) FROM payment_setting WHERE id = 1")
                    if cursor.fetchone()[0] == 0:
                        cursor.execute("INSERT INTO payment_setting (id) VALUES (1)")
                        conn.commit()
                        print("✓ PaymentSetting инициализирован (через SQL, колонки неполные)")
                    else:
                        print("✓ PaymentSetting уже существует")
                    conn.close()
                except sqlite3.IntegrityError as e:
                    if 'UNIQUE constraint' in str(e):
                        print("✓ PaymentSetting уже существует")
                    else:
                        print(f"⚠️  Ошибка при создании PaymentSetting через SQL: {e}")
                except Exception as e:
                    print(f"⚠️  Ошибка при создании PaymentSetting через SQL: {e}")
            else:
                # Используем ORM, если все колонки на месте
                try:
                    payment_setting = PaymentSetting(id=1)
                    db.session.add(payment_setting)
                    db.session.commit()
                    print("✓ PaymentSetting инициализирован")
                except Exception as e:
                    print(f"⚠️  Ошибка при создании PaymentSetting через ORM: {e}")
                    # Если ORM не работает, пробуем через raw SQL
                    try:
                        db.session.rollback()
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        # Проверяем еще раз перед вставкой
                        cursor.execute("SELECT COUNT(*) FROM payment_setting WHERE id = 1")
                        if cursor.fetchone()[0] == 0:
                            cursor.execute("INSERT INTO payment_setting (id) VALUES (1)")
                            conn.commit()
                            print("✓ PaymentSetting инициализирован (через SQL после ошибки ORM)")
                        else:
                            print("✓ PaymentSetting уже существует")
                        conn.close()
                    except sqlite3.IntegrityError as e2:
                        if 'UNIQUE constraint' in str(e2):
                            print("✓ PaymentSetting уже существует")
                        else:
                            print(f"⚠️  Ошибка при создании PaymentSetting через SQL: {e2}")
                    except Exception as e2:
                        print(f"⚠️  Ошибка при создании PaymentSetting через SQL: {e2}")
                        try:
                            db.session.rollback()
                        except:
                            pass
        
        # 4. BrandingSetting
        try:
            branding_exists = BrandingSetting.query.first() is not None
        except:
            branding_exists = False
        
        if not branding_exists:
            branding_setting = BrandingSetting(
                id=1,
                logo_url=None,
                site_name=SERVICE_NAME,
                site_subtitle=None,
                primary_color="#3F69FF",
                secondary_color="#ffffff",
                accent_color="#3F69FF",
                login_welcome_text=None,
                register_welcome_text=None,
                footer_text=None,
                dashboard_servers_title=None,
                dashboard_servers_description=None,
                dashboard_tariffs_title=None,
                dashboard_tariffs_description=None,
                dashboard_tagline=None
            )
            db.session.add(branding_setting)
            db.session.commit()
            print("✓ BrandingSetting инициализирован")
        
        # 5. TariffFeatureSetting
        tiers = ['basic', 'pro', 'elite']
        default_features = {
            'basic': [
                "Базовый уровень защиты",
                "Стандартные серверы",
                "Базовая поддержка"
            ],
            'pro': [
                "Продвинутый уровень защиты",
                "Приоритетные серверы",
                "Приоритетная поддержка",
                "Дополнительные функции"
            ],
            'elite': [
                "Максимальный уровень защиты",
                "Премиум серверы",
                "24/7 приоритетная поддержка",
                "Все функции Pro",
                "Эксклюзивные возможности"
            ]
        }
        
        for tier in tiers:
            try:
                tier_exists = TariffFeatureSetting.query.filter_by(tier=tier).first() is not None
            except:
                tier_exists = False
            
            if not tier_exists:
                features_json = json.dumps(default_features[tier], ensure_ascii=False)
                tariff_feature = TariffFeatureSetting(
                    tier=tier,
                    features=features_json
                )
                db.session.add(tariff_feature)
                db.session.commit()
                print(f"✓ TariffFeatureSetting для '{tier}' инициализирован")
        
        print("✅ База данных инициализирована успешно!")
        print("📝 Следующий шаг: создайте администратора командой:")
        print("   python3 -m flask --app app make-admin ВАШ_EMAIL")
        print()

# Обработка POST запросов к корневому пути /miniapp/
# Miniapp может отправлять POST запросы к /miniapp/ для получения данных подписки
@app.route('/miniapp/', methods=['POST', 'OPTIONS'])
@limiter.limit("30 per minute")
def miniapp_root_post():
    """
    Обработка POST запросов к корневому пути /miniapp/.
    Обрабатывает запросы на получение данных подписки (аналогично /miniapp/subscription).
    """
    # Обработка CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    print(f"[MINIAPP] POST /miniapp/ received")
    print(f"[MINIAPP] Content-Type: {request.content_type}")
    print(f"[MINIAPP] Method: {request.method}")
    print(f"[MINIAPP] Headers: {dict(request.headers)}")
    print(f"[MINIAPP] Args: {dict(request.args)}")
    
    # Проверяем, может ли это быть запрос от формы или навигации
    # Если это запрос с пустым телом и заголовками браузера, возможно это навигация
    if not request.data and not request.form and not request.is_json:
        # Проверяем, может ли это быть запрос на получение статических файлов
        # (например, форма пытается отправить данные, но форма пустая)
        if request.headers.get('Sec-Fetch-Dest') == 'document':
            print(f"[MINIAPP] Possible navigation request detected. Serving index.html")
            # Это может быть запрос на навигацию, отдаем index.html
            import os
            miniapp_dir = get_miniapp_path()
            if miniapp_dir:
                index_path = os.path.join(miniapp_dir, 'index.html')
                if os.path.exists(index_path):
                    return send_file(index_path, mimetype='text/html')
            # Если index.html не найден, перенаправляем на GET
            return redirect('/miniapp/', code=302)
    
    try:
        # Пробуем получить данные из разных источников
        data = {}
        
        # 0. Пробуем получить initData из заголовков (если miniapp отправляет его туда)
        init_data_from_header = request.headers.get('X-Telegram-Init-Data') or request.headers.get('X-Init-Data') or ''
        
        # 1. Пробуем JSON
        try:
            if request.is_json:
                data = request.json or {}
                print(f"[MINIAPP] Data from JSON: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
        except Exception as e:
            print(f"[MINIAPP] Error parsing JSON: {e}")
        
        # 2. Пробуем form-data
        if not data and request.form:
            data = dict(request.form)
            print(f"[MINIAPP] Data from form: {list(data.keys())}")
        
        # 3. Пробуем raw data
        if not data and request.data:
            try:
                import json as json_lib
                raw_data = request.data.decode('utf-8')
                print(f"[MINIAPP] Raw data preview: {raw_data[:200]}")
                # Пробуем распарсить как JSON
                if raw_data.strip().startswith('{') or raw_data.strip().startswith('['):
                    data = json_lib.loads(raw_data)
                    print(f"[MINIAPP] Data from raw JSON: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                else:
                    # Если не JSON, пробуем как URL-encoded
                    import urllib.parse
                    data = urllib.parse.parse_qs(raw_data)
                    # Преобразуем списки в строки
                    data = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in data.items()}
                    print(f"[MINIAPP] Data from URL-encoded: {list(data.keys())}")
            except Exception as e:
                print(f"[MINIAPP] Error parsing raw data: {e}")
        
        # 4. Пробуем получить initData из URL параметров
        init_data_from_args = request.args.get('initData') or request.args.get('init_data') or ''
        
        # Логируем входящие данные для отладки (без чувствительной информации)
        print(f"[MINIAPP] Final data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
        print(f"[MINIAPP] initData from header: {bool(init_data_from_header)}")
        print(f"[MINIAPP] initData from args: {bool(init_data_from_args)}")
        
        # Пробуем получить initData из разных возможных источников
        init_data = (data.get('initData') or 
                    data.get('init_data') or 
                    data.get('data') or 
                    init_data_from_header or 
                    init_data_from_args or 
                    '')
        
        # Пробуем также получить данные из initDataUnsafe (если miniapp отправляет их)
        init_data_unsafe = data.get('initDataUnsafe') or data.get('init_data_unsafe') or {}
        user_from_unsafe = None
        if isinstance(init_data_unsafe, dict):
            user_from_unsafe = init_data_unsafe.get('user')
        elif isinstance(data, dict):
            # Пробуем получить user напрямую из data
            user_from_unsafe = data.get('user')
        
        # Если initData не строка, пробуем преобразовать
        if not isinstance(init_data, str):
            if isinstance(init_data, dict):
                # Если initData уже объект, пробуем извлечь user напрямую
                user_data = init_data.get('user') or init_data
                if isinstance(user_data, dict) and 'id' in user_data:
                    telegram_id = user_data.get('id')
                    if telegram_id:
                        # Пропускаем парсинг, используем данные напрямую
                        user = User.query.filter_by(telegram_id=telegram_id).first()
                        if not user:
                            return jsonify({
                                "detail": {
                                    "title": "User Not Found",
                                    "message": "User not registered. Please register in the bot first.",
                                    "code": "user_not_found"
                                }
                            }), 404
                        # Продолжаем обработку - получаем данные из RemnaWave
                        current_uuid = user.remnawave_uuid
                        cache_key = f'live_data_{current_uuid}'
                        if cached := cache.get(cache_key):
                            response_data = cached.copy()
                            response_data.update({
                                'referral_code': user.referral_code,
                                'preferred_lang': user.preferred_lang,
                                'preferred_currency': user.preferred_currency,
                                'telegram_id': user.telegram_id,
                                'telegram_username': user.telegram_username,
                                'balance': convert_from_usd(float(user.balance) if user.balance else 0.0, user.preferred_currency)
                            })
                            return jsonify(response_data), 200
                        
                        # Получаем данные из RemnaWave API
                        try:
                            resp = requests.get(
                                f"{API_URL}/api/users/{current_uuid}",
                                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                                timeout=10
                            )
                            
                            if resp.status_code != 200:
                                if resp.status_code == 404:
                                    return jsonify({
                                        "detail": {
                                            "title": "Subscription Not Found",
                                            "message": "User not found in VPN system. Please contact support."
                                        }
                                    }), 404
                                return jsonify({
                                    "detail": {
                                        "title": "Subscription Not Found",
                                        "message": f"Failed to fetch subscription data: {resp.status_code}"
                                    }
                                }), 500
                            
                            response_data = resp.json()
                            result_data = response_data.get('response', {}) if isinstance(response_data, dict) else response_data
                            
                            if isinstance(result_data, dict):
                                result_data.update({
                                    'referral_code': user.referral_code,
                                    'preferred_lang': user.preferred_lang,
                                    'preferred_currency': user.preferred_currency,
                                    'telegram_id': user.telegram_id,
                                    'telegram_username': user.telegram_username,
                                    'balance': convert_from_usd(float(user.balance) if user.balance else 0.0, user.preferred_currency)
                                })
                            
                            cache.set(cache_key, result_data, timeout=300)
                            return jsonify(result_data), 200
                        except requests.RequestException as e:
                            print(f"Request Error in miniapp_root_post: {e}")
                            return jsonify({
                                "detail": {
                                    "title": "Subscription Not Found",
                                    "message": f"Failed to connect to VPN system: {str(e)}"
                                }
                            }), 500
                    else:
                        return jsonify({
                            "detail": {
                                "title": "Authorization Error",
                                "message": "Telegram ID not found in initData."
                            }
                        }), 401
                else:
                    return jsonify({
                        "detail": {
                            "title": "Authorization Error",
                            "message": "Invalid initData format: user data not found."
                        }
                    }), 401
            else:
                init_data = str(init_data) if init_data else ''
        
        # Если initData пустой, но есть user из initDataUnsafe, пробуем использовать его
        if not init_data and user_from_unsafe and isinstance(user_from_unsafe, dict) and 'id' in user_from_unsafe:
            telegram_id = user_from_unsafe.get('id')
            if telegram_id:
                print(f"[MINIAPP] Using user data from initDataUnsafe: telegram_id={telegram_id}")
                user = User.query.filter_by(telegram_id=telegram_id).first()
                if not user:
                    return jsonify({
                        "detail": {
                            "title": "User Not Found",
                            "message": "User not registered. Please register in the bot first.",
                            "code": "user_not_found"
                        }
                    }), 404
                # Продолжаем обработку - получаем данные из RemnaWave
                current_uuid = user.remnawave_uuid
                cache_key = f'live_data_{current_uuid}'
                if cached := cache.get(cache_key):
                    response_data = cached.copy()
                    response_data.update({
                        'referral_code': user.referral_code,
                        'preferred_lang': user.preferred_lang,
                        'preferred_currency': user.preferred_currency,
                        'telegram_id': user.telegram_id,
                        'telegram_username': user.telegram_username
                    })
                    return jsonify(response_data), 200
                
                # Получаем данные из RemnaWave API
                try:
                    resp = requests.get(
                        f"{API_URL}/api/users/{current_uuid}",
                        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                        timeout=10
                    )
                    
                    if resp.status_code != 200:
                        if resp.status_code == 404:
                            return jsonify({
                                "detail": {
                                    "title": "Subscription Not Found",
                                    "message": "User not found in VPN system. Please contact support."
                                }
                            }), 404
                        return jsonify({
                            "detail": {
                                "title": "Subscription Not Found",
                                "message": f"Failed to fetch subscription data: {resp.status_code}"
                            }
                        }), 500
                    
                    response_data = resp.json()
                    result_data = response_data.get('response', {}) if isinstance(response_data, dict) else response_data
                    
                    if isinstance(result_data, dict):
                        result_data.update({
                            'referral_code': user.referral_code,
                            'preferred_lang': user.preferred_lang,
                            'preferred_currency': user.preferred_currency,
                            'telegram_id': user.telegram_id,
                            'telegram_username': user.telegram_username
                        })
                    
                    cache.set(cache_key, result_data, timeout=300)
                    return jsonify(result_data), 200
                except requests.RequestException as e:
                    print(f"Request Error in miniapp_root_post: {e}")
                    return jsonify({
                        "detail": {
                            "title": "Subscription Not Found",
                            "message": f"Failed to connect to VPN system: {str(e)}"
                        }
                    }), 500
        
        if not init_data:
            # Если initData отсутствует, возможно miniapp открыт не из Telegram
            # Логируем подробную информацию для отладки
            print(f"[MINIAPP] No initData found. Request details:")
            print(f"  - Content-Type: {request.content_type}")
            print(f"  - Has JSON: {request.is_json}")
            print(f"  - Has form: {bool(request.form)}")
            print(f"  - Has data: {bool(request.data)}")
            print(f"  - Data length: {len(request.data) if request.data else 0}")
            if request.data:
                try:
                    print(f"  - Data preview: {request.data.decode('utf-8')[:500]}")
                except:
                    print(f"  - Data (bytes): {request.data[:100]}")
            
            # Если тело запроса полностью пустое, возможно это запрос на проверку доступности
            # или miniapp открыт не из Telegram
            if not request.data and not request.form and not request.is_json:
                print(f"[MINIAPP] Empty request body detected. This might be a health check or miniapp opened outside Telegram.")
                return jsonify({
                    "detail": {
                        "title": "Authorization Error",
                        "message": "Missing initData. Please open the mini app from Telegram.",
                        "hint": "The mini app must be opened from Telegram to work properly. If you're testing, make sure to open it through Telegram Web App.",
                        "error_code": "MISSING_INIT_DATA"
                    }
                }), 401
            
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Missing initData. Please open the mini app from Telegram.",
                    "hint": "The mini app must be opened from Telegram to work properly.",
                    "error_code": "MISSING_INIT_DATA"
                }
            }), 401
        
        # Парсим initData от Telegram Web App
        # Формат может быть: URL-encoded строка или уже декодированный JSON
        import urllib.parse
        import json as json_lib
        
        telegram_id = None
        user_data = None
        
        # Пробуем разные форматы
        try:
            # Вариант 1: URL-encoded строка (стандартный формат Telegram Web App)
            if '=' in init_data or '&' in init_data:
                parsed_data = urllib.parse.parse_qs(init_data)
                user_str = parsed_data.get('user', [''])[0]
                
                if user_str:
                    # Декодируем JSON из user параметра
                    try:
                        user_data = json_lib.loads(urllib.parse.unquote(user_str))
                        telegram_id = user_data.get('id')
                    except (json_lib.JSONDecodeError, KeyError) as e:
                        print(f"[MINIAPP] Error parsing user from URL-encoded initData: {e}")
                        # Пробуем другой формат
                        pass
        except Exception as e:
            print(f"[MINIAPP] Error parsing URL-encoded initData: {e}")
        
        # Вариант 2: Если не получилось, пробуем как JSON напрямую
        if not telegram_id:
            try:
                # Пробуем декодировать как JSON
                if init_data.startswith('{') or init_data.startswith('['):
                    parsed_json = json_lib.loads(init_data)
                    if isinstance(parsed_json, dict):
                        user_data = parsed_json.get('user') or parsed_json
                        telegram_id = user_data.get('id') if isinstance(user_data, dict) else None
            except (json_lib.JSONDecodeError, AttributeError) as e:
                print(f"[MINIAPP] Error parsing JSON initData: {e}")
        
        # Вариант 3: Если initData уже содержит user объект напрямую
        if not telegram_id and isinstance(data, dict):
            user_obj = data.get('user')
            if isinstance(user_obj, dict) and 'id' in user_obj:
                telegram_id = user_obj.get('id')
                user_data = user_obj
        
        if not telegram_id:
            print(f"[MINIAPP] Failed to extract telegram_id from initData. Format: {type(init_data)}, Preview: {str(init_data)[:100]}")
            return jsonify({
                "detail": {
                    "title": "Authorization Error",
                    "message": "Invalid initData format. Please open the mini app from Telegram."
                }
            }), 401
        
        # Находим пользователя по telegram_id
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            return jsonify({
                "detail": {
                    "title": "User Not Found",
                    "message": "User not registered. Please register in the bot first.",
                    "code": "user_not_found"
                }
            }), 404
        
        # Получаем данные пользователя из RemnaWave (аналогично get_client_me)
        current_uuid = user.remnawave_uuid
        
        # Проверяем кэш
        cache_key = f'live_data_{current_uuid}'
        if cached := cache.get(cache_key):
            # Добавляем данные из локальной БД
            response_data = cached.copy()
            response_data.update({
                'referral_code': user.referral_code,
                'preferred_lang': user.preferred_lang,
                'preferred_currency': user.preferred_currency,
                'telegram_id': user.telegram_id,
                'telegram_username': user.telegram_username
            })
            return jsonify(response_data), 200
        
        # Получаем данные из RemnaWave API
        try:
            resp = requests.get(
                f"{API_URL}/api/users/{current_uuid}",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                timeout=10
            )
            
            if resp.status_code != 200:
                if resp.status_code == 404:
                    return jsonify({
                        "detail": {
                            "title": "Subscription Not Found",
                            "message": "User not found in VPN system. Please contact support."
                        }
                    }), 404
                return jsonify({
                    "detail": {
                        "title": "Subscription Not Found",
                        "message": f"Failed to fetch subscription data: {resp.status_code}"
                    }
                }), 500
            
            response_data = resp.json()
            data = response_data.get('response', {}) if isinstance(response_data, dict) else response_data
            
            # Добавляем данные из локальной БД
            if isinstance(data, dict):
                data.update({
                    'referral_code': user.referral_code,
                    'preferred_lang': user.preferred_lang,
                    'preferred_currency': user.preferred_currency,
                    'telegram_id': user.telegram_id,
                    'telegram_username': user.telegram_username,
                    'balance': convert_from_usd(float(user.balance) if user.balance else 0.0, user.preferred_currency)
                })
            
            # Кэшируем на 5 минут
            cache.set(cache_key, data, timeout=300)
            
            print(f"[MINIAPP] Successfully fetched subscription data for user {telegram_id}")
            print(f"[MINIAPP] Response keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
            if isinstance(data, dict):
                print(f"[MINIAPP] Sample fields: expireAt={data.get('expireAt')}, subscription_url={bool(data.get('subscription_url'))}")
            
            return jsonify(data), 200
            
        except requests.RequestException as e:
            print(f"Request Error in miniapp_root_post: {e}")
            return jsonify({
                "detail": {
                    "title": "Subscription Not Found",
                    "message": f"Failed to connect to VPN system: {str(e)}"
                }
            }), 500
        except Exception as e:
            print(f"Error in miniapp_root_post: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "detail": {
                    "title": "Subscription Not Found",
                    "message": "Internal server error"
                }
            }), 500
            
    except Exception as e:
        print(f"Error parsing initData in miniapp_root_post: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "detail": {
                "title": "Authorization Error",
                "message": "Invalid initData format."
            }
        }), 401

# Маршрут для статических файлов miniapp (должен быть в конце, после всех специфичных маршрутов)
@app.route('/miniapp/', defaults={'path': ''}, methods=['GET', 'HEAD'])
@app.route('/miniapp/<path:path>', methods=['GET', 'HEAD'])
def miniapp_static(path):
    """
    Отдача статических файлов miniapp.
    Этот маршрут должен быть в конце, чтобы не перехватывать специфичные маршруты.
    """
    import os
    miniapp_dir = get_miniapp_path()
    
    if not miniapp_dir:
        return jsonify({"error": "Miniapp directory not found. Set MINIAPP_PATH in .env"}), 404
    
    # Если путь пустой или заканчивается на /, отдаем index.html
    if not path or path.endswith('/'):
        index_path = os.path.join(miniapp_dir, 'index.html')
        if os.path.exists(index_path):
            return send_file(index_path, mimetype='text/html')
        return jsonify({"error": "index.html not found"}), 404
    
    # Безопасность: проверяем, что путь не выходит за пределы директории
    file_path = os.path.join(miniapp_dir, path)
    file_path = os.path.normpath(file_path)
    
    if not file_path.startswith(os.path.normpath(miniapp_dir)):
        return jsonify({"error": "Invalid path"}), 403
    
    if os.path.isfile(file_path):
        # Определяем MIME type по расширению
        mimetype = None
        if path.endswith('.html'):
            mimetype = 'text/html'
        elif path.endswith('.js'):
            mimetype = 'application/javascript'
        elif path.endswith('.css'):
            mimetype = 'text/css'
        elif path.endswith('.json'):
            mimetype = 'application/json'
        elif path.endswith('.png'):
            mimetype = 'image/png'
        elif path.endswith('.jpg') or path.endswith('.jpeg'):
            mimetype = 'image/jpeg'
        elif path.endswith('.svg'):
            mimetype = 'image/svg+xml'
        
        return send_file(file_path, mimetype=mimetype)
    
    # Если файл не найден, но это может быть SPA роутинг - отдаем index.html
    index_path = os.path.join(miniapp_dir, 'index.html')
    if os.path.exists(index_path):
        return send_file(index_path, mimetype='text/html')
    
    return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    with app.app_context():
        init_database()
    app.run(port=5000, debug=False)
    app.run(port=5000, debug=False)
