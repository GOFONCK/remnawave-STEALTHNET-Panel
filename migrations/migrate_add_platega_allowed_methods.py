"""
Скрипт: добавляет столбец platega_allowed_methods в таблицу payment_setting

Запуск:
    python migrate_add_platega_allowed_methods.py
    или
    python3 migrate_add_platega_allowed_methods.py
"""
import sqlite3
import sys
from pathlib import Path


def find_database():
    for db_path in [
        Path("instance/stealthnet.db"),
        Path("stealthnet.db"),
        Path("/var/www/stealthnet-api/instance/stealthnet.db"),
        Path("/var/www/stealthnet-api/stealthnet.db"),
    ]:
        if db_path.exists():
            return db_path
    return None


db_path = find_database()
if not db_path:
    print("⚠️ База данных не найдена. Укажите путь вручную, если она в другом месте.")
    sys.exit(1)

print(f"➡️ Используем БД: {db_path.absolute()}")

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

try:
    cursor.execute("PRAGMA table_info(payment_setting)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Текущие поля payment_setting: {', '.join(columns)}")

    if "platega_allowed_methods" not in columns:
        print("➕ Добавляем столбец platega_allowed_methods...")
        cursor.execute("ALTER TABLE payment_setting ADD COLUMN platega_allowed_methods TEXT")
        conn.commit()
        print("✅ Миграция выполнена.")
    else:
        print("ℹ️ platega_allowed_methods уже существует, изменений не требуется.")

    cursor.execute("PRAGMA table_info(payment_setting)")
    final_columns = [row[1] for row in cursor.fetchall()]
    print(f"Итоговые поля payment_setting: {', '.join(final_columns)}")

except sqlite3.Error as e:
    print(f"❌ Ошибка миграции: {e}")
    conn.rollback()
    sys.exit(1)
finally:
    conn.close()
