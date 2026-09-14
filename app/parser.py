from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal


TransactionKind = Literal["income", "expense"]
Account = Literal["card", "cash"]


@dataclass(slots=True)
class ParsedTransaction:
    kind: TransactionKind
    amount: int
    account: Account
    category: str | None
    raw_text: str


class ParseError(ValueError):
    pass


AMOUNT_RE = re.compile(
    r"(?<!\w)(\d+(?:[ ]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"(?:\s*(к|k|тыс\.?|тысяч(?:а|и)?|м|m|млн|миллион(?:а|ов)?))?(?!\w)",
    re.IGNORECASE,
)

CARD_RE = re.compile(r"\b(карта|карты|карту|карте|картой|card)\b", re.IGNORECASE)
CASH_RE = re.compile(r"\b(наличные|наличка|налом|нал|кэш|cash)\b", re.IGNORECASE)

INCOME_WORDS = {
    "плюс", "пришло", "пришли", "получил", "получила", "заработал",
    "заработала", "доход", "поступило", "закинул", "закинули", "вернули",
}
EXPENSE_WORDS = {
    "минус", "потратил", "потратила", "потрачено", "купил", "купила",
    "заплатил", "заплатила", "оплатил", "оплатила", "расход", "ушло",
}
STOP_WORDS = {
    "на", "с", "со", "из", "за", "в", "во", "по", "для", "от", "до",
    "мне", "я", "мы", "это", "ещё", "еще",
}

CATEGORY_ALIASES: dict[str, set[str]] = {
    "Еда": {
        "еда", "еду", "поел", "поела", "покушал", "покушала", "обед", "ужин",
        "завтрак", "ресторан", "кафе", "кофе", "фастфуд", "шаурма", "донер",
        "ош", "плов", "продукты", "продукт", "магазин продуктов",
    },
    "Такси": {"такси", "яндекс", "yandex", "uber", "yandex go"},
    "Кредит": {"кредит", "кредиту", "кредита", "займ", "платёж по кредиту", "платеж по кредиту"},
    "Покупки": {
        "покупка", "покупки", "одежда", "обувь", "техника", "маркетплейс",
        "корзинка", "uzum",
    },
    "Развлечения": {"развлечения", "кино", "игры", "игра", "клуб", "боулинг", "караоке"},
    "Подписки": {"подписка", "подписки", "netflix", "spotify", "youtube"},
    "Здоровье": {"здоровье", "аптека", "лекарства", "лекарство", "врач", "стоматолог"},
    "Транспорт": {"бензин", "топливо", "метро", "автобус", "парковка", "парковку"},
    "Подарки": {"подарок", "подарки", "подарил", "подарила"},
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().replace("ё", "е"))


def parse_amount(text: str, *, allow_small: bool = False) -> tuple[int, tuple[int, int]]:
    match = AMOUNT_RE.search(_normalize(text))
    if not match:
        raise ParseError("Не нашёл сумму. Например: 150k, 150000 или 1.5m.")

    number_raw = match.group(1).replace(" ", "").replace(",", ".")
    suffix = (match.group(2) or "").lower().rstrip(".")

    try:
        value = float(number_raw)
    except ValueError as exc:
        raise ParseError("Не смог разобрать сумму.") from exc

    if suffix in {"к", "k", "тыс", "тысяч", "тысяча", "тысячи"}:
        value *= 1_000
    elif suffix in {"м", "m", "млн", "миллион", "миллиона", "миллионов"}:
        value *= 1_000_000

    amount = int(round(value))
    if amount < 0:
        raise ParseError("Сумма не может быть отрицательной внутри записи.")
    if amount == 0:
        return 0, match.span()

    if not suffix and amount < 1_000 and not allow_small:
        raise ParseError("Слишком маленькая сумма без суффикса. Напиши, например, 15k или 15000.")

    return amount, match.span()


def _detect_kind(text: str) -> TransactionKind:
    normalized = _normalize(text)
    if normalized.startswith("+"):
        return "income"
    if normalized.startswith("-"):
        return "expense"

    words = set(re.findall(r"[a-zа-я]+", normalized))
    if words & INCOME_WORDS:
        return "income"
    if words & EXPENSE_WORDS:
        return "expense"
    return "expense"


def _detect_account(text: str) -> Account | None:
    normalized = _normalize(text)
    if CASH_RE.search(normalized):
        return "cash"
    if CARD_RE.search(normalized):
        return "card"
    return None


def _known_category(text: str) -> str | None:
    normalized = _normalize(text)
    for category, aliases in CATEGORY_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
                return category
    return None


def _candidate_category(text: str, amount_span: tuple[int, int]) -> str:
    normalized = _normalize(text)
    start, end = amount_span
    cleaned = normalized[:start] + " " + normalized[end:]
    cleaned = CARD_RE.sub(" ", cleaned)
    cleaned = CASH_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("+", " ").replace("-", " ")

    remove_words = INCOME_WORDS | EXPENSE_WORDS | STOP_WORDS
    tokens = [
        token for token in re.findall(r"[a-zа-я0-9]+", cleaned)
        if token not in remove_words
    ]
    if not tokens:
        return "Другое"
    return " ".join(tokens[:3]).strip().capitalize()


def _match_existing(candidate: str, existing_categories: list[str]) -> str | None:
    best_name: str | None = None
    best_score = 0.0
    candidate_norm = _normalize(candidate)

    for name in existing_categories:
        score = SequenceMatcher(None, candidate_norm, _normalize(name)).ratio()
        if score > best_score:
            best_score = score
            best_name = name

    return best_name if best_score >= 0.86 else None


def parse_transaction(text: str, existing_categories: list[str] | None = None) -> ParsedTransaction:
    normalized = _normalize(text)
    if not normalized:
        raise ParseError("Пустое сообщение.")

    kind = _detect_kind(normalized)
    amount, amount_span = parse_amount(normalized)
    if amount <= 0:
        raise ParseError("Сумма должна быть больше нуля.")

    known = _known_category(normalized)
    if kind == "income":
        category = None
    elif known:
        category = known
    else:
        candidate = _candidate_category(normalized, amount_span)
        category = _match_existing(candidate, existing_categories or []) or candidate

    account = _detect_account(normalized)
    if account is None and category == "Кредит":
        account = "card"

    if account is None:
        raise ParseError("Не вижу «карта» или «наличные». Например: еда 50k карта.")

    return ParsedTransaction(
        kind=kind,
        amount=amount,
        account=account,
        category=category,
        raw_text=text.strip(),
    )
