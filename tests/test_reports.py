from app.reports import _render


def test_business_transfers_do_not_count_as_income_or_expense():
    rows = [
        {"kind": "expense", "amount": 50_000, "category": "Еда"},
        {"kind": "business_out", "amount": 200_000, "category": "KADI"},
        {"kind": "business_in", "amount": 100_000, "category": "KADI"},
        {"kind": "income", "amount": 30_000, "category": None},
    ]

    text = _render(rows, "Тест")

    assert "Потрачено: 50 000 сум" in text
    assert "Поступило: 30 000 сум" in text
    assert "В оборот: 200 000 сум" in text
    assert "Из оборота: 100 000 сум" in text


def test_internal_transfers_do_not_count_as_income_or_expense():
    rows = [
        {"kind": "transfer", "amount": 120_000, "category": "Карта → Наличные"},
        {"kind": "transfer", "amount": 50_000, "category": "Наличные → Карта"},
    ]

    text = _render(rows, "Тест")

    assert "Потрачено: 0 сум" in text
    assert "Поступило: 0 сум" in text
    assert "Карта → Наличные: 120 000 сум" in text
    assert "Наличные → Карта: 50 000 сум" in text


def test_today_details_show_original_expense_text_grouped_by_category():
    rows = [
        {
            "kind": "expense",
            "amount": 45_000,
            "category": "Еда",
            "account": "card",
            "raw_text": "еда 45k карта",
        },
        {
            "kind": "expense",
            "amount": 20_000,
            "category": "Еда",
            "account": "cash",
            "raw_text": "кофе 20k наличные",
        },
        {
            "kind": "expense",
            "amount": 40_000,
            "category": "Такси",
            "account": "card",
            "raw_text": "яндекс 40к карта",
        },
    ]

    text = _render(rows, "Сегодня", show_expense_details=True)

    assert "Потрачено: 105 000 сум" in text
    assert "• Еда: 65 000 сум" in text
    assert "↳ еда 45k карта · Карта" in text
    assert "↳ кофе 20k наличные · Наличные" in text
    assert "• Такси: 40 000 сум" in text
    assert "↳ яндекс 40к карта · Карта" in text
