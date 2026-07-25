from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from config import MINIAPP_URL


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Регистрация", callback_data="reg")],
        [InlineKeyboardButton(text="Войти в сессию", callback_data="join_session")],
        [InlineKeyboardButton(text="🔍 Просмотр", web_app=WebAppInfo(url=MINIAPP_URL))],
    ])


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Создать сессию", callback_data="admin_create_session")],
        [InlineKeyboardButton(text="Все сессии", callback_data="admin_all_sessions")],
        [InlineKeyboardButton(text="Карточки дегустации", callback_data="admin_cards")],
        [InlineKeyboardButton(text="🔍 Просмотр (Mini App)", web_app=WebAppInfo(url=MINIAPP_URL))],
        [InlineKeyboardButton(text="Меню участника", callback_data="to_main")],
    ])


def phone_request_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Отправить номер телефона",
            request_contact=True,
            callback_data="send_phone"
        )]
    ])


def sessions_list_kb(sessions: list[dict], prefix: str = "select_session") -> InlineKeyboardMarkup:
    buttons = []
    for s in sessions:
        status = "[активна]" if s["is_active"] else "[закрыта]"
        blind = " (слепая)" if s.get("is_blind") else ""
        buttons.append([InlineKeyboardButton(
            text=f"{s['title']} ({s['tasting_date']}) {status}{blind}",
            callback_data=f"{prefix}:{s['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="to_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def active_sessions_kb(sessions: list[dict]) -> InlineKeyboardMarkup:
    kb = sessions_list_kb(sessions, prefix="join_session")
    kb.inline_keyboard[-1] = [InlineKeyboardButton(text="Назад", callback_data="to_main")]
    return kb


def all_sessions_kb(sessions: list[dict]) -> InlineKeyboardMarkup:
    return sessions_list_kb(sessions, prefix="select_session")


def back_kb(back_to: str = "to_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data=back_to)]
    ])
