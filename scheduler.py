import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from database import (
    get_pool, close_pool,
    get_upcoming_sessions, get_all_registered_participants,
    get_session_by_id,
)
from config import REMINDER_HOURS_BEFORE, BOT_TOKEN

logger = logging.getLogger(__name__)


def _parse_date(date_str: str) -> datetime | None:
    try:
        return datetime.strptime(date_str, "%d.%m.%Y")
    except (ValueError, TypeError):
        return None


def _format_reminder_text(session: dict, hours: int) -> str:
    return (
        f"Напоминание о дегустации!\n\n"
        f"{session['title']}\n"
        f"Дата: {session['tasting_date']}\n"
        f"Через {hours} ч.\n\n"
        f"Не забудьте зарегистрироваться в боте и заполнить карточки дегустации!"
    )


async def send_reminders_job():
    try:
        sessions = await get_upcoming_sessions()
        now = datetime.now()
        participants = await get_all_registered_participants()
        if not participants:
            return
        bot = Bot(token=BOT_TOKEN)
        for session in sessions:
            tasting_dt = _parse_date(session["tasting_date"])
            if tasting_dt is None:
                continue
            remind_at = tasting_dt - timedelta(hours=REMINDER_HOURS_BEFORE)
            diff = (now - remind_at).total_seconds()
            if 0 <= diff <= 300:
                text = _format_reminder_text(session, REMINDER_HOURS_BEFORE)
                sent = 0
                for p in participants:
                    try:
                        await bot.send_message(chat_id=p["tg_id"], text=text)
                        sent += 1
                    except Exception:
                        pass
                logger.info(
                    f"Напоминание отправлено для сессии '{session['title']}': {sent} участников"
                )
        await bot.session.close()
    except Exception as e:
        logger.error(f"Ошибка в send_reminders_job: {e}")


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        send_reminders_job,
        trigger="interval",
        minutes=5,
        id="reminders",
        replace_existing=True,
    )
    return scheduler
