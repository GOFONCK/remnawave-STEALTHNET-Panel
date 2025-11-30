"""
Миграция: Добавление полей yookassa_shop_id и yookassa_secret_key в таблицу payment_setting

Использование:
    python migrate_add_yookassa_fields.py
    или
    python3 migrate_add_yookassa_fields.py
"""
import sqlite3
import os
import sys
from pathlib import Path

def find_database():
    """Находит путь к базе данных"""
    possible_paths = [
        Path('instance/stealthnet.db'),
        Path('stealthnet.db'),
        Path('/var/www/stealthnet-api/instance/stealthnet.db'),
        Path('/var/www/stealthnet-api/stealthnet.db'),
    ]
    
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
    
    changes_made = False
    
    # Добавляем yookassa_shop_id, если его нет
    if 'yookassa_shop_id' not in columns:
        print("➕ Добавляем колонку yookassa_shop_id...")
        cursor.execute("ALTER TABLE payment_setting ADD COLUMN yookassa_shop_id TEXT")
        print("✓ Колонка yookassa_shop_id добавлена")
        changes_made = True
    else:
        print("✓ Колонка yookassa_shop_id уже существует")
    
    # Добавляем yookassa_secret_key, если его нет
    if 'yookassa_secret_key' not in columns:
        print("➕ Добавляем колонку yookassa_secret_key...")
        cursor.execute("ALTER TABLE payment_setting ADD COLUMN yookassa_secret_key TEXT")
        print("✓ Колонка yookassa_secret_key добавлена")
        changes_made = True
    else:
        print("✓ Колонка yookassa_secret_key уже существует")
    
    # Сохраняем изменения
    if changes_made:
        conn.commit()
        print("\n✅ Миграция успешно завершена!")
    else:
        print("\n✅ Все необходимые колонки уже существуют. Миграция не требуется.")
    
    # Показываем финальную структуру таблицы
    cursor.execute("PRAGMA table_info(payment_setting)")
    final_columns = [row[1] for row in cursor.fetchall()]
    print(f"📋 Финальные колонки в payment_setting: {', '.join(final_columns)}")
    
except sqlite3.Error as e:
    print(f"❌ Ошибка при выполнении миграции: {e}")
    conn.rollback()
    sys.exit(1)
finally:
    conn.close()

