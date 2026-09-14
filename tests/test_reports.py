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
