# Парсер vseinstrumenti

Парсер для сайта vseinstrumenti.ru с API для подключения к удобному сервису для доставки уведомлений (планируется Telegram bot).

## Возможности

- Наблюдение за набором карточек товаров (добавление по URL или числовому id товара).
- Настраиваемый интервал проверки: глобальный + переопределение на товар.
- Ручной запуск проверки через API.
- История состояний и история цен для графиков.
- Лента событий: `price_changed`, `went_out_of_stock`, `back_in_stock`,
  `discount_started`, `discount_ended`, `promo_changed`, `parse_failed`.
- Авторизация по API-ключу. Модель данных с `tenant_id` для нескольких пользователей.
- Абстрагированный транспорт (fetcher): httpx по умолчанию, точки расширения под
  прокси / headless / внешние сервисы.
- Глобальный rate-limit и джиттер расписания для избежания бана.

## Архитектура

- `api` (FastAPI) - REST, управление watchlist, чтение состояния/истории/событий.
- `scheduler` - выбирает товары с наступившим `next_check_at` и ставит задачи в очередь.
- `worker` - выполняет цикл fetch → parse → diff → persist → events.
- PostgreSQL - данные и история. Redis - очередь и rate-limit.

Структура кода описана в `app/` (`api`, `core`, `db`, `fetch`, `parse`, `monitor`, `worker`).

## Запуск

```
cp .env.example .env
# Заполнить .env: пароли, BOOTSTRAP_API_KEY, TARGET_CITY
docker-compose up --build
```

При старте контейнер `api` применяет миграции (`alembic upgrade head`) и создает
tenant по `BOOTSTRAP_API_KEY`. API на `http://localhost:8000`,
Swagger - на `/docs`, метрики Prometheus - на `/metrics`.

## Локальный запуск

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# офлайн-тесты
pytest tests/test_extractor.py tests/test_urls.py tests/test_diff.py
ruff check app tests
```

## API

- `POST /v1/products` - добавить товар (`{"ref": "<url|id>"}`).
- `GET /v1/products` / `GET /v1/products/{id}` - список / карточка с текущим состоянием.
- `PATCH /v1/products/{id}` - интервал, активность.
- `DELETE /v1/products/{id}` - удалить карточку.
- `POST /v1/products/{id}/check` - ручная проверка одного товара.
- `POST /v1/products/check` - массовая проверка.
- `GET /v1/products/{id}/snapshots` - история состояний.
- `GET /v1/products/{id}/price-history` - точки для графика.
- `GET /v1/events` - лента событий (`type`, `product_id`, `since`, `until`).
- `GET /v1/jobs/{id}` - статус задачи проверки.
- `POST|GET|DELETE /v1/webhooks` - вебхуки.
- `GET /health`, `GET /metrics`.

## Проблемы 

 - Сырой curl на сайт vseinstrumenti.ru отдает 403 из-за антибот системы.
 - Playwright парсер также отдает 403.
 - Живой автоматизированный Chromium браузер выдает капчу при заходе.
 - Подмена реальных Cookie не тестировалась, предположительно будет капча.
 - После нескольих запросов при реальном заходе с браузера сайт также отдает капчу.

## Решение

 - Cookie-harvest не работает: curl_cffi с TLS Firefox и полными cookie все равно 403 (нужен живой JS на каждый запрос).
 - Работает headed patchright + постоянный профиль на чистом IP: `FETCHER_BACKEND=playwright`, `headless=false`, `channel=chromium`.
 - На сервере без экрана - через `xvfb`. Челлендж решается один раз, дальше держится в профиле.
 - Проверено: 200, парсинг цены/наличия за ~3с. Для 10k - низкая параллельность + большие интервалы.
 - Установка: `pip install -e ".[browser]"` и `patchright install chromium`.
 - В Docker worker крутит headed Chromium под Xvfb (образ `Dockerfile.worker`), профиль в volume `browserprofile`.
 - Под Xvfb нужен спуфинг WebGL (software-GL палится) - уже вшит в fetcher.
 - Если worker начал стабильно ловить капчу - профиль «отравлен», очистить volume: `docker compose down && docker volume rm vseinstrumenti_browserprofile`.
 - Запуск всего стека: `docker compose up --build` (первый билд worker тянет браузер, ~пара минут).
