import os
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union, Any

import aiohttp
import aiosqlite
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
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
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("giftbot")


# =========================
# ENV
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
RELAYER_SESSION = env_required("RELAYER_SESSION")  # Telethon StringSession

CRYPTOPAY_TOKEN = env_required("CRYPTOPAY_TOKEN")  # from @CryptoBot -> /pay -> Crypto Pay -> My Apps
# Pricing (you control this)
PRICE_PER_STAR = float(os.getenv("PRICE_PER_STAR", "0.01"))  # in FIAT (USD/UZS/etc) or in crypto amount if you use currency_type=crypto
PRICE_MIN = float(os.getenv("PRICE_MIN", "0.01"))

# Crypto Pay invoice currency settings:
# If currency_type=fiat: set CP_FIAT like USD/UZS and optional CP_ACCEPTED_ASSETS (comma)
# If currency_type=crypto: set CP_ASSET like USDT
CP_CURRENCY_TYPE = os.getenv("CP_CURRENCY_TYPE", "fiat").lower()  # "fiat" or "crypto"
CP_FIAT = os.getenv("CP_FIAT", "USD").upper()
CP_ASSET = os.getenv("CP_ASSET", "USDT").upper()
CP_ACCEPTED_ASSETS = [x.strip().upper() for x in os.getenv("CP_ACCEPTED_ASSETS", "USDT").split(",") if x.strip()]

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0") or "0")

DB_PATH = os.getenv("DB_PATH", "bot.db")

INVOICE_POLL_INTERVAL = float(os.getenv("INVOICE_POLL_INTERVAL", "5"))
INVOICE_POLL_BATCH = int(os.getenv("INVOICE_POLL_BATCH", "25"))


# =========================
# Gift Catalog (static)
# =========================
@dataclass(frozen=True)
class GiftItem:
    id: int
    stars: int
    label: str

GIFT_CATALOG: List[GiftItem] = [
    GiftItem(6028601630662853006, 50,  "🍾 50★"),
    GiftItem(5170521118301225164, 100, "💎 100★"),
    GiftItem(5170690322832818290, 100, "💍 100★"),
    GiftItem(5168043875654172773, 100, "🏆 100★"),
    GiftItem(5170564780938756245, 50,  "🚀 50★"),
    GiftItem(5170314324215857265, 50,  "💐 50★"),
    GiftItem(5170144170496491616, 50,  "🎂 50★"),
    GiftItem(5168103777563050263, 25,  "🌹 25★"),
    GiftItem(5170250947678437525, 25,  "🎁 25★"),
    GiftItem(5170233102089322756, 15,  "🧸 15★"),
    GiftItem(5170145012310081615, 15,  "💝 15★"),
    GiftItem(5922558454332916696, 50,  "🎄 50★"),
    GiftItem(5956217000635139069, 50,  "🧸(hat) 50★"),
]

GIFTS_BY_PRICE: Dict[int, List[GiftItem]] = {}
GIFTS_BY_ID: Dict[int, GiftItem] = {}
for g in GIFT_CATALOG:
    GIFTS_BY_PRICE.setdefault(g.stars, []).append(g)
    GIFTS_BY_ID[g.id] = g
ALLOWED_PRICES = sorted(GIFTS_BY_PRICE.keys())


# =========================
# i18n (EN/RU)
# =========================
T: Dict[str, Dict[str, str]] = {
    "en": {
        "menu_title": "📌 Current settings:",
        "target": "🎯 Receiver",
        "comment": "💬 Comment",
        "gift": "🎁 Gift",
        "mode": "🔒 Mode",
        "lang": "🌐 Language",
        "send": "💳 Pay",
        "back_menu": "⬅️ Menu",
        "back_prices": "⬅️ Prices",
        "confirm_pay": "✅ Create invoice",
        "check": "🔎 Check payment",
        "paid": "✅ Invoice PAID ✅\n🎁 Gift is being sent automatically...",
        "not_paid": "⏳ Not paid yet. Try again later.",
        "already_delivered": "✅ Already delivered. No duplicates.",
        "order_failed": "❌ Delivery failed.",
        "ask_target": "🎯 Send receiver:\n- `me`\n- `@username`\n- `user_id` (digits)\n\n⚠️ If user_id doesn't resolve: use @username or receiver must message relayer once.",
        "ask_comment": "💬 Send comment (optional).\nSend `-` to clear.",
        "pick_price": "🎁 Choose price:",
        "pick_gift": "⭐ Choose a gift for {price}:",
        "gift_selected": "✅ Gift selected:\n{label} (⭐{stars})\nID: {gid}\n\nNow create invoice.",
        "mode_show": "👤 Show name (in profile)",
        "mode_hide": "🕵️ Hide name (in profile)",
        "mode_hint": "Note: hiding name only affects profile display. Receiver still sees who sent it.",
        "lang_en": "English",
        "lang_ru": "Русский",
        "saved": "✅ Saved.",
        "comment_cleared": "✅ Comment cleared.",
        "invoice_text": "🧾 Order #{oid}\n🎁 {gift}\n🎯 {target}\n🔒 {mode}\n💬 {comment}\n\n💳 Pay: {pay_url}\n\nAfter payment the gift will be sent automatically.",
        "starting": "✅ Bot started.",
        "need_gift": "❌ Select a gift first.",
        "telethon_missing": "❌ Your Telethon build doesn't include StarGift TL objects.\nInstall correct Telethon (see requirements.txt).",
        "err": "❌ Error: {e}",
    },
    "ru": {
        "menu_title": "📌 Текущие настройки:",
        "target": "🎯 Получатель",
        "comment": "💬 Комментарий",
        "gift": "🎁 Подарок",
        "mode": "🔒 Режим",
        "lang": "🌐 Язык",
        "send": "💳 Оплатить",
        "back_menu": "⬅️ Меню",
        "back_prices": "⬅️ Цены",
        "confirm_pay": "✅ Создать инвойс",
        "check": "🔎 Проверить оплату",
        "paid": "✅ Инвойс ОПЛАЧЕН ✅\n🎁 Подарок отправляется автоматически...",
        "not_paid": "⏳ Не оплачено. Попробуйте позже.",
        "already_delivered": "✅ Уже доставлено. Дубликатов не будет.",
        "order_failed": "❌ Ошибка доставки.",
        "ask_target": "🎯 Отправьте получателя:\n- `me`\n- `@username`\n- `user_id` (цифры)\n\n⚠️ Если user_id не резолвится: используйте @username или получатель должен написать relayer 1 раз.",
        "ask_comment": "💬 Отправьте комментарий (необязательно).\nОтправьте `-` чтобы очистить.",
        "pick_price": "🎁 Выберите цену:",
        "pick_gift": "⭐ Выберите подарок за {price}:",
        "gift_selected": "✅ Подарок выбран:\n{label} (⭐{stars})\nID: {gid}\n\nТеперь создайте инвойс.",
        "mode_show": "👤 Имя видно (в профиле)",
        "mode_hide": "🕵️ Скрыть имя (в профиле)",
        "mode_hint": "Важно: скрытие имени влияет только на отображение в профиле. Получатель всё равно видит отправителя.",
        "lang_en": "English",
        "lang_ru": "Русский",
        "saved": "✅ Сохранено.",
        "comment_cleared": "✅ Комментарий очищен.",
        "invoice_text": "🧾 Заказ #{oid}\n🎁 {gift}\n🎯 {target}\n🔒 {mode}\n💬 {comment}\n\n💳 Оплата: {pay_url}\n\nПосле оплаты подарок отправится автоматически.",
        "starting": "✅ Бот запущен.",
        "need_gift": "❌ Сначала выберите подарок.",
        "telethon_missing": "❌ В вашей версии Telethon нет StarGift TL-объектов.\nУстановите правильный Telethon (см. requirements.txt).",
        "err": "❌ Ошибка: {e}",
    },
}

def tr(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in T else "ru"
    s = T[lang].get(key, key)
    if kwargs:
        try:
            return s.format(**kwargs)
        except Exception:
            return s
    return s


# =========================
# DB
# =========================
_db_lock = asyncio.Lock()

async def db_init() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA busy_timeout=5000;")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT 'ru',
            target TEXT DEFAULT 'me',
            comment TEXT DEFAULT NULL,
            selected_gift_id INTEGER DEFAULT NULL,
            hide_name INTEGER DEFAULT 0
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            target TEXT NOT NULL,
            gift_id INTEGER NOT NULL,
            stars INTEGER NOT NULL,
            comment TEXT DEFAULT NULL,
            hide_name INTEGER DEFAULT 0,

            invoice_id INTEGER DEFAULT NULL,
            pay_url TEXT DEFAULT NULL,
            amount TEXT DEFAULT NULL,
            currency_type TEXT DEFAULT NULL,
            asset TEXT DEFAULT NULL,
            fiat TEXT DEFAULT NULL,

            status TEXT NOT NULL DEFAULT 'created', -- created|paid|delivering|delivered|failed|cancelled
            error TEXT DEFAULT NULL,

            msg_chat_id INTEGER DEFAULT NULL,
            msg_message_id INTEGER DEFAULT NULL,

            created_at INTEGER NOT NULL,
            paid_at INTEGER DEFAULT NULL,
            delivered_at INTEGER DEFAULT NULL
        )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_invoice_id ON orders(invoice_id);")
        await db.commit()


async def db_ensure_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
        await db.commit()


async def db_get_user(user_id: int) -> Tuple[str, str, Optional[str], Optional[int], int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT lang, target, comment, selected_gift_id, hide_name FROM users WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return ("ru", "me", None, None, 0)
        return (row[0] or "ru", row[1] or "me", row[2], row[3], int(row[4] or 0))


async def db_set_lang(user_id: int, lang: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
        await db.commit()


async def db_set_target(user_id: int, target: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET target=? WHERE user_id=?", (target, user_id))
        await db.commit()


async def db_set_comment(user_id: int, comment: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET comment=? WHERE user_id=?", (comment, user_id))
        await db.commit()


async def db_set_selected_gift(user_id: int, gift_id: Optional[int]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET selected_gift_id=? WHERE user_id=?", (gift_id, user_id))
        await db.commit()


async def db_toggle_hide_name(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT hide_name FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        curv = int(row[0] or 0) if row else 0
        newv = 0 if curv == 1 else 1
        await db.execute("UPDATE users SET hide_name=? WHERE user_id=?", (newv, user_id))
        await db.commit()
        return newv


async def db_create_order(
    *,
    user_id: int,
    target: str,
    gift: GiftItem,
    comment: Optional[str],
    hide_name: int,
) -> int:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
        INSERT INTO orders(user_id, target, gift_id, stars, comment, hide_name, created_at, status)
        VALUES(?,?,?,?,?,?,?, 'created')
        """, (user_id, target, gift.id, gift.stars, comment, hide_name, now))
        await db.commit()
        return int(cur.lastrowid)


async def db_attach_invoice(
    order_id: int,
    *,
    invoice_id: int,
    pay_url: str,
    amount: str,
    currency_type: str,
    asset: Optional[str],
    fiat: Optional[str],
    msg_chat_id: int,
    msg_message_id: int,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        UPDATE orders
        SET invoice_id=?, pay_url=?, amount=?, currency_type=?, asset=?, fiat=?,
            msg_chat_id=?, msg_message_id=?
        WHERE id=?
        """, (invoice_id, pay_url, amount, currency_type, asset, fiat, msg_chat_id, msg_message_id, order_id))
        await db.commit()


async def db_get_order(order_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
        SELECT id, user_id, target, gift_id, stars, comment, hide_name,
               invoice_id, pay_url, amount, currency_type, asset, fiat,
               status, error, msg_chat_id, msg_message_id, created_at, paid_at, delivered_at
        FROM orders WHERE id=?
        """, (order_id,))
        r = await cur.fetchone()
        if not r:
            return None
        keys = [
            "id","user_id","target","gift_id","stars","comment","hide_name",
            "invoice_id","pay_url","amount","currency_type","asset","fiat",
            "status","error","msg_chat_id","msg_message_id","created_at","paid_at","delivered_at"
        ]
        return dict(zip(keys, r))


async def db_list_pending_orders(limit: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
        SELECT id, invoice_id FROM orders
        WHERE status='created' AND invoice_id IS NOT NULL
        ORDER BY id ASC
        LIMIT ?
        """, (limit,))
        rows = await cur.fetchall()
        return [{"id": int(a), "invoice_id": int(b)} for (a, b) in rows if b is not None]


async def db_mark_paid(order_id: int) -> bool:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
        UPDATE orders
        SET status='paid', paid_at=?
        WHERE id=? AND status='created'
        """, (now, order_id))
        await db.commit()
        return cur.rowcount == 1


async def db_claim_delivery(order_id: int) -> bool:
    # one-shot claim to avoid double delivery (manual check + watcher)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
        UPDATE orders
        SET status='delivering'
        WHERE id=? AND status='paid'
        """, (order_id,))
        await db.commit()
        return cur.rowcount == 1


async def db_mark_delivered(order_id: int) -> None:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        UPDATE orders
        SET status='delivered', delivered_at=?, error=NULL
        WHERE id=?
        """, (now, order_id))
        await db.commit()


async def db_mark_failed(order_id: int, error: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        UPDATE orders
        SET status='failed', error=?
        WHERE id=?
        """, (error[:400], order_id))
        await db.commit()


# =========================
# Crypto Pay API client (@CryptoBot)  https://help.crypt.bot/crypto-pay-api
# =========================
class CryptoPay:
    BASE = "https://pay.crypt.bot/api/"

    def __init__(self, token: str):
        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()

    async def start(self):
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20)
            )

    async def stop(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def _post(self, method: str, data: Dict[str, Any]) -> Any:
        if not self._session:
            raise RuntimeError("CryptoPay session not started")
        url = self.BASE + method
        headers = {"Crypto-Pay-API-Token": self.token}
        async with self._lock:
            async with self._session.post(url, json=data, headers=headers) as resp:
                js = await resp.json(content_type=None)
                if not js or not js.get("ok"):
                    raise RuntimeError(f"CryptoPay {method} failed: {js}")
                return js["result"]

    async def create_invoice(
        self,
        *,
        amount: float,
        description: str,
        payload: str,
    ) -> Dict[str, Any]:
        # currency settings
        data: Dict[str, Any] = {
            "amount": float(f"{amount:.2f}"),
            "description": description[:120],
            "payload": payload,
            "allow_anonymous": True,
        }
        if CP_CURRENCY_TYPE == "fiat":
            data["currency_type"] = "fiat"
            data["fiat"] = CP_FIAT
            if CP_ACCEPTED_ASSETS:
                data["accepted_assets"] = CP_ACCEPTED_ASSETS
        else:
            data["currency_type"] = "crypto"
            data["asset"] = CP_ASSET

        return await self._post("createInvoice", data)

    async def get_invoices(self, invoice_ids: List[int]) -> List[Dict[str, Any]]:
        # Crypto Pay: getInvoices supports invoice_ids param
        # Some implementations accept comma string, safer to pass list.
        res = await self._post("getInvoices", {"invoice_ids": invoice_ids})
        if isinstance(res, dict) and "items" in res:
            return res["items"] or []
        if isinstance(res, list):
            return res
        return []


cryptopay = CryptoPay(CRYPTOPAY_TOKEN)


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
            raise RuntimeError("RELAYER_SESSION invalid. Recreate session via QR.")
        me = await self.client.get_me()

        # Hard check: needed TL objects exist
        if not hasattr(types, "InputInvoiceStarGift") or not hasattr(functions.payments, "GetPaymentFormRequest"):
            raise RuntimeError("TELETHON_STARGIFT_TL_MISSING")

        return me

    async def stop(self):
        await self.client.disconnect()

    @staticmethod
    def _clean_comment(s: Optional[str]) -> Optional[str]:
        if not s:
            return None
        t = s.strip().replace("\r", " ").replace("\n", " ")
        if not t:
            return None
        # keep it small; Telegram may reject some long texts
        if len(t) > 120:
            t = t[:120]
        return t

    async def send_star_gift(
        self,
        *,
        target: Union[str, int],
        gift: GiftItem,
        comment: Optional[str],
        hide_name: bool,
    ) -> None:
        async with self._lock:
            # Resolve entity
            try:
                peer = await self.client.get_input_entity(target)
            except Exception:
                if isinstance(target, int):
                    raise RuntimeError(
                        "Cannot resolve user_id. Use @username or receiver must message relayer once."
                    )
                raise

            cleaned = self._clean_comment(comment)
            msg_obj = types.TextWithEntities(text=cleaned, entities=[]) if cleaned else None

            extra: Dict[str, Any] = {}
            if hide_name:
                extra["hide_name"] = True

            async def _try_send(message_obj):
                invoice = types.InputInvoiceStarGift(
                    peer=peer,
                    gift_id=gift.id,
                    message=message_obj,
                    **extra,
                )
                form = await self.client(functions.payments.GetPaymentFormRequest(invoice=invoice))
                await self.client(functions.payments.SendStarsFormRequest(form_id=form.form_id, invoice=invoice))

            # IMPORTANT:
            # If Telegram rejects message, we do NOT silently resend without comment.
            # We fail and let user change comment (so comment doesn't "disappear").
            try:
                await _try_send(msg_obj)
            except RPCError as e:
                if "STARGIFT_MESSAGE_INVALID" in str(e):
                    raise RuntimeError("STARGIFT_MESSAGE_INVALID: comment rejected. Try shorter / plain text.")
                raise


relayer = Relayer()


# =========================
# Bot UI
# =========================
def kb_menu(lang: str, hide_name: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=tr(lang, "target"), callback_data="m:target")
    kb.button(text=tr(lang, "comment"), callback_data="m:comment")
    kb.button(text=tr(lang, "gift"), callback_data="m:gift")
    kb.button(text=tr(lang, "send"), callback_data="m:pay")
    kb.button(text=(tr(lang, "mode_hide") if hide_name == 1 else tr(lang, "mode_show")), callback_data="m:mode")
    kb.button(text=tr(lang, "lang"), callback_data="m:lang")
    kb.adjust(2, 2, 2)
    return kb.as_markup()

def kb_back(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=tr(lang, "back_menu"), callback_data="m:home")
    return kb.as_markup()

def kb_prices(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in ALLOWED_PRICES:
        kb.button(text=f"⭐ {p}", callback_data=f"p:{p}")
    kb.button(text=tr(lang, "back_menu"), callback_data="m:home")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def kb_gifts(lang: str, price: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in GIFTS_BY_PRICE.get(price, []):
        kb.button(text=f"{g.label} » {g.id}", callback_data=f"g:{g.id}")
    kb.button(text=tr(lang, "back_prices"), callback_data="m:gift")
    kb.adjust(1)
    return kb.as_markup()

def kb_lang(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=tr(lang, "lang_en"), callback_data="lang:en")
    kb.button(text=tr(lang, "lang_ru"), callback_data="lang:ru")
    kb.button(text=tr(lang, "back_menu"), callback_data="m:home")
    kb.adjust(2, 1)
    return kb.as_markup()

def kb_invoice(lang: str, order_id: int, pay_url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=tr(lang, "check"), callback_data=f"o:{order_id}:check")
    kb.button(text="💳 Pay", url=pay_url)
    kb.adjust(1, 1)
    return kb.as_markup()

def kb_invoice_done() -> InlineKeyboardMarkup:
    # no buttons (prevents duplicate sends)
    return InlineKeyboardMarkup(inline_keyboard=[])

       # =========================
# FSM
# =========================
class Form(StatesGroup):
    waiting_target = State()
    waiting_comment = State()


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

def safe_comment(text: str) -> str:
    t = (text or "").strip()
    if len(t) > 250:
        t = t[:250]
    return t

def resolve_target(stored_target: str, user_id: int, username: Optional[str]) -> Union[str, int]:
    t = (stored_target or "me").strip()
    if t.lower() == "me":
        return ("@" + username) if username else user_id
    if t.startswith("@"):
        return t
    if t.isdigit():
        return int(t)
    return "@" + t

def calc_invoice_amount(stars: int) -> float:
    amt = stars * PRICE_PER_STAR
    if amt < PRICE_MIN:
        amt = PRICE_MIN
    return float(f"{amt:.2f}")


async def render_status(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    lang, target, comment, sel_gift_id, hide_name = await db_get_user(user_id)
    gift_txt = "—"
    if sel_gift_id and sel_gift_id in GIFTS_BY_ID:
        g = GIFTS_BY_ID[sel_gift_id]
        gift_txt = f"{g.label} (⭐{g.stars}) — {g.id}"
    mode_txt = tr(lang, "mode_hide") if hide_name == 1 else tr(lang, "mode_show")
    comment_txt = comment if comment else "(—)"
    text = (
        f"{tr(lang, 'menu_title')}\n"
        f"🎯 {target}\n"
        f"💬 {comment_txt}\n"
        f"🎁 {gift_txt}\n"
        f"🔒 {mode_txt}\n\n"
        f"{tr(lang, 'mode_hint')}"
    )
    return text, kb_menu(lang, hide_name)


async def safe_edit(msg: Message, *, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        raise


async def admin_notify(bot: Bot, text: str):
    if ADMIN_CHAT_ID and ADMIN_CHAT_ID != 0:
        try:
            await bot.send_message(ADMIN_CHAT_ID, text)
        except Exception:
            pass


# =========================
# Core payment->delivery logic
# =========================
async def create_invoice_for_order(
    bot: Bot,
    user_lang: str,
    order_id: int,
    gift: GiftItem,
    target: str,
    comment: Optional[str],
    hide_name: int,
) -> Tuple[int, str, str]:
    amount = calc_invoice_amount(gift.stars)
    desc = f"Gift {gift.stars}★ | order #{order_id}"
    payload = f"order:{order_id}"

    inv = await cryptopay.create_invoice(amount=amount, description=desc, payload=payload)

    invoice_id = int(inv["invoice_id"])
    pay_url = str(inv["pay_url"])
    # amount returned might be string
    inv_amount = str(inv.get("amount", amount))

    return invoice_id, pay_url, inv_amount


async def is_invoice_paid(invoice: Dict[str, Any]) -> bool:
    # Crypto Pay invoice statuses: "active", "paid", "expired" etc
    st = (invoice.get("status") or "").lower()
    return st == "paid"


async def deliver_order_if_needed(
    bot: Bot,
    order_id: int,
    *,
    source: str,
) -> None:
    """
    Idempotent: will NOT deliver twice.
    """
    async with _db_lock:
        order = await db_get_order(order_id)
        if not order:
            return

        if order["status"] == "delivered":
            return
        if order["status"] == "delivering":
            return
        if order["status"] not in ("paid", "created"):
            return

    # If status is created, we still need invoice status; manual check path might call this.
    if order["status"] == "created":
        if not order["invoice_id"]:
            return
        invs = await cryptopay.get_invoices([int(order["invoice_id"])])
        inv = invs[0] if invs else None
        if not inv or not await is_invoice_paid(inv):
            return
        await db_mark_paid(order_id)

    # Claim delivery (prevents duplicates)
    claimed = await db_claim_delivery(order_id)
    if not claimed:
        return

    # Now load full
    order = await db_get_order(order_id)
    if not order:
        return

    user_id = int(order["user_id"])
    lang, _, _, _, _ = await db_get_user(user_id)

    gift_id = int(order["gift_id"])
    gift = GIFTS_BY_ID.get(gift_id)
    if not gift:
        await db_mark_failed(order_id, f"Unknown gift_id: {gift_id}")
        return

    # Resolve target for relayer
    # If target stored is "me" -> send to buyer
    buyer_username = None
    try:
        # we don't have direct username here; keep target as stored string
        pass
    except Exception:
        pass

    resolved_target = resolve_target(str(order["target"]), user_id, buyer_username)
    hide_name = bool(int(order["hide_name"] or 0))
    comment = order.get("comment")

    # Try send
    try:
        await relayer.send_star_gift(
            target=resolved_target,
            gift=gift,
            comment=comment,
            hide_name=hide_name,
        )
        await db_mark_delivered(order_id)

        # Update invoice message to "done" and remove buttons
        if order.get("msg_chat_id") and order.get("msg_message_id"):
            try:
                m = await bot.edit_message_text(
                    chat_id=int(order["msg_chat_id"]),
                    message_id=int(order["msg_message_id"]),
                    text=tr(lang, "paid") + "\n\n" + tr(lang, "already_delivered"),
                    reply_markup=kb_invoice_done(),
                )
                _ = m
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e).lower():
                    log.warning("edit invoice msg failed: %s", e)

        await admin_notify(bot, f"✅ Delivered | order #{order_id} | source={source}")

    except Exception as e:
        await db_mark_failed(order_id, str(e))
        await admin_notify(bot, f"❌ Delivery failed | order #{order_id} | {e}")

# =========================
# Invoice watcher
# =========================
_invoice_task: Optional[asyncio.Task] = None

async def invoice_watcher(bot: Bot):
    while True:
        try:
            await asyncio.sleep(INVOICE_POLL_INTERVAL)
            pending = await db_list_pending_orders(INVOICE_POLL_BATCH)
            if not pending:
                continue

            invoice_ids = [p["invoice_id"] for p in pending if p.get("invoice_id")]
            if not invoice_ids:
                continue

            invs = await cryptopay.get_invoices(invoice_ids)
            inv_by_id = {int(x["invoice_id"]): x for x in invs if x.get("invoice_id")}

            for p in pending:
                oid = int(p["id"])
                iid = int(p["invoice_id"])
                inv = inv_by_id.get(iid)
                if not inv:
                    continue
                if await is_invoice_paid(inv):
                    changed = await db_mark_paid(oid)
                    # even if already paid, deliver_if_needed is idempotent
                    await deliver_order_if_needed(bot, oid, source="watcher")

        except Exception as e:
            log.error("invoice_watcher error: %s", e)


# =========================
# Aiogram app
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await db_ensure_user(m.from_user.id)
    text, kb = await render_status(m.from_user.id)
    await m.answer(text, reply_markup=kb)


@dp.message(Command("menu"))
async def cmd_menu(m: Message, state: FSMContext):
    await state.clear()
    await db_ensure_user(m.from_user.id)
    text, kb = await render_status(m.from_user.id)
    await m.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "m:home")
async def cb_home(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db_ensure_user(c.from_user.id)
    text, kb = await render_status(c.from_user.id)
    await safe_edit(c.message, text=text, reply_markup=kb)


@dp.callback_query(F.data == "m:target")
async def cb_target(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    lang, *_ = await db_get_user(c.from_user.id)
    await state.set_state(Form.waiting_target)
    await safe_edit(c.message, text=tr(lang, "ask_target"), reply_markup=kb_back(lang))


@dp.message(Form.waiting_target)
async def st_target(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    lang, *_ = await db_get_user(m.from_user.id)
    t = normalize_target(m.text or "")
    await db_set_target(m.from_user.id, t)
    await state.clear()
    text, kb = await render_status(m.from_user.id)
    await m.answer(tr(lang, "saved") + "\n\n" + text, reply_markup=kb)


@dp.callback_query(F.data == "m:comment")
async def cb_comment(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    lang, *_ = await db_get_user(c.from_user.id)
    await state.set_state(Form.waiting_comment)
    await safe_edit(c.message, text=tr(lang, "ask_comment"), reply_markup=kb_back(lang))


@dp.message(Form.waiting_comment)
async def st_comment(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    lang, *_ = await db_get_user(m.from_user.id)

    raw = (m.text or "").strip()
    if raw == "-" or raw.lower() in ("off", "none"):
        await db_set_comment(m.from_user.id, None)
        await state.clear()
        text, kb = await render_status(m.from_user.id)
        await m.answer(tr(lang, "comment_cleared") + "\n\n" + text, reply_markup=kb)
        return

    cm = safe_comment(raw)
    await db_set_comment(m.from_user.id, cm)
    await state.clear()
    text, kb = await render_status(m.from_user.id)
    await m.answer(tr(lang, "saved") + "\n\n" + text, reply_markup=kb)


@dp.callback_query(F.data == "m:gift")
async def cb_gift(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    lang, *_ = await db_get_user(c.from_user.id)
    await safe_edit(c.message, text=tr(lang, "pick_price"), reply_markup=kb_prices(lang))


@dp.callback_query(F.data.startswith("p:"))
async def cb_price(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    lang, *_ = await db_get_user(c.from_user.id)
    price = int(c.data.split(":", 1)[1])
    if price not in GIFTS_BY_PRICE:
        await safe_edit(c.message, text=tr(lang, "pick_price"), reply_markup=kb_prices(lang))
        return
    await safe_edit(c.message, text=tr(lang, "pick_gift", price=price), reply_markup=kb_gifts(lang, price))


@dp.callback_query(F.data.startswith("g:"))
async def cb_pick_gift(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    lang, *_ = await db_get_user(c.from_user.id)
    gid = int(c.data.split(":", 1)[1])
    if gid not in GIFTS_BY_ID:
        await safe_edit(c.message, text=tr(lang, "pick_price"), reply_markup=kb_prices(lang))
        return
    await db_set_selected_gift(c.from_user.id, gid)
    g = GIFTS_BY_ID[gid]
    await safe_edit(
        c.message,
        text=tr(lang, "gift_selected", label=g.label, stars=g.stars, gid=g.id),
        reply_markup=kb_menu(lang, (await db_get_user(c.from_user.id))[4]),
    )


@dp.callback_query(F.data == "m:mode")
async def cb_mode(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    newv = await db_toggle_hide_name(c.from_user.id)
    lang, *_ = await db_get_user(c.from_user.id)
    text, kb = await render_status(c.from_user.id)
    await safe_edit(c.message, text=tr(lang, "saved") + "\n\n" + text, reply_markup=kb)


@dp.callback_query(F.data == "m:lang")
async def cb_lang_menu(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    lang, *_ = await db_get_user(c.from_user.id)
    await safe_edit(c.message, text="🌐", reply_markup=kb_lang(lang))


@dp.callback_query(F.data.startswith("lang:"))
async def cb_lang_set(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    lang = c.data.split(":", 1)[1]
    if lang not in ("en", "ru"):
        lang = "ru"
    await db_set_lang(c.from_user.id, lang)
    text, kb = await render_status(c.from_user.id)
    await safe_edit(c.message, text=tr(lang, "saved") + "\n\n" + text, reply_markup=kb)


@dp.callback_query(F.data == "m:pay")
async def cb_pay(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)

    lang, target, comment, sel_gift_id, hide_name = await db_get_user(c.from_user.id)
    if not sel_gift_id or sel_gift_id not in GIFTS_BY_ID:
        text, kb = await render_status(c.from_user.id)
        await safe_edit(c.message, text=tr(lang, "need_gift") + "\n\n" + text, reply_markup=kb)
        return

    gift = GIFTS_BY_ID[sel_gift_id]
    # store order with target string as user set (can be "me")
    order_id = await db_create_order(
        user_id=c.from_user.id,
        target=target,
        gift=gift,
        comment=comment,
        hide_name=hide_name,
    )

    try:
        invoice_id, pay_url, inv_amount = await create_invoice_for_order(
            bot, lang, order_id, gift, target, comment, hide_name
        )

        mode_txt = tr(lang, "mode_hide") if hide_name == 1 else tr(lang, "mode_show")
        cm_txt = comment if comment else "(—)"
        text = tr(
            lang,
            "invoice_text",
            oid=order_id,
            gift=f"{gift.label} (⭐{gift.stars})",
            target=target,
            mode=mode_txt,
            comment=cm_txt,
            pay_url=pay_url,
        )

        sent = await c.message.answer(text, reply_markup=kb_invoice(lang, order_id, pay_url))
        await db_attach_invoice(
            order_id,
            invoice_id=invoice_id,
            pay_url=pay_url,
            amount=inv_amount,
            currency_type=CP_CURRENCY_TYPE,
            asset=(CP_ASSET if CP_CURRENCY_TYPE == "crypto" else None),
            fiat=(CP_FIAT if CP_CURRENCY_TYPE == "fiat" else None),
            msg_chat_id=sent.chat.id,
            msg_message_id=sent.message_id,
        )

        # refresh menu message
        menu_text, menu_kb = await render_status(c.from_user.id)
        await safe_edit(c.message, text=menu_text, reply_markup=menu_kb)

    except Exception as e:
        text, kb = await render_status(c.from_user.id)
        await safe_edit(c.message, text=tr(lang, "err", e=e) + "\n\n" + text, reply_markup=kb)


@dp.callback_query(F.data.startswith("o:"))
async def cb_order_actions(c: CallbackQuery):
    await c.answer()
    parts = c.data.split(":")
    if len(parts) != 3:
        return
    order_id = int(parts[1])
    action = parts[2]

    await db_ensure_user(c.from_user.id)
    lang, *_ = await db_get_user(c.from_user.id)

    order = await db_get_order(order_id)
    if not order or int(order["user_id"]) != c.from_user.id:
        return

    # If already delivered -> remove buttons, stop duplicates
    if order["status"] == "delivered":
        await safe_edit(c.message, text=tr(lang, "already_delivered"), reply_markup=kb_invoice_done())
        return

    if action == "check":
        # Check invoice status
        if not order.get("invoice_id"):
            await safe_edit(c.message, text=tr(lang, "err", e="no invoice id"), reply_markup=kb_invoice_done())
            return

        invs = await cryptopay.get_invoices([int(order["invoice_id"])])
        inv = invs[0] if invs else None
        if not inv or not await is_invoice_paid(inv):
            # keep same markup; safe_edit prevents message-not-modified crash
            await safe_edit(c.message, text=tr(lang, "not_paid"), reply_markup=kb_invoice(lang, order_id, order.get("pay_url") or ""))
            return

        # mark paid (if not already) and deliver (idempotent)
        await db_mark_paid(order_id)
        await safe_edit(c.message, text=tr(lang, "paid"), reply_markup=kb_invoice_done())
        await deliver_order_if_needed(bot, order_id, source="manual_check")
        # =========================
# Startup / Shutdown
# =========================
async def on_startup():
    await db_init()
    await cryptopay.start()

    try:
        me = await relayer.start()
    except RuntimeError as e:
        if "TELETHON_STARGIFT_TL_MISSING" in str(e):
            log.error("Telethon missing StarGift TL")
            raise RuntimeError(T["ru"]["telethon_missing"])
        raise

    log.info("[RELAYER] authorized as id=%s username=%s", me.id, me.username)

    global _invoice_task
    _invoice_task = asyncio.create_task(invoice_watcher(bot))
    log.info("invoice_watcher started")


async def on_shutdown():
    global _invoice_task
    if _invoice_task:
        _invoice_task.cancel()
        _invoice_task = None
    await cryptopay.stop()
    await relayer.stop()


async def main():
    await on_startup()
    try:
        await dp.start_polling(bot)
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
