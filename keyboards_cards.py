"""Клавиатуры для карточек дегустации."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


SCORE_HINT = (
    "\n"
    "📊  Шкала оценки:\n"
    "1–3 — слабо / не выражено\n"
    "4–6 — нормально / средне\n"
    "7–8 — хорошо\n"
    "9–10 — очень хорошо / ярко"
)


def score_kb() -> InlineKeyboardMarkup:
    row1 = [InlineKeyboardButton(text=str(s), callback_data=f"card_score:{s}") for s in range(1, 6)]
    row2 = [InlineKeyboardButton(text=str(s), callback_data=f"card_score:{s}") for s in range(6, 11)]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


FIELDS = [
    ("color",       "🎨 Цвет"),
    ("aroma",       "🌿 Аромат"),
    ("taste",       "🥤 Вкус"),
    ("aftertaste",  "🍃 Послевкусие"),
    ("defects",     "⚠️ Дефекты"),
    ("impression",  "✨ Общее впечатление"),
    ("comment",     "💬 Комментарий"),
    ("score",       "⭐ Оценка (1–10)"),
]


DEFECTS_LIST = [
    "TCA / пробковый",
    "Окисление",
    "Бретт (Brettanomyces)",
    "Летучая кислотность",
    "Восстановление / редукция",
]


def defects_kb() -> InlineKeyboardMarkup:
    buttons = []
    for i, d in enumerate(DEFECTS_LIST):
        buttons.append([InlineKeyboardButton(
            text=d,
            callback_data=f"card_defect:{i}",
        )])
    buttons.append([InlineKeyboardButton(text="Нет дефектов", callback_data="card_defect:none")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def card_session_menu_kb(session_id: int, wines_count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"📝 Заполнить карточки ({wines_count} образцов)",
            callback_data=f"card_start:{session_id}",
        )],
        [InlineKeyboardButton(
            text="🔄 Перезаполнить карточки",
            callback_data=f"card_redo:{session_id}",
        )],
        [InlineKeyboardButton(
            text="📊 Мои карточки",
            callback_data=f"card_my:{session_id}",
        )],
        [InlineKeyboardButton(text="Назад", callback_data="to_main")],
    ])


def skip_field_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="card_skip")],
    ])


def back_to_session_kb(session_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data=f"card_menu:{session_id}")],
    ])


def admin_cards_menu_kb(session_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📊 Сводка карточек",
            callback_data=f"admin_cards_summary:{session_id}",
        )],
        [InlineKeyboardButton(
            text="📋 Карточки участников",
            callback_data=f"admin_cards_participants:{session_id}",
        )],
        [InlineKeyboardButton(
            text="📥 Экспорт Excel",
            callback_data=f"admin_cards_export:{session_id}",
        )],
        [InlineKeyboardButton(text="Назад", callback_data="to_admin")],
    ])
