import os
from flask import Flask, request, jsonify, render_template, current_app
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
FERNET_KEY_STR = os.getenv("FERNET_KEY")
BOT_API_URL = os.getenv("BOT_API_URL", "")  # URL веб-API бота (например, http://localhost:8080)
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN", "")  # Токен для доступа к API бота
TELEGRAM_BOT_NAME = os.getenv("TELEGRAM_BOT_NAME", "")  # Имя бота для Telegram Login Widget

app = Flask(__name__)

# CORS
CORS(app, resources={r"/api/.*": {"origins": ["http://localhost:3000", YOUR_SERVER_IP_OR_DOMAIN]}})

# База данных и Секреты
app.config['JWT_SECRET_KEY'] = os.getenv("JWT_SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stealthnet.db'
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
app.config['MAIL_DEFAULT_SENDER'] = ('StealthNET', app.config['MAIL_USERNAME'])

# Лимитер (Защита от спама запросами)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["2000 per day", "500 per hour"],
    storage_uri="memory://"
)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
fernet = Fernet(app.config['FERNET_KEY'])
mail = Mail(app)


# ----------------------------------------------------
# МОДЕЛИ БАЗЫ ДАННЫХ
# ----------------------------------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True)  # Nullable для Telegram пользователей
    password_hash = db.Column(db.String(128), nullable=True)  # Nullable для Telegram пользователей
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
    tier = db.Column(db.String(20), nullable=True)  # Уровень тарифа: 'basic', 'pro', 'elite' (если NULL - определяется автоматически)
    badge = db.Column(db.String(50), nullable=True)  # Бейдж тарифа (например, 'top_sale', NULL = без бейджа)

class PromoCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    promo_type = db.Column(db.String(20), nullable=False, default='PERCENT')
    value = db.Column(db.Integer, nullable=False) 
    uses_left = db.Column(db.Integer, nullable=False, default=1) 

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
    yookassa_api_key = db.Column(db.Text, nullable=True)
    cryptobot_api_key = db.Column(db.Text, nullable=True)

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    default_language = db.Column(db.String(10), default='ru', nullable=False)
    default_currency = db.Column(db.String(10), default='uah', nullable=False)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(100), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tariff_id = db.Column(db.Integer, db.ForeignKey('tariff.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='PENDING') 
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(5), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    payment_system_id = db.Column(db.String(100), nullable=True)
    payment_provider = db.Column(db.String(20), nullable=True, default='crystalpay')  # 'crystalpay' или 'heleket'
    promo_code_id = db.Column(db.Integer, db.ForeignKey('promo_code.id'), nullable=True)  # Промокод, использованный при оплате 


# ----------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ----------------------------------------------------
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
    return fernet.encrypt(key.encode('utf-8'))

def decrypt_key(key):
    if not key: return ""
    try: return fernet.decrypt(key).decode('utf-8')
    except Exception: return ""

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
            admin_headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
            resp = requests.get(f"{API_URL}/api/users/{referrer_uuid}", headers=admin_headers)
            if resp.ok:
                live_data = resp.json().get('response', {})
                curr = datetime.fromisoformat(live_data.get('expireAt'))
                new_exp = max(datetime.now(timezone.utc), curr) + timedelta(days=bonus_days)
                requests.patch(f"{API_URL}/api/users", 
                             headers={"Content-Type": "application/json", **admin_headers}, 
                             json={ "uuid": referrer_uuid, "expireAt": new_exp.isoformat() })
                cache.delete(f'live_data_{referrer_uuid}')
        except Exception as e: print(f"[ФОН] ОШИБКА: {e}")

def send_email_in_background(app_context, recipient, subject, html_body):
    with app_context:
        try:
            msg = Message(subject, recipients=[recipient])
            msg.html = html_body
            mail.send(msg)
        except Exception as e:
            print(f"[EMAIL] ОШИБКА: {e}")


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
        resp = requests.post(f"{API_URL}/api/users", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}, json=payload_create)
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
        html = render_template('email_verification.html', verification_url=url)
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
            data.update({
                'referral_code': user.referral_code, 
                'preferred_lang': user.preferred_lang, 
                'preferred_currency': user.preferred_currency,
                'telegram_id': user.telegram_id,
                'telegram_username': user.telegram_username
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
        
        requests.patch(f"{API_URL}/api/users", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}, 
                       json={"uuid": user.remnawave_uuid, "expireAt": new_exp, "activeInternalSquads": [trial_squad_id]})
        cache.delete(f'live_data_{user.remnawave_uuid}')
        cache.delete('all_live_users_map')
        cache.delete(f'nodes_{user.remnawave_uuid}')  # Очищаем кэш серверов при изменении сквада
        return jsonify({"message": "Trial activated"}), 200
    except Exception as e: return jsonify({"message": "Internal Error"}), 500

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
        resp = requests.get(f"{API_URL}/api/users/{user.remnawave_uuid}/accessible-nodes", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
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
            resp = requests.get(f"{API_URL}/api/users", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
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
        try:
            requests.delete(f"{API_URL}/api/users/{u.remnawave_uuid}", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
        except: pass
        cache.delete('all_live_users_map')
        db.session.delete(u); db.session.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception as e: return jsonify({"message": str(e)}), 500

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
        "tier": t.tier,
        "badge": t.badge
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
        
        nt = Tariff(
            name=d['name'], 
            duration_days=int(d['duration_days']), 
            price_uah=float(d['price_uah']), 
            price_rub=float(d['price_rub']), 
            price_usd=float(d['price_usd']),
            squad_id=d.get('squad_id'),  # Опциональное поле
            traffic_limit_bytes=traffic_limit,
            tier=tier,
            badge=badge
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
            "tier": nt.tier,
            "badge": nt.badge
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
                "tier": t.tier,
                "badge": t.badge
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
        html_body = render_template('email_broadcast.html', subject=subject, message=message)
        
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
        "badge": t.badge
    } for t in Tariff.query.all()]), 200

@app.route('/api/client/settings', methods=['POST'])
def set_settings():
    user = get_user_from_token()
    if not user: return jsonify({"message": "Auth Error"}), 401
    d = request.json
    if 'lang' in d: user.preferred_lang = d['lang']
    if 'currency' in d: user.preferred_currency = d['currency']
    db.session.commit()
    return jsonify({"message": "OK"}), 200

# --- SYSTEM SETTINGS (Default Language & Currency) ---
@app.route('/api/admin/system-settings', methods=['GET', 'POST'])
@admin_required
def system_settings(current_admin):
    s = SystemSetting.query.first() or SystemSetting(id=1)
    if not s.id: db.session.add(s); db.session.commit()
    
    if request.method == 'GET':
        return jsonify({
            "default_language": s.default_language,
            "default_currency": s.default_currency
        }), 200
    
    # POST - обновление
    try:
        data = request.json
        if 'default_language' in data:
            if data['default_language'] not in ['ru', 'ua', 'cn']:
                return jsonify({"message": "Invalid language"}), 400
            s.default_language = data['default_language']
        if 'default_currency' in data:
            if data['default_currency'] not in ['uah', 'rub', 'usd']:
                return jsonify({"message": "Invalid currency"}), 400
            s.default_currency = data['default_currency']
        db.session.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

# --- PAYMENT & SUPPORT ---

@app.route('/api/admin/payment-settings', methods=['GET', 'POST'])
@admin_required
def pay_settings(current_admin):
    s = PaymentSetting.query.first() or PaymentSetting()
    if not s.id: db.session.add(s); db.session.commit()
    if request.method == 'POST':
        d = request.json
        s.crystalpay_api_key = encrypt_key(d.get('crystalpay_api_key', ''))
        s.crystalpay_api_secret = encrypt_key(d.get('crystalpay_api_secret', ''))
        s.heleket_api_key = encrypt_key(d.get('heleket_api_key', ''))
        s.telegram_bot_token = encrypt_key(d.get('telegram_bot_token', ''))
        db.session.commit()
    return jsonify({
        "crystalpay_api_key": decrypt_key(s.crystalpay_api_key), 
        "crystalpay_api_secret": decrypt_key(s.crystalpay_api_secret),
        "heleket_api_key": decrypt_key(s.heleket_api_key),
        "telegram_bot_token": decrypt_key(s.telegram_bot_token)
    }), 200

@app.route('/api/client/create-payment', methods=['POST'])
def create_payment():
    user = get_user_from_token()
    if not user: return jsonify({"message": "Auth Error"}), 401
    try:
        # 🛡️ TYPE CHECK
        tid = request.json.get('tariff_id')
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
        
        else:
            # CrystalPay API (по умолчанию)
            login = decrypt_key(s.crystalpay_api_key)
            secret = decrypt_key(s.crystalpay_api_secret)
            
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
    t = db.session.get(Tariff, p.tariff_id)
    
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
    
    requests.patch(f"{API_URL}/api/users", headers={"Content-Type": "application/json", **h}, json=patch_payload)
    
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
    
    patch_resp = requests.patch(f"{API_URL}/api/users", headers={"Content-Type": "application/json", **h}, json=patch_payload)
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

@app.route('/api/webhook/telegram', methods=['POST'])
def telegram_webhook():
    """Webhook для обработки платежей Telegram Stars"""
    try:
        update = request.json
        if not update:
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
                    return jsonify({"ok": True}), 200
                
                if p.status == 'PAID':
                    print(f"Telegram successful payment: Payment already paid for order_id={order_id}")
                    return jsonify({"ok": True}), 200
                
                u = db.session.get(User, p.user_id)
                t = db.session.get(Tariff, p.tariff_id)
                
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
                
                patch_resp = requests.patch(f"{API_URL}/api/users", headers={"Content-Type": "application/json", **h}, json=patch_payload)
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
        return jsonify({"ok": True}), 200  # Всегда возвращаем успех, чтобы Telegram не повторял запрос

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
        html = render_template('email_verification.html', verification_url=url)
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
            current_expire_at = datetime.fromisoformat(live_data.get('expireAt'))
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not ReferralSetting.query.first(): db.session.add(ReferralSetting()); db.session.commit()
        if not PaymentSetting.query.first(): db.session.add(PaymentSetting(id=1)); db.session.commit()
        if not SystemSetting.query.first(): db.session.add(SystemSetting(id=1)); db.session.commit()
    app.run(port=5000, debug=False)