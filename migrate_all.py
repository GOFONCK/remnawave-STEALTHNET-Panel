#!/usr/bin/env python3
"""
Объединенный скрипт миграции базы данных.
Выполняет все миграции в правильном порядке.

Использование:
    python3 migration/migrate_all.py
    или
    python3 migration/migrate_all.py /path/to/stealthnet.db
"""

import sqlite3
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime, timezone

def find_database():
    """Находит путь к базе данных"""
    # Сначала пробуем найти через переменные окружения или стандартные пути
    possible_paths = [
        Path('instance/stealthnet.db'),
        Path('stealthnet.db'),
        Path('/var/www/stealthnet-api/instance/stealthnet.db'),
        Path('/var/www/stealthnet-api/stealthnet.db'),
    ]
    
    # Если есть .env, пробуем прочитать путь из него
    try:
        from dotenv import load_dotenv
        load_dotenv()
        db_uri = os.getenv('SQLALCHEMY_DATABASE_URI', '')
        if db_uri and db_uri.startswith('sqlite:///'):
            db_path = Path(db_uri.replace('sqlite:///', ''))
            if db_path.exists():
                return db_path
    except:
        pass
    
    # Ищем в стандартных путях
    for db_path in possible_paths:
        if db_path.exists():
            return db_path
    
    return None

def check_column_exists(cursor, table_name, column_name):
    """Проверяет, существует ли колонка в таблице"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns

def check_table_exists(cursor, table_name):
    """Проверяет, существует ли таблица"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

def migrate_all(db_path):
    """Выполняет все миграции в правильном порядке"""
    if not os.path.exists(db_path):
        print(f"❌ ОШИБКА: База данных {db_path} не найдена!")
        return False
    
    print(f"📂 Подключение к базе данных: {db_path}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    changes_made = False
    
    try:
        # ============================================
        # 1. МИГРАЦИЯ: Добавление полей Telegram в user
        # ============================================
        print("\n" + "=" * 60)
        print("1️⃣  Миграция: Добавление полей Telegram в user")
        print("=" * 60)
        
        if check_table_exists(cursor, 'user'):
            cursor.execute("PRAGMA table_info(user)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'telegram_id' not in columns:
                print("   ➕ Добавление поля telegram_id...")
                cursor.execute("ALTER TABLE user ADD COLUMN telegram_id INTEGER")
                print("   ✅ Поле telegram_id добавлено")
                changes_made = True
            else:
                print("   ✓ Поле telegram_id уже существует")
            
            if 'telegram_username' not in columns:
                print("   ➕ Добавление поля telegram_username...")
                cursor.execute("ALTER TABLE user ADD COLUMN telegram_username VARCHAR(100)")
                print("   ✅ Поле telegram_username добавлено")
                changes_made = True
            else:
                print("   ✓ Поле telegram_username уже существует")
        else:
            print("   ⚠️  Таблица user не найдена, пропускаем")
        
        # ============================================
        # 2. МИГРАЦИЯ: Добавление поля balance в user
        # ============================================
        print("\n" + "=" * 60)
        print("2️⃣  Миграция: Добавление поля balance в user")
        print("=" * 60)
        
        if check_table_exists(cursor, 'user'):
            if not check_column_exists(cursor, 'user', 'balance'):
                print("   ➕ Добавление поля balance...")
                cursor.execute("ALTER TABLE user ADD COLUMN balance REAL NOT NULL DEFAULT 0.0")
                cursor.execute("UPDATE user SET balance = 0.0 WHERE balance IS NULL")
                print("   ✅ Поле balance добавлено")
                changes_made = True
            else:
                print("   ✓ Поле balance уже существует")
        else:
            print("   ⚠️  Таблица user не найдена, пропускаем")
        
        # ============================================
        # 3. МИГРАЦИЯ: Добавление поля encrypted_password в user
        # ============================================
        print("\n" + "=" * 60)
        print("3️⃣  Миграция: Добавление поля encrypted_password в user")
        print("=" * 60)
        
        if check_table_exists(cursor, 'user'):
            if not check_column_exists(cursor, 'user', 'encrypted_password'):
                print("   ➕ Добавление поля encrypted_password...")
                cursor.execute("ALTER TABLE user ADD COLUMN encrypted_password TEXT")
                print("   ✅ Поле encrypted_password добавлено")
                changes_made = True
            else:
                print("   ✓ Поле encrypted_password уже существует")
        else:
            print("   ⚠️  Таблица user не найдена, пропускаем")
        
        # ============================================
        # 4. МИГРАЦИЯ: Добавление таблицы currency_rate
        # ============================================
        print("\n" + "=" * 60)
        print("4️⃣  Миграция: Создание таблицы currency_rate")
        print("=" * 60)
        
        if not check_table_exists(cursor, 'currency_rate'):
            print("   ➕ Создание таблицы currency_rate...")
            cursor.execute("""
                CREATE TABLE currency_rate (
                    id INTEGER PRIMARY KEY,
                    currency VARCHAR(10) NOT NULL UNIQUE,
                    rate_to_usd REAL NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Инициализируем дефолтные курсы
            default_rates = [
                ('UAH', 40.0),
                ('RUB', 100.0)
            ]
            
            for currency, rate in default_rates:
                cursor.execute("""
                    INSERT INTO currency_rate (currency, rate_to_usd, updated_at)
                    VALUES (?, ?, ?)
                """, (currency, rate, datetime.now(timezone.utc).isoformat()))
                print(f"   ✓ Курс {currency}: 1 USD = {rate} {currency}")
            
            print("   ✅ Таблица currency_rate создана")
            changes_made = True
        else:
            print("   ✓ Таблица currency_rate уже существует")
        
        # ============================================
        # 5. МИГРАЦИЯ: Добавление полей платежных систем в payment_setting
        # ============================================
        print("\n" + "=" * 60)
        print("5️⃣  Миграция: Добавление полей платежных систем в payment_setting")
        print("=" * 60)
        
        if check_table_exists(cursor, 'payment_setting'):
            cursor.execute("PRAGMA table_info(payment_setting)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Список всех полей платежных систем
            payment_fields = {
                # Heleket
                'heleket_api_key': 'TEXT',
                # YooKassa
                'yookassa_shop_id': 'TEXT',
                'yookassa_secret_key': 'TEXT',
                # Platega
                'platega_api_key': 'TEXT',
                'platega_merchant_id': 'TEXT',
                # Mulenpay
                'mulenpay_api_key': 'TEXT',
                'mulenpay_secret_key': 'TEXT',
                'mulenpay_shop_id': 'TEXT',
                # UrlPay
                'urlpay_api_key': 'TEXT',
                'urlpay_secret_key': 'TEXT',
                'urlpay_shop_id': 'TEXT',
                # Monobank
                'monobank_token': 'TEXT',
                # BTCPayServer
                'btcpayserver_url': 'TEXT',
                'btcpayserver_api_key': 'TEXT',
                'btcpayserver_store_id': 'TEXT',
                # Freekassa
                'freekassa_shop_id': 'TEXT',
                'freekassa_secret': 'TEXT',
                'freekassa_secret2': 'TEXT',
                # Robokassa
                'robokassa_merchant_login': 'TEXT',
                'robokassa_password1': 'TEXT',
                'robokassa_password2': 'TEXT',
                # Tribute
                'tribute_api_key': 'TEXT',
                # Telegram Stars
                'telegram_bot_token': 'TEXT',
            }
            
            for col_name, col_type in payment_fields.items():
                if col_name not in columns:
                    print(f"   ➕ Добавление поля {col_name}...")
                    cursor.execute(f"ALTER TABLE payment_setting ADD COLUMN {col_name} {col_type}")
                    print(f"   ✅ Поле {col_name} добавлено")
                    changes_made = True
                else:
                    print(f"   ✓ Поле {col_name} уже существует")
        else:
            print("   ⚠️  Таблица payment_setting не найдена, пропускаем")
        
        # ============================================
        # 6. МИГРАЦИЯ: Добавление поля payment_provider в payment
        # ============================================
        print("\n" + "=" * 60)
        print("6️⃣  Миграция: Добавление поля payment_provider в payment")
        print("=" * 60)
        
        if check_table_exists(cursor, 'payment'):
            if not check_column_exists(cursor, 'payment', 'payment_provider'):
                print("   ➕ Добавление поля payment_provider...")
                cursor.execute("ALTER TABLE payment ADD COLUMN payment_provider VARCHAR(20) DEFAULT 'crystalpay'")
                print("   ✅ Поле payment_provider добавлено")
                changes_made = True
            else:
                print("   ✓ Поле payment_provider уже существует")
        else:
            print("   ⚠️  Таблица payment не найдена, пропускаем")
        
        # ============================================
        # 7. МИГРАЦИЯ: Добавление поля promo_code_id в payment
        # ============================================
        print("\n" + "=" * 60)
        print("7️⃣  Миграция: Добавление поля promo_code_id в payment")
        print("=" * 60)
        
        if check_table_exists(cursor, 'payment'):
            if not check_column_exists(cursor, 'payment', 'promo_code_id'):
                print("   ➕ Добавление поля promo_code_id...")
                cursor.execute("ALTER TABLE payment ADD COLUMN promo_code_id INTEGER")
                print("   ✅ Поле promo_code_id добавлено")
                changes_made = True
            else:
                print("   ✓ Поле promo_code_id уже существует")
        else:
            print("   ⚠️  Таблица payment не найдена, пропускаем")
        
        # ============================================
        # 8. МИГРАЦИЯ: Делаем tariff_id nullable в payment
        # ============================================
        print("\n" + "=" * 60)
        print("8️⃣  Миграция: Делаем tariff_id nullable в payment")
        print("=" * 60)
        
        if check_table_exists(cursor, 'payment'):
            cursor.execute("PRAGMA table_info(payment)")
            columns_info = cursor.fetchall()
            tariff_id_col = next((col for col in columns_info if col[1] == 'tariff_id'), None)
            
            if tariff_id_col:
                is_nullable = not tariff_id_col[3]  # col[3] это notnull
                if not is_nullable:
                    print("   ⚠️  Колонка tariff_id имеет ограничение NOT NULL")
                    print("   🔄 Выполняем миграцию через пересоздание таблицы...")
                    
                    # Создаем резервную копию
                    backup_path = f"{db_path}.backup_tariff_id_{int(datetime.now().timestamp())}"
                    shutil.copy2(db_path, backup_path)
                    print(f"   📝 Резервная копия сохранена: {backup_path}")
                    
                    # Получаем структуру старой таблицы
                    cursor.execute("PRAGMA table_info(payment)")
                    old_columns_info = cursor.fetchall()
                    old_columns = [col[1] for col in old_columns_info]
                    
                    # Получаем все данные
                    cursor.execute("SELECT COUNT(*) FROM payment")
                    payments_count = cursor.fetchone()[0]
                    print(f"   📋 Найдено записей в payment: {payments_count}")
                    
                    # Создаем новую таблицу
                    cursor.execute("""
                        CREATE TABLE payment_new (
                            id INTEGER PRIMARY KEY,
                            order_id VARCHAR(100) UNIQUE NOT NULL,
                            user_id INTEGER NOT NULL,
                            tariff_id INTEGER,
                            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                            amount REAL NOT NULL,
                            currency VARCHAR(5) NOT NULL,
                            created_at DATETIME,
                            payment_system_id VARCHAR(100),
                            payment_provider VARCHAR(20) DEFAULT 'crystalpay',
                            promo_code_id INTEGER,
                            FOREIGN KEY (user_id) REFERENCES user(id),
                            FOREIGN KEY (tariff_id) REFERENCES tariff(id),
                            FOREIGN KEY (promo_code_id) REFERENCES promo_code(id)
                        )
                    """)
                    
                    # Копируем данные
                    if payments_count > 0:
                        # Определяем общие колонки между старой и новой таблицей
                        new_columns = ['id', 'order_id', 'user_id', 'tariff_id', 'status', 'amount', 'currency', 
                                      'created_at', 'payment_system_id', 'payment_provider', 'promo_code_id']
                        
                        # Формируем список колонок, которые есть в обеих таблицах
                        common_cols = [col for col in new_columns if col in old_columns]
                        
                        if common_cols:
                            cols_str = ', '.join(common_cols)
                            cursor.execute(f"INSERT INTO payment_new ({cols_str}) SELECT {cols_str} FROM payment")
                            print(f"   📋 Скопировано данных из колонок: {', '.join(common_cols)}")
                        else:
                            print("   ⚠️  Нет общих колонок для копирования")
                    
                    # Проверяем количество
                    cursor.execute("SELECT COUNT(*) FROM payment")
                    old_count = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM payment_new")
                    new_count = cursor.fetchone()[0]
                    
                    if old_count == new_count:
                        cursor.execute("DROP TABLE payment")
                        cursor.execute("ALTER TABLE payment_new RENAME TO payment")
                        print(f"   ✅ Таблица пересоздана ({new_count} записей сохранено)")
                        changes_made = True
                    else:
                        print(f"   ❌ Ошибка: количество записей не совпадает ({old_count} != {new_count})")
                        cursor.execute("DROP TABLE payment_new")
                        conn.rollback()
                        return False
                else:
                    print("   ✓ Колонка tariff_id уже nullable")
            else:
                print("   ⚠️  Колонка tariff_id не найдена")
        else:
            print("   ⚠️  Таблица payment не найдена, пропускаем")
        
        # ============================================
        # 9. МИГРАЦИЯ: Добавление поля badge в tariff
        # ============================================
        print("\n" + "=" * 60)
        print("9️⃣  Миграция: Добавление поля badge в tariff")
        print("=" * 60)
        
        if check_table_exists(cursor, 'tariff'):
            if not check_column_exists(cursor, 'tariff', 'badge'):
                print("   ➕ Добавление поля badge...")
                cursor.execute("ALTER TABLE tariff ADD COLUMN badge VARCHAR(50)")
                print("   ✅ Поле badge добавлено")
                changes_made = True
            else:
                print("   ✓ Поле badge уже существует")
        else:
            print("   ⚠️  Таблица tariff не найдена, пропускаем")
        
        # ============================================
        # 10. МИГРАЦИЯ: Добавление поля show_language_currency_switcher в system_setting
        # ============================================
        print("\n" + "=" * 60)
        print("🔟 Миграция: Добавление поля show_language_currency_switcher в system_setting")
        print("=" * 60)
        
        if check_table_exists(cursor, 'system_setting'):
            if not check_column_exists(cursor, 'system_setting', 'show_language_currency_switcher'):
                print("   ➕ Добавление поля show_language_currency_switcher...")
                cursor.execute("""
                    ALTER TABLE system_setting 
                    ADD COLUMN show_language_currency_switcher BOOLEAN DEFAULT 1 NOT NULL
                """)
                cursor.execute("""
                    UPDATE system_setting 
                    SET show_language_currency_switcher = 1 
                    WHERE show_language_currency_switcher IS NULL
                """)
                print("   ✅ Поле show_language_currency_switcher добавлено")
                changes_made = True
            else:
                print("   ✓ Поле show_language_currency_switcher уже существует")
        else:
            print("   ⚠️  Таблица system_setting не найдена, пропускаем")
        
        # Сохраняем все изменения
        if changes_made:
            conn.commit()
            print("\n" + "=" * 60)
            print("✅ Все миграции успешно завершены!")
            print("=" * 60)
            
            # Создаем резервную копию после успешной миграции
            backup_path = f"{db_path}.backup_all_migrations_{int(datetime.now().timestamp())}"
            shutil.copy2(db_path, backup_path)
            print(f"\n📝 Резервная копия сохранена: {backup_path}")
        else:
            print("\n" + "=" * 60)
            print("✅ Все необходимые миграции уже выполнены. Изменения не требуются.")
            print("=" * 60)
        
        return True
        
    except sqlite3.Error as e:
        print(f"\n❌ ОШИБКА SQLite: {e}")
        conn.rollback()
        return False
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        conn.close()

def main():
    """Главная функция"""
    print("=" * 60)
    print("  ОБЪЕДИНЕННАЯ МИГРАЦИЯ БАЗЫ ДАННЫХ")
    print("=" * 60)
    print()
    
    # Ищем базу данных
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
        if not db_path.exists():
            print(f"❌ Указанный путь не существует: {db_path}")
            sys.exit(1)
    else:
        db_path = find_database()
    
    if not db_path:
        print("❌ База данных не найдена!")
        print("\nПопробуйте указать путь вручную:")
        print("  python3 migration/migrate_all.py /path/to/stealthnet.db")
        print()
        sys.exit(1)
    
    # Выполняем миграцию
    success = migrate_all(db_path)
    
    if success:
        print("\n📝 Следующие шаги:")
        print("  1. Перезапустите Flask приложение")
        print("  2. Проверьте работу всех функций")
        sys.exit(0)
    else:
        print("\n❌ Миграция завершилась с ошибками!")
        sys.exit(1)

if __name__ == "__main__":
    main()
