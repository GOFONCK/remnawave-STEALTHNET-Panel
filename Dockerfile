FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем файлы зависимостей
COPY requirements.txt .
COPY client_bot_requirements.txt .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r client_bot_requirements.txt

# Копируем весь проект (включая миграции, если они есть)
COPY . .

# Создаем директорию для базы данных и кэша
RUN mkdir -p instance cache logs

# Устанавливаем рабочую директорию для instance
ENV INSTANCE_PATH=/app/instance

# Устанавливаем права на выполнение
RUN chmod +x app.py client_bot.py

# Открываем порты
EXPOSE 5000

# Команда по умолчанию (запуск Flask API)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app:app"]

