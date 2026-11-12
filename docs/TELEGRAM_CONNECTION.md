# Подключение настоящего Telegram-бота и хостинга (когда будете готовы)

Сейчас проект работает только на ТЕСТОВЫХ данных. К Telegram он не подключён,
бот не написан (этап 3), хостинга нет. Этот файл — чек-лист на будущее.

## Что требует настоящего BOT_TOKEN
1. Создать бота: Telegram → @BotFather → /newbot → получить токен.
2. Вписать токен в `.env` (только на своём компьютере/сервере, не в чат и не в git).
3. Проверка подписи `initData` на реальных данных от Telegram (сейчас проверена только на тестовых).
4. Бот (этап 3): приветствие, выбор языка, кнопка Mini App, уведомления администратору.
5. Настройка кнопки меню / Mini App в @BotFather (/setmenubutton или /newapp).

## Что требует внешнего хостинга
1. Сервер (VPS) или платформа, работающая 24/7: без него бот и магазин не доступны круглосуточно.
2. Домен и HTTPS-сертификат (Let's Encrypt бесплатен). Telegram открывает Mini App только по HTTPS.
3. Публичный адрес Mini App -> `WEBAPP_URL`, а адрес фронтенда добавить в `CORS_ORIGINS` (https).
4. PostgreSQL (по желанию; SQLite работает без него): `DATABASE_URL=postgresql+psycopg://...`
   и `pip install -r requirements-postgres.txt`.
5. Реверс-прокси (nginx): HTTPS, `client_max_body_size`, лимит запросов,
   `uvicorn --proxy-headers --forwarded-allow-ips=<адрес прокси>`.
6. Регулярный вынос резервных копий (`backend/backups`) с сервера в другое место (cron + python -m app.services.backup).
7. Процесс-менеджер (systemd/docker) для автозапуска и перезапуска.

## Переключение с тестового режима на боевой
- В `.env`: `APP_ENV=production`, настоящий `BOT_TOKEN`, свой `SECRET_KEY` и `ADMIN_PASSWORD`, `DEBUG=false`,
  `CORS_ORIGINS` только https-адреса.
- В production сервер не запустится с тестовым токеном (метка TEST_ONLY), с DEBUG=true, с `*` в CORS.
- Тестовые файлы (`.env.test`, `test_local.db`, `test_uploads/`, `test_backups/`) на сервер не переносить.

## Не заявляйте «работает 24/7», пока бот и сайт не развёрнуты на реальном хостинге и не проверены.
