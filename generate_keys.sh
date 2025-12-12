#!/bin/bash
# Скрипт для генерации ключей для .env файла

echo "=========================================="
echo "  Генерация ключей для StealthNET VPN"
echo "=========================================="
echo ""

# Генерация JWT_SECRET_KEY
echo "JWT_SECRET_KEY:"
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
echo ""

# Генерация FERNET_KEY
echo "FERNET_KEY:"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
echo ""

echo "=========================================="
echo "Скопируйте эти ключи в ваш .env файл"
echo "=========================================="

