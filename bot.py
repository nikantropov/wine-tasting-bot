import os
import json
import hashlib
import hmac as hmac_module
import logging
import sys
from urllib.parse import parse_qs

from aiohttp import web
from aiogram import Router, F, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, Update,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import (
    BOT_TOKEN, ADMIN_IDS, WEBHOOK_URL, WEBHOOK_PATH,
    REMINDER_HOURS_BEFORE,
)
from database import (
    init_db, close_pool, get_or_create_participant, update_participant,
    is_participant_registered, create_session, add_wine,
    close_session, reopen_session,
    get_active_sessions, get_all_sessions, get_session_by_id,
    get_wines_by_session, get_wine_id_by_position,
)
from database_cards import (
    init_cards_table, update_card_field, get_participant_cards,
    get_cards_by_session, get_session_cards_summary, get_card_participants,
)
from keyboards import (
    main_menu_kb, admin_menu_kb, phone_request_kb,
    active_sessions_kb, all_sessions_kb, back_kb,
)
from keyboards_cards import (
    FIELDS, DEFECTS_LIST, SCORE_HINT,
    score_kb, defects_kb, skip_field_kb,
    card_session_menu_kb, back_to_session_kb, admin_cards_menu_kb,
)
from scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
#  MINI APP HTML (встроено, без папки static/)
# ============================================================

MINIAPP_HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
  <title>Дегустация вин</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:          var(--tg-bg-color, #fff);
      --bg2:         var(--tg-secondary-bg-color, #f0f0f0);
      --text:        var(--tg-text-color, #222);
      --text2:       var(--tg-hint-color, #999);
      --accent:      var(--tg-theme-button-color, #3390ec);
      --accent-text: var(--tg-theme-button-text-color, #fff);
      --danger:      #e53935;
      --success:     #43a047;
      --warning:     #fb8c00;
      --gold:        #f9a825;
      --radius:      12px;
      --shadow:      0 1px 3px rgba(0,0,0,.08);
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      font-size: 15px;
      line-height: 1.5;
      min-height: 100vh;
      padding-bottom: 20px;
    }

    .header {
      position: sticky; top: 0; z-index: 10;
      background: var(--bg2);
      padding: 14px 16px;
      display: flex; align-items: center; gap: 12px;
      border-bottom: 1px solid rgba(0,0,0,.06);
    }
    .header h1 { font-size: 18px; font-weight: 600; flex: 1; }
    .back-btn {
      width: 32px; height: 32px; border-radius: 50%;
      background: var(--accent); color: var(--accent-text);
      border: none; font-size: 18px; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
    }

    .center-msg {
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      padding: 60px 24px; color: var(--text2); text-align: center;
    }
    .center-msg .icon { font-size: 48px; margin-bottom: 12px; }
    .spinner {
      width: 32px; height: 32px; border: 3px solid var(--bg2);
      border-top-color: var(--accent); border-radius: 50%;
      animation: spin .8s linear infinite; margin-bottom: 12px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    .tabs {
      display: flex; padding: 0 16px; gap: 8px; margin: 12px 0;
    }
    .tab {
      padding: 8px 16px; border-radius: 20px; border: none;
      background: var(--bg2); color: var(--text); font-size: 14px;
      font-weight: 500; cursor: pointer; transition: .2s;
    }
    .tab.active { background: var(--accent); color: var(--accent-text); }

    .sessions { padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
    .session-card {
      background: var(--bg2); border-radius: var(--radius);
      padding: 14px 16px; cursor: pointer; transition: .15s;
      box-shadow: var(--shadow);
    }
    .session-card:active { transform: scale(.98); opacity: .85; }
    .session-card .title { font-weight: 600; font-size: 16px; margin-bottom: 4px; }
    .session-card .meta { font-size: 13px; color: var(--text2); }
    .badge {
      display: inline-block; padding: 2px 8px; border-radius: 10px;
      font-size: 11px; font-weight: 600; margin-left: 6px;
    }
    .badge-active  { background: #e8f5e9; color: #2e7d32; }
    .badge-closed  { background: #fce4ec; color: #c62828; }
    .badge-blind   { background: #fff3e0; color: #e65100; }

    .cards-list { padding: 12px 16px; display: flex; flex-direction: column; gap: 12px; }
    .wine-card {
      background: var(--bg2); border-radius: var(--radius);
      overflow: hidden; box-shadow: var(--shadow);
    }
    .wine-card-header {
      padding: 14px 16px 10px; display: flex;
      align-items: center; justify-content: space-between;
    }
    .wine-card-header .name { font-weight: 600; font-size: 16px; }
    .score-badge {
      padding: 4px 10px; border-radius: 8px;
      font-size: 14px; font-weight: 700; min-width: 40px; text-align: center;
    }
    .score-1-3   { background: #ffebee; color: #c62828; }
    .score-4-6   { background: #fff8e1; color: #f57f17; }
    .score-7-8   { background: #e8f5e9; color: #2e7d32; }
    .score-9-10  { background: #e8f5e9; color: #1b5e20; border: 2px solid #43a047; }
    .score-none   { background: var(--bg); color: var(--text2); }

    .wine-card-body { padding: 0 16px 14px; display: flex; flex-direction: column; gap: 8px; }
    .field-row { display: flex; gap: 8px; }
    .field-label {
      font-size: 13px; font-weight: 600; color: var(--text2);
      min-width: 110px; flex-shrink: 0;
    }
    .field-value { font-size: 14px; flex: 1; }
    .field-value.defect-present { color: var(--danger); font-weight: 600; }
    .field-value.empty { color: var(--text2); font-style: italic; }

    .summary-list { padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
    .summary-row {
      background: var(--bg2); border-radius: var(--radius);
      padding: 14px 16px; box-shadow: var(--shadow);
    }
    .summary-row .wine-name { font-weight: 600; margin-bottom: 8px; }
    .summary-row .bar-wrap {
      height: 8px; background: var(--bg); border-radius: 4px; overflow: hidden; margin-bottom: 6px;
    }
    .summary-row .bar { height: 100%; border-radius: 4px; transition: width .6s ease; }
    .summary-row .bar-info { display: flex; justify-content: space-between; font-size: 13px; color: var(--text2); }

    .participant-block { margin-bottom: 16px; }
    .participant-name {
      font-weight: 600; font-size: 15px; padding: 8px 0 4px;
      border-bottom: 1px solid rgba(0,0,0,.06); margin-bottom: 8px;
    }
    .participant-phone { font-size: 12px; color: var(--text2); margin-left: 8px; font-weight: 400; }

    .empty { text-align: center; padding: 40px 24px; color: var(--text2); }
    .empty .icon { font-size: 40px; margin-bottom: 8px; }
  </style>
</head>
<body>
<div id="app"></div>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
let state = {
  user: null, participantId: null, isAdmin: false,
  sessions: [], currentSession: null, tab: 'my', screen: 'loading',
};
const BASE = window.location.origin;

async function init() {
  if (tg) { tg.ready(); tg.expand(); }
  render();
  try {
    const resp = await fetch(BASE + '/api/auth', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ initData: tg.initData }),
    });
    if (!resp.ok) throw new Error('Auth failed');
    const data = await resp.json();
    state.user = data;
    state.participantId = data.participant_id;
    state.isAdmin = data.is_admin;
    state.screen = 'sessions';
    await loadSessions();
  } catch (e) { state.screen = 'error'; render(); }
}

async function loadSessions() {
  state.screen = 'loading'; render();
  try {
    const resp = await fetch(BASE + '/api/sessions');
    state.sessions = await resp.json();
    state.screen = 'sessions'; render();
  } catch (e) { state.screen = 'error'; render(); }
}

async function openSession(id) {
  state.screen = 'loading';
  state.currentSession = state.sessions.find(s => s.id === id);
  state.tab = 'my'; render();
  try {
    await Promise.all([loadMyCards(id), state.isAdmin ? loadSummary(id) : Promise.resolve()]);
    state.screen = 'detail'; render();
  } catch (e) { state.screen = 'error'; render(); }
}

async function loadMyCards(sid) {
  const resp = await fetch(BASE + '/api/sessions/' + sid + '/my-cards?participant_id=' + state.participantId);
  state.myCards = await resp.json();
}

async function loadSummary(sid) {
  const resp = await fetch(BASE + '/api/sessions/' + sid + '/summary');
  state.summaryData = await resp.json();
}

async function loadAllCards(sid) {
  state.screen = 'loading'; render();
  try {
    const resp = await fetch(BASE + '/api/sessions/' + sid + '/all-cards', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user_id: state.user.user_id }),
    });
    state.allCards = await resp.json();
    state.screen = 'detail'; render();
  } catch (e) { state.screen = 'error'; render(); }
}

function scoreClass(s) {
  if (s == null) return 'score-none';
  if (s <= 3) return 'score-1-3'; if (s <= 6) return 'score-4-6';
  if (s <= 8) return 'score-7-8'; return 'score-9-10';
}
function scoreLabel(s) {
  if (s == null) return '-';
  if (s <= 3) return s + '/10 слабо';
  if (s <= 6) return s + '/10 нормально';
  if (s <= 8) return s + '/10 хорошо';
  return s + '/10 отлично';
}
function scoreColor(s) {
  if (s == null) return '#ccc';
  if (s <= 3) return '#e53935'; if (s <= 6) return '#fb8c00';
  if (s <= 8) return '#43a047'; return '#1b5e20';
}
function esc(str) {
  if (!str) return '';
  const d = document.createElement('div'); d.textContent = str; return d.innerHTML;
}
function fieldVal(v) {
  if (!v || v === '-') return '<span class="field-value empty">не указано</span>';
  return esc(v);
}

function render() {
  const app = document.getElementById('app');
  switch (state.screen) {
    case 'loading':  app.innerHTML = '<div class="center-msg"><div class="spinner"></div><span>Загрузка...</span></div>'; break;
    case 'error':    app.innerHTML = '<div class="center-msg"><div class="icon">\u26A0\uFE0F</div><span>Не удалось загрузить данные.<br>Попробуйте позже.</span></div>'; break;
    case 'sessions': app.innerHTML = renderSessions(); break;
    case 'detail':  app.innerHTML = renderDetail(); break;
  }
}

function renderSessions() {
  if (!state.sessions.length) {
    return '<div class="center-msg"><div class="icon">\uD83C\uDF77</div><span>Сессий пока нет</span></div>';
  }
  let html = '<div class="header"><h1>\uD83C\uDF77 Дегустация</h1></div><div class="sessions">';
  for (const s of state.sessions) {
    const st = s.is_active ? '<span class="badge badge-active">активна</span>' : '<span class="badge badge-closed">закрыта</span>';
    const bl = s.is_blind ? '<span class="badge badge-blind">слепая</span>' : '';
    html += '<div class="session-card" onclick="openSession(' + s.id + ')"><div class="title">' + esc(s.title) + '</div><div class="meta">' + esc(s.tasting_date) + st + bl + ' &middot; ' + s.wines_count + ' обр.</div></div>';
  }
  html += '</div>';
  return html;
}

function renderDetail() {
  const s = state.currentSession;
  let html = '<div class="header"><button class="back-btn" onclick="backToSessions()">\u2190</button><h1>' + esc(s.title) + '</h1></div>';
  html += '<div class="tabs">';
  html += '<button class="tab' + (state.tab === 'my' ? ' active' : '') + '" onclick="switchTab(\'my\')">\uD83D\uDCDD Мои</button>';
  if (state.isAdmin) {
    html += '<button class="tab' + (state.tab === 'summary' ? ' active' : '') + '" onclick="switchTab(\'summary\')">\uD83D\uDCCA Сводка</button>';
    html += '<button class="tab' + (state.tab === 'all' ? ' active' : '') + '" onclick="switchTab(\'all\')">\uD83D\uDCB9 Все</button>';
  }
  html += '</div>';
  if (state.tab === 'my')      html += renderMyCards();
  else if (state.tab === 'summary') html += renderSummary();
  else if (state.tab === 'all')     html += renderAllCards();
  return html;
}

function renderMyCards() {
  const cards = state.myCards || [];
  if (!cards.length) return '<div class="empty"><div class="icon">\uD83D\uDCDD</div><span>Вы ещё не заполнили ни одной карточки</span></div>';
  let html = '<div class="cards-list">';
  for (const c of cards) html += renderWineCard(c);
  html += '</div>'; return html;
}

function renderWineCard(c) {
  const isBlind = state.currentSession && state.currentSession.is_blind;
  const name = isBlind ? 'Образец ' + c.wine_position : esc(c.wine_name);
  const sc = scoreClass(c.score);
  const sl = scoreLabel(c.score);
  let html = '<div class="wine-card"><div class="wine-card-header"><span class="name">' + name + '</span><span class="score-badge ' + sc + '">' + sl + '</span></div><div class="wine-card-body">';
  const fields = [
    ['\uD83C\uDFA8 Цвет', c.color],
    ['\uD83C\uDF3F Аромат', c.aroma],
    ['\uD83E\uDD64 Вкус', c.taste],
    ['\uD83C\uDF43 Послевкусие', c.aftertaste],
    ['\u26A0\uFE0F Дефекты', c.defects],
    ['\u2728 Впечатление', c.impression],
    ['\uD83D\uDCAC Комментарий', c.comment],
  ];
  for (const [label, val] of fields) {
    const dc = (label.includes('Дефекты') && val && val !== '' && val !== '-') ? ' defect-present' : '';
    html += '<div class="field-row"><span class="field-label">' + label + '</span><span class="field-value' + dc + '">' + fieldVal(val) + '</span></div>';
  }
  html += '</div></div>'; return html;
}

function renderSummary() {
  const data = state.summaryData || [];
  if (!data.length) return '<div class="empty"><div class="icon">\uD83D\uDCCA</div><span>Карточек пока нет</span></div>';
  let html = '<div class="summary-list">';
  for (const s of data) {
    const avg = parseFloat(s.avg_score) || 0;
    const pct = Math.round(avg * 10);
    const color = scoreColor(avg);
    html += '<div class="summary-row"><div class="wine-name">' + esc(s.wine_name) + '</div><div class="bar-wrap"><div class="bar" style="width:' + pct + '%;background:' + color + '"></div></div><div class="bar-info"><span>' + (avg ? avg.toFixed(1) + ' / 10' : 'нет оценок') + '</span><span>' + s.card_count + ' карт.</span></div></div>';
  }
  html += '</div>'; return html;
}

function renderAllCards() {
  const cards = state.allCards || [];
  if (!cards.length) return '<div class="empty"><div class="icon">\uD83D\uDCB9</div><span>Карточек пока нет</span></div>';
  const groups = {};
  for (const c of cards) {
    const key = c.participant_name || 'Аноним';
    if (!groups[key]) groups[key] = { phone: c.participant_phone || '', cards: [] };
    groups[key].cards.push(c);
  }
  let html = '<div class="cards-list">';
  for (const [name, g] of Object.entries(groups)) {
    html += '<div class="participant-block"><div class="participant-name">' + esc(name) + '<span class="participant-phone">' + esc(g.phone) + '</span></div>';
    for (const c of g.cards) html += renderWineCard(c);
    html += '</div>';
  }
  html += '</div>'; return html;
}

function backToSessions() {
  state.screen = 'sessions'; state.currentSession = null;
  state.myCards = null; state.summaryData = null; state.allCards = null;
  render();
}

async function switchTab(tab) {
  state.tab = tab; render();
  const sid = state.currentSession.id;
  if (tab === 'my' && !state.myCards) { await loadMyCards(sid); render(); }
  else if (tab === 'summary' && !state.summaryData) { await loadSummary(sid); render(); }
  else if (tab === 'all' && !state.allCards) { await loadAllCards(sid); }
}

init();
</script>
</body>
</html>"""


# ============================================================
#  ROUTERS
# ============================================================

admin_router = Router()
participant_router = Router()
cards_router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ============================================================
#  FSM
# ============================================================

class AdminFSM(StatesGroup):
    session_title = State()
    session_date = State()
    blind_mode = State()
    wine_count = State()
    wine_name = State()


class ParticipantFSM(StatesGroup):
    waiting_phone = State()
    waiting_name = State()


class CardFSM(StatesGroup):
    filling = State()


# ============================================================
#  ADMIN HANDLERS
# ============================================================

@admin_router.message(F.text == "/admin")
async def cmd_admin(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return
    await state.clear()
    await message.answer("Администрирование\nВыберите действие:", reply_markup=admin_menu_kb())


@admin_router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("Администрирование\nВыберите действие:", reply_markup=admin_menu_kb())


@admin_router.callback_query(F.data == "to_admin")
async def cb_to_admin(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Администрирование\nВыберите действие:", reply_markup=admin_menu_kb())


# --- Создание сессии ---

@admin_router.callback_query(F.data == "admin_create_session")
async def cb_create_session_start(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminFSM.session_title)
    await callback.message.edit_text(
        "Создание новой сессии дегустации\n\nОтправьте название сессии (например, Красные вина Франции):",
        reply_markup=back_kb("admin_menu"),
    )


@admin_router.message(AdminFSM.session_title)
async def process_session_title(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.update_data(session_title=message.text)
    await state.set_state(AdminFSM.session_date)
    await message.answer(
        f"Название: {message.text}\n\nОтправьте дату дегустации в формате ДД.ММ.ГГГГ (например: 15.08.2025):",
        reply_markup=back_kb("admin_menu"),
    )


@admin_router.message(AdminFSM.session_date)
async def process_session_date(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    date_text = message.text.strip()
    parts = date_text.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        await message.answer("Неверный формат даты. Используйте ДД.ММ.ГГГГ, например: 15.08.2025")
        return
    await state.update_data(session_date=date_text)
    await state.set_state(AdminFSM.blind_mode)
    await message.answer(
        f"Дата: {date_text}\n\nСлепая дегустация? (названия вин скрыты от участников):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да, слепая", callback_data="set_blind:1")],
            [InlineKeyboardButton(text="Нет, обычная", callback_data="set_blind:0")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_menu")],
        ]),
    )


@admin_router.callback_query(F.data.startswith("set_blind:"))
async def cb_set_blind(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    is_blind = callback.data.split(":")[1] == "1"
    await state.update_data(is_blind=is_blind)
    await state.set_state(AdminFSM.wine_count)
    mode = "слепая" if is_blind else "обычная"
    await callback.message.edit_text(
        f"Режим: {mode}\n\nСколько образцов вина будет на дегустации? (число от 1 до 20):",
        reply_markup=back_kb("admin_menu"),
    )


@admin_router.message(AdminFSM.wine_count)
async def process_wine_count(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    try:
        count = int(message.text.strip())
        if not 1 <= count <= 20:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 1 до 20.")
        return
    await state.update_data(wine_count=count, _wine_index=1)
    await state.set_state(AdminFSM.wine_name)
    await message.answer(f"Будет {count} образцов.\n\nВведите название образца \u21161:", reply_markup=back_kb("admin_menu"))


@admin_router.message(AdminFSM.wine_name)
async def process_wine_name(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    wine_name = message.text.strip()
    idx = data["_wine_index"]
    count = data["wine_count"]
    wines = data.get("_wines", [])
    wines.append(wine_name)
    if idx < count:
        await state.update_data(_wines=wines, _wine_index=idx + 1)
        await message.answer(f"Образец \u2116{idx}: {wine_name}\n\nВведите название образца \u2116{idx + 1}:")
    else:
        title = data["session_title"]
        date = data["session_date"]
        is_blind = data["is_blind"]
        session_id = await create_session(title, date, is_blind=is_blind)
        for pos, name in enumerate(wines, start=1):
            await add_wine(session_id, name, pos)
        await state.clear()
        wine_list = "\n".join(f"  {i}. {n}" for i, n in enumerate(wines, 1))
        blind_tag = " (СЛЕПАЯ)" if is_blind else ""
        await message.answer(
            f"Сессия создана!{blind_tag}\n\nНазвание: {title}\nДата: {date}\nОбразцы:\n{wine_list}\n\nID сессии: {session_id}",
            reply_markup=admin_menu_kb(),
        )


# --- Все сессии ---

@admin_router.callback_query(F.data == "admin_all_sessions")
async def cb_all_sessions(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    sessions = await get_all_sessions()
    if not sessions:
        await callback.message.edit_text("Нет созданных сессий.", reply_markup=back_kb("admin_menu"))
        return
    lines = ["Все сессии:\n"]
    for s in sessions:
        st = "активна" if s["is_active"] else "закрыта"
        bl = " (слепая)" if s["is_blind"] else ""
        lines.append(f"  #{s['id']} {s['title']} ({s['tasting_date']}) [{st}]{bl}")
    lines.append("")
    lines.append("Нажмите на сессию, чтобы посмотреть детали и карточки:")
    kb = all_sessions_kb(sessions)
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.callback_data and btn.callback_data.startswith("select_session:"):
                sid = btn.callback_data.split(":")[1]
                btn.callback_data = f"admin_session_detail:{sid}"
    await callback.message.edit_text("\n".join(lines), reply_markup=kb)


@admin_router.callback_query(F.data.startswith("admin_session_detail:"))
async def cb_session_detail(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    session_id = int(callback.data.split(":")[1])
    session = await get_session_by_id(session_id)
    wines = await get_wines_by_session(session_id)
    is_active = session["is_active"]
    is_blind = session["is_blind"]
    status = "Активна" if is_active else "Закрыта"
    blind = " | Слепая" if is_blind else ""
    close_text = "Закрыть" if is_active else "Открыть"
    await callback.message.edit_text(
        f"{session['title']}{blind}\nДата: {session['tasting_date']} | Статус: {status}\nВин: {len(wines)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{close_text} сессию", callback_data=f"toggle_session:{session_id}")],
            [InlineKeyboardButton(text="Карточки дегустации", callback_data=f"admin_cards_session:{session_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_all_sessions")],
        ]),
    )


@admin_router.callback_query(F.data.startswith("toggle_session:"))
async def cb_toggle_session(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    session_id = int(callback.data.split(":")[1])
    session = await get_session_by_id(session_id)
    if session["is_active"]:
        await close_session(session_id)
        status = "закрыта"
    else:
        await reopen_session(session_id)
        status = "открыта"
    await callback.answer(f"Сессия {status}")
    is_active = not session["is_active"]
    close_text = "Закрыть" if is_active else "Открыть"
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{close_text} сессию", callback_data=f"toggle_session:{session_id}")],
            [InlineKeyboardButton(text="Карточки дегустации", callback_data=f"admin_cards_session:{session_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_all_sessions")],
        ]),
    )


# ============================================================
#  PARTICIPANT HANDLERS
# ============================================================

@participant_router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "Вино и не только... Дегустация!\n\n"
        "Добро пожаловать в бота для дегустации вин.\n\n"
        "Для начала зарегистрируйтесь, указав номер телефона и имя."
    )
    kb = main_menu_kb()
    if _is_admin(message.from_user.id):
        kb = admin_menu_kb()
        text = "Бот дегустации вин\n\nВы администратор. Используйте /admin для управления."
    await message.answer(text, reply_markup=kb)


@participant_router.callback_query(F.data == "to_main")
async def cb_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if _is_admin(callback.from_user.id):
        await callback.message.edit_text("Главное меню администратора", reply_markup=admin_menu_kb())
    else:
        await callback.message.edit_text("Главное меню\n\nВыберите действие:", reply_markup=main_menu_kb())


# --- Регистрация ---

@participant_router.callback_query(F.data == "reg")
async def cb_register(callback: CallbackQuery, state: FSMContext):
    registered = await is_participant_registered(callback.from_user.id)
    if registered:
        p = await get_or_create_participant(callback.from_user.id)
        await callback.message.edit_text(
            f"Вы уже зарегистрированы!\n\nИмя: {p['name']}\nТелефон: {p['phone']}",
            reply_markup=back_kb("to_main"),
        )
        return
    await state.set_state(ParticipantFSM.waiting_phone)
    await callback.message.edit_text("Регистрация\n\nШаг 1: Отправьте ваш номер телефона.", reply_markup=phone_request_kb())


@participant_router.message(ParticipantFSM.waiting_phone, F.contact)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith("+") and phone.startswith("8"):
        phone = "+7" + phone[1:]
    await update_participant(message.from_user.id, phone=phone)
    await state.set_state(ParticipantFSM.waiting_name)
    await message.answer(f"Телефон сохранён: {phone}\n\nШаг 2: Отправьте ваше имя и фамилию.", reply_markup=back_kb("to_main"))


@participant_router.message(ParticipantFSM.waiting_phone)
async def process_phone_text(message: Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not phone.isdigit() or len(phone) < 10:
        await message.answer("Пожалуйста, отправьте корректный номер телефона (используйте кнопку ниже).", reply_markup=phone_request_kb())
        return
    if phone.startswith("8"):
        phone = "+7" + phone[1:]
    elif not phone.startswith("+"):
        phone = "+" + phone
    await update_participant(message.from_user.id, phone=phone)
    await state.set_state(ParticipantFSM.waiting_name)
    await message.answer(f"Телефон сохранён: {phone}\n\nШаг 2: Отправьте ваше имя и фамилию.", reply_markup=back_kb("to_main"))


@participant_router.message(ParticipantFSM.waiting_name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое. Введите имя и фамилию.")
        return
    await update_participant(message.from_user.id, name=name)
    await state.clear()
    await message.answer(f"Регистрация завершена!\n\nИмя: {name}\nВы можете войти в активную сессию и заполнить карточку дегустации.", reply_markup=main_menu_kb())


# --- Вход в сессию ---

@participant_router.callback_query(F.data == "join_session")
async def cb_join_session(callback: CallbackQuery):
    registered = await is_participant_registered(callback.from_user.id)
    if not registered:
        await callback.message.edit_text("Для участия в дегустации необходимо зарегистрироваться.\n\nНажмите Регистрация в главном меню.", reply_markup=back_kb("to_main"))
        return
    sessions = await get_active_sessions()
    if not sessions:
        await callback.message.edit_text("Сейчас нет активных сессий для дегустации.\nДождитесь, когда администратор создаст новую сессию.", reply_markup=back_kb("to_main"))
        return
    await callback.message.edit_text("Активные сессии:\n\nВыберите сессию для участия:", reply_markup=active_sessions_kb(sessions))


@participant_router.callback_query(F.data.startswith("join_session:"))
async def cb_enter_session(callback: CallbackQuery):
    session_id = int(callback.data.split(":")[1])
    session = await get_session_by_id(session_id)
    if not session or not session["is_active"]:
        await callback.answer("Сессия не найдена или закрыта.", show_alert=True)
        return
    wines = await get_wines_by_session(session_id)
    blind_tag = "\nРежим: слепая дегустация" if session["is_blind"] else ""
    await callback.message.edit_text(
        f"Сессия: {session['title']}\nДата: {session['tasting_date']}\nОбразцов: {len(wines)}{blind_tag}\n\nВыберите действие:",
        reply_markup=card_session_menu_kb(session_id, len(wines)),
    )


# ============================================================
#  CARD HANDLERS
# ============================================================

def _score_label(score) -> str:
    if score is None:
        return "-"
    if score <= 3:
        tag = "слабо"
    elif score <= 6:
        tag = "нормально"
    elif score <= 8:
        tag = "хорошо"
    else:
        tag = "очень хорошо"
    return f"{score}/10 ({tag})"


def _is_button_field(field_key: str) -> bool:
    return field_key in ("defects", "score")


def _field_prompt(field_key: str) -> str:
    prompts = {
        "color": "Опишите цвет вина",
        "aroma": "Опишите аромат",
        "taste": "Опишите вкус",
        "aftertaste": "Опишите послевкусие",
        "defects": "Выберите дефект из списка",
        "impression": "Опишите общее впечатление",
        "comment": "Оставьте комментарий",
        "score": "Поставьте оценку",
    }
    return prompts.get(field_key, "")


@cards_router.callback_query(F.data.startswith("card_menu:"))
async def cb_card_menu(callback: CallbackQuery):
    session_id = int(callback.data.split(":")[1])
    wines = await get_wines_by_session(session_id)
    await callback.message.edit_text(f"Образцов: {len(wines)}\n\nКарточки дегустации — развёрнутая оценка каждого вина.", reply_markup=card_session_menu_kb(session_id, len(wines)))


async def _ask_field(msg, state: FSMContext, field_index: int):
    data = await state.get_data()
    wine_pos = data["wine_position"]
    total_wines = data["total_wines"]
    is_blind = data["is_blind"]
    session_id = data["session_id"]
    wines = await get_wines_by_session(session_id)
    display = f"Образец {wine_pos}" if is_blind else wines[wine_pos - 1]["name"]
    fk, fname = FIELDS[field_index]
    header = f"Образец {wine_pos} из {total_wines}\n{display}\n\n{fname}"
    prompt = _field_prompt(fk)
    if fk == "score":
        text = f"{header}\n\n{prompt}:{SCORE_HINT}"
        kb = score_kb()
    elif fk == "defects":
        text = f"{header}\n\n{prompt}:"
        kb = defects_kb()
    else:
        text = f"{header}\n\n{prompt} (или нажмите Пропустить):"
        kb = skip_field_kb()
    await msg.edit_text(text, reply_markup=kb)


async def _start_wine(source, state: FSMContext, session_id: int, wines: list[dict], is_blind: bool, position: int):
    await state.set_state(CardFSM.filling)
    await state.update_data(session_id=session_id, total_wines=len(wines), is_blind=is_blind, wine_position=position, field_index=0, card_data={})
    msg = source.message if isinstance(source, CallbackQuery) else source
    await _ask_field(msg, state, 0)


@cards_router.callback_query(F.data.startswith("card_start:"))
async def cb_card_start(callback: CallbackQuery, state: FSMContext):
    registered = await is_participant_registered(callback.from_user.id)
    if not registered:
        await callback.answer("Сначала зарегистрируйтесь!", show_alert=True)
        return
    session_id = int(callback.data.split(":")[1])
    session = await get_session_by_id(session_id)
    if not session or not session["is_active"]:
        await callback.answer("Сессия закрыта.", show_alert=True)
        return
    wines = await get_wines_by_session(session_id)
    if not wines:
        await callback.answer("Нет вин.", show_alert=True)
        return
    await _start_wine(callback, state, session_id, wines, session["is_blind"], 1)


@cards_router.callback_query(F.data.startswith("card_redo:"))
async def cb_card_redo(callback: CallbackQuery, state: FSMContext):
    session_id = int(callback.data.split(":")[1])
    session = await get_session_by_id(session_id)
    wines = await get_wines_by_session(session_id)
    await _start_wine(callback, state, session_id, wines, session["is_blind"], 1)


@cards_router.callback_query(F.data == "card_skip", CardFSM.filling)
async def cb_card_skip(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    fk = FIELDS[data["field_index"]][0]
    card = data.get("card_data", {})
    card[fk] = ""
    await state.update_data(card_data=card)
    await _advance(callback, state)


@cards_router.message(CardFSM.filling)
async def process_text_field(message: Message, state: FSMContext):
    data = await state.get_data()
    fk = FIELDS[data["field_index"]][0]
    if _is_button_field(fk):
        if fk == "score":
            await message.answer(f"Выберите оценку кнопками ниже.{SCORE_HINT}", reply_markup=score_kb())
        elif fk == "defects":
            await message.answer("Выберите дефект из списка:", reply_markup=defects_kb())
        return
    card = data.get("card_data", {})
    card[fk] = message.text.strip()
    await state.update_data(card_data=card)
    await _advance(message, state)


@cards_router.callback_query(F.data.startswith("card_defect:"), CardFSM.filling)
async def cb_card_defect(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    defect_text = "" if val == "none" else DEFECTS_LIST[int(val)]
    data = await state.get_data()
    card = data.get("card_data", {})
    card["defects"] = defect_text
    await state.update_data(card_data=card)
    await _advance(callback, state)


@cards_router.callback_query(F.data.startswith("card_score:"), CardFSM.filling)
async def cb_card_score(callback: CallbackQuery, state: FSMContext):
    score = int(callback.data.split(":")[1])
    data = await state.get_data()
    card = data.get("card_data", {})
    card["score"] = score
    await state.update_data(card_data=card)
    await _advance(callback, state)


async def _advance(source, state: FSMContext):
    data = await state.get_data()
    field_index = data["field_index"]
    wine_pos = data["wine_position"]
    total_wines = data["total_wines"]
    is_blind = data["is_blind"]
    session_id = data["session_id"]
    card = data.get("card_data", {})
    msg = source.message if isinstance(source, CallbackQuery) else source
    participant = await get_or_create_participant(msg.from_user.id)
    wine_id = await get_wine_id_by_position(session_id, wine_pos)
    if wine_id:
        for fk, _ in FIELDS:
            val = card.get(fk, "")
            if fk == "score" and val == "":
                continue
            await update_card_field(participant["id"], wine_id, fk, val if val else None)
    next_field = field_index + 1
    if next_field < len(FIELDS):
        await state.update_data(field_index=next_field)
        await _ask_field(msg, state, next_field)
    else:
        next_wine = wine_pos + 1
        if next_wine <= total_wines:
            wines = await get_wines_by_session(session_id)
            await _start_wine(msg, state, session_id, wines, is_blind, next_wine)
        else:
            await state.clear()
            await msg.edit_text(f"Все {total_wines} карточек заполнены!\n\nСпасибо за подробную оценку.", reply_markup=card_session_menu_kb(session_id, total_wines))


def _format_card(c: dict, is_blind: bool) -> list[str]:
    wname = c["wine_name"] if not is_blind else f"Образец {c['wine_position']}"
    return [
        f"{'=' * 30}", f"{wname}",
        f"  Цвет:          {c['color'] or '-'}",
        f"  Аромат:        {c['aroma'] or '-'}",
        f"  Вкус:          {c['taste'] or '-'}",
        f"  Послевкусие:   {c['aftertaste'] or '-'}",
        f"  Дефекты:       {c['defects'] or '-'}",
        f"  Впечатление:   {c['impression'] or '-'}",
        f"  Комментарий:   {c['comment'] or '-'}",
        f"  Оценка:        {_score_label(c['score'])}", "",
    ]


@cards_router.callback_query(F.data.startswith("card_my:"))
async def cb_card_my(callback: CallbackQuery):
    session_id = int(callback.data.split(":")[1])
    participant = await get_or_create_participant(callback.from_user.id)
    cards = await get_participant_cards(participant["id"], session_id)
    session = await get_session_by_id(session_id)
    is_blind = session["is_blind"] if session else False
    if not cards:
        await callback.message.edit_text(f"Сессия: {session['title'] if session else ''}\n\nВы ещё не заполнили ни одной карточки.", reply_markup=back_to_session_kb(session_id))
        return
    lines = [f"Ваши карточки — {session['title']}\n"]
    for c in cards:
        lines.extend(_format_card(c, is_blind))
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3850] + "\n\n... (показаны не все данные)"
    await callback.message.edit_text(text, reply_markup=back_to_session_kb(session_id))


@cards_router.callback_query(F.data == "admin_cards")
@cards_router.callback_query(F.data.startswith("admin_cards:"))
async def cb_admin_cards(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if callback.data.startswith("admin_cards_session:"):
        session_id = int(callback.data.split(":")[1])
        session = await get_session_by_id(session_id)
        wines = await get_wines_by_session(session_id)
        await callback.message.edit_text(f"{session['title']} ({session['tasting_date']})\nВин: {len(wines)}\n\nВыберите действие:", reply_markup=admin_cards_menu_kb(session_id))
        return
    sessions = await get_all_sessions()
    if not sessions:
        await callback.message.edit_text("Нет созданных сессий.", reply_markup=admin_menu_kb())
        return
    kb = all_sessions_kb(sessions)
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.callback_data and btn.callback_data.startswith("select_session:"):
                sid = btn.callback_data.split(":")[1]
                btn.callback_data = f"admin_cards_session:{sid}"
    await callback.message.edit_text("Карточки дегустации\n\nВыберите сессию:", reply_markup=kb)


@cards_router.callback_query(F.data.startswith("admin_cards_summary:"))
async def cb_admin_cards_summary(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    session_id = int(callback.data.split(":")[1])
    session = await get_session_by_id(session_id)
    summary = await get_session_cards_summary(session_id)
    if not summary:
        await callback.message.edit_text(f"{session['title']}\n\nКарточек пока нет.", reply_markup=admin_cards_menu_kb(session_id))
        return
    lines = [f"Сводка карточек — {session['title']}\n"]
    for s in summary:
        avg = float(s["avg_score"]) if s["avg_score"] else 0
        cnt = s["card_count"]
        lines.append(f"  {s['wine_name']}: {_score_label(round(avg))} ({cnt} карт.)")
    await callback.message.edit_text("\n".join(lines), reply_markup=admin_cards_menu_kb(session_id))


@cards_router.callback_query(F.data.startswith("admin_cards_participants:"))
async def cb_admin_cards_participants(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    session_id = int(callback.data.split(":")[1])
    session = await get_session_by_id(session_id)
    participants = await get_card_participants(session_id)
    wines = await get_wines_by_session(session_id)
    if not participants:
        await callback.message.edit_text(f"{session['title']}\n\nНикто ещё не заполнил карточки.", reply_markup=admin_cards_menu_kb(session_id))
        return
    lines = [f"{session['title']} — карточки участников\nУчастников: {len(participants)} | Вин: {len(wines)}\n"]
    for p in participants:
        lines.append(f"{'=' * 30}")
        lines.append(f"{p['name']} ({p['phone']})")
        cards = await get_participant_cards(p["participant_id"], session_id)
        for c in cards:
            lines.append(f"  {c['wine_name']}:")
            lines.append(f"    Цвет: {c['color'] or '-'}")
            lines.append(f"    Аромат: {c['aroma'] or '-'}")
            lines.append(f"    Вкус: {c['taste'] or '-'}")
            lines.append(f"    Послевкусие: {c['aftertaste'] or '-'}")
            lines.append(f"    Дефекты: {c['defects'] or '-'}")
            lines.append(f"    Впечатление: {c['impression'] or '-'}")
            lines.append(f"    Комментарий: {c['comment'] or '-'}")
            lines.append(f"    Оценка: {_score_label(c['score'])}")
        lines.append("")
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3850] + "\n\n... (используйте экспорт Excel)"
    await callback.message.edit_text(text, reply_markup=admin_cards_menu_kb(session_id))


@cards_router.callback_query(F.data.startswith("admin_cards_export:"))
async def cb_admin_cards_export(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    session_id = int(callback.data.split(":")[1])
    session = await get_session_by_id(session_id)
    await callback.message.edit_text("Генерирую Excel с карточками...")
    try:
        from export_cards import export_cards_excel
        filepath = await export_cards_excel(session_id)
        with open(filepath, "rb") as f:
            await callback.message.answer_document(document=f, caption=f"Карточки: {session['title']} ({session['tasting_date']})")
        await callback.message.answer("Файл отправлен!", reply_markup=admin_cards_menu_kb(session_id))
    except Exception as e:
        await callback.message.answer(f"Ошибка при экспорте: {e}", reply_markup=admin_cards_menu_kb(session_id))


# ============================================================
#  MINI APP API
# ============================================================

def _validate_init_data(init_data: str) -> dict | None:
    try:
        params = dict(parse_qs(init_data))
        hash_value = params.pop("hash", [None])[0]
        if not hash_value:
            return None
        data_check_string = "\n".join(f"{k}={v[0]}" for k, v in sorted(params.items()))
        secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
        calculated_hash = hmac_module.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if calculated_hash == hash_value:
            return json.loads(params.get("user", ["{}"])[0])
        return None
    except Exception:
        return None


async def miniapp_handler(request: web.Request) -> web.Response:
    return web.Response(text=MINIAPP_HTML, content_type="text/html")


async def api_auth(request: web.Request) -> web.Response:
    body = await request.json()
    user = _validate_init_data(body.get("initData", ""))
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    is_admin = user.get("id") in ADMIN_IDS
    participant = await get_or_create_participant(user["id"])
    return web.json_response({"user_id": user["id"], "name": user.get("first_name", ""), "is_admin": is_admin, "participant_id": participant["id"]})


async def api_sessions(request: web.Request) -> web.Response:
    sessions = await get_all_sessions()
    for s in sessions:
        wines = await get_wines_by_session(s["id"])
        s["wines_count"] = len(wines)
    return web.json_response(sessions)


async def api_my_cards(request: web.Request) -> web.Response:
    session_id = int(request.match_info["session_id"])
    participant_id = int(request.query["participant_id"])
    cards = await get_participant_cards(participant_id, session_id)
    return web.json_response(cards)


async def api_summary(request: web.Request) -> web.Response:
    session_id = int(request.match_info["session_id"])
    summary = await get_session_cards_summary(session_id)
    return web.json_response(summary)


async def api_all_cards(request: web.Request) -> web.Response:
    session_id = int(request.match_info["session_id"])
    body = await request.json()
    if body.get("user_id") not in ADMIN_IDS:
        return web.json_response({"error": "Forbidden"}, status=403)
    cards = await get_cards_by_session(session_id)
    return web.json_response(cards)


# ============================================================
#  LIFECYCLE + WEB SERVER
# ============================================================

async def on_startup(app):
    await init_db()
    await init_cards_table()
    logger.info("PostgreSQL initialized.")
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    logger.info(f"Webhook set: {WEBHOOK_URL}")
    scheduler = setup_scheduler()
    scheduler.start()
    app["scheduler"] = scheduler
    logger.info("Scheduler started.")


async def on_shutdown(app):
    scheduler = app.get("scheduler")
    if scheduler:
        scheduler.shutdown()
    await bot.delete_webhook()
    await close_pool()
    await bot.session.close()
    logger.info("Shutdown complete.")


async def health_handler(request: web.Request) -> web.Response:
    return web.Response(text="OK", status=200)


async def webhook_handler(request: web.Request) -> web.Response:
    update = Update.model_validate(await request.json())
    await dp.feed_webhook_update(bot, update)
    return web.Response(status=200)


bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(admin_router)
dp.include_router(participant_router)
dp.include_router(cards_router)

app = web.Application()
app.router.add_get("/health", health_handler)
app.router.add_post(WEBHOOK_PATH, webhook_handler)
app.router.add_get("/miniapp/", miniapp_handler)
app.router.add_post("/api/auth", api_auth)
app.router.add_get("/api/sessions", api_sessions)
app.router.add_get("/api/sessions/{session_id}/my-cards", api_my_cards)
app.router.add_get("/api/sessions/{session_id}/summary", api_summary)
app.router.add_post("/api/sessions/{session_id}/all-cards", api_all_cards)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        sys.exit(1)
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
