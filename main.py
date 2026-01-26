import os
import json
import time
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
from contextlib import asynccontextmanager

import aiosqlite
import aiohttp
from aiohttp import web
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import RPCError


# =========================
# Logging
# =========================
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("giftbot")


# =========================
# Env
# =========================
load_dotenv()


def env_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


BOT_TOKEN = env_required("BOT_TOKEN")
TG_API_ID = int(env_required("TG_API_ID"))
TG_API_HASH = env_required("TG_API_HASH")
RELAYER_SESSION = env_required("RELAYER_SESSION")

CRYPTOPAY_TOKEN = env_required("CRYPTOPAY_TOKEN")
CRYPTOPAY_BASE_URL = os.getenv("CRYPTOPAY_BASE_URL", "https://pay.crypt.bot").rstrip("/")

# Pricing (your business logic)
PRICE_PER_STAR = float(os.getenv("PRICE_PER_STAR", "0.015"))
PRICE_MIN = float(os.getenv("PRICE_MIN", "0.10"))

# CryptoBot Invoice config
CURRENCY_TYPE = os.getenv("CRYPTOPAY_CURRENCY_TYPE", "crypto").lower().strip()  # "crypto" | "fiat"
PAY_ASSET = os.getenv("CRYPTOPAY_ASSET", "USDT").upper().strip()
PAY_FIAT = os.getenv("CRYPTOPAY_FIAT", "USD").upper().strip()
ACCEPTED_ASSETS = os.getenv("CRYPTOPAY_ACCEPTED_ASSETS", "USDT,TON").upper().strip()

INVOICE_EXPIRES_IN = int(os.getenv("INVOICE_EXPIRES_IN", "1800"))
INVOICE_POLL_INTERVAL = float(os.getenv("INVOICE_POLL_INTERVAL", "10"))

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

DB_PATH = os.getenv("DB_PATH", "bot.db")

PORT = int(os.getenv("PORT", "8080"))
WEB_BIND = os.getenv("WEB_BIND", "0.0.0.0")

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip()  # optional for paid button


# =========================
# i18n
# ========================
LANGS = ("uz", "ru", "en")

T = {
    "uz": {
        "menu_recipient": "🎯 Qabul qiluvchi",
        "menu_comment": "💬 Komment",
        "menu_gift": "🎁 Sovg'a tanlash",
        "menu_mode_anon": "🕵️ Anonim (hide name)",
        "menu_mode_profile": "👤 Profil (show name)",
        "menu_invoice": "💳 CryptoBot Invoice",
        "menu_lang": "🌐 Til",
        "back_menu": "⬅️ Menu",
        "back_prices": "⬅️ Narxlar",

        "status_title": "📌 Hozirgi sozlamalar:",
        "status_target": "🎯 Qabul qiluvchi: {target}",
        "status_comment": "💬 Komment: {comment}",
        "status_gift": "🎁 Sovg‘a: {gift}",
        "status_mode": "🔒 Rejim: {mode}",
        "status_choose": "\nQuyidan tanlang:",

        "mode_anon": "🕵️ Anonim (hide name)",
        "mode_profile": "👤 Profil (show name)",
        "comment_empty": "(yo‘q)",
        "gift_none": "Tanlanmagan",

        "prompt_target": (
            "🎯 Qabul qiluvchini yuboring:\n"
            "- `me` (siz)\n"
            "- `@username`\n"
            "- `user_id` (raqam)\n\n"
            "✅ Eng ishonchlisi: @username\n"
            "⚠️ user_id ba’zan ishlamasligi mumkin."
        ),
        "prompt_comment": (
            "💬 Komment yuboring (ixtiyoriy).\n"
            "O‘chirish uchun: `-` yuboring.\n"
            "Masalan: `Congrats 🎁` yoki `:)`"
        ),
        "pick_price": "🎁 Sovg‘a narxini tanlang:",
        "pick_by_price": "⭐ {price} bo‘yicha sovg‘a tanlang:",
        "gift_selected": "✅ Sovg‘a tanlandi:\n{label} (⭐{stars})\nID: {gid}\n\nEndi: 💳 Invoice yarating.",

        "saved_target": "✅ Qabul qiluvchi saqlandi.\n\n{status}",
        "saved_comment": "✅ Komment saqlandi.\n\n{status}",
        "deleted_comment": "✅ Komment o‘chirildi.\n\n{status}",

        "need_gift_first": "❌ Avval sovg‘ani tanlang.\n\n{status}",

        "invoice_creating": (
            "⏳ Invoice yaratilmoqda...\n"
            "🧾 Buyurtma: #{order}\n"
            "🎁 Gift: {gift} (⭐{stars})\n"
            "🎯 Target: {target}\n"
            "🔒 Rejim: {mode}\n"
            "💬 Comment: {comment}\n"
            "💵 To‘lov: {amount} {cur}"
        ),
        "invoice_ready": (
            "✅ Invoice tayyor!\n\n"
            "🧾 Buyurtma: #{order}\n"
            "🎁 Gift: {gift} (⭐{stars})\n"
            "🎯 Target: {target}\n"
            "💵 To‘lov: {amount} {cur}\n\n"
            "To‘lang, bot o‘zi tekshiradi va sovg‘ani yuboradi."
        ),
        "invoice_open": "💳 Invoice ochish",
        "invoice_check": "🔄 Tekshirish",

        "check_not_found": "❌ Invoice topilmadi (API).",
        "check_forbidden": "❌ Buyurtma topilmadi yoki ruxsat yo‘q.",
        "check_no_invoice": "❌ Invoice yo‘q.",
        "check_expired": "⌛ Invoice muddati tugagan (expired).",
        "check_status": "🧾 Buyurtma: #{order}\n📌 Invoice status: {status}\n\nTo‘lagan bo‘lsangiz, 5-10 soniyada yangilanadi.",

        "paid_sending": "✅ Invoice PAID ✅\n🎁 Sovg‘a avtomatik yuborilmoqda...",
        "already_sent": "✅ Bu buyurtma allaqachon yakunlangan.\n🎁 Sovg‘a yuborilgan.",
        "already_sending": "⏳ Sovg‘a yuborilmoqda, biroz kuting.",

        "delivery_sent_dm": (
            "✅ Sovg‘a yuborildi!\n"
            "🧾 Buyurtma: #{order}\n"
            "🎁 {gift} (⭐{stars})\n"
            "🎯 Target: {target}\n"
            "🔒 Rejim: {mode}\n"
            "{comment_line}"
            "{comment_warn}"
        ),
        "comment_line": "💬 Comment: {comment}\n",
        "comment_warn": "⚠️ Komment qabul qilinmadi (fallback comment-siz yuborildi).\n",

        "delivery_failed_dm": "❌ Sovg‘ani yuborib bo‘lmadi.\n🧾 Buyurtma: #{order}\nXatolik: {err}",
        "toggle_anon_on": "✅ Anonim yoqildi (hide name)",
        "toggle_anon_off": "✅ Profil ko‘rinadi (show name)",

        "lang_pick": "🌐 Tilni tanlang:",
        "lang_set": "✅ Til saqlandi.",
    },

    "ru": {
        "menu_recipient": "🎯 Получатель",
        "menu_comment": "💬 Комментарий",
        "menu_gift": "🎁 Выбор подарка",
        "menu_mode_anon": "🕵️ Анонимно (hide name)",
        "menu_mode_profile": "👤 Профиль (show name)",
        "menu_invoice": "💳 CryptoBot Invoice",
        "menu_lang": "🌐 Язык",
        "back_menu": "⬅️ Меню",
        "back_prices": "⬅️ Цены",

        "status_title": "📌 Текущие настройки:",
        "status_target": "🎯 Получатель: {target}",
        "status_comment": "💬 Комментарий: {comment}",
        "status_gift": "🎁 Подарок: {gift}",
        "status_mode": "🔒 Режим: {mode}",
        "status_choose": "\nВыберите действие:",

        "mode_anon": "🕵️ Анонимно (hide name)",
        "mode_profile": "👤 Профиль (show name)",
        "comment_empty": "(нет)",
        "gift_none": "Не выбран",

        "prompt_target": (
            "🎯 Отправьте получателя:\n"
            "- `me` (вы)\n"
            "- `@username`\n"
            "- `user_id` (цифры)\n\n"
            "✅ Самый надежный: @username\n"
            "⚠️ user_id иногда не работает."
        ),
        "prompt_comment": (
            "💬 Отправьте комментарий (необязательно).\n"
            "Чтобы удалить: отправьте `-`.\n"
            "Напр.: `Congrats 🎁` или `:)`"
        ),
        "pick_price": "🎁 Выберите цену подарка:",
        "pick_by_price": "⭐ Подарки за {price}:",
        "gift_selected": "✅ Подарок выбран:\n{label} (⭐{stars})\nID: {gid}\n\nДалее: 💳 Создайте invoice.",

        "saved_target": "✅ Получатель сохранен.\n\n{status}",
        "saved_comment": "✅ Комментарий сохранен.\n\n{status}",
        "deleted_comment": "✅ Комментарий удален.\n\n{status}",

        "need_gift_first": "❌ Сначала выберите подарок.\n\n{status}",

        "invoice_creating": (
            "⏳ Создаю invoice...\n"
            "🧾 Заказ: #{order}\n"
            "🎁 Gift: {gift} (⭐{stars})\n"
            "🎯 Target: {target}\n"
            "🔒 Режим: {mode}\n"
            "💬 Comment: {comment}\n"
            "💵 Оплата: {amount} {cur}"
        ),
        "invoice_ready": (
            "✅ Invoice готов!\n\n"
            "🧾 Заказ: #{order}\n"
            "🎁 Gift: {gift} (⭐{stars})\n"
            "🎯 Target: {target}\n"
            "💵 Оплата: {amount} {cur}\n\n"
            "Оплатите — бот сам проверит и отправит подарок."
        ),
        "invoice_open": "💳 Открыть invoice",
        "invoice_check": "🔄 Проверить",

        "check_not_found": "❌ Invoice не найден (API).",
        "check_forbidden": "❌ Заказ не найден или нет доступа.",
        "check_no_invoice": "❌ Нет invoice.",
        "check_expired": "⌛ Invoice просрочен (expired).",
        "check_status": "🧾 Заказ: #{order}\n📌 Статус invoice: {status}\n\nЕсли оплатили — обновится через 5-10 секунд.",

        "paid_sending": "✅ Invoice PAID ✅\n🎁 Подарок отправляется автоматически...",
        "already_sent": "✅ Этот заказ уже выполнен.\n🎁 Подарок отправлен.",
        "already_sending": "⏳ Подарок отправляется, подождите.",

        "delivery_sent_dm": (
            "✅ Подарок отправлен!\n"
            "🧾 Заказ: #{order}\n"
            "🎁 {gift} (⭐{stars})\n"
            "🎯 Target: {target}\n"
            "🔒 Режим: {mode}\n"
            "{comment_line}"
            "{comment_warn}"
        ),
        "comment_line": "💬 Comment: {comment}\n",
        "comment_warn": "⚠️ Комментарий не применился (fallback без комментария).\n",

        "delivery_failed_dm": "❌ Не удалось отправить подарок.\n🧾 Заказ: #{order}\nОшибка: {err}",
        "toggle_anon_on": "✅ Анонимный режим включен (hide name)",
        "toggle_anon_off": "✅ Профиль виден (show name)",

        "lang_pick": "🌐 Выберите язык:",
        "lang_set": "✅ Язык сохранен.",
    },

    "en": {
        "menu_recipient": "🎯 Recipient",
        "menu_comment": "💬 Comment",
        "menu_gift": "🎁 Choose gift",
        "menu_mode_anon": "🕵️ Anonymous (hide name)",
        "menu_mode_profile": "👤 Profile (show name)",
        "menu_invoice": "💳 CryptoBot Invoice",
        "menu_lang": "🌐 Language",
        "back_menu": "⬅️ Menu",
        "back_prices": "⬅️ Prices",

        "status_title": "📌 Current settings:",
        "status_target": "🎯 Recipient: {target}",
        "status_comment": "💬 Comment: {comment}",
        "status_gift": "🎁 Gift: {gift}",
        "status_mode": "🔒 Mode: {mode}",
        "status_choose": "\nChoose:",

        "mode_anon": "🕵️ Anonymous (hide name)",
        "mode_profile": "👤 Profile (show name)",
        "comment_empty": "(none)",
        "gift_none": "Not selected",

        "prompt_target": (
            "🎯 Send recipient:\n"
            "- `me` (you)\n"
            "- `@username`\n"
            "- `user_id` (digits)\n\n"
            "✅ Best: @username\n"
            "⚠️ user_id may not work sometimes."
        ),
        "prompt_comment": (
            "💬 Send a comment (optional).\n"
            "To delete: send `-`.\n"
            "E.g.: `Congrats 🎁` or `:)`"
        ),
        "pick_price": "🎁 Choose price:",
        "pick_by_price": "⭐ Gifts for {price}:",
        "gift_selected": "✅ Gift selected:\n{label} (⭐{stars})\nID: {gid}\n\nNext: create invoice.",

        "saved_target": "✅ Recipient saved.\n\n{status}",
        "saved_comment": "✅ Comment saved.\n\n{status}",
        "deleted_comment": "✅ Comment removed.\n\n{status}",

        "need_gift_first": "❌ Choose a gift first.\n\n{status}",

        "invoice_creating": (
            "⏳ Creating invoice...\n"
            "🧾 Order: #{order}\n"
            "🎁 Gift: {gift} (⭐{stars})\n"
            "🎯 Target: {target}\n"
            "🔒 Mode: {mode}\n"
            "💬 Comment: {comment}\n"
            "💵 Pay: {amount} {cur}"
        ),
        "invoice_ready": (
            "✅ Invoice ready!\n\n"
            "🧾 Order: #{order}\n"
            "🎁 Gift: {gift} (⭐{stars})\n"
            "🎯 Target: {target}\n"
            "💵 Pay: {amount} {cur}\n\n"
            "Pay it — bot will auto-check and send the gift."
        ),
        "invoice_open": "💳 Open invoice",
        "invoice_check": "🔄 Check",

        "check_not_found": "❌ Invoice not found (API).",
        "check_forbidden": "❌ Order not found or no access.",
        "check_no_invoice": "❌ No invoice.",
        "check_expired": "⌛ Invoice expired.",
        "check_status": "🧾 Order: #{order}\n📌 Invoice status: {status}\n\nIf paid, it updates in 5–10 seconds.",

        "paid_sending": "✅ Invoice PAID ✅\n🎁 Gift is being sent automatically...",
        "already_sent": "✅ This order is completed.\n🎁 Gift already sent.",
        "already_sending": "⏳ Gift is being sent, please wait.",

        "delivery_sent_dm": (
            "✅ Gift sent!\n"
            "🧾 Order: #{order}\n"
            "🎁 {gift} (⭐{stars})\n"
            "🎯 Target: {target}\n"
            "🔒 Mode: {mode}\n"
            "{comment_line}"
            "{comment_warn}"
        ),
        "comment_line": "💬 Comment: {comment}\n",
        "comment_warn": "⚠️ Comment was rejected (fallback sent without comment).\n",

        "delivery_failed_dm": "❌ Failed to send gift.\n🧾 Order: #{order}\nError: {err}",
        "toggle_anon_on": "✅ Anonymous enabled (hide name)",
        "toggle_anon_off": "✅ Profile visible (show name)",

        "lang_pick": "🌐 Choose language:",
        "lang_set": "✅ Language saved.",
    },
}


def t(lang: str, key: str, **kw) -> str:
    lang = lang if lang in T else "ru"
    s = T[lang].get(key) or T["ru"].get(key) or key
    try:
        return s.format(**kw)
    except Exception:
        return s


# =========================
# Gifts
# =========================
@dataclass(frozen=True)
class GiftItem:
    id: int
    stars: int
    label: str


GIFT_CATALOG: List[GiftItem] = [
    GiftItem(6028601630662853006, 50, "🍾 50★"),
    GiftItem(5170521118301225164, 100, "💎 100★"),
    GiftItem(5170690322832818290, 100, "💍 100★"),
    GiftItem(5168043875654172773, 100, "🏆 100★"),
    GiftItem(5170564780938756245, 50, "🚀 50★"),
    GiftItem(5170314324215857265, 50, "💐 50★"),
    GiftItem(5170144170496491616, 50, "🎂 50★"),
    GiftItem(5168103777563050263, 25, "🌹 25★"),
    GiftItem(5170250947678437525, 25, "🎁 25★"),
    GiftItem(5170233102089322756, 15, "🧸 15★"),
    GiftItem(5170145012310081615, 15, "💝 15★"),
    GiftItem(5922558454332916696, 50, "🎄 50★"),
    GiftItem(5956217000635139069, 50, "🧸(hat) 50★"),
]

GIFTS_BY_PRICE: Dict[int, List[GiftItem]] = {}
GIFTS_BY_ID: Dict[int, GiftItem] = {}
for g in GIFT_CATALOG:
    GIFTS_BY_PRICE.setdefault(g.stars, []).append(g)
    GIFTS_BY_ID[g.id] = g

ALLOWED_PRICES = sorted(GIFTS_BY_PRICE.keys())


# =========================
# DB (aiosqlite safe + migrations)
# =========================
@asynccontextmanager
async def db_connect():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute("PRAGMA busy_timeout=5000;")
        yield db


async def _table_info(db: aiosqlite.Connection, table: str) -> List[str]:
    cur = await db.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    return [r[1] for r in rows]  # name column


async def _add_column_if_missing(db: aiosqlite.Connection, table: str, col_name: str, col_def_sql: str):
    cols = await _table_info(db, table)
    if col_name in cols:
        return
    await db.execute(f"ALTER TABLE {table} ADD COLUMN {col_def_sql}")


async def db_init():
    async with db_connect() as db:
        # create tables if not exist
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            target TEXT DEFAULT NULL,
            comment TEXT DEFAULT NULL,
            selected_gift_id INTEGER DEFAULT NULL,
            anonymous INTEGER DEFAULT 0,
            lang TEXT DEFAULT 'ru'
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            target TEXT NOT NULL,
            gift_id INTEGER NOT NULL,
            stars INTEGER NOT NULL,
            comment TEXT DEFAULT NULL,
            anonymous INTEGER NOT NULL DEFAULT 0,

            price_amount TEXT NOT NULL,
            price_currency TEXT NOT NULL,

            invoice_id INTEGER,
            invoice_url TEXT,

            origin_chat_id INTEGER,
            origin_message_id INTEGER,

            status TEXT NOT NULL DEFAULT 'creating', -- creating|active|paid|sending|sent|failed|expired
            error TEXT DEFAULT NULL,

            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            paid_at INTEGER,
            sent_at INTEGER
        );
        """)
        # migrations for older DB
        await _add_column_if_missing(db, "user_settings", "lang", "lang TEXT DEFAULT 'ru'")
        await _add_column_if_missing(db, "orders", "origin_chat_id", "origin_chat_id INTEGER")
        await _add_column_if_missing(db, "orders", "origin_message_id", "origin_message_id INTEGER")
        await _add_column_if_missing(db, "orders", "paid_at", "paid_at INTEGER")
        await _add_column_if_missing(db, "orders", "sent_at", "sent_at INTEGER")

        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_invoice ON orders(invoice_id);")
        await db.commit()


async def db_ensure_user(user_id: int, default_target: Optional[str] = None):
    async with db_connect() as db:
        await db.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES(?)", (user_id,))
        if default_target:
            await db.execute(
                "UPDATE user_settings SET target=COALESCE(target, ?) WHERE user_id=?",
                (default_target, user_id),
            )
        await db.commit()


async def db_get_settings(user_id: int) -> Tuple[str, Optional[str], Optional[int], int, str]:
    async with db_connect() as db:
        cur = await db.execute(
            "SELECT target, comment, selected_gift_id, anonymous, lang FROM user_settings WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return ("me", None, None, 0, "ru")
        lang = (row[4] or "ru").lower()
        if lang not in LANGS:
            lang = "ru"
        return (row[0] or "me", row[1], row[2], int(row[3] or 0), lang)


async def db_set_lang(user_id: int, lang: str):
    lang = (lang or "ru").lower()
    if lang not in LANGS:
        lang = "ru"
    async with db_connect() as db:
        await db.execute("UPDATE user_settings SET lang=? WHERE user_id=?", (lang, user_id))
        await db.commit()


async def db_set_target(user_id: int, target: str):
    async with db_connect() as db:
        await db.execute("UPDATE user_settings SET target=? WHERE user_id=?", (target, user_id))
        await db.commit()


async def db_set_comment(user_id: int, comment: Optional[str]):
    async with db_connect() as db:
        await db.execute("UPDATE user_settings SET comment=? WHERE user_id=?", (comment, user_id))
        await db.commit()


async def db_set_selected_gift(user_id: int, gift_id: Optional[int]):
    async with db_connect() as db:
        await db.execute("UPDATE user_settings SET selected_gift_id=? WHERE user_id=?", (gift_id, user_id))
        await db.commit()


async def db_toggle_anonymous(user_id: int) -> int:
    async with db_connect() as db:
        cur = await db.execute("SELECT anonymous FROM user_settings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        current = int(row[0] or 0) if row else 0
        new_val = 0 if current == 1 else 1
        await db.execute("UPDATE user_settings SET anonymous=? WHERE user_id=?", (new_val, user_id))
        await db.commit()
        return new_val


async def db_create_order(
    user_id: int,
    target: str,
    gift: GiftItem,
    comment: Optional[str],
    anonymous: int,
    price_amount: str,
    price_currency: str,
) -> int:
    now = int(time.time())
    async with db_connect() as db:
        cur = await db.execute("""
            INSERT INTO orders(
                user_id, target, gift_id, stars, comment, anonymous,
                price_amount, price_currency,
                status, created_at, updated_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (
            user_id, target, gift.id, gift.stars, comment, anonymous,
            price_amount, price_currency,
            "creating", now, now
        ))
        await db.commit()
        return int(cur.lastrowid)


async def db_attach_invoice(order_id: int, invoice_id: int, invoice_url: str):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET invoice_id=?, invoice_url=?, status='active', updated_at=?, error=NULL
            WHERE order_id=?
        """, (invoice_id, invoice_url, now, order_id))
        await db.commit()


async def db_set_order_origin_message(order_id: int, chat_id: int, message_id: int):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET origin_chat_id=?, origin_message_id=?, updated_at=?
            WHERE order_id=?
        """, (chat_id, message_id, now, order_id))
        await db.commit()


async def db_get_order(order_id: int) -> Optional[dict]:
    async with db_connect() as db:
        cur = await db.execute("""
            SELECT order_id, user_id, target, gift_id, stars, comment, anonymous,
                   price_amount, price_currency, invoice_id, invoice_url,
                   origin_chat_id, origin_message_id,
                   status, error, created_at, updated_at, paid_at, sent_at
            FROM orders
            WHERE order_id=?
        """, (order_id,))
        r = await cur.fetchone()
        if not r:
            return None
        return {
            "order_id": r[0],
            "user_id": r[1],
            "target": r[2],
            "gift_id": r[3],
            "stars": r[4],
            "comment": r[5],
            "anonymous": r[6],
            "price_amount": r[7],
            "price_currency": r[8],
            "invoice_id": r[9],
            "invoice_url": r[10],
            "origin_chat_id": r[11],
            "origin_message_id": r[12],
            "status": r[13],
            "error": r[14],
            "created_at": r[15],
            "updated_at": r[16],
            "paid_at": r[17],
            "sent_at": r[18],
        }


async def db_list_active_invoice_orders(limit: int = 200) -> List[dict]:
    """
    Only orders that still need invoice polling.
    IMPORTANT: do NOT include 'sent' orders here.
    """
    async with db_connect() as db:
        cur = await db.execute("""
            SELECT order_id, user_id, invoice_id
            FROM orders
            WHERE status IN ('active','creating') AND invoice_id IS NOT NULL
            ORDER BY created_at ASC
            LIMIT ?
        """, (limit,))
        rows = await cur.fetchall()
        return [{"order_id": r[0], "user_id": r[1], "invoice_id": r[2]} for r in rows]


async def db_mark_paid_if_needed(order_id: int) -> bool:
    """
    Mark paid ONLY if current status is 'active' or 'creating'.
    Never revert from 'sent' back to 'paid'.
    Returns True if changed to paid.
    """
    now = int(time.time())
    async with db_connect() as db:
        cur = await db.execute("""
            UPDATE orders
            SET status='paid', paid_at=?, updated_at=?, error=NULL
            WHERE order_id=? AND status IN ('active','creating')
        """, (now, now, order_id))
        await db.commit()
        return cur.rowcount == 1


async def db_mark_expired_if_needed(order_id: int) -> bool:
    now = int(time.time())
    async with db_connect() as db:
        cur = await db.execute("""
            UPDATE orders
            SET status='expired', updated_at=?, error='Invoice expired'
            WHERE order_id=? AND status IN ('active','creating')
        """, (now, order_id))
        await db.commit()
        return cur.rowcount == 1


async def db_claim_sending(order_id: int) -> bool:
    """
    Atomic claim: only one worker can move paid -> sending.
    Returns True if successfully claimed.
    """
    now = int(time.time())
    async with db_connect() as db:
        cur = await db.execute("""
            UPDATE orders
            SET status='sending', updated_at=?
            WHERE order_id=? AND status='paid'
        """, (now, order_id))
        await db.commit()
        return cur.rowcount == 1


async def db_mark_sent(order_id: int):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET status='sent', sent_at=?, updated_at=?, error=NULL
            WHERE order_id=?
        """, (now, now, order_id))
        await db.commit()


async def db_mark_failed(order_id: int, error: str):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET status='failed', updated_at=?, error=?
            WHERE order_id=?
        """, (now, error, order_id))
        await db.commit()


# =========================
# Crypto Pay API
# =========================
class CryptoPayAPI:
    def __init__(self, token: str, base_url: str):
        self.token = token
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        if self.session:
            return
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))

    async def stop(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def _post(self, method_name: str, params: Optional[dict] = None) -> dict:
        if not self.session:
            raise RuntimeError("CryptoPayAPI not started")
        url = f"{self.base_url}/api/{method_name}"
        headers = {
            "Crypto-Pay-API-Token": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        async with self.session.post(url, headers=headers, json=(params or {})) as resp:
            data = await resp.json(content_type=None)
            if not isinstance(data, dict) or data.get("ok") is not True:
                raise RuntimeError(f"CryptoPay API error ({method_name}): {data}")
            return data["result"]

    async def get_me(self) -> dict:
        return await self._post("getMe")

    async def create_invoice(
        self,
        *,
        description: str,
        payload: str,
        amount: str,
        currency_type: str,
        asset: Optional[str] = None,
        fiat: Optional[str] = None,
        accepted_assets: Optional[str] = None,
        expires_in: Optional[int] = None,
        allow_comments: bool = False,
        allow_anonymous: bool = True,
        paid_btn_url: Optional[str] = None,
    ) -> dict:
        params: dict = {
            "currency_type": currency_type,
            "amount": amount,
            "description": description[:1024],
            "payload": payload[:4096],
            "allow_comments": allow_comments,
            "allow_anonymous": allow_anonymous,
        }
        if expires_in:
            params["expires_in"] = int(expires_in)

        if paid_btn_url:
            params["paid_btn_name"] = "openBot"
            params["paid_btn_url"] = paid_btn_url

        if currency_type == "crypto":
            params["asset"] = asset
        else:
            params["fiat"] = fiat
            if accepted_assets:
                params["accepted_assets"] = accepted_assets

        return await self._post("createInvoice", params)

    async def get_invoices(self, *, invoice_ids: str) -> List[dict]:
        result = await self._post("getInvoices", {"invoice_ids": invoice_ids, "count": 1000})
        return result.get("items", [])


# =========================
# Relayer (Telethon)
# =========================
class Relayer:
    def __init__(self):
        self.client = TelegramClient(
            StringSession(RELAYER_SESSION),
            TG_API_ID,
            TG_API_HASH,
            timeout=25,
            connection_retries=5,
            retry_delay=2,
            auto_reconnect=True,
        )
        self._lock = asyncio.Lock()

    async def start(self):
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError("RELAYER_SESSION invalid. QR bilan qayta session oling.")
        return await self.client.get_me()

    async def stop(self):
        await self.client.disconnect()

    @staticmethod
    def _clean_comment(s: Optional[str]) -> Optional[str]:
        if not s:
            return None
        t0 = s.strip().replace("\r", " ").replace("\n", " ")
        if not t0:
            return None
        if len(t0) > 120:
            t0 = t0[:120]
        return t0

    async def send_star_gift(
        self,
        *,
        target: Union[str, int],
        gift: GiftItem,
        comment: Optional[str],
        hide_name: bool,
    ) -> bool:
        async with self._lock:
            can = await self.client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")

            try:
                peer = await self.client.get_input_entity(target)
            except Exception:
                if isinstance(target, int):
                    raise RuntimeError(
                        "❌ user_id orqali entity topilmadi.\n"
                        "✅ @username ishlating yoki qabul qiluvchi relayerga 1 marta yozsin."
                    )
                raise

            cleaned = self._clean_comment(comment)
            msg_obj = None
            if cleaned:
                msg_obj = types.TextWithEntities(text=cleaned, entities=[])

            extra = {}
            if hide_name:
                extra["hide_name"] = True

            async def _try_send(message_obj):
                invoice = types.InputInvoiceStarGift(
                    peer=peer,
                    gift_id=gift.id,
                    message=message_obj,
                    **extra
                )
                form = await self.client(functions.payments.GetPaymentFormRequest(invoice=invoice))
                await self.client(functions.payments.SendStarsFormRequest(form_id=form.form_id, invoice=invoice))

            if msg_obj is None:
                await _try_send(None)
                return False

            try:
                await _try_send(msg_obj)
                return True
            except RPCError as e:
                if "STARGIFT_MESSAGE_INVALID" in str(e):
                    await _try_send(None)
                    return False
                raise


# =========================
# Utils
# =========================
def calc_invoice_amount(stars: int) -> float:
    amt = stars * PRICE_PER_STAR
    if amt < PRICE_MIN:
        amt = PRICE_MIN
    return float(f"{amt:.2f}")


def normalize_target(text: str) -> str:
    t0 = (text or "").strip()
    if not t0:
        return "me"
    if t0.lower() == "me":
        return "me"
    if t0.startswith("@"):
        return t0
    if t0.isdigit():
        return t0
    return "@" + t0


def safe_comment(text: str) -> str:
    t0 = (text or "").strip()
    if len(t0) > 250:
        t0 = t0[:250]
    return t0


def resolve_target_for_user(stored_target: str, user_id: int, username: Optional[str]) -> Union[str, int]:
    t0 = (stored_target or "me").strip()
    if t0.lower() == "me":
        return ("@" + username) if username else user_id
    if t0.startswith("@"):
        return t0
    if t0.isdigit():
        return int(t0)
    return "@" + t0


async def admin_notify(text: str, bot: Bot):
    if ADMIN_CHAT_ID and ADMIN_CHAT_ID != 0:
        try:
            await bot.send_message(ADMIN_CHAT_ID, text)
        except Exception:
            pass


async def safe_edit_message_obj(msg, *, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    """
    Avoid 'message is not modified' when user clicks buttons repeatedly.
    """
    try:
        cur_text = getattr(msg, "text", None) or ""
        cur_kb = getattr(msg, "reply_markup", None)
        if cur_text == text and ((reply_markup is None and cur_kb is None) or (reply_markup is not None and cur_kb == reply_markup)):
            return False
        await msg.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return False
        raise


async def safe_edit_by_id(bot: Bot, chat_id: int, message_id: int, *, text: str, reply_markup: Optional[InlineKeyboardMarkup]):
    try:
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        # if message deleted/invalid - ignore silently
        if "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
            return
        raise
    except Exception:
        return


# =========================
# UI builders
# =========================
def main_menu_kb(lang: str, anonymous: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "menu_recipient"), callback_data="menu:target")
    kb.button(text=t(lang, "menu_comment"), callback_data="menu:comment")
    kb.button(text=t(lang, "menu_gift"), callback_data="menu:gift")
    kb.button(
        text=(t(lang, "menu_mode_anon") if anonymous == 1 else t(lang, "menu_mode_profile")),
        callback_data="toggle:anon"
    )
    kb.button(text=t(lang, "menu_invoice"), callback_data="pay:create")
    kb.button(text=t(lang, "menu_lang"), callback_data="lang:menu")
    kb.adjust(2, 2, 2)
    return kb.as_markup()


def back_menu_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "back_menu"), callback_data="menu:home")
    return kb.as_markup()


def price_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in ALLOWED_PRICES:
        kb.button(text=f"⭐ {p}", callback_data=f"price:{p}")
    kb.button(text=t(lang, "back_menu"), callback_data="menu:home")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def gifts_by_price_kb(lang: str, price: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in GIFTS_BY_PRICE.get(price, []):
        kb.button(text=f"{g.label}", callback_data=f"gift:{g.id}")
    kb.button(text=t(lang, "back_prices"), callback_data="menu:gift")
    kb.adjust(1)
    return kb.as_markup()


def pay_invoice_kb(lang: str, invoice_url: str, order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "invoice_open"), url=invoice_url)
    kb.button(text=t(lang, "invoice_check"), callback_data=f"pay:check:{order_id}")
    kb.button(text=t(lang, "back_menu"), callback_data="menu:home")
    kb.adjust(1, 2)
    return kb.as_markup()


def paid_done_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "back_menu"), callback_data="menu:home")
    return kb.as_markup()


def lang_pick_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🇺🇿 UZ", callback_data="lang:set:uz")
    kb.button(text="🇷🇺 RU", callback_data="lang:set:ru")
    kb.button(text="🇬🇧 EN", callback_data="lang:set:en")
    kb.button(text=t(lang, "back_menu"), callback_data="menu:home")
    kb.adjust(3, 1)
    return kb.as_markup()


async def render_status_text_and_kb(user_id: int) -> Tuple[str, InlineKeyboardMarkup, str]:
    target, comment, sel_gift_id, anonymous, lang = await db_get_settings(user_id)

    gift_txt = t(lang, "gift_none")
    if sel_gift_id and sel_gift_id in GIFTS_BY_ID:
        g = GIFTS_BY_ID[sel_gift_id]
        gift_txt = f"{g.label} (⭐{g.stars})"

    comment_txt = comment if comment else t(lang, "comment_empty")
    mode_txt = t(lang, "mode_anon") if anonymous == 1 else t(lang, "mode_profile")

    text = (
        f"{t(lang, 'status_title')}\n"
        f"{t(lang, 'status_target', target=target)}\n"
        f"{t(lang, 'status_comment', comment=comment_txt)}\n"
        f"{t(lang, 'status_gift', gift=gift_txt)}\n"
        f"{t(lang, 'status_mode', mode=mode_txt)}\n"
        f"{t(lang, 'status_choose')}"
    )
    return text, main_menu_kb(lang, anonymous), lang


# =========================
# App objects
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
cryptopay = CryptoPayAPI(CRYPTOPAY_TOKEN, CRYPTOPAY_BASE_URL)
relayer = Relayer()

# local in-process guard for same order task spam
_processing: set[int] = set()
_processing_lock = asyncio.Lock()


# =========================
# Delivery core
# =========================
async def _update_origin_message(order: dict, lang: str, text: str, done: bool):
    chat_id = order.get("origin_chat_id")
    msg_id = order.get("origin_message_id")
    if chat_id and msg_id:
        kb = paid_done_kb(lang) if done else paid_done_kb(lang)
        await safe_edit_by_id(bot, int(chat_id), int(msg_id), text=text, reply_markup=kb)


async def process_order_send(order_id: int):
    """
    Sends gift exactly once:
    - requires order.status == 'paid'
    - atomically claims paid->sending using db_claim_sending
    - marks sent/failed
    """
    async with _processing_lock:
        if order_id in _processing:
            return
        _processing.add(order_id)

    try:
        order = await db_get_order(order_id)
        if not order:
            return

        user_id = int(order["user_id"])
        _, _, _, _, lang = await db_get_settings(user_id)

        # if already sent/sending -> do nothing
        if order["status"] == "sent":
            return
        if order["status"] == "sending":
            return

        # claim paid->sending atomically (prevents double-send)
        claimed = await db_claim_sending(order_id)
        if not claimed:
            # maybe not paid yet / already claimed / already sent
            return

        # update origin message: sending
        await _update_origin_message(order, lang, t(lang, "paid_sending"), done=False)

        gift = GIFTS_BY_ID.get(int(order["gift_id"]))
        if not gift:
            raise RuntimeError("Gift not found in catalog")

        stored_target = str(order["target"])
        if stored_target.startswith("@"):
            target: Union[str, int] = stored_target
        elif stored_target.isdigit():
            target = int(stored_target)
        else:
            target = stored_target

        comment = order.get("comment")
        anonymous = int(order.get("anonymous") or 0)
        mode_txt = t(lang, "mode_anon") if anonymous == 1 else t(lang, "mode_profile")

        comment_attached = await relayer.send_star_gift(
            target=target,
            gift=gift,
            comment=comment,
            hide_name=(anonymous == 1),
        )

        await db_mark_sent(order_id)

        # update origin message: sent (no more check button!)
        done_text = t(lang, "already_sent")
        await _update_origin_message(order, lang, done_text, done=True)

        comment_line = ""
        comment_warn = ""
        if comment:
            comment_line = t(lang, "comment_line", comment=comment)
            if not comment_attached:
                comment_warn = t(lang, "comment_warn")

        await bot.send_message(
            user_id,
            t(
                lang,
                "delivery_sent_dm",
                order=order_id,
                gift=gift.label,
                stars=gift.stars,
                target=stored_target,
                mode=mode_txt,
                comment_line=comment_line,
                comment_warn=comment_warn,
            )
        )

    except Exception as e:
        err = str(e)
        await db_mark_failed(order_id, err)
        try:
            order = await db_get_order(order_id)
            if order:
                user_id = int(order["user_id"])
                _, _, _, _, lang = await db_get_settings(user_id)
                await _update_origin_message(order, lang, t(lang, "delivery_failed_dm", order=order_id, err=err), done=True)
                await bot.send_message(user_id, t(lang, "delivery_failed_dm", order=order_id, err=err))
        except Exception:
            pass
        await admin_notify(f"❌ Delivery failed | order #{order_id} | {err}", bot)
    finally:
        async with _processing_lock:
            _processing.discard(order_id)


# =========================
# Invoice watcher (polling)
# =========================
async def invoice_watcher():
    while True:
        try:
            rows = await db_list_active_invoice_orders(limit=200)
            if not rows:
                await asyncio.sleep(INVOICE_POLL_INTERVAL)
                continue

            invoice_ids = [str(int(r["invoice_id"])) for r in rows if r.get("invoice_id") is not None]
            if not invoice_ids:
                await asyncio.sleep(INVOICE_POLL_INTERVAL)
                continue

            # CryptoPay supports invoice_ids list as comma separated
            chunk_size = 80
            for i in range(0, len(invoice_ids), chunk_size):
                chunk = invoice_ids[i:i + chunk_size]
                items = await cryptopay.get_invoices(invoice_ids=",".join(chunk))

                # Map invoice_id -> status
                inv_status = {}
                for inv in items:
                    try:
                        inv_id = str(int(inv.get("invoice_id")))
                        inv_status[inv_id] = inv.get("status")
                    except Exception:
                        continue

                for r in rows:
                    inv_id = str(int(r["invoice_id"]))
                    st = inv_status.get(inv_id)
                    if not st:
                        continue

                    oid = int(r["order_id"])

                    if st == "paid":
                        # mark paid only if active/creating (never revert sent)
                        changed = await db_mark_paid_if_needed(oid)
                        # if paid already (changed False), still try send (safe claim prevents duplicates)
                        asyncio.create_task(process_order_send(oid), name=f"send_{oid}")

                    elif st == "expired":
                        await db_mark_expired_if_needed(oid)

            await asyncio.sleep(INVOICE_POLL_INTERVAL)

        except asyncio.CancelledError:
            return
        except Exception as e:
            log.error("invoice_watcher error: %s", e)
            await asyncio.sleep(max(5.0, INVOICE_POLL_INTERVAL))


# =========================
# States
# =========================
class Form(StatesGroup):
    waiting_target = State()
    waiting_comment = State()


# =========================
# Handlers
# =========================
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    default_target = f"@{m.from_user.username}" if m.from_user.username else str(m.from_user.id)
    await db_ensure_user(m.from_user.id, default_target=default_target)
    text, kb, _lang = await render_status_text_and_kb(m.from_user.id)
    await m.answer(text, reply_markup=kb)


@dp.message(Command("menu"))
async def cmd_menu(m: Message, state: FSMContext):
    await state.clear()
    await db_ensure_user(m.from_user.id)
    text, kb, _lang = await render_status_text_and_kb(m.from_user.id)
    await m.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "menu:home")
async def menu_home(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db_ensure_user(c.from_user.id)
    text, kb, _lang = await render_status_text_and_kb(c.from_user.id)
    await safe_edit_message_obj(c.message, text=text, reply_markup=kb)


@dp.callback_query(F.data == "toggle:anon")
async def toggle_anon(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db_ensure_user(c.from_user.id)
    new_val = await db_toggle_anonymous(c.from_user.id)
    text, kb, lang = await render_status_text_and_kb(c.from_user.id)
    note = t(lang, "toggle_anon_on") if new_val == 1 else t(lang, "toggle_anon_off")
    await safe_edit_message_obj(c.message, text=note + "\n\n" + text, reply_markup=kb)


@dp.callback_query(F.data == "lang:menu")
async def lang_menu(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    _, _, _, _, lang = await db_get_settings(c.from_user.id)
    await safe_edit_message_obj(c.message, text=t(lang, "lang_pick"), reply_markup=lang_pick_kb(lang))


@dp.callback_query(F.data.startswith("lang:set:"))
async def lang_set(c: CallbackQuery):
    await c.answer()
    lang_new = c.data.split(":")[-1].strip().lower()
    await db_ensure_user(c.from_user.id)
    await db_set_lang(c.from_user.id, lang_new)
    text, kb, lang = await render_status_text_and_kb(c.from_user.id)
    await safe_edit_message_obj(c.message, text=t(lang, "lang_set") + "\n\n" + text, reply_markup=kb)


@dp.callback_query(F.data == "menu:target")
async def menu_target(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    _, _, _, _, lang = await db_get_settings(c.from_user.id)
    await state.set_state(Form.waiting_target)
    await safe_edit_message_obj(c.message, text=t(lang, "prompt_target"), reply_markup=back_menu_kb(lang))


@dp.callback_query(F.data == "menu:comment")
async def menu_comment(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    _, _, _, _, lang = await db_get_settings(c.from_user.id)
    await state.set_state(Form.waiting_comment)
    await safe_edit_message_obj(c.message, text=t(lang, "prompt_comment"), reply_markup=back_menu_kb(lang))


@dp.callback_query(F.data == "menu:gift")
async def menu_gift(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db_ensure_user(c.from_user.id)
    _, _, _, _, lang = await db_get_settings(c.from_user.id)
    await safe_edit_message_obj(c.message, text=t(lang, "pick_price"), reply_markup=price_kb(lang))


@dp.callback_query(F.data.startswith("price:"))
async def choose_price(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    _, _, _, _, lang = await db_get_settings(c.from_user.id)
    price = int(c.data.split(":", 1)[1])
    if price not in GIFTS_BY_PRICE:
        return await safe_edit_message_obj(c.message, text=t(lang, "pick_price"), reply_markup=price_kb(lang))
    await safe_edit_message_obj(c.message, text=t(lang, "pick_by_price", price=price), reply_markup=gifts_by_price_kb(lang, price))


@dp.callback_query(F.data.startswith("gift:"))
async def choose_gift(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    gift_id = int(c.data.split(":", 1)[1])
    _, _, _, _, lang = await db_get_settings(c.from_user.id)

    if gift_id not in GIFTS_BY_ID:
        return await safe_edit_message_obj(c.message, text=t(lang, "pick_price"), reply_markup=price_kb(lang))

    await db_set_selected_gift(c.from_user.id, gift_id)
    g = GIFTS_BY_ID[gift_id]
    _, _, _, anonymous, lang = await db_get_settings(c.from_user.id)

    await safe_edit_message_obj(
        c.message,
        text=t(lang, "gift_selected", label=g.label, stars=g.stars),
        reply_markup=main_menu_kb(lang, anonymous)
    )


@dp.message(Form.waiting_target)
async def set_target(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    target_norm = normalize_target(m.text or "")
    await db_set_target(m.from_user.id, target_norm)
    await state.clear()
    text, kb, lang = await render_status_text_and_kb(m.from_user.id)
    await m.answer(t(lang, "saved_target", status=text), reply_markup=kb)


@dp.message(Form.waiting_comment)
async def set_comment(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    raw = (m.text or "").strip()
    _, _, _, _, lang = await db_get_settings(m.from_user.id)

    if raw == "-" or raw.lower() in ("off", "none", "null"):
        await db_set_comment(m.from_user.id, None)
        await state.clear()
        text, kb, lang = await render_status_text_and_kb(m.from_user.id)
        return await m.answer(t(lang, "deleted_comment", status=text), reply_markup=kb)

    comment = safe_comment(raw)
    await db_set_comment(m.from_user.id, comment)
    await state.clear()
    text, kb, lang = await render_status_text_and_kb(m.from_user.id)
    await m.answer(t(lang, "saved_comment", status=text), reply_markup=kb)


# =========================
# Payments
# =========================
@dp.callback_query(F.data == "pay:create")
async def pay_create(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)

    target_str, comment, sel_gift_id, anonymous, lang = await db_get_settings(c.from_user.id)
    if not sel_gift_id or sel_gift_id not in GIFTS_BY_ID:
        status_text, status_kb, lang = await render_status_text_and_kb(c.from_user.id)
        return await safe_edit_message_obj(
            c.message,
            text=t(lang, "need_gift_first", status=status_text),
            reply_markup=status_kb
        )

    gift = GIFTS_BY_ID[sel_gift_id]
    target = resolve_target_for_user(target_str, c.from_user.id, c.from_user.username)

    amount = calc_invoice_amount(gift.stars)
    amount_str = f"{amount:.2f}"
    price_currency = PAY_ASSET if CURRENCY_TYPE == "crypto" else PAY_FIAT

    mode_txt = t(lang, "mode_anon") if anonymous == 1 else t(lang, "mode_profile")
    comment_txt = comment if comment else t(lang, "comment_empty")

    order_id = await db_create_order(
        user_id=c.from_user.id,
        target=str(target),
        gift=gift,
        comment=comment,
        anonymous=anonymous,
        price_amount=amount_str,
        price_currency=price_currency,
    )

    await safe_edit_message_obj(
        c.message,
        text=t(
            lang,
            "invoice_creating",
            order=order_id,
            gift=gift.label,
            stars=gift.stars,
            target=target,
            mode=mode_txt,
            comment=comment_txt,
            amount=amount_str,
            cur=price_currency
        ),
        reply_markup=None
    )

    try:
        paid_btn_url = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else None
        inv = await cryptopay.create_invoice(
            description=f"Telegram Gift: {gift.label} (⭐{gift.stars})",
            payload=json.dumps({"order_id": order_id}, ensure_ascii=False),
            amount=amount_str,
            currency_type=("crypto" if CURRENCY_TYPE == "crypto" else "fiat"),
            asset=(PAY_ASSET if CURRENCY_TYPE == "crypto" else None),
            fiat=(PAY_FIAT if CURRENCY_TYPE == "fiat" else None),
            accepted_assets=(ACCEPTED_ASSETS if CURRENCY_TYPE == "fiat" else None),
            expires_in=INVOICE_EXPIRES_IN,
            allow_comments=False,
            allow_anonymous=True,
            paid_btn_url=paid_btn_url,
        )

        invoice_id = int(inv["invoice_id"])
        invoice_url = inv.get("bot_invoice_url") or inv.get("pay_url")
        if not invoice_url:
            raise RuntimeError(f"Invoice URL not found: {inv}")

        await db_attach_invoice(order_id, invoice_id, invoice_url)

        await safe_edit_message_obj(
            c.message,
            text=t(
                lang,
                "invoice_ready",
                order=order_id,
                gift=gift.label,
                stars=gift.stars,
                target=target,
                amount=amount_str,
                cur=price_currency,
            ),
            reply_markup=pay_invoice_kb(lang, invoice_url, order_id)
        )

        # store message where invoice is shown -> we will update it when sent
        await db_set_order_origin_message(order_id, int(c.message.chat.id), int(c.message.message_id))

    except Exception as e:
        await db_mark_failed(order_id, str(e))
        await admin_notify(f"❌ Invoice create failed | order #{order_id} | {e}", bot)
        status_text, status_kb, lang = await render_status_text_and_kb(c.from_user.id)
        await safe_edit_message_obj(
            c.message,
            text=f"❌ Invoice error: {e}\n\n{status_text}",
            reply_markup=status_kb
        )


@dp.callback_query(F.data.startswith("pay:check:"))
async def pay_check(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    _, _, _, _, lang = await db_get_settings(c.from_user.id)

    order_id = int(c.data.split(":")[-1])
    order = await db_get_order(order_id)

    if not order or int(order["user_id"]) != int(c.from_user.id):
        return await safe_edit_message_obj(c.message, text=t(lang, "check_forbidden"), reply_markup=back_menu_kb(lang))

    # IMPORTANT: if already sent/sending -> do not revert status; no extra sending
    if order["status"] == "sent":
        return await safe_edit_message_obj(c.message, text=t(lang, "already_sent"), reply_markup=paid_done_kb(lang))
    if order["status"] == "sending":
        return await safe_edit_message_obj(c.message, text=t(lang, "already_sending"), reply_markup=paid_done_kb(lang))

    inv_id = order.get("invoice_id")
    if not inv_id:
        return await safe_edit_message_obj(c.message, text=t(lang, "check_no_invoice"), reply_markup=back_menu_kb(lang))

    try:
        items = await cryptopay.get_invoices(invoice_ids=str(int(inv_id)))
        inv = items[0] if items else None
        if not inv:
            return await safe_edit_message_obj(c.message, text=t(lang, "check_not_found"), reply_markup=back_menu_kb(lang))

        status = inv.get("status")

        if status == "paid":
            # mark paid only if needed (won't revert sent)
            await db_mark_paid_if_needed(order_id)

            # kick sender (safe claim prevents duplicates)
            asyncio.create_task(process_order_send(order_id), name=f"send_{order_id}")

            # update this message (and store it as origin too)
            await db_set_order_origin_message(order_id, int(c.message.chat.id), int(c.message.message_id))

            return await safe_edit_message_obj(
                c.message,
                text=t(lang, "paid_sending"),
                reply_markup=paid_done_kb(lang)  # no more "check" button
            )

        if status == "expired":
            await db_mark_expired_if_needed(order_id)
            return await safe_edit_message_obj(c.message, text=t(lang, "check_expired"), reply_markup=back_menu_kb(lang))

        # not paid yet
        kb = pay_invoice_kb(lang, order["invoice_url"], order_id) if order.get("invoice_url") else back_menu_kb(lang)
        txt = t(lang, "check_status", order=order_id, status=status)
        edited = await safe_edit_message_obj(c.message, text=txt, reply_markup=kb)
        if not edited:
            await c.answer("No changes.", show_alert=False)

    except Exception as e:
        # show toast instead of breaking UI
        await c.answer(f"Error: {e}", show_alert=True)


# =========================
# Web server (health)
# =========================
async def web_health(_request: web.Request):
    return web.json_response({"ok": True})


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", web_health)
    app.router.add_get("/health", web_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_BIND, PORT)
    await site.start()
    log.info("Web server listening on %s:%s", WEB_BIND, PORT)
    return runner


# =========================
# Main
# =========================
async def main():
    log.info("BOOT: starting...")
    await db_init()
    log.info("BOOT: db_init OK")

    await cryptopay.start()
    me_app = await cryptopay.get_me()
    log.info("CryptoPay OK | app_id=%s name=%s", me_app.get("app_id"), me_app.get("name"))

    rel = await relayer.start()
    log.info("Relayer OK | id=%s username=%s", getattr(rel, "id", None), getattr(rel, "username", None))

    runner = await start_web_server()

    watcher_task = asyncio.create_task(invoice_watcher(), name="invoice_watcher")

    try:
        log.info("BOOT: polling...")
        await dp.start_polling(bot)
    finally:
        watcher_task.cancel()
        try:
            await watcher_task
        except Exception:
            pass

        await cryptopay.stop()
        await relayer.stop()

        try:
            await runner.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
