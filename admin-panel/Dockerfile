# Multi-stage build для React приложения
FROM node:18-alpine AS build

WORKDIR /app

# Копирование package файлов
COPY package*.json ./

# Установка зависимостей
RUN npm install --legacy-peer-deps

# Копирование исходного кода
COPY . .

# Сборка приложения
RUN npm run build

# Production stage с nginx
FROM nginx:alpine

# Копирование собранного приложения
COPY --from=build /app/build /usr/share/nginx/html

# Копирование конфигурации nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Открытие порта
EXPOSE 80

# Запуск nginx
CMD ["nginx", "-g", "daemon off;"]

