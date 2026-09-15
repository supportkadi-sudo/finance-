from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.db import Database


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " сум"


def account_name(account: str) -> str:
    return "Карта" if account == "card" else "Наличные"


def _period_bounds(now: datetime, period: str) -> tuple[datetime, datetime, str]:
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now, "Сегодня"

    if period == "week":
        start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return start, now, "Эта неделя"

    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now, "Этот месяц"

    raise ValueError(f"Unknown period: {period}")


def _render(
    rows: list[dict],
    title: str,
    *,
    show_percentages: bool = False,
    show_expense_details: bool = False,
    balances: dict[str, int] | None = None,
) -> str:
    expenses = [row for row in rows if row["kind"] == "expense"]
    incomes = [row for row in rows if row["kind"] == "income"]
    business_out = [row for row in rows if row["kind"] == "business_out"]
    business_in = [row for row in rows if row["kind"] == "business_in"]
    transfers = [row for row in rows if row["kind"] == "transfer"]

    spent = sum(int(row["amount"]) for row in expenses)
    received = sum(int(row["amount"]) for row in incomes)
    sent_to_business = sum(int(row["amount"]) for row in business_out)
    returned_from_business = sum(int(row["amount"]) for row in business_in)

    transfer_totals: dict[str, int] = defaultdict(int)
    for row in transfers:
        transfer_totals[row.get("category") or "Перевод"] += int(row["amount"])

    by_category: dict[str, int] = defaultdict(int)
    for row in expenses:
        by_category[row.get("category") or "Другое"] += int(row["amount"])

    lines = [
        f"📊 {title}",
        "",
        f"Потрачено: {money(spent)}",
        f"Поступило: {money(received)}",
        f"Операций: {len(rows)}",
    ]

    if sent_to_business or returned_from_business:
        lines.extend(["", "↔️ KADI"])
        if sent_to_business:
            lines.append(f"• В оборот: {money(sent_to_business)}")
        if returned_from_business:
            lines.append(f"• Из оборота: {money(returned_from_business)}")

    if transfer_totals:
        lines.extend(["", "🔄 Между своими"])
        for direction, amount in transfer_totals.items():
            lines.append(f"• {direction}: {money(amount)}")

    if by_category:
        lines.extend(["", "Расходы по категориям:"])
        for category, amount in sorted(by_category.items(), key=lambda item: item[1], reverse=True):
            if show_percentages and spent:
                percent = amount / spent * 100
                lines.append(f"• {category}: {money(amount)} · {percent:.0f}%")
            else:
                lines.append(f"• {category}: {money(amount)}")

            if show_expense_details:
                category_rows = [
                    row for row in expenses
                    if (row.get("category") or "Другое") == category
                ]
                for row in category_rows:
                    raw_text = (row.get("raw_text") or "").strip()
                    account = account_name(row.get("account") or "card")
                    if raw_text:
                        lines.append(f"  ↳ {raw_text} · {account}")
                    else:
                        lines.append(
                            f"  ↳ {money(int(row['amount']))} · {account}"
                        )

    if balances is not None:
        total = balances["card"] + balances["cash"]
        lines.extend(
            [
                "",
                "💰 Остаток",
                f"Карта: {money(balances['card'])}",
                f"Наличные: {money(balances['cash'])}",
                f"Всего: {money(total)}",
            ]
        )

    return "\n".join(lines)


async def current_period_report(
    db: Database,
    telegram_id: int,
    timezone: str,
    period: str,
) -> str:
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    start, end, title = _period_bounds(now, period)
    rows = await db.transactions_between(telegram_id, start, end)
    balances = await db.get_balances(telegram_id)
    return _render(
        rows,
        title,
        show_percentages=period in {"week", "month"},
        show_expense_details=period == "today",
        balances=balances,
    )


async def previous_day_report(db: Database, telegram_id: int, timezone: str) -> str:
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)
    rows = await db.transactions_between(telegram_id, start, end)
    balances = await db.get_balances(telegram_id)
    return _render(rows, f"Итоги {start:%d.%m.%Y}", balances=balances)


async def previous_week_report(db: Database, telegram_id: int, timezone: str) -> str:
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    end = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=7)
    rows = await db.transactions_between(telegram_id, start, end)
    balances = await db.get_balances(telegram_id)
    return _render(
        rows,
        f"Итоги недели {start:%d.%m}–{(end - timedelta(days=1)):%d.%m}",
        show_percentages=True,
        balances=balances,
    )


async def previous_month_report(db: Database, telegram_id: int, timezone: str) -> str:
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month_last = end - timedelta(days=1)
    start = previous_month_last.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = await db.transactions_between(telegram_id, start, end)
    balances = await db.get_balances(telegram_id)
    return _render(
        rows,
        f"Итоги {start:%m.%Y}",
        show_percentages=True,
        balances=balances,
    )
