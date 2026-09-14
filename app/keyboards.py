from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Сегодня"),
            KeyboardButton(text="Неделя"),
            KeyboardButton(text="Месяц"),
        ],
        [
            KeyboardButton(text="Баланс"),
            KeyboardButton(text="Последние операции"),
        ],
    ],
    resize_keyboard=True,
)
