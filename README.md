# Finance Bot

Личный Telegram-бот для простого учёта денег.

## MVP

- При первом `/start` спрашивает текущий баланс карты и наличных.
- Понимает свободный ввод:
  - `еда 15k карта`
  - `обед 25к наличные`
  - `потратил 150к на еду с карты`
  - `минус 30к яндекс наличные`
  - `+500k карта`
  - `пришло 1.5m на карту`
  - `200k кредит` — кредит по умолчанию списывается с карты.
- Нормализует распространённые категории и не плодит очевидные дубли.
- Новые категории появляются автоматически из текста операции.
- Кнопки: Сегодня, Неделя, Месяц, Баланс, Последние операции.
- Автоотчёты по Asia/Tashkent:
  - каждый день в 00:01;
  - понедельник в 00:05 за прошлую неделю, с процентами по категориям;
  - 1-го числа в 00:10 за прошлый месяц.

## Стек

- Python 3.12
- aiogram 3
- Supabase / PostgreSQL
- APScheduler

Без FastAPI, Redis, Celery и SQLAlchemy: для одного личного бота они пока только добавляют места, где что-то может сломаться.

## Supabase

Создай проект Supabase и выполни SQL из:

`supabase/schema.sql`

Расход/доход и изменение баланса выполняются одной PostgreSQL-функцией `record_transaction`, поэтому операция не может записаться наполовину.

## Настройки

```bash
cp .env.example .env
```

Заполни:

```env
BOT_TOKEN=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
OWNER_TELEGRAM_ID=...
TIMEZONE=Asia/Tashkent
```

`OWNER_TELEGRAM_ID` делает бота приватным. Ключ `service_role` хранится только на сервере и не коммитится в Git.

## Запуск

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

## Тесты

```bash
pip install -r requirements-dev.txt
pytest -q
```
