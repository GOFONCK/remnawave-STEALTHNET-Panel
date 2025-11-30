#!/usr/bin/env python3
"""
Скрипт миграции для добавления новых платежных систем в существующую базу данных.
Добавляет колонки для Platega, Mulenpay и UrlPay в таблицу payment_setting.

Использование:
    python3 migrate_payment_systems.py
"""

import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime

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

# Находим базу данных
db_path = find_database()
if not db_path:
    print("❌ База данных не найдена. Проверьте следующие пути:")
    for p in [Path('instance/stealthnet.db'), Path('stealthnet.db')]:
        print(f"   - {p.absolute()}")
    sys.exit(1)

print(f"📦 Найдена база данных: {db_path.absolute()}")

# Подключаемся к базе данных
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

try:
    # Проверяем существующие колонки
    cursor.execute("PRAGMA table_info(payment_setting)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"📋 Существующие колонки в payment_setting: {', '.join(columns)}")
    print()
    
    changes_made = False
    
    # Колонки для добавления
    new_columns = {
        'platega_api_key': 'TEXT',
        'platega_merchant_id': 'TEXT',
        'mulenpay_api_key': 'TEXT',
        'mulenpay_secret_key': 'TEXT',
        'mulenpay_shop_id': 'TEXT',
        'urlpay_api_key': 'TEXT',
        'urlpay_secret_key': 'TEXT',
        'urlpay_shop_id': 'TEXT',
    }
    
    # Добавляем каждую колонку, если её нет
    for col_name, col_type in new_columns.items():
        if col_name not in columns:
            print(f"➕ Добавляем колонку {col_name}...")
            cursor.execute(f"ALTER TABLE payment_setting ADD COLUMN {col_name} {col_type}")
            print(f"✓ Колонка {col_name} добавлена")
            changes_made = True
        else:
            print(f"✓ Колонка {col_name} уже существует")
    
    # Сохраняем изменения
    if changes_made:
        conn.commit()
        print()
        print("✅ Миграция успешно завершена!")
        
        # Создаем резервную копию после успешной миграции
        backup_path = f"{db_path}.backup_{int(datetime.now().timestamp())}"
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"📝 Резервная копия сохранена: {backup_path}")
    else:
        print()
        print("✅ Все необходимые колонки уже существуют. Миграция не требуется.")
    
    # Показываем финальную структуру таблицы
    print()
    cursor.execute("PRAGMA table_info(payment_setting)")
    final_columns = [row[1] for row in cursor.fetchall()]
    print(f"📋 Финальные колонки в payment_setting: {', '.join(final_columns)}")
    
except sqlite3.Error as e:
    print(f"❌ Ошибка при выполнении миграции: {e}")
    conn.rollback()
    sys.exit(1)
finally:
    conn.close()

