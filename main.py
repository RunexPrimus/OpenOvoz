import os
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import aiosqlite
import aiohttp
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
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
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("giftbot")


# =========================
# ENV
# =========================
load_dotenv()

def env_required(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v

BOT_TOKEN = env_required("BOT_TOKEN")
TG_API_ID = int(env_required("TG_API_ID"))
TG_API_HASH = env_required("TG_API_HASH")
RELAYER_SESSION = env_required("RELAYER_SESSION")

CRYPTOPAY_TOKEN = env_required("CRYPTOPAY_TOKEN")
INVOICE_ASSET = os.environ.get("INVOICE_ASSET", "USDT")

PRICE_PER_STAR = float(os.environ.get("PRICE_PER_STAR", "0.01"))
PRICE_MIN = float(os.environ.get("PRICE_MIN", "0.10"))

ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0") or "0")
INVOICE_POLL_SECONDS = int(os.environ.get("INVOICE_POLL_SECONDS", "8") or "8")

DB_PATH = os.environ.get("DB_PATH", "bot.db")


# =========================
# i18n (EN/RU)
# =========================
STR = {
    "start_title": {
        "en": "🎁 Gift Shop Bot (CryptoBot payments)",
        "ru": "🎁 Gift Shop Bot (оплата через CryptoBot)",
    },
    "choose": {
        "en": "Choose an option:",
        "ru": "Выберите действие:",
    },
    "receiver_saved": {
        "en": "✅ Receiver saved.",
        "ru": "✅ Получатель сохранён.",
    },
    "comment_saved": {
        "en": "✅ Comment saved.",
        "ru": "✅ Комментарий сохранён.",
    },
    "comment_removed": {
        "en": "✅ Comment removed.",
        "ru": "✅ Комментарий удалён.",
    },
    "gift_selected": {
        "en": "✅ Gift selected.",
        "ru": "✅ Подарок выбран.",
    },
    "need_gift": {
        "en": "❌ Please select a gift first.",
        "ru": "❌ Сначала выберите подарок.",
    },
    "need_receiver": {
        "en": "❌ Please set receiver first.",
        "ru": "❌ Сначала укажите получателя.",
    },
    "receiver_prompt": {
        "en": "🎯 Send receiver:\n- `me`\n- `@username`\n- `user_id` (digits)\n\n⚠️ Best: @username.",
        "ru": "🎯 Отправьте получателя:\n- `me`\n- `@username`\n- `user_id` (цифры)\n\n⚠️ Лучше: @username.",
    },
    "comment_prompt": {
        "en": "💬 Send comment (optional).\nSend `-` to remove.\nExample: `:)`",
        "ru": "💬 Отправьте комментарий (необязательно).\nОтправьте `-` чтобы удалить.\nПример: `:)`",
    },
    "pick_price": {
        "en": "⭐ Pick a price tier:",
        "ru": "⭐ Выберите ценовую категорию:",
    },
    "confirm_buy": {
        "en": "🧾 Create CryptoBot invoice and pay to auto-send the gift.",
        "ru": "🧾 Создайте инвойс CryptoBot и оплатите для авто-отправки.",
    },
    "invoice_created": {
        "en": "✅ Invoice created.\n\nPay here:\n{url}\n\nAfter payment the gift will be delivered automatically.",
        "ru": "✅ Инвойс создан.\n\nОплатить:\n{url}\n\nПосле оплаты подарок отправится автоматически.",
    },
    "checking": {
        "en": "🔍 Checking payment...",
        "ru": "🔍 Проверяю оплату...",
    },
    "paid_sending": {
        "en": "✅ Invoice PAID ✅\n🎁 Sending gift automatically...",
        "ru": "✅ Инвойс ОПЛАЧЕН ✅\n🎁 Авто-отправка подарка...",
    },
    "already_delivered": {
        "en": "✅ Already delivered. (Order #{oid})",
        "ru": "✅ Уже доставлено. (Заказ #{oid})",
    },
    "already_processing": {
        "en": "⏳ Already processing. (Order #{oid})",
        "ru": "⏳ Уже обрабатывается. (Заказ #{oid})",
    },
    "not_paid_yet": {
        "en": "❌ Not paid yet. Please pay the invoice.",
        "ru": "❌ Пока не оплачено. Оплатите инвойс.",
    },
    "expired": {
        "en": "⌛ Invoice expired. Create a new one.",
        "ru": "⌛ Инвойс истёк. Создайте новый.",
    },
    "delivery_ok": {
        "en": "✅ Delivered! (Order #{oid})",
        "ru": "✅ Доставлено! (Заказ #{oid})",
    },
    "delivery_fail": {
        "en": "❌ Delivery failed (Order #{oid}).\nError: {err}",
        "ru": "❌ Ошибка доставки (Заказ #{oid}).\nОшибка: {err}",
    },
    "lang_set_en": {"en": "✅ Language set: English", "ru": "✅ Язык установлен: English"},
    "lang_set_ru": {"en": "✅ Language set: Русский", "ru": "✅ Язык установлен: Русский"},
    "mode_profile": {"en": "👤 Show profile", "ru": "👤 Показать профиль"},
    "mode_anon": {"en": "🕵️ Hide name (Telegram-limited)", "ru": "🕵️ Скрыть имя (ограничено Telegram)"},
    "db_corrupt": {
        "en": "Database looks corrupted. Delete bot.db or restore from backup.",
        "ru": "База повреждена. Удалите bot.db или восстановите из бэкапа.",
    },
}

def tr(lang: str, key: str, **kwargs) -> str:
    lang = "ru" if lang == "ru" else "en"
    s = STR.get(key, {}).get(lang) or STR.get(key, {}).get("en") or key
    return s.format(**kwargs)


# =========================
# Gifts (static)
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
# DB
# =========================
async def db_init():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    lang TEXT DEFAULT 'en',
                    target TEXT DEFAULT 'me',
                    comment TEXT DEFAULT NULL,
                    selected_gift_id INTEGER DEFAULT NULL,
                    anonymous INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    status TEXT NOT NULL,              -- pending | paid | delivering | delivered | failed | expired
                    gift_id INTEGER NOT NULL,
                    stars INTEGER NOT NULL,
                    target TEXT NOT NULL,
                    comment TEXT DEFAULT NULL,
                    anonymous INTEGER DEFAULT 0,

                    asset TEXT NOT NULL,
                    amount REAL NOT NULL,
                    invoice_id INTEGER DEFAULT NULL,
                    pay_url TEXT DEFAULT NULL,

                    invoice_chat_id INTEGER DEFAULT NULL,
                    invoice_message_id INTEGER DEFAULT NULL,
                    lang TEXT DEFAULT 'en',

                    last_check_at INTEGER DEFAULT NULL,
                    delivered_at INTEGER DEFAULT NULL,
                    error TEXT DEFAULT NULL,
                    attempts INTEGER DEFAULT 0
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_invoice_id ON orders(invoice_id);")
            await db.commit()
    except Exception as e:
        # if sqlite corruption happens on disk:
        log.error("db_init error: %s", e)
        raise

async def db_ensure_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_settings(user_id) VALUES (?)",
            (user_id,),
        )
        await db.commit()

async def db_get_user_settings(user_id: int) -> Tuple[str, str, Optional[str], Optional[int], int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT lang, target, comment, selected_gift_id, anonymous FROM user_settings WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return ("en", "me", None, None, 0)
        return (
            (row[0] or "en"),
            (row[1] or "me"),
            row[2],
            row[3],
            int(row[4] or 0),
        )

async def db_set_lang(user_id: int, lang: str):
    lang = "ru" if lang == "ru" else "en"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE user_settings SET lang=? WHERE user_id=?", (lang, user_id))
        await db.commit()

async def db_set_target(user_id: int, target: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE user_settings SET target=? WHERE user_id=?", (target, user_id))
        await db.commit()

async def db_set_comment(user_id: int, comment: Optional[str]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE user_settings SET comment=? WHERE user_id=?", (comment, user_id))
        await db.commit()

async def db_set_selected_gift(user_id: int, gift_id: Optional[int]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE user_settings SET selected_gift_id=? WHERE user_id=?", (gift_id, user_id))
        await db.commit()

async def db_toggle_anonymous(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT anonymous FROM user_settings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        cur_val = int(row[0] or 0) if row else 0
        new_val = 0 if cur_val == 1 else 1
        await db.execute("UPDATE user_settings SET anonymous=? WHERE user_id=?", (new_val, user_id))
        await db.commit()
        return new_val

async def db_create_order(
    *,
    user_id: int,
    lang: str,
    gift: GiftItem,
    target: str,
    comment: Optional[str],
    anonymous: int,
    asset: str,
    amount: float,
) -> int:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO orders (
                user_id, created_at, status,
                gift_id, stars, target, comment, anonymous,
                asset, amount, lang
            ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, now, gift.id, gift.stars, target, comment, anonymous, asset, amount, lang),
        )
        await db.commit()
        return int(cur.lastrowid)

async def db_attach_invoice(
    order_id: int,
    invoice_id: int,
    pay_url: str,
    chat_id: int,
    message_id: int,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE orders
            SET invoice_id=?, pay_url=?, invoice_chat_id=?, invoice_message_id=?, last_check_at=?
            WHERE id=?
            """,
            (invoice_id, pay_url, chat_id, message_id, int(time.time()), order_id),
        )
        await db.commit()

async def db_get_order(order_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id,user_id,created_at,status,gift_id,stars,target,comment,anonymous,asset,amount,invoice_id,pay_url,invoice_chat_id,invoice_message_id,lang,last_check_at,delivered_at,error,attempts FROM orders WHERE id=?",
            (order_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        keys = [
            "id","user_id","created_at","status","gift_id","stars","target","comment","anonymous",
            "asset","amount","invoice_id","pay_url","invoice_chat_id","invoice_message_id","lang",
            "last_check_at","delivered_at","error","attempts"
        ]
        return dict(zip(keys, row))

async def db_mark_paid_if_pending(order_id: int) -> bool:
    """Atomically: pending -> paid. Returns True if changed."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE;")
        cur = await db.execute("SELECT status FROM orders WHERE id=?", (order_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute("ROLLBACK;")
            return False
        st = row[0]
        if st != "pending":
            await db.execute("ROLLBACK;")
            return False
        await db.execute("UPDATE orders SET status='paid', last_check_at=? WHERE id=?", (int(time.time()), order_id))
        await db.commit()
        return True

async def db_try_mark_delivering(order_id: int) -> bool:
    """Atomically: paid -> delivering. Prevents double-send."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE;")
        cur = await db.execute("SELECT status FROM orders WHERE id=?", (order_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute("ROLLBACK;")
            return False
        if row[0] != "paid":
            await db.execute("ROLLBACK;")
            return False
        await db.execute("UPDATE orders SET status='delivering', attempts=attempts+1 WHERE id=?", (order_id,))
        await db.commit()
        return True

async def db_mark_delivered(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status='delivered', delivered_at=?, error=NULL WHERE id=?",
            (int(time.time()), order_id),
        )
        await db.commit()

async def db_mark_failed(order_id: int, err: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status='failed', error=? WHERE id=?",
            (err[:900], order_id),
        )
        await db.commit()

async def db_mark_expired(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status='expired', error=NULL WHERE id=?",
            (order_id,),
        )
        await db.commit()

async def db_list_pending_orders(limit: int = 50) -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM orders WHERE status='pending' AND invoice_id IS NOT NULL ORDER BY id ASC LIMIT ?",
            (limit,),
        )
        ids = [r[0] for r in await cur.fetchall()]
    out = []
    for oid in ids:
        o = await db_get_order(oid)
        if o:
            out.append(o)
    return out

async def db_list_paid_orders(limit: int = 50) -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM orders WHERE status='paid' ORDER BY id ASC LIMIT ?",
            (limit,),
        )
        ids = [r[0] for r in await cur.fetchall()]
    out = []
    for oid in ids:
        o = await db_get_order(oid)
        if o:
            out.append(o)
    return out


# =========================
# Helpers
# =========================
def normalize_target(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "me"
    if t.lower() == "me":
        return "me"
    if t.startswith("@"):
        return t
    if t.isdigit():
        return t
    return "@" + t

def safe_comment(text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None
    if len(t) > 120:
        t = t[:120]
    return t

def calc_invoice_amount(stars: int) -> float:
    amt = stars * PRICE_PER_STAR
    if amt < PRICE_MIN:
        amt = PRICE_MIN
    return float(f"{amt:.2f}")

async def admin_notify(bot: Bot, text: str):
    if ADMIN_CHAT_ID and ADMIN_CHAT_ID != 0:
        try:
            await bot.send_message(ADMIN_CHAT_ID, text)
        except Exception:
            pass

async def safe_edit(msg: Message, *, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
    """
    Prevents: Bad Request: message is not modified
    """
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        raise


# =========================
# Crypto Pay API client (@CryptoBot)
# =========================
class CryptoPay:
    BASE_URL = "https://pay.crypt.bot/api"  # 3

    def __init__(self, token: str, session: aiohttp.ClientSession):
        self.token = token
        self.session = session

    async def _post(self, method: str, payload: dict) -> dict:
        url = f"{self.BASE_URL}/{method}"
        headers = {
            "Crypto-Pay-API-Token": self.token,  # 4
            "Content-Type": "application/json",
        }
        async with self.session.post(url, json=payload, headers=headers, timeout=25) as r:
            data = await r.json(content_type=None)
            if not data.get("ok"):
                raise RuntimeError(f"CryptoPay API error: {data}")
            return data["result"]

    async def create_invoice(
        self,
        *,
        asset: str,
        amount: float,
        description: str,
        payload: str,
        expires_in: int = 1800,
    ) -> Tuple[int, str]:
        # createInvoice supports payload and expires_in (see docs). 5
        result = await self._post("createInvoice", {
            "asset": asset,
            "amount": str(amount),
            "description": description,
            "payload": payload,
            "expires_in": expires_in,
        })
        invoice_id = int(result["invoice_id"])
        bot_invoice_url = result["bot_invoice_url"]
        return invoice_id, bot_invoice_url

    async def get_invoice_status(self, invoice_id: int) -> str:
        # getInvoices with invoice_ids. 6
        result = await self._post("getInvoices", {"invoice_ids": str(invoice_id)})
        items = result.get("items") or []
        if not items:
            return "unknown"
        return items[0].get("status", "unknown")


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
            raise RuntimeError("RELAYER_SESSION invalid. Generate StringSession via QR and set RELAYER_SESSION.")
        me = await self.client.get_me()
        return me

    async def stop(self):
        await self.client.disconnect()

    async def send_star_gift(
        self,
        *,
        target: Union[str, int],
        gift: GiftItem,
        comment: Optional[str],
        hide_name: bool,
    ) -> bool:
        """
        Returns True if comment was used, False if had to fallback without comment.
        """
        async with self._lock:
            # resolve entity
            try:
                peer = await self.client.get_input_entity(target)
            except Exception:
                if isinstance(target, int):
                    raise RuntimeError("Cannot resolve user_id. Use @username or make receiver message relayer once.")
                raise

            cleaned = safe_comment(comment or "")
            msg_obj = types.TextWithEntities(text=cleaned, entities=[]) if cleaned else None

            # Optional: checkCanSendGift exists on newer TL (Telethon 1.42+). 7
            if hasattr(functions.payments, "CheckCanSendGiftRequest"):
                can = await self.client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
                if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                    reason = getattr(can.reason, "text", None) or str(can.reason)
                    raise RuntimeError(f"Can't send gift: {reason}")

            async def _try_send(message_obj):
                # InputInvoiceStarGift exists on newer TL (Telethon 1.42+). 8
                extra = {}
                if hide_name:
                    extra["hide_name"] = True

                invoice = types.InputInvoiceStarGift(
                    peer=peer,
                    gift_id=gift.id,
                    message=message_obj,
                    **extra,
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
                # If Telegram rejects message, resend without comment
                if "STARGIFT_MESSAGE_INVALID" in str(e):
                    await _try_send(None)
                    return False
                raise


# =========================
# UI Keyboards
# =========================
def kb_main(lang: str, anonymous: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎯 Receiver" if lang == "en" else "🎯 Получатель", callback_data="menu:target")
    kb.button(text="💬 Comment" if lang == "en" else "💬 Коммент", callback_data="menu:comment")
    kb.button(text="🎁 Gift" if lang == "en" else "🎁 Подарок", callback_data="menu:gift")
    kb.button(text="🧾 Buy" if lang == "en" else "🧾 Купить", callback_data="menu:buy")

    mode_text = tr(lang, "mode_anon") if anonymous == 1 else tr(lang, "mode_profile")
    kb.button(text=mode_text, callback_data="toggle:anon")

    kb.button(text=("🌐 Language" if lang == "en" else "🌐 Язык"), callback_data="menu:lang")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()

def kb_back(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Back" if lang == "en" else "⬅️ Назад", callback_data="menu:home")
    return kb.as_markup()

def kb_lang() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="English", callback_data="lang:en")
    kb.button(text="Русский", callback_data="lang:ru")
    kb.adjust(2)
    return kb.as_markup()

def kb_prices(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in ALLOWED_PRICES:
        kb.button(text=f"⭐ {p}", callback_data=f"price:{p}")
    kb.button(text="⬅️ Back" if lang == "en" else "⬅️ Назад", callback_data="menu:home")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()

def kb_gifts(lang: str, price: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in GIFTS_BY_PRICE.get(price, []):
        kb.button(text=f"{g.label} » {g.id}", callback_data=f"gift:{g.id}")
    kb.button(text="⬅️ Back" if lang == "en" else "⬅️ Назад", callback_data="menu:gift")
    kb.adjust(1)
    return kb.as_markup()

def kb_invoice(lang: str, order_id: int, pay_url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=("💳 Pay" if lang == "en" else "💳 Оплатить"), url=pay_url))
    kb.row(InlineKeyboardButton(text=("🔍 Check" if lang == "en" else "🔍 Проверить"), callback_data=f"order:check:{order_id}"))
    kb.row(InlineKeyboardButton(text=("⬅️ Menu" if lang == "en" else "⬅️ Меню"), callback_data="menu:home"))
    return kb.as_markup()

def kb_done(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=("⬅️ Menu" if lang == "en" else "⬅️ Меню"), callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()

# =========================
# Status renderer
# =========================
async def render_status(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    lang, target, comment, selected_gift_id, anonymous = await db_get_user_settings(user_id)

    gift_txt = "—"
    if selected_gift_id and selected_gift_id in GIFTS_BY_ID:
        g = GIFTS_BY_ID[selected_gift_id]
        gift_txt = f"{g.label} (⭐{g.stars}) — {g.id}"

    comment_txt = comment if comment else ("(none)" if lang == "en" else "(нет)")
    mode_txt = tr(lang, "mode_anon") if anonymous == 1 else tr(lang, "mode_profile")

    text = (
        f"{tr(lang, 'start_title')}\n\n"
        f"🎯 {'Receiver' if lang=='en' else 'Получатель'}: {target}\n"
        f"💬 {'Comment' if lang=='en' else 'Коммент'}: {comment_txt}\n"
        f"🎁 {'Gift' if lang=='en' else 'Подарок'}: {gift_txt}\n"
        f"🔒 {'Mode' if lang=='en' else 'Режим'}: {mode_txt}\n\n"
        f"{tr(lang, 'choose')}"
    )
    return text, kb_main(lang, anonymous)


# =========================
# FSM
# =========================
class Form(StatesGroup):
    waiting_target = State()
    waiting_comment = State()


# =========================
# App objects
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
relayer = Relayer()

http_session: aiohttp.ClientSession | None = None
cryptopay: CryptoPay | None = None

watcher_task: asyncio.Task | None = None


# =========================
# Delivery pipeline
# =========================
async def deliver_order(order_id: int):
    order = await db_get_order(order_id)
    if not order:
        return

    lang = order["lang"] or "en"
    user_id = int(order["user_id"])
    gift = GIFTS_BY_ID.get(int(order["gift_id"]))
    if not gift:
        await db_mark_failed(order_id, "Gift not found in catalog")
        return

    # idempotency guard: only paid -> delivering can proceed
    ok = await db_try_mark_delivering(order_id)
    if not ok:
        # already delivering/delivered/failed/etc
        return

    # target resolve:
    stored_target = order["target"] or "me"
    t = stored_target.strip()
    if t.lower() == "me":
        # best effort: use username if possible, else user_id
        # (relayer sometimes can't resolve numeric id unless contact exists)
        target: Union[str, int] = user_id
    elif t.startswith("@"):
        target = t
    elif t.isdigit():
        target = int(t)
    else:
        target = "@" + t

    comment = order["comment"]
    hide_name = bool(order["anonymous"] == 1)

    try:
        used_comment = await relayer.send_star_gift(
            target=target,
            gift=gift,
            comment=comment,
            hide_name=hide_name,
        )
        await db_mark_delivered(order_id)

        # notify user
        try:
            await bot.send_message(
                user_id,
                tr(lang, "delivery_ok", oid=order_id) + ("" if used_comment else ("\n\n⚠️ Comment fallback: sent without comment." if lang=="en" else "\n\n⚠️ Коммент не прошёл: отправлено без него.")),
                reply_markup=kb_done(lang),
            )
        except Exception:
            pass

        # update invoice message if saved
        if order.get("invoice_chat_id") and order.get("invoice_message_id"):
            try:
                msg = await bot.edit_message_text(
                    chat_id=int(order["invoice_chat_id"]),
                    message_id=int(order["invoice_message_id"]),
                    text=tr(lang, "delivery_ok", oid=order_id),
                    reply_markup=kb_done(lang),
                )
            except TelegramBadRequest:
                pass

        await admin_notify(bot, f"✅ Delivered | order #{order_id} | user={user_id}")

    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        await db_mark_failed(order_id, err)

        try:
            await bot.send_message(user_id, tr(lang, "delivery_fail", oid=order_id, err=err), reply_markup=kb_done(lang))
        except Exception:
            pass
        await admin_notify(bot, f"❌ Delivery failed | order #{order_id} | {err}")


async def invoice_watcher():
    """
    Background task:
    - Poll pending invoices
    - If paid => mark paid => deliver
    """
    assert cryptopay is not None
    while True:
        try:
            pending = await db_list_pending_orders(limit=50)
            for o in pending:
                invoice_id = o.get("invoice_id")
                if not invoice_id:
                    continue

                st = await cryptopay.get_invoice_status(int(invoice_id))
                if st == "paid":
                    changed = await db_mark_paid_if_pending(o["id"])
                    if changed:
                        # update invoice message quickly (paid -> sending)
                        try:
                            if o.get("invoice_chat_id") and o.get("invoice_message_id"):
                                await bot.edit_message_text(
                                    chat_id=int(o["invoice_chat_id"]),
                                    message_id=int(o["invoice_message_id"]),
                                    text=tr(o.get("lang") or "en", "paid_sending"),
                                    reply_markup=kb_done(o.get("lang") or "en"),
                                )
                        except TelegramBadRequest:
                            pass
                        asyncio.create_task(deliver_order(o["id"]))
                elif st in ("expired", "cancelled"):
                    await db_mark_expired(o["id"])
        except Exception as e:
            log.error("invoice_watcher error: %s", e)
        await asyncio.sleep(INVOICE_POLL_SECONDS)

# =========================
# Handlers
# =========================
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await db_ensure_user(m.from_user.id)
    text, kb = await render_status(m.from_user.id)
    await m.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "menu:home")
async def cb_home(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db_ensure_user(c.from_user.id)
    text, kb = await render_status(c.from_user.id)
    await safe_edit(c.message, text=text, reply_markup=kb)

@dp.callback_query(F.data == "menu:lang")
async def cb_lang_menu(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    lang, *_ = await db_get_user_settings(c.from_user.id)
    await safe_edit(
        c.message,
        text=("🌐 Choose language:" if lang == "en" else "🌐 Выберите язык:"),
        reply_markup=kb_lang()
    )

@dp.callback_query(F.data.startswith("lang:"))
async def cb_set_lang(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    new_lang = c.data.split(":", 1)[1]
    await db_set_lang(c.from_user.id, new_lang)
    lang, *_ = await db_get_user_settings(c.from_user.id)
    toast = tr(lang, "lang_set_ru") if lang == "ru" else tr(lang, "lang_set_en")
    text, kb = await render_status(c.from_user.id)
    await safe_edit(c.message, text=toast + "\n\n" + text, reply_markup=kb)

@dp.callback_query(F.data == "toggle:anon")
async def cb_toggle_anon(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db_ensure_user(c.from_user.id)
    await db_toggle_anonymous(c.from_user.id)
    text, kb = await render_status(c.from_user.id)
    await safe_edit(c.message, text=text, reply_markup=kb)

@dp.callback_query(F.data == "menu:target")
async def cb_target(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    lang, *_ = await db_get_user_settings(c.from_user.id)
    await state.set_state(Form.waiting_target)
    await safe_edit(c.message, text=tr(lang, "receiver_prompt"), reply_markup=kb_back(lang))

@dp.message(Form.waiting_target)
async def st_target(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    lang, *_ = await db_get_user_settings(m.from_user.id)
    t = normalize_target(m.text or "")
    await db_set_target(m.from_user.id, t)
    await state.clear()
    text, kb = await render_status(m.from_user.id)
    await m.answer(tr(lang, "receiver_saved") + "\n\n" + text, reply_markup=kb)

@dp.callback_query(F.data == "menu:comment")
async def cb_comment(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    lang, *_ = await db_get_user_settings(c.from_user.id)
    await state.set_state(Form.waiting_comment)
    await safe_edit(c.message, text=tr(lang, "comment_prompt"), reply_markup=kb_back(lang))

@dp.message(Form.waiting_comment)
async def st_comment(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    lang, *_ = await db_get_user_settings(m.from_user.id)

    raw = (m.text or "").strip()
    if raw == "-" or raw.lower() == "off":
        await db_set_comment(m.from_user.id, None)
        await state.clear()
        text, kb = await render_status(m.from_user.id)
        return await m.answer(tr(lang, "comment_removed") + "\n\n" + text, reply_markup=kb)

    cmt = safe_comment(raw)
    await db_set_comment(m.from_user.id, cmt)
    await state.clear()
    text, kb = await render_status(m.from_user.id)
    await m.answer(tr(lang, "comment_saved") + "\n\n" + text, reply_markup=kb)

@dp.callback_query(F.data == "menu:gift")
async def cb_gift(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db_ensure_user(c.from_user.id)
    lang, *_ = await db_get_user_settings(c.from_user.id)
    await safe_edit(c.message, text=tr(lang, "pick_price"), reply_markup=kb_prices(lang))

@dp.callback_query(F.data.startswith("price:"))
async def cb_price(c: CallbackQuery):
    await c.answer()
    price = int(c.data.split(":", 1)[1])
    lang, *_ = await db_get_user_settings(c.from_user.id)
    if price not in GIFTS_BY_PRICE:
        return await safe_edit(c.message, text=tr(lang, "pick_price"), reply_markup=kb_prices(lang))
    await safe_edit(c.message, text=f"⭐ {price}", reply_markup=kb_gifts(lang, price))

@dp.callback_query(F.data.startswith("gift:"))
async def cb_gift_pick(c: CallbackQuery):
    await c.answer()
    gift_id = int(c.data.split(":", 1)[1])
    await db_ensure_user(c.from_user.id)
    lang, *_ = await db_get_user_settings(c.from_user.id)

    if gift_id not in GIFTS_BY_ID:
        return await safe_edit(c.message, text=tr(lang, "pick_price"), reply_markup=kb_prices(lang))

    await db_set_selected_gift(c.from_user.id, gift_id)
    text, kb = await render_status(c.from_user.id)
    await safe_edit(c.message, text=tr(lang, "gift_selected") + "\n\n" + text, reply_markup=kb)

@dp.callback_query(F.data == "menu:buy")
async def cb_buy(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    lang, target, comment, selected_gift_id, anonymous = await db_get_user_settings(c.from_user.id)

    if not selected_gift_id or selected_gift_id not in GIFTS_BY_ID:
        text, kb = await render_status(c.from_user.id)
        return await safe_edit(c.message, text=tr(lang, "need_gift") + "\n\n" + text, reply_markup=kb)

    gift = GIFTS_BY_ID[selected_gift_id]
    amount = calc_invoice_amount(gift.stars)

    await safe_edit(c.message, text=tr(lang, "confirm_buy"), reply_markup=None)

    # Create order
    order_id = await db_create_order(
        user_id=c.from_user.id,
        lang=lang,
        gift=gift,
        target=target,
        comment=comment,
        anonymous=anonymous,
        asset=INVOICE_ASSET,
        amount=amount,
    )

    # Create CryptoBot invoice
    assert cryptopay is not None
    desc = f"Gift {gift.label} ({gift.stars}★) | order #{order_id}"
    payload = str(order_id)
    invoice_id, pay_url = await cryptopay.create_invoice(
        asset=INVOICE_ASSET,
        amount=amount,
        description=desc,
        payload=payload,
        expires_in=1800,
    )

    # Send invoice message + buttons
    msg = await c.message.answer(
        tr(lang, "invoice_created", url=pay_url),
        reply_markup=kb_invoice(lang, order_id, pay_url),
    )
    await db_attach_invoice(order_id, invoice_id, pay_url, msg.chat.id, msg.message_id)

    await admin_notify(bot, f"🧾 Invoice created | order #{order_id} | user={c.from_user.id} | amount={amount} {INVOICE_ASSET}")

@dp.callback_query(F.data.startswith("order:check:"))
async def cb_check(c: CallbackQuery):
    await c.answer()
    order_id = int(c.data.split(":")[-1])
    order = await db_get_order(order_id)
    if not order:
        return

    # Security: only owner can check
    if int(order["user_id"]) != int(c.from_user.id):
        return

    lang = order.get("lang") or "en"
    status = order.get("status")

    # If already delivered/delivering/failed/expired — do NOT send again
    if status == "delivered":
        return await safe_edit(c.message, text=tr(lang, "already_delivered", oid=order_id), reply_markup=kb_done(lang))
    if status == "delivering":
        return await safe_edit(c.message, text=tr(lang, "already_processing", oid=order_id), reply_markup=kb_done(lang))
    if status == "expired":
        return await safe_edit(c.message, text=tr(lang, "expired"), reply_markup=kb_done(lang))
    if status == "failed":
        err = order.get("error") or "unknown"
        return await safe_edit(c.message, text=tr(lang, "delivery_fail", oid=order_id, err=err), reply_markup=kb_done(lang))

    # pending -> check cryptopay
    if status == "pending":
        assert cryptopay is not None
        await safe_edit(c.message, text=tr(lang, "checking"), reply_markup=c.message.reply_markup)

        inv_id = order.get("invoice_id")
        if not inv_id:
            return

        st = await cryptopay.get_invoice_status(int(inv_id))
        if st == "paid":
            changed = await db_mark_paid_if_pending(order_id)
            # show paid text
            await safe_edit(c.message, text=tr(lang, "paid_sending"), reply_markup=kb_done(lang))

            # deliver (idempotent inside deliver_order)
            asyncio.create_task(deliver_order(order_id))
            return

        if st in ("expired", "cancelled"):
            await db_mark_expired(order_id)
            return await safe_edit(c.message, text=tr(lang, "expired"), reply_markup=kb_done(lang))

        # still not paid
        pay_url = order.get("pay_url") or ""
        return await safe_edit(c.message, text=tr(lang, "not_paid_yet"), reply_markup=kb_invoice(lang, order_id, pay_url))

    # paid but not delivered yet
    if status == "paid":
        await safe_edit(c.message, text=tr(lang, "paid_sending"), reply_markup=kb_done(lang))
        asyncio.create_task(deliver_order(order_id))
        return


# =========================
# Main
# =========================
async def main():
    global http_session, cryptopay, watcher_task

    await db_init()

    http_session = aiohttp.ClientSession()
    cryptopay = CryptoPay(CRYPTOPAY_TOKEN, http_session)

    me = await relayer.start()
    log.info("[RELAYER] authorized as id=%s username=%s", me.id, me.username)

    watcher_task = asyncio.create_task(invoice_watcher())

    try:
        await dp.start_polling(bot)
    finally:
        if watcher_task:
            watcher_task.cancel()
            with contextlib.suppress(Exception):
                await watcher_task
        await relayer.stop()
        if http_session:
            await http_session.close()

if __name__ == "__main__":
    import contextlib
    asyncio.run(main())
