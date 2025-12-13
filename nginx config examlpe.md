---
# Это пример когфига для запуска вручную , если запуск через докер то 127.0.0.1 меняете на api, готовый конфиг в папке nginx

---


 server #Начало

    server_name panel.stealthnet.app; # ❗️ ВАШ IP-АДРЕС СЮДА


    # --- 1. ОБРАБОТКА БЭКЕНДА ---

    # Любой запрос, начинающийся с /api/... 

    location /api/ {

        # 127.0.0.1:5000 — это Gunicorn, который мы запустили

        proxy_pass http://127.0.0.1:5000; 



        # Стандартные заголовки, чтобы бэкенд "понимал", кто к нему пришел

        proxy_set_header Host $host;

        proxy_set_header X-Real-IP $remote_addr;

        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

    }

    # Proxy POST requests to /miniapp/* to backend
    location /miniapp/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }



    # --- 2. ОБРАБОТКА ФРОНТЕНДА ---

    # Любой другой запрос (напр. / или /login или /dashboard)

    location / {

        # Путь к "собранному" React-проекту

        root /var/www/stealthnet-client/build; 



        # Сначала ищем файл

        try_files $uri $uri/ 

        # Если не нашли (напр. /dashboard) - отдаем главный index.html

        # (React Router сам разберется, что показать)

                  /index.html; 

    }


    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/panel.stealthnet.app/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/panel.stealthnet.app/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot

}
server {
    if ($host = panel.stealthnet.app) {
        return 301 https://$host$request_uri;
    } # managed by Certbot



    listen 80;

    server_name panel.stealthnet.app;
    return 404; # managed by Certbot



}

















