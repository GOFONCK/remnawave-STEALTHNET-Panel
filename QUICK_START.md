# ⚡ Быстрый старт - StealthNET VPN

Минимальная инструкция для быстрого запуска проекта.

## 📋 Предварительные требования

- Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- Docker и Docker Compose установлены
- Минимум 2GB RAM
- Домен или IP адрес сервера

## 🚀 Установка за 5 минут

### 1. Установите Docker (если еще не установлен)

```bash
# Устанавливаем Docker одной командой (работает на Ubuntu/Debian/CentOS)
sudo curl -fsSL https://get.docker.com | sh

# Если вы используете не root пользователя, добавьте его в группу docker:
# sudo usermod -aG docker $USER
# newgrp docker

# Проверка
docker --version
docker compose version
```

### 2. Клонируйте проект на сервер

```bash
cd /opt
git clone https://github.com/GOFONCK/STEALTHNET-Admin-Panel.git
cd STEALTHNET-Admin-Panel
```

### 3. Настройте переменные окружения

```bash
# Генерируем ключи
chmod +x generate_keys.sh
./generate_keys.sh

# Создаем .env файл
cp .env.example .env
nano .env  # Заполните минимум:
# - JWT_SECRET_KEY (скопируйте из generate_keys.sh)
# - FERNET_KEY (скопируйте из generate_keys.sh)
# - API_URL
# - ADMIN_TOKEN
# - DEFAULT_SQUAD_ID
# - CLIENT_BOT_TOKEN
# - YOUR_SERVER_IP
```

### 4. Проверьте frontend build

```bash
# Frontend build должен быть уже в проекте из GitHub:
ls -la frontend/build/

# Если его нет, соберите React проект и скопируйте:
# cp -r /path/to/admin-panel/build/* frontend/build/
```

### 5. Запустите проект

```bash
# Используйте скрипт запуска
chmod +x start.sh
./start.sh

# Или вручную:
docker compose build
docker compose up -d  # База данных создастся автоматически при первом запуске
```

### 6. Проверьте работу

```bash
# Статус
docker compose ps

# Логи
docker compose logs -f

# API
curl http://localhost:5000/api/public/health
```

## ✅ Готово!

Откройте в браузере: `http://your-server-ip` или `https://your-domain`

---

**Подробная инструкция**: [INSTALLATION.md](./INSTALLATION.md)

