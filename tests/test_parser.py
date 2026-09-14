import pytest

from app.parser import ParseError, parse_transaction


@pytest.mark.parametrize(
    ("text", "kind", "amount", "account", "category"),
    [
        ("еда 15k карта", "expense", 15_000, "card", "Еда"),
        ("обед 25к наличные", "expense", 25_000, "cash", "Еда"),
        ("потратил 150к на еду с карты", "expense", 150_000, "card", "Еда"),
        ("минус 32к яндекс наличные", "expense", 32_000, "cash", "Такси"),
        ("+500k карта", "income", 500_000, "card", None),
        ("пришло 1.5m на карту", "income", 1_500_000, "card", None),
        ("прибыль KADI 300k карта", "income", 300_000, "card", None),
        ("200k кредит", "expense", 200_000, "card", "Кредит"),
        ("барбер 150000 карта", "expense", 150_000, "card", "Барбер"),
        ("в KADI 200k карта", "business_out", 200_000, "card", "KADI"),
        ("в оборот KADI 250k карта", "business_out", 250_000, "card", "KADI"),
        ("закинул 300k в KADI карта", "business_out", 300_000, "card", "KADI"),
        ("из KADI 100k карта", "business_in", 100_000, "card", "KADI"),
        ("из оборота KADI 150k карта", "business_in", 150_000, "card", "KADI"),
        ("забрал 200k из KADI карта", "business_in", 200_000, "card", "KADI"),
    ],
)
def test_parser(text, kind, amount, account, category):
    parsed = parse_transaction(text)
    assert parsed.kind == kind
    assert parsed.amount == amount
    assert parsed.account == account
    assert parsed.category == category


def test_fuzzy_existing_category():
    parsed = parse_transaction("барбр 150k карта", existing_categories=["Барбер"])
    assert parsed.category == "Барбер"


def test_missing_account_is_rejected():
    with pytest.raises(ParseError):
        parse_transaction("еда 50k")


def test_small_ambiguous_number_is_rejected():
    with pytest.raises(ParseError):
        parse_transaction("еда 50 карта")
