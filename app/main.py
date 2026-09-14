from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, TelegramObject
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.db import Database
from app.keyboards import main_keyboard
from app.parser import ParseError, parse_amount, parse_transaction
from app.reports import (
    account_name,
    current_period_report,
    money,
    previous_day_report,
    previous_month_report,
    previous_week_report,
)


logging.basicConfig(level=logging.INFO)
router = Router()
db = Database()


class Onboarding(StatesGroup):
    card = State()
    cash = State()


class OwnerOnlyMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user and user.id != settings.owner_telegram_id:
            if isinstance(event, Message):
                await event.answer("Этот бот приватный.")
            return None
        return await handler(event, data)


def _balance_input(text: str) -> int:
    if text.strip() == "0":
        return 0
    amount, _ = parse_amount(text, allow_small=True)
    return amount


async def _ensure_ready(message: Message) -> bool:
    user = await db.get_user(message.from_user.id)
    if not user or not user.get("initialized_at"):
        await message.answer("Сначала нажми /start и задай стартовый баланс.")
        return False
    return True


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    user = await db.ensure_user(message.from_user.id)
    if user.get("initialized_at"):
        balances = await db.get_balances(message.from_user.id)
        await message.answer(
            "Учёт уже запущен. Просто пиши расходы и доходы обычным сообщением.\n\n"
            f"Карта: {money(balances['card'])}\n"
            f"Наличные: {money(balances['cash'])}",
            reply_markup=main_keyboard,
        )
        return

    await state.set_state(Onboarding.card)
    await message.answer(
        "Для начала зафиксируем реальные деньги.\n\n"
        "Сколько сейчас на карте?\n"
        "Можно написать: 2500000, 2.5m или 2.5 млн"
    )


@router.message(Onboarding.card)
async def onboarding_card(message: Message, state: FSMContext) -> None:
    try:
        card = _balance_input(message.text or "")
    except ParseError as exc:
        await message.answer(str(exc))
        return

    await state.update_data(card=card)
    await state.set_state(Onboarding.cash)
    await message.answer("Сколько сейчас наличными?")


@router.message(Onboarding.cash)
async def onboarding_cash(message: Message, state: FSMContext) -> None:
    try:
        cash = _balance_input(message.text or "")
    except ParseError as exc:
        await message.answer(str(exc))
        return

    data = await state.get_data()
    card = int(data["card"])
    await db.set_initial_balances(message.from_user.id, card, cash)
    await state.clear()

    await message.answer(
        "Готово. Стартовая точка зафиксирована.\n\n"
        f"Карта: {money(card)}\n"
        f"Наличные: {money(cash)}\n"
        f"Всего: {money(card + cash)}\n\n"
        "Теперь можно писать, например:\n"
        "еда 50k карта\n"
        "такси 30к наличные\n"
        "+500k карта",
        reply_markup=main_keyboard,
    )


@router.message(Command("balance"))
@router.message(F.text.casefold() == "баланс")
async def balance(message: Message) -> None:
    if not await _ensure_ready(message):
        return
    balances = await db.get_balances(message.from_user.id)
    await message.answer(
        f"💰 Баланс\n\n"
        f"Карта: {money(balances['card'])}\n"
        f"Наличные: {money(balances['cash'])}\n"
        f"Всего: {money(balances['card'] + balances['cash'])}"
    )


async def _send_period(message: Message, period: str) -> None:
    if not await _ensure_ready(message):
        return
    text = await current_period_report(db, message.from_user.id, settings.timezone, period)
    await message.answer(text)


@router.message(Command("today"))
@router.message(F.text.casefold() == "сегодня")
async def today(message: Message) -> None:
    await _send_period(message, "today")


@router.message(Command("week"))
@router.message(F.text.casefold() == "неделя")
async def week(message: Message) -> None:
    await _send_period(message, "week")


@router.message(Command("month"))
@router.message(F.text.casefold() == "месяц")
async def month(message: Message) -> None:
    await _send_period(message, "month")


@router.message(Command("last"))
@router.message(F.text.casefold() == "последние операции")
async def last(message: Message) -> None:
    if not await _ensure_ready(message):
        return

    rows = await db.recent_transactions(message.from_user.id, limit=10)
    if not rows:
        await message.answer("Операций пока нет.")
        return

    tz = ZoneInfo(settings.timezone)
    lines = ["🧾 Последние операции", ""]
    for row in rows:
        created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).astimezone(tz)
        kind = row["kind"]
        if kind == "income":
            sign, category = "+", "Доход"
        elif kind == "business_out":
            sign, category = "↗", "В KADI"
        elif kind == "business_in":
            sign, category = "↙", "Из KADI"
        else:
            sign, category = "−", row.get("category") or "Другое"
        lines.append(
            f"{created:%d.%m %H:%M} · {sign}{money(int(row['amount']))} · "
            f"{category} · {account_name(row['account'])}"
        )

    await message.answer("\n".join(lines))


@router.message(Command("undo"))
@router.message(F.text.casefold() == "отменить последнюю")
async def undo_last(message: Message) -> None:
    if not await _ensure_ready(message):
        return

    result = await db.undo_last_transaction(message.from_user.id)
    if not result:
        await message.answer("Отменять нечего: операций пока нет.")
        return

    if result["kind"] == "income":
        sign, label = "+", "Доход"
    elif result["kind"] == "business_out":
        sign, label = "↗", "В KADI"
    elif result["kind"] == "business_in":
        sign, label = "↙", "Из KADI"
    else:
        sign, label = "−", result.get("category") or "Другое"
    card = int(result["card_balance"])
    cash = int(result["cash_balance"])

    await message.answer(
        f"↩️ Отменено: {sign}{money(int(result['amount']))} · "
        f"{label} · {account_name(result['account'])}\n\n"
        f"Карта: {money(card)}\n"
        f"Наличные: {money(cash)}\n"
        f"Всего: {money(card + cash)}"
    )


@router.message(F.text)
async def transaction(message: Message) -> None:
    if not await _ensure_ready(message):
        return

    categories = await db.list_categories(message.from_user.id)
    try:
        parsed = parse_transaction(message.text, existing_categories=categories)
    except ParseError as exc:
        await message.answer(
            f"Не записал: {exc}\n\n"
            "Примеры:\n"
            "еда 50k карта\n"
            "минус 30к такси наличные\n"
            "+500k карта\n"
            "в KADI 200k карта\n"
            "из KADI 100k карта"
        )
        return

    result = await db.record_transaction(
        message.from_user.id,
        kind=parsed.kind,
        amount=parsed.amount,
        category=parsed.category,
        account=parsed.account,
        raw_text=parsed.raw_text,
    )

    now = datetime.now(ZoneInfo(settings.timezone))
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await db.transactions_between(message.from_user.id, start, now + timedelta(seconds=1))
    spent_today = sum(int(row["amount"]) for row in rows if row["kind"] == "expense")

    card = int(result["card_balance"])
    cash = int(result["cash_balance"])

    if parsed.kind == "business_out":
        headline = f"↗️ В KADI: {money(parsed.amount)} · {account_name(parsed.account)}"
    elif parsed.kind == "business_in":
        headline = f"↙️ Из KADI: {money(parsed.amount)} · {account_name(parsed.account)}"
    else:
        sign = "+" if parsed.kind == "income" else "−"
        label = parsed.category or "Доход"
        headline = f"✅ {sign}{money(parsed.amount)} · {label} · {account_name(parsed.account)}"

    await message.answer(
        f"{headline}\n\n"
        f"Сегодня потрачено: {money(spent_today)}\n"
        f"Карта: {money(card)}\n"
        f"Наличные: {money(cash)}\n"
        f"Всего: {money(card + cash)}"
    )


async def send_daily(bot: Bot) -> None:
    text = await previous_day_report(db, settings.owner_telegram_id, settings.timezone)
    await bot.send_message(settings.owner_telegram_id, text)


async def send_weekly(bot: Bot) -> None:
    text = await previous_week_report(db, settings.owner_telegram_id, settings.timezone)
    await bot.send_message(settings.owner_telegram_id, text)


async def send_monthly(bot: Bot) -> None:
    text = await previous_month_report(db, settings.owner_telegram_id, settings.timezone)
    await bot.send_message(settings.owner_telegram_id, text)


async def main() -> None:
    bot = Bot(settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(OwnerOnlyMiddleware())
    dp.include_router(router)

    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(send_daily, "cron", hour=0, minute=1, args=[bot], id="daily-report", replace_existing=True)
    scheduler.add_job(
        send_weekly, "cron", day_of_week="mon", hour=0, minute=5,
        args=[bot], id="weekly-report", replace_existing=True,
    )
    scheduler.add_job(
        send_monthly, "cron", day=1, hour=0, minute=10,
        args=[bot], id="monthly-report", replace_existing=True,
    )
    scheduler.start()

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
