import asyncio
import sqlite3
import os
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, CallbackQuery, Message
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN       = os.getenv("BOT_TOKEN")
BOT_USERNAME    = os.getenv("BOT_USERNAME", "Bormor54bot")
ADMIN_ID        = int(os.getenv("ADMIN_ID", "7950533047"))
ADMIN_USERNAME  = os.getenv("ADMIN_USERNAME", "feji73")
CHANNEL_LINK    = os.getenv("CHANNEL_LINK", "https://t.me/+otgte7DKQF40YmMy")
STARS_BUY       = os.getenv("STARS_BUY", "https://split.tg/?ref=UQD06L7Gv3pWk1J8DJ1wUeNsflj30ZmUyuZnb3zknSmVy5J-")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")

PLANS = {
    "full":   {"label": "50 ГБ", "stars": 600, "crypto": "https://t.me/send?start=IVfBnFlf6v5b"},
    "medium": {"label": "15 ГБ", "stars": 400, "crypto": "https://t.me/send?start=IVCR8jU3BohU"},
    "small":  {"label": "5 ГБ",  "stars": 350, "crypto": None},
}
PLAN_NAMES = {"full": "50 ГБ", "medium": "15 ГБ", "small": "5 ГБ"}

LEVELS = [
    (0,    "Новичок"),
    (3,    "Продвинутый"),
    (10,   "Опытный"),
    (25,   "Эксперт"),
    (50,   "Легенда"),
    (100,  "Топ"),
]

def get_level(invited_count: int):
    current = LEVELS[0][1]
    for threshold, name in LEVELS:
        if invited_count >= threshold:
            current = name
    return current

DB = "tendo.db"

def db_init():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            joined_at   TEXT,
            ref_by      INTEGER DEFAULT NULL,
            banned      INTEGER DEFAULT 0,
            total_spent INTEGER DEFAULT 0,
            last_daily  TEXT DEFAULT NULL,
            balance     INTEGER DEFAULT 0,
            ref_percent INTEGER DEFAULT 20
        )
    """)
    try:
        cur.execute("ALTER TABLE users ADD COLUMN balance INTEGER DEFAULT 0")
        con.commit()
    except:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN ref_percent INTEGER DEFAULT 20")
        con.commit()
    except:
        pass
    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            plan        TEXT,
            stars       INTEGER,
            paid_at     TEXT,
            ref_owner   INTEGER DEFAULT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ref_earnings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id    INTEGER,
            from_user   INTEGER,
            stars       INTEGER,
            earned      INTEGER,
            paid_at     TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            amount      INTEGER,
            status      TEXT DEFAULT 'pending',
            requested_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ref_notify_sent (
            owner_id    INTEGER,
            from_user   INTEGER,
            PRIMARY KEY (owner_id, from_user)
        )
    """)
    con.commit()
    con.close()

def db_get_ref_percent(user_id: int) -> int:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    row = cur.execute("SELECT ref_percent FROM users WHERE user_id=?", (user_id,)).fetchone()
    con.close()
    return row[0] if row else 20

def db_set_ref_percent(user_id: int, percent: int):
    con = sqlite3.connect(DB)
    con.execute("UPDATE users SET ref_percent=? WHERE user_id=?", (percent, user_id))
    con.commit()
    con.close()

def db_add_user(user: types.User, ref_by: int = None):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at, ref_by, banned, total_spent, last_daily, balance, ref_percent)
        VALUES (?, ?, ?, ?, ?, 0, 0, NULL, 0, 20)
    """, (user.id, user.username, user.first_name,
          datetime.now().strftime("%Y-%m-%d %H:%M"), ref_by))
    con.commit()
    con.close()

def db_get_balance(user_id: int) -> int:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    row = cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
    con.close()
    return row[0] if row else 0

def db_update_balance(user_id: int, amount: int):
    con = sqlite3.connect(DB)
    con.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    con.commit()
    con.close()

def db_get_total_spent(user_id: int) -> int:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    row = cur.execute("SELECT total_spent FROM users WHERE user_id=?", (user_id,)).fetchone()
    con.close()
    return row[0] if row else 0

def db_update_total_spent(user_id: int, stars: int):
    con = sqlite3.connect(DB)
    con.execute("UPDATE users SET total_spent = total_spent + ? WHERE user_id=?", (stars, user_id))
    con.commit()
    con.close()

def db_can_claim_daily(user_id: int) -> bool:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    row = cur.execute("SELECT last_daily FROM users WHERE user_id=?", (user_id,)).fetchone()
    con.close()
    if not row or not row[0]:
        return True
    last = datetime.strptime(row[0], "%Y-%m-%d")
    return datetime.now().date() > last.date()

def db_claim_daily(user_id: int) -> int:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("UPDATE users SET last_daily=? WHERE user_id=?", (datetime.now().strftime("%Y-%m-%d"), user_id))
    cur.execute("UPDATE users SET balance = balance + 5 WHERE user_id=?", (user_id,))
    con.commit()
    con.close()
    return 5

def db_get_ref_by(user_id: int):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    row = cur.execute("SELECT ref_by FROM users WHERE user_id=?", (user_id,)).fetchone()
    con.close()
    return row[0] if row else None

def db_get_invited_count(owner_id: int) -> int:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    count = cur.execute("SELECT COUNT(*) FROM users WHERE ref_by=?", (owner_id,)).fetchone()[0]
    con.close()
    return count

def db_has_ref_notify_sent(owner_id: int, from_user: int) -> bool:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    row = cur.execute("SELECT 1 FROM ref_notify_sent WHERE owner_id=? AND from_user=?", (owner_id, from_user)).fetchone()
    con.close()
    return row is not None

def db_mark_ref_notify_sent(owner_id: int, from_user: int):
    con = sqlite3.connect(DB)
    con.execute("INSERT OR IGNORE INTO ref_notify_sent (owner_id, from_user) VALUES (?, ?)", (owner_id, from_user))
    con.commit()
    con.close()

def db_is_banned(user_id: int) -> bool:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    row = cur.execute("SELECT banned FROM users WHERE user_id=?", (user_id,)).fetchone()
    con.close()
    return row[0] == 1 if row else False

def db_ban_user(user_id: int, ban: bool = True):
    con = sqlite3.connect(DB)
    con.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if ban else 0, user_id))
    con.commit()
    con.close()

def db_add_purchase(user_id: int, plan: str, stars: int) -> tuple:
    db_update_total_spent(user_id, stars)
    ref_by = db_get_ref_by(user_id)
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO purchases (user_id, plan, stars, paid_at, ref_owner)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, plan, stars, datetime.now().strftime("%Y-%m-%d %H:%M"), ref_by))
    con.commit()
    con.close()
    if ref_by and ref_by != user_id:
        pct = db_get_ref_percent(ref_by)
        earned = int(stars * pct / 100)
        con = sqlite3.connect(DB)
        cur = con.cursor()
        cur.execute("""
            INSERT INTO ref_earnings (owner_id, from_user, stars, earned, paid_at)
            VALUES (?, ?, ?, ?, ?)
        """, (ref_by, user_id, stars, earned, datetime.now().strftime("%Y-%m-%d %H:%M")))
        con.commit()
        con.close()
        db_update_balance(ref_by, earned)
        return ref_by, earned
    return 0, 0

def db_get_ref_stats(user_id: int):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    invited = cur.execute("SELECT COUNT(*) FROM users WHERE ref_by=?", (user_id,)).fetchone()[0]
    buyers = cur.execute("SELECT COUNT(DISTINCT from_user) FROM ref_earnings WHERE owner_id=?", (user_id,)).fetchone()[0]
    total_earned = cur.execute("SELECT COALESCE(SUM(earned),0) FROM ref_earnings WHERE owner_id=?", (user_id,)).fetchone()[0]
    paid_out = cur.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE user_id=? AND status='done'", (user_id,)).fetchone()[0]
    pending_req = cur.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE user_id=? AND status='pending'", (user_id,)).fetchone()[0]
    balance = total_earned - paid_out - pending_req
    recent = cur.execute("""
        SELECT u.first_name, u.username, re.stars, re.earned, re.paid_at
        FROM ref_earnings re LEFT JOIN users u ON re.from_user = u.user_id
        WHERE re.owner_id=? ORDER BY re.id DESC LIMIT 5
    """, (user_id,)).fetchall()
    con.close()
    return {
        "invited": invited, "buyers": buyers,
        "total_earned": total_earned, "paid_out": paid_out,
        "pending": pending_req, "balance": balance, "recent": recent
    }

def db_get_stats():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    s = {
        "total_users": cur.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "today_users": cur.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today}%",)).fetchone()[0],
        "total_purchases": cur.execute("SELECT COUNT(*) FROM purchases").fetchone()[0],
        "today_purchases": cur.execute("SELECT COUNT(*) FROM purchases WHERE paid_at LIKE ?", (f"{today}%",)).fetchone()[0],
        "total_stars": cur.execute("SELECT COALESCE(SUM(stars),0) FROM purchases").fetchone()[0],
        "total_earned": cur.execute("SELECT COALESCE(SUM(earned),0) FROM ref_earnings").fetchone()[0],
        "pending_withdrawals": cur.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0],
        "recent": cur.execute("""
            SELECT u.first_name, u.username, p.plan, p.stars, p.paid_at
            FROM purchases p LEFT JOIN users u ON p.user_id=u.user_id
            ORDER BY p.id DESC LIMIT 5
        """).fetchall(),
    }
    con.close()
    return s

def db_get_all_users():
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT user_id FROM users").fetchall()
    con.close()
    return [r[0] for r in rows]

def db_get_top_refs():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    rows = cur.execute("""
        SELECT u.user_id, u.first_name, u.username,
               (SELECT COUNT(*) FROM users u2 WHERE u2.ref_by = u.user_id) as invited,
               (SELECT COALESCE(SUM(earned),0) FROM ref_earnings re WHERE re.owner_id = u.user_id) as earned
        FROM users u
        WHERE (SELECT COUNT(*) FROM users u2 WHERE u2.ref_by = u.user_id) > 0
        ORDER BY invited DESC LIMIT 10
    """).fetchall()
    con.close()
    return rows

def db_get_workers():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    rows = cur.execute("""
        SELECT u.user_id, u.first_name, u.username,
               (SELECT COUNT(*) FROM users u2 WHERE u2.ref_by = u.user_id) as invited,
               (SELECT COUNT(DISTINCT from_user) FROM ref_earnings re WHERE re.owner_id = u.user_id) as buyers,
               (SELECT COALESCE(SUM(earned),0) FROM ref_earnings re WHERE re.owner_id = u.user_id) as earned
        FROM users u
        WHERE (SELECT COUNT(*) FROM users u2 WHERE u2.ref_by = u.user_id) > 0
        ORDER BY invited DESC
    """).fetchall()
    con.close()
    return rows

def db_get_user_detail(user_id: int):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    user = cur.execute("SELECT first_name, username, banned, total_spent, joined_at, ref_percent FROM users WHERE user_id=?", (user_id,)).fetchone()
    invited = cur.execute("SELECT COUNT(*) FROM users WHERE ref_by=?", (user_id,)).fetchone()[0]
    earnings = cur.execute("""
        SELECT u.first_name, u.username, re.stars, re.earned, re.paid_at
        FROM ref_earnings re LEFT JOIN users u ON re.from_user=u.user_id
        WHERE re.owner_id=? ORDER BY re.id DESC LIMIT 10
    """, (user_id,)).fetchall()
    total = cur.execute("SELECT COALESCE(SUM(earned),0) FROM ref_earnings WHERE owner_id=?", (user_id,)).fetchone()[0]
    paid = cur.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE user_id=? AND status='done'", (user_id,)).fetchone()[0]
    pending = cur.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE user_id=? AND status='pending'", (user_id,)).fetchone()[0]
    buyers = cur.execute("SELECT COUNT(DISTINCT from_user) FROM ref_earnings WHERE owner_id=?", (user_id,)).fetchone()[0]
    con.close()
    return {
        "user": user, "invited": invited, "earnings": earnings,
        "total": total, "paid": paid, "pending": pending,
        "balance": total - paid - pending, "buyers": buyers,
        "ref_percent": user[5] if user else 20
    }

def db_get_pending_withdrawals():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    rows = cur.execute("""
        SELECT w.id, w.user_id, u.first_name, u.username, w.amount, w.requested_at
        FROM withdrawals w LEFT JOIN users u ON w.user_id=u.user_id
        WHERE w.status='pending' ORDER BY w.id
    """).fetchall()
    con.close()
    return rows

def db_set_withdrawal_status(wid: int, status: str):
    con = sqlite3.connect(DB)
    con.execute("UPDATE withdrawals SET status=? WHERE id=?", (status, wid))
    con.commit()
    con.close()

def db_request_withdrawal(user_id: int, amount: int):
    db_update_balance(user_id, -amount)
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO withdrawals (user_id, amount, status, requested_at)
        VALUES (?, ?, 'pending', ?)
    """, (user_id, amount, datetime.now().strftime("%Y-%m-%d %H:%M")))
    con.commit()
    con.close()

def db_get_recent_users(limit=20):
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT user_id, first_name, username, joined_at FROM users ORDER BY rowid DESC LIMIT ?",
        (limit,)
    ).fetchall()
    con.close()
    return rows

# FSM
class BroadcastState(StatesGroup):
    waiting_text = State()

class AdminState(StatesGroup):
    user_lookup = State()
    set_percent_user = State()
    set_percent_value = State()

# INIT
db_init()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# КЛАВИАТУРЫ
def kb_main():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⭐ Оплатить звёздами", callback_data="menu_stars"))
    kb.row(InlineKeyboardButton(text="🌐 Оплатить криптой", callback_data="menu_crypto"))
    kb.row(InlineKeyboardButton(text="🤝 Реферальная программа", callback_data="ref_menu"))
    kb.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    kb.row(InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="daily"))
    kb.row(InlineKeyboardButton(text="💫 Где купить звёзды?", url=STARS_BUY))
    return kb.as_markup()

def kb_admin():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats"))
    kb.row(InlineKeyboardButton(text="👥 Все пользователи", callback_data="adm_users"))
    kb.row(InlineKeyboardButton(text="📋 Последние покупки", callback_data="adm_recent"))
    kb.row(InlineKeyboardButton(text="🏆 Топ рефереров", callback_data="adm_refs"))
    kb.row(InlineKeyboardButton(text="👷 Рабочие", callback_data="adm_workers"))
    kb.row(InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="adm_user_lookup"))
    kb.row(InlineKeyboardButton(text="💸 Заявки на выплату", callback_data="adm_withdrawals"))
    kb.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast"))
    kb.row(InlineKeyboardButton(text="⚙️ Проценты", callback_data="adm_percent"))
    kb.row(InlineKeyboardButton(text="❌ Закрыть", callback_data="adm_close"))
    return kb.as_markup()

def kb_back_admin():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад в админ", callback_data="adm_back")
    ]])

# /start
@dp.message(CommandStart())
async def cmd_start(message: Message):
    if db_is_banned(message.from_user.id):
        return

    args = message.text.split()
    ref_by = None
    new_user = False

    con = sqlite3.connect(DB)
    cur = con.cursor()
    existing = cur.execute("SELECT 1 FROM users WHERE user_id=?", (message.from_user.id,)).fetchone()
    con.close()

    if not existing:
        new_user = True
        if len(args) > 1 and args[1].startswith("ref"):
            try:
                ref_id = int(args[1][3:])
                if ref_id != message.from_user.id:
                    existing_ref = db_get_ref_by(message.from_user.id)
                    if existing_ref is None:
                        ref_by = ref_id
            except ValueError:
                pass

    db_add_user(message.from_user, ref_by)

    if ref_by and new_user:
        if not db_has_ref_notify_sent(ref_by, message.from_user.id):
            db_mark_ref_notify_sent(ref_by, message.from_user.id)
            try:
                invited_count = db_get_invited_count(ref_by)
                level_name = get_level(invited_count)
                pct = db_get_ref_percent(ref_by)
                await bot.send_message(
                    ref_by,
                    f"👤 Новый реферал!\n\nПо вашей ссылке перешёл: {message.from_user.first_name}\n🏆 Уровень: {level_name}\n📊 Твой процент: {pct}%\n👥 Приглашено: {invited_count + 1} чел.",
                    parse_mode="HTML"
                )
            except:
                pass

    await message.answer(
        "🌿 TENDO\n\n✅ Автовыдача сразу после оплаты\n🔒 Безопасная оплата через Telegram Stars\n\nВыберите способ оплаты:",
        parse_mode="HTML",
        reply_markup=kb_main()
    )

# /profile
@dp.message(Command("profile"))
@dp.callback_query(F.data == "profile")
async def show_profile(event):
    is_callback = isinstance(event, CallbackQuery)
    user_id = event.from_user.id
    msg = event.message if is_callback else event

    con = sqlite3.connect(DB)
    cur = con.cursor()
    row = cur.execute("SELECT balance, total_spent, joined_at, first_name, username, ref_percent FROM users WHERE user_id=?", (user_id,)).fetchone()
    con.close()

    if not row:
        if is_callback:
            await event.answer("Ошибка")
        else:
            await event.answer("Ошибка")
        return

    balance, total_spent, joined_at, first_name, username, ref_percent = row
    username_str = f"@{username}" if username else "—"
    invited_count = db_get_invited_count(user_id)
    level = get_level(invited_count)

    text = (
        f"👤 Профиль\n\n"
        f"Имя: {first_name}\n"
        f"Username: {username_str}\n"
        f"ID: <code>{user_id}</code>\n"
        f"Регистрация: {joined_at[:10]}\n\n"
        f"🏆 Уровень: {level}\n"
        f"📊 Процент: {ref_percent}%\n"
        f"💰 Баланс: <b>{balance}⭐</b>\n"
        f"💸 Потрачено: <b>{total_spent}⭐</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_start")
    ]])

    if is_callback:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)

# /daily
@dp.message(Command("daily"))
@dp.callback_query(F.data == "daily")
async def daily_bonus(event):
    is_callback = isinstance(event, CallbackQuery)
    user_id = event.from_user.id

    if db_is_banned(user_id):
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_start")
    ]])

    if db_can_claim_daily(user_id):
        amount = db_claim_daily(user_id)
        new_balance = db_get_balance(user_id)
        text = f"✅ Ежедневный бонус получен!\n\n🎁 +{amount}⭐\n💰 Баланс: {new_balance}⭐"
        if is_callback:
            await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            await event.answer()
        else:
            await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        text = "❌ Вы уже забирали бонус сегодня!\n\nПриходите завтра."
        if is_callback:
            await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            await event.answer()
        else:
            await event.answer(text, parse_mode="HTML", reply_markup=kb)

# /admin
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    s = db_get_stats()
    await message.answer(
        f"🛡 Админ-панель TENDO\n\n"
        f"👥 Пользователей: <b>{s['total_users']}</b>\n"
        f"🆕 Сегодня: <b>{s['today_users']}</b>\n"
        f"💳 Покупок сегодня: <b>{s['today_purchases']}</b>\n"
        f"⭐ Всего звёзд: <b>{s['total_stars']}</b>",
        parse_mode="HTML",
        reply_markup=kb_admin()
    )

# РЕФЕРАЛЬНОЕ МЕНЮ
@dp.callback_query(F.data == "ref_menu")
async def ref_menu(call: CallbackQuery):
    if db_is_banned(call.from_user.id):
        return

    uid = call.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref{uid}"
    s = db_get_ref_stats(uid)
    invited_count = s["invited"]
    level = get_level(invited_count)
    pct = db_get_ref_percent(uid)

    recent_lines = ""
    if s["recent"]:
        lines = []
        for name, uname, stars, earned, at in s["recent"]:
            lines.append(f"  • {name or '?'} — {stars}⭐ покупка, тебе +{earned}⭐ ({at[:10]})")
        recent_lines = "\n\n📜 Последние начисления:\n" + "\n".join(lines)

    text = (
        f"⭐ Реферальная программа\n\n"
        f"🏆 Уровень: {level}\n"
        f"📊 Твой процент: <b>{pct}%</b>\n\n"
        f"💸 Приглашай и получай {pct}% с их покупок!\n"
        f"600⭐ → ты получишь <b>{int(600*pct/100)}⭐</b>!\n\n"
        f"🔗 Твоя ссылка:\n"
        f"<code>{link}</code>\n\n"
        f"📈 Статистика:\n"
        f"👥 Приглашено: <b>{s['invited']}</b>\n"
        f"✅ Купили: <b>{s['buyers']}</b>\n"
        f"⭐ Заработано: <b>{s['total_earned']}</b>\n"
        f"💸 Выплачено: <b>{s['paid_out']}</b>\n"
        f"⏳ В обработке: <b>{s['pending']}</b>\n"
        f"💰 Баланс: <b>{s['balance']}</b>"
        f"{recent_lines}\n\n"
        f"По вопросам: @{ADMIN_USERNAME}"
    )

    kb = InlineKeyboardBuilder()
    if s["balance"] > 0:
        kb.row(InlineKeyboardButton(
            text=f"💸 Вывести {s['balance']}⭐", callback_data="ref_withdraw"
        ))
    kb.row(InlineKeyboardButton(text="ℹ️ Как работает", callback_data="ref_howto"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_start"))

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

@dp.callback_query(F.data == "ref_howto")
async def ref_howto(call: CallbackQuery):
    uid = call.from_user.id
    pct = db_get_ref_percent(uid)
    text = (
        "⭐ Как работает реферальная система\n\n"
        "Ты приглашаешь людей по своей ссылке → получаешь процент с их покупок.\n\n"
        f"💰 Твой процент: {pct}%\n\n"
        f"600⭐ → ты получишь <b>{int(600*pct/100)}⭐</b>\n\n"
        "📢 При переходе по ссылке ты получишь уведомление."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад", callback_data="ref_menu")
    ]])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "ref_withdraw")
async def ref_withdraw(call: CallbackQuery):
    if db_is_banned(call.from_user.id):
        return

    uid = call.from_user.id
    s = db_get_ref_stats(uid)
    if s["balance"] <= 0:
        await call.answer("Нет доступного баланса", show_alert=True)
        return

    db_request_withdrawal(uid, s["balance"])

    uname = f"@{call.from_user.username}" if call.from_user.username else call.from_user.first_name
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💸 Заявка на вывод!\n\n👤 {uname} (ID: <code>{uid}</code>)\n⭐ Сумма: <b>{s['balance']}</b> звёзд\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            parse_mode="HTML"
        )
    except:
        pass

    await call.answer("✅ Заявка отправлена!", show_alert=True)
    await ref_menu(call)

# ADMIN CALLBACKS
@dp.callback_query(lambda c: c.data and c.data.startswith("adm_"))
async def admin_handler(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔ Нет доступа", show_alert=True)
        return

    action = call.data

    if action == "adm_stats":
        s = db_get_stats()
        text = (
            "📊 Статистика TENDO\n\n"
            f"👥 Пользователей: <b>{s['total_users']}</b>\n"
            f"🆕 Сегодня: <b>{s['today_users']}</b>\n\n"
            f"💳 Покупок всего: <b>{s['total_purchases']}</b>\n"
            f"📅 Сегодня: <b>{s['today_purchases']}</b>\n"
            f"⭐ Получено: <b>{s['total_stars']}</b>\n\n"
            f"🤝 Реф. выплат: <b>{s['total_earned']}</b>⭐\n"
            f"💸 Заявок: <b>{s['pending_withdrawals']}</b>"
        )
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_back_admin())

    elif action == "adm_recent":
        s = db_get_stats()
        if not s["recent"]:
            text = "📋 Покупок ещё нет."
        else:
            lines = ["📋 Последние 5 покупок:\n"]
            for name, uname, plan, stars, at in s["recent"]:
                ustr = f"@{uname}" if uname else "—"
                lines.append(f"• {name or '?'} ({ustr})\n  📦 {PLAN_NAMES.get(plan, plan)} — {stars}⭐ — {at}")
            text = "\n\n".join(lines)
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_back_admin())

    elif action == "adm_refs":
        rows = db_get_top_refs()
        if not rows:
            text = "🤝 Реферальных продаж ещё нет."
        else:
            lines = ["🏆 Топ рефереров:\n"]
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            for i, (uid, name, uname, invited, earned) in enumerate(rows):
                ustr = f"@{uname}" if uname else f"ID:{uid}"
                medal = medals[i] if i < len(medals) else f"{i+1}."
                lines.append(
                    f"{medal} {name or '?'} ({ustr})\n"
                    f"   👥 {invited} пригл. | ⭐ {earned} заработано"
                )
            text = "\n\n".join(lines)
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_back_admin())

    elif action == "adm_workers":
        rows = db_get_workers()
        if not rows:
            await call.message.edit_text("👷 Рабочих нет.", reply_markup=kb_back_admin())
        else:
            kb = InlineKeyboardBuilder()
            lines = [f"👷 Рабочие — {len(rows)} чел.\n\n"]
            for uid, name, uname, invited, buyers, earned in rows:
                ustr = f"@{uname}" if uname else f"ID:{uid}"
                level = get_level(invited)
                pct = db_get_ref_percent(uid)
                lines.append(
                    f"• {name or '?'} ({ustr})\n"
                    f"  👥 {invited} пригл. | ✅ {buyers} куп. | ⭐ {earned} заработано\n"
                    f"  🏆 {level} | 📊 {pct}%\n"
                )
                kb.row(InlineKeyboardButton(
                    text=f"🔍 {name or ustr}",
                    callback_data=f"worker_{uid}"
                ))
            kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back"))
            await call.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())

    elif action == "adm_percent":
        await state.set_state(AdminState.set_percent_user)
        await call.message.edit_text(
            "⚙️ Настройка процента\n\nВведите ID пользователя:\n\nДля отмены /cancel",
            parse_mode="HTML"
        )

    elif action == "adm_user_lookup":
        await state.set_state(AdminState.user_lookup)
        await call.message.edit_text(
            "🔍 Введите ID пользователя:\n\nДля отмены /cancel",
            parse_mode="HTML"
        )

    elif action == "adm_withdrawals":
        rows = db_get_pending_withdrawals()
        if not rows:
            await call.message.edit_text("💸 Заявок нет.", reply_markup=kb_back_admin())
        else:
            for wid, uid, name, uname, amount, req_at in rows:
                ustr = f"@{uname}" if uname else "—"
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Оплачено", callback_data=f"wdone_{wid}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wdecline_{wid}"),
                ]])
                await bot.send_message(
                    ADMIN_ID,
                    f"💸 Заявка #{wid}\n👤 {name or '?'} ({ustr}) — ID <code>{uid}</code>\n⭐ Сумма: <b>{amount}</b> звёзд\n📅 {req_at}",
                    parse_mode="HTML",
                    reply_markup=kb
                )
            await call.message.edit_text(f"📋 Отправлено <b>{len(rows)}</b> заявок ↑", parse_mode="HTML", reply_markup=kb_back_admin())

    elif action == "adm_users":
        s = db_get_stats()
        rows = db_get_recent_users(20)
        lines = [f"👥 Пользователи\nВсего: <b>{s['total_users']}</b> | Сегодня: <b>{s['today_users']}</b>\n\nПоследние 20:"]
        for uid, name, uname, joined in rows:
            ustr = f"@{uname}" if uname else "—"
            lines.append(f"• {name or '?'} ({ustr}) — {joined[:10]}")
        await call.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb_back_admin())

    elif action == "adm_broadcast":
        await state.set_state(BroadcastState.waiting_text)
        await call.message.edit_text(
            "📢 Рассылка\n\nОтправь текст (HTML поддерживается).\nДля отмены /cancel",
            parse_mode="HTML"
        )

    elif action == "adm_back":
        await state.clear()
        s = db_get_stats()
        await call.message.edit_text(
            f"🛡 Админ-панель\n\n👥 Всего: <b>{s['total_users']}</b> | Сегодня: <b>{s['today_users']}</b>\n💳 Покупок сегодня: <b>{s['today_purchases']}</b>",
            parse_mode="HTML",
            reply_markup=kb_admin()
        )

    elif action == "adm_close":
        await call.message.delete()

    await call.answer()

# НАСТРОЙКА ПРОЦЕНТА
@dp.message(AdminState.set_percent_user)
async def set_percent_user(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb_admin())
        return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("Введите числовой ID.")
        return

    con = sqlite3.connect(DB)
    row = con.execute("SELECT first_name, username FROM users WHERE user_id=?", (uid,)).fetchone()
    con.close()

    if not row:
        await message.answer("Пользователь не найден.")
        return

    await state.update_data(user_id=uid)
    await state.set_state(AdminState.set_percent_value)
    await message.answer(
        f"👤 {row[0]} (@{row[1] if row[1] else '—'})\nВведите процент (1-100):\n\nДля отмены /cancel",
        parse_mode="HTML"
    )

@dp.message(AdminState.set_percent_value)
async def set_percent_value(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb_admin())
        return
    try:
        value = int(message.text.strip())
        if value < 1 or value > 100:
            await message.answer("Введите число от 1 до 100.")
            return
    except ValueError:
        await message.answer("Введите число.")
        return

    data = await state.get_data()
    uid = data.get("user_id")
    db_set_ref_percent(uid, value)
    await state.clear()

    con = sqlite3.connect(DB)
    row = con.execute("SELECT first_name FROM users WHERE user_id=?", (uid,)).fetchone()
    con.close()
    name = row[0] if row else str(uid)

    await message.answer(
        f"✅ Процент для {name} изменён на <b>{value}%</b>!",
        parse_mode="HTML",
        reply_markup=kb_admin()
    )

# ПРОСМОТР РАБОЧЕГО
@dp.callback_query(lambda c: c.data and c.data.startswith("worker_"))
async def worker_detail(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Нет доступа", show_alert=True)
        return

    try:
        uid = int(call.data.split("_")[1])
    except:
        await call.answer("Ошибка")
        return

    d = db_get_user_detail(uid)
    if not d["user"]:
        await call.answer("Пользователь не найден", show_alert=True)
        return

    name, uname, banned, total_spent, joined_at, ref_percent = d["user"]
    invited_count = d["invited"]
    ustr = f"@{uname}" if uname else "—"
    level = get_level(invited_count)

    lines = [
        f"🔍 <b>{name or '?'} ({ustr})</b>\nID: <code>{uid}</code>\n\n"
        f"🏆 Уровень: {level}\n"
        f"📊 Процент: {ref_percent}%\n"
        f"👥 Приглашено: <b>{invited_count}</b>\n"
        f"✅ Купили: <b>{d['buyers']}</b>\n"
        f"⭐ Заработано: <b>{d['total']}</b>⭐\n"
        f"💸 Выплачено: <b>{d['paid']}</b>⭐\n"
        f"⏳ В обработке: <b>{d['pending']}</b>⭐\n"
        f"💰 Остаток: <b>{d['balance']}</b>⭐"
    ]

    if d["earnings"]:
        lines.append("\n📜 Последние покупки рефералов:")
        for rname, runame, stars, earned, at in d["earnings"]:
            lines.append(f"  • {rname or '?'} — {stars}⭐ → +{earned}⭐ ({at[:10]})")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад", callback_data="adm_workers")
    ]])

    await call.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    await call.answer()

# ПОИСК ПОЛЬЗОВАТЕЛЯ
@dp.message(AdminState.user_lookup)
async def user_lookup_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb_admin())
        return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("Введите числовой ID.")
        return

    await state.clear()
    d = db_get_user_detail(uid)
    if not d["user"]:
        await message.answer("Пользователь не найден.", reply_markup=kb_admin())
        return

    name, uname, banned, total_spent, joined_at, ref_percent = d["user"]
    invited_count = d["invited"]
    ustr = f"@{uname}" if uname else "—"
    level = get_level(invited_count)
    ban_status = "🔴 ЗАБЛОКИРОВАН" if banned else "🟢 АКТИВЕН"

    lines = [
        f"🔍 <b>Пользователь: {name or '?'} ({ustr})</b>\nID: <code>{uid}</code>\n\n"
        f"Статус: {ban_status}\n"
        f"🏆 Уровень: {level}\n"
        f"📊 Процент: {ref_percent}%\n"
        f"💰 Потрачено: <b>{total_spent}</b>⭐\n"
        f"👥 Приглашено: <b>{d['invited']}</b>\n"
        f"✅ Купили: <b>{d['buyers']}</b>\n"
        f"⭐ Заработано: <b>{d['total']}</b>⭐\n"
        f"💸 Выплачено: <b>{d['paid']}</b>⭐\n"
        f"⏳ В обработке: <b>{d['pending']}</b>⭐\n"
        f"💰 Остаток: <b>{d['balance']}</b>⭐"
    ]

    kb = InlineKeyboardBuilder()
    if banned:
        kb.row(InlineKeyboardButton(text="🔓 Разбанить", callback_data=f"unban_{uid}"))
    else:
        kb.row(InlineKeyboardButton(text="🔒 Забанить", callback_data=f"ban_{uid}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back"))

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())

# БАН/РАЗБАН
@dp.callback_query(lambda c: c.data and (c.data.startswith("ban_") or c.data.startswith("unban_")))
async def handle_ban(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    parts = call.data.split("_")
    action = parts[0]
    uid = int(parts[1])

    if action == "ban":
        db_ban_user(uid, True)
        await call.answer(f"✅ Пользователь {uid} заблокирован", show_alert=True)
    else:
        db_ban_user(uid, False)
        await call.answer(f"✅ Пользователь {uid} разблокирован", show_alert=True)

    d = db_get_user_detail(uid)
    if d["user"]:
        name, uname, banned, total_spent, joined_at, ref_percent = d["user"]
        invited_count = d["invited"]
        ustr = f"@{uname}" if uname else "—"
        level = get_level(invited_count)
        ban_status = "🔴 ЗАБЛОКИРОВАН" if banned else "🟢 АКТИВЕН"

        lines = [
            f"🔍 <b>Пользователь: {name or '?'} ({ustr})</b>\nID: <code>{uid}</code>\n\n"
            f"Статус: {ban_status}\n"
            f"🏆 Уровень: {level}\n"
            f"📊 Процент: {ref_percent}%\n"
            f"💰 Потрачено: <b>{total_spent}</b>⭐\n"
            f"👥 Приглашено: <b>{d['invited']}</b>\n"
            f"✅ Купили: <b>{d['buyers']}</b>\n"
            f"⭐ Заработано: <b>{d['total']}</b>⭐\n"
            f"💸 Выплачено: <b>{d['paid']}</b>⭐\n"
            f"⏳ В обработке: <b>{d['pending']}</b>⭐\n"
            f"💰 Остаток: <b>{d['balance']}</b>⭐"
        ]

        kb = InlineKeyboardBuilder()
        if banned:
            kb.row(InlineKeyboardButton(text="🔓 Разбанить", callback_data=f"unban_{uid}"))
        else:
            kb.row(InlineKeyboardButton(text="🔒 Забанить", callback_data=f"ban_{uid}"))
        kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back"))

        await call.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())

# ВЫПЛАТЫ
@dp.callback_query(lambda c: c.data and (c.data.startswith("wdone_") or c.data.startswith("wdecline_")))
async def handle_withdrawal(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    parts = call.data.split("_")
    action = parts[0]
    wid = int(parts[1])

    con = sqlite3.connect(DB)
    row = con.execute("SELECT user_id, amount FROM withdrawals WHERE id=?", (wid,)).fetchone()
    con.close()

    if not row:
        await call.answer("Заявка не найдена")
        return

    uid, amount = row

    if action == "wdone":
        db_set_withdrawal_status(wid, "done")
        await bot.send_message(uid, f"✅ Выплата {amount}⭐ одобрена!", parse_mode="HTML")
        await call.message.edit_text(f"✅ Заявка #{wid} — оплачено ({amount}⭐)")
    else:
        db_set_withdrawal_status(wid, "declined")
        await bot.send_message(uid, f"❌ Заявка на вывод {amount}⭐ отклонена.\n\nСвяжитесь с @{ADMIN_USERNAME}", parse_mode="HTML")
        await call.message.edit_text(f"❌ Заявка #{wid} — отклонена")
    await call.answer()

# РАССЫЛКА
@dp.message(BroadcastState.waiting_text)
async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=kb_admin())
        return

    await state.clear()
    users = db_get_all_users()
    total = len(users)
    ok, fail = 0, 0

    status_msg = await message.answer(f"⏳ Рассылка... 0/{total}")

    for i, uid in enumerate(users, 1):
        try:
            await bot.send_message(uid, message.html_text, parse_mode="HTML")
            ok += 1
        except:
            fail += 1

        if i % 20 == 0 or i == total:
            try:
                await status_msg.edit_text(f"⏳ Рассылка... {ok}/{total}")
            except:
                pass

        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"✅ Рассылка завершена!\n📨 Отправлено: {ok}\n❌ Ошибок: {fail}",
        parse_mode="HTML",
        reply_markup=kb_back_admin()
    )

# ОПЛАТА
@dp.callback_query(F.data == "menu_stars")
async def menu_stars(call: CallbackQuery):
    if db_is_banned(call.from_user.id):
        return

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="50 ГБ — 600 ⭐", callback_data="stars_full"))
    kb.row(InlineKeyboardButton(text="15 ГБ — 400 ⭐", callback_data="stars_medium"))
    kb.row(InlineKeyboardButton(text="5 ГБ — 350 ⭐", callback_data="stars_small"))
    kb.row(InlineKeyboardButton(text="💫 Где купить звёзды?", url=STARS_BUY))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_start"))
    await call.message.edit_text(
        "⭐ Оплата звёздами\n\n✅ После оплаты — доступ сразу.\nВыберите объём:",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@dp.callback_query(F.data == "menu_crypto")
async def menu_crypto(call: CallbackQuery):
    if db_is_banned(call.from_user.id):
        return

    kb = InlineKeyboardBuilder()
    if PLANS["full"]["crypto"]:
        kb.row(InlineKeyboardButton(text="50 ГБ — Оплатить", url=PLANS["full"]["crypto"]))
    if PLANS["medium"]["crypto"]:
        kb.row(InlineKeyboardButton(text="15 ГБ — Оплатить", url=PLANS["medium"]["crypto"]))
    if PLANS["small"]["crypto"]:
        kb.row(InlineKeyboardButton(text="5 ГБ — Оплатить", url=PLANS["small"]["crypto"]))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_start"))
    await call.message.edit_text(
        "🌐 Оплата криптой\n\n✅ После оплаты — доступ сразу.",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("stars_"))
async def send_invoice(call: CallbackQuery):
    if db_is_banned(call.from_user.id):
        return

    key = call.data.replace("stars_", "")
    plan = PLANS.get(key)
    if not plan:
        await call.answer("Тариф не найден", show_alert=True)
        return

    await bot.send_invoice(
        chat_id=call.message.chat.id,
        title=f"TENDO — {plan['label']}",
        description=f"Доступ к контенту {plan['label']}. Автовыдача сразу ✅",
        payload=f"tendo_{key}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="XTR", amount=plan["stars"])],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"⭐ Заплатить {plan['stars']} звёзд", pay=True)
        ]])
    )
    await call.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(lambda m: m.successful_payment is not None)
async def successful_payment(message: Message):
    key = message.successful_payment.invoice_payload.replace("tendo_", "")
    stars = message.successful_payment.total_amount
    ref_id, earned = db_add_purchase(message.from_user.id, key, stars)

    if ref_id and earned:
        buyer_name = message.from_user.first_name
        pct = db_get_ref_percent(ref_id)
        invited_count = db_get_invited_count(ref_id)
        level = get_level(invited_count)
        try:
            await bot.send_message(
                ref_id,
                f"🎉 Реферал купил!\n\n👤 {buyer_name}\n📦 {PLAN_NAMES.get(key, key)} — {stars}⭐\n💰 Ты получил: +{earned}⭐\n🏆 Уровень: {level}\n📊 Процент: {pct}%",
                parse_mode="HTML"
            )
        except:
            pass

    uname = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 Новая покупка!\n\n👤 {uname} (ID: <code>{message.from_user.id}</code>)\n📦 {PLAN_NAMES.get(key, key)} — {stars}⭐\n{'🤝 Реферал от ID: ' + str(ref_id) + f' (+{earned}⭐)' if ref_id else '🔗 Без реферала'}\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            parse_mode="HTML"
        )
    except:
        pass

    await message.answer(
        "✅ Оплата прошла успешно!\n\nНажми кнопку ниже 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📁 Получить контент", url=CHANNEL_LINK)
        ]])
    )

@dp.callback_query(F.data == "back_start")
async def back_start(call: CallbackQuery):
    if db_is_banned(call.from_user.id):
        return

    await call.message.edit_text(
        "🌿 TENDO\n\n✅ Автовыдача сразу после оплаты\n🔒 Безопасная оплата через Telegram Stars\n\nВыберите способ оплаты:",
        parse_mode="HTML",
        reply_markup=kb_main()
    )
    await call.answer()

# ЗАПУСК
async def main():
    print("✅ Бот TENDO запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())