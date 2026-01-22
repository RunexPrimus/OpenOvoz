import os
import json
import time
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import aiosqlite
import aiohttp
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import RPCError

from aiohttp import web
from contextlib import asynccontextmanager
import aiosqlite
import os, time
import logging

log = logging.getLogger("giftbot")
DB_PATH = os.getenv("DB_PATH", "bot.db")

@asynccontextmanager
async def db_connect():
    """
    Correct aiosqlite usage:
    - do NOT 'await connect' and then 'async with' it again.
    - open inside context, close automatically.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.execute("PRAGMA busy_timeout=5000;")
            yield db
    except aiosqlite.DatabaseError as e:
        # if corrupted -> rename and recreate next run
        msg = str(e).lower()
        if "malformed" in msg or "disk image" in msg:
            ts = int(time.time())
            corrupt_name = f"{DB_PATH}.corrupt.{ts}"
            try:
                os.replace(DB_PATH, corrupt_name)
                log.error("DB corrupted -> renamed to %s", corrupt_name)
            except Exception:
                pass
        raise

# =========================
# Logging
# =========================
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("giftbot")


# =========================
# Env / Config
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

# Crypto Pay API (@CryptoBot)
CRYPTOPAY_TOKEN = env_required("CRYPTOPAY_TOKEN")
CRYPTOPAY_BASE_URL = os.getenv("CRYPTOPAY_BASE_URL", "https://pay.crypt.bot")  # mainnet default

# Pricing (invoice amount)
# Example: 1 Star = 0.02 USDT  => 15⭐ => 0.30 USDT
PRICE_PER_STAR = float(os.getenv("PRICE_PER_STAR", "0.02"))
PRICE_MIN = float(os.getenv("PRICE_MIN", "0.10"))

# Invoice currency mode:
# - crypto: createInvoice(asset=..., amount=...)
# - fiat:   createInvoice(currency_type=fiat, fiat=USD, accepted_assets=..., amount=...)
CURRENCY_TYPE = os.getenv("CRYPTOPAY_CURRENCY_TYPE", "crypto").lower().strip()  # "crypto" or "fiat"
PAY_ASSET = os.getenv("CRYPTOPAY_ASSET", "USDT").upper().strip()               # for crypto mode
PAY_FIAT = os.getenv("CRYPTOPAY_FIAT", "USD").upper().strip()                 # for fiat mode
ACCEPTED_ASSETS = os.getenv("CRYPTOPAY_ACCEPTED_ASSETS", "USDT,TON").upper().strip()

# Delivery flow
INVOICE_EXPIRES_IN = int(os.getenv("INVOICE_EXPIRES_IN", "1800"))  # seconds
INVOICE_POLL_INTERVAL = float(os.getenv("INVOICE_POLL_INTERVAL", "10"))

# Admin notifications
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))  # 0 => disabled

# Hosting / health server (Heroku, etc.)
PORT = int(os.getenv("PORT", "8080"))
WEB_BIND = os.getenv("WEB_BIND", "0.0.0.0")

# DB
DB_PATH = os.getenv("DB_PATH", "bot.db")


# =========================
# Gift Catalog (static)
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
# DB helpers (robust)
# =========================
async def _db_connect() -> aiosqlite.Connection:
    # If DB is corrupted, rename and recreate
    try:
        db = await aiosqlite.connect(DB_PATH)
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute("PRAGMA busy_timeout=5000;")
        return db
    except Exception as e:
        # Try to detect malformed DB
        msg = str(e).lower()
        if "malformed" in msg or "disk image" in msg:
            ts = int(time.time())
            corrupt_name = f"{DB_PATH}.corrupt.{ts}"
            try:
                os.replace(DB_PATH, corrupt_name)
                log.error("DB corrupted -> renamed to %s", corrupt_name)
            except Exception:
                pass
            db = await aiosqlite.connect(DB_PATH)
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.execute("PRAGMA busy_timeout=5000;")
            return db
        raise


async def db_init():
    async with db_connect() as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            target TEXT DEFAULT NULL,
            comment TEXT DEFAULT NULL,
            selected_gift_id INTEGER DEFAULT NULL,
            anonymous INTEGER DEFAULT 0
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
            status TEXT NOT NULL DEFAULT 'creating',
            error TEXT DEFAULT NULL,

            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);")
        await db.commit()

log.info("BOOT: db_init OK")

async def db_ensure_user(user_id: int, default_target: Optional[str] = None):
    async with await _db_connect() as db:
        await db.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES(?)", (user_id,))
        if default_target:
            await db.execute(
                "UPDATE user_settings SET target=COALESCE(target, ?) WHERE user_id=?",
                (default_target, user_id),
            )
        await db.commit()


async def db_get_settings(user_id: int) -> Tuple[str, Optional[str], Optional[int], int]:
    async with await _db_connect() as db:
        cur = await db.execute(
            "SELECT target, comment, selected_gift_id, anonymous FROM user_settings WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return ("me", None, None, 0)
        target = row[0] or "me"
        comment = row[1]
        sel = row[2]
        anonymous = int(row[3] or 0)
        return (target, comment, sel, anonymous)


async def db_set_target(user_id: int, target: str):
    async with await _db_connect() as db:
        await db.execute("UPDATE user_settings SET target=? WHERE user_id=?", (target, user_id))
        await db.commit()


async def db_set_comment(user_id: int, comment: Optional[str]):
    async with await _db_connect() as db:
        await db.execute("UPDATE user_settings SET comment=? WHERE user_id=?", (comment, user_id))
        await db.commit()


async def db_set_selected_gift(user_id: int, gift_id: Optional[int]):
    async with await _db_connect() as db:
        await db.execute("UPDATE user_settings SET selected_gift_id=? WHERE user_id=?", (gift_id, user_id))
        await db.commit()


async def db_toggle_anonymous(user_id: int) -> int:
    async with await _db_connect() as db:
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
    async with await _db_connect() as db:
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
    async with await _db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET invoice_id=?, invoice_url=?, status='active', updated_at=?, error=NULL
            WHERE order_id=?
        """, (invoice_id, invoice_url, now, order_id))
        await db.commit()


async def db_mark_status(order_id: int, status: str, error: Optional[str] = None):
    now = int(time.time())
    async with await _db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET status=?, error=?, updated_at=?
            WHERE order_id=?
        """, (status, error, now, order_id))
        await db.commit()


async def db_get_active_orders(limit: int = 200) -> List[dict]:
    async with await _db_connect() as db:
        cur = await db.execute("""
            SELECT order_id, user_id, target, gift_id, stars, comment, anonymous,
                   price_amount, price_currency, invoice_id, invoice_url, status
            FROM orders
            WHERE status IN ('active','paid')
            ORDER BY created_at ASC
            LIMIT ?
        """, (limit,))
        rows = await cur.fetchall()
        out = []
        for r in rows:
            out.append({
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
                "status": r[11],
            })
        return out


async def db_get_order(order_id: int) -> Optional[dict]:
    async with await _db_connect() as db:
        cur = await db.execute("""
            SELECT order_id, user_id, target, gift_id, stars, comment, anonymous,
                   price_amount, price_currency, invoice_id, invoice_url, status, error
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
            "status": r[11],
            "error": r[12],
        }


# =========================
# Crypto Pay API client
# =========================
class CryptoPayAPI:
    def __init__(self, token: str, base_url: str):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        if self.session:
            return
        timeout = aiohttp.ClientTimeout(total=20)
        self.session = aiohttp.ClientSession(timeout=timeout)

    async def stop(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def _request(self, method_name: str, params: Optional[dict] = None) -> dict:
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
        return await self._request("getMe")

    async def create_invoice(
        self,
        *,
        description: str,
        payload: str,
        amount: str,
        currency_type: str = "crypto",
        asset: Optional[str] = None,
        fiat: Optional[str] = None,
        accepted_assets: Optional[str] = None,
        expires_in: Optional[int] = None,
        allow_comments: bool = False,
        allow_anonymous: bool = True,
        paid_btn_name: Optional[str] = "openBot",
        paid_btn_url: Optional[str] = None,
        hidden_message: Optional[str] = None,
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
        if hidden_message:
            params["hidden_message"] = hidden_message[:2048]
        if paid_btn_name and paid_btn_url:
            params["paid_btn_name"] = paid_btn_name
            params["paid_btn_url"] = paid_btn_url

        if currency_type == "crypto":
            if not asset:
                raise ValueError("asset required for currency_type=crypto")
            params["asset"] = asset
        elif currency_type == "fiat":
            if not fiat:
                raise ValueError("fiat required for currency_type=fiat")
            params["fiat"] = fiat
            if accepted_assets:
                params["accepted_assets"] = accepted_assets
        else:
            raise ValueError("currency_type must be crypto or fiat")

        return await self._request("createInvoice", params)

    async def get_invoices(self, *, invoice_ids: Optional[str] = None, status: Optional[str] = None, count: int = 100) -> List[dict]:
        params: dict = {"count": max(1, min(1000, int(count)))}
        if invoice_ids:
            params["invoice_ids"] = invoice_ids
        if status:
            params["status"] = status
        result = await self._request("getInvoices", params)
        # API returns: {"items": [...]}
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
        me = await self.client.get_me()
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
        # Telegram tarafda "message invalid" bo'lishi mumkin, shuning uchun limit
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
    ) -> bool:
        """
        Returns: comment_attached (best-effort).
        """
        async with self._lock:
            # 1) Can send?
            can = await self.client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")

            # 2) Resolve entity
            try:
                peer = await self.client.get_input_entity(target)
            except Exception:
                if isinstance(target, int):
                    raise RuntimeError(
                        "❌ user_id orqali entity topilmadi.\n"
                        "✅ @username ishlating yoki qabul qiluvchi relayerga 1 marta yozsin."
                    )
                raise

            # 3) Build TextWithEntities
            cleaned = self._clean_comment(comment)
            msg_obj = None
            if cleaned:
                # plain text; entities empty is OK. If Telegram rejects -> retry without comment.
                msg_obj = types.TextWithEntities(text=cleaned, entities=[])

            # 4) Invoice params: hide_name faqat True bo'lsa uzatamiz
            extra = {}
            if hide_name:
                extra["hide_name"] = True

            async def _try_send(message_obj) -> None:
                invoice = types.InputInvoiceStarGift(
                    peer=peer,
                    gift_id=gift.id,
                    message=message_obj,
                    **extra
                )
                form = await self.client(functions.payments.GetPaymentFormRequest(invoice=invoice))
                await self.client(functions.payments.SendStarsFormRequest(form_id=form.form_id, invoice=invoice))

            # 5) Attempt with comment (if any), fallback no comment on STARGIFT_MESSAGE_INVALID
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
# Bot UI
# =========================
def main_menu_kb(anonymous: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎯 Qabul qiluvchi", callback_data="menu:target")
    kb.button(text="💬 Komment", callback_data="menu:comment")
    kb.button(text="🎁 Sovg'a tanlash", callback_data="menu:gift")
    kb.button(text="🕵️ Anonim (hide name)" if anonymous == 1 else "👤 Profil (show name)", callback_data="toggle:anon")
    kb.button(text="💳 CryptoBot Invoice", callback_data="pay:create")
    kb.button(text="🚀 Test yuborish (pul yo‘q)", callback_data="send:test")
    kb.adjust(2, 2, 2)
    return kb.as_markup()


def back_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Menu", callback_data="menu:home")
    return kb.as_markup()


def price_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in ALLOWED_PRICES:
        kb.button(text=f"⭐ {p}", callback_data=f"price:{p}")
    kb.button(text="⬅️ Menu", callback_data="menu:home")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def gifts_by_price_kb(price: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in GIFTS_BY_PRICE.get(price, []):
        kb.button(text=f"{g.label} » {g.id}", callback_data=f"gift:{g.id}")
    kb.button(text="⬅️ Narxlar", callback_data="menu:gift")
    kb.adjust(1)
    return kb.as_markup()


def pay_invoice_kb(invoice_url: str, order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Invoice ochish", url=invoice_url)
    kb.button(text="🔄 Tekshirish", callback_data=f"pay:check:{order_id}")
    kb.button(text="⬅️ Menu", callback_data="menu:home")
    kb.adjust(1, 2)
    return kb.as_markup()


def confirm_test_send_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Test yuborish", callback_data="send:go")
    kb.button(text="⬅️ Menu", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


# =========================
# States
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
        return t  # keep as str; later parse to int
    return "@" + t


def safe_comment(text: str) -> str:
    t = (text or "").strip()
    if len(t) > 250:
        t = t[:250]
    return t


def calc_invoice_amount_usd(stars: int) -> float:
    amt = stars * PRICE_PER_STAR
    if amt < PRICE_MIN:
        amt = PRICE_MIN
    # round to 2 decimals for USDT/USD-like
    return float(f"{amt:.2f}")


async def render_status(user: Message) -> Tuple[str, InlineKeyboardMarkup]:
    user_id = user.from_user.id
    target, comment, sel_gift_id, anonymous = await db_get_settings(user_id)

    gift_txt = "Tanlanmagan"
    if sel_gift_id and sel_gift_id in GIFTS_BY_ID:
        g = GIFTS_BY_ID[sel_gift_id]
        gift_txt = f"{g.label} (⭐{g.stars}) — {g.id}"

    comment_txt = comment if comment else "(yo‘q)"
    mode_txt = "🕵️ Anonim (hide name)" if anonymous == 1 else "👤 Profil (show name)"

    text = (
        "📌 Hozirgi sozlamalar:\n"
        f"🎯 Qabul qiluvchi: {target}\n"
        f"💬 Komment: {comment_txt}\n"
        f"🎁 Sovg‘a: {gift_txt}\n"
        f"🔒 Rejim: {mode_txt}\n\n"
        "Quyidan tanlang:"
    )
    return text, main_menu_kb(anonymous)


def resolve_target_for_user(
    *,
    stored_target: str,
    user_telegram_id: int,
    user_username: Optional[str],
) -> Union[str, int]:
    """
    Botdagi "me" => user'ning @username bo'lsa shunga, bo'lmasa user_id.
    """
    t = (stored_target or "me").strip()
    if t.lower() == "me":
        if user_username:
            return "@" + user_username
        return user_telegram_id
    if t.startswith("@"):
        return t
    if t.isdigit():
        return int(t)
    return "@" + t


# =========================
# App objects
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

cryptopay = CryptoPayAPI(CRYPTOPAY_TOKEN, CRYPTOPAY_BASE_URL)
relayer = Relayer()

_processing_orders: set[int] = set()
_processing_lock = asyncio.Lock()


async def admin_notify(text: str):
    if ADMIN_CHAT_ID and ADMIN_CHAT_ID != 0:
        try:
            await bot.send_message(ADMIN_CHAT_ID, text)
        except Exception:
            pass


# =========================
# Handlers
# =========================
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    # Default target: if user has @username, use it (relayer can resolve)
    default_target = f"@{m.from_user.username}" if m.from_user.username else str(m.from_user.id)
    await db_ensure_user(m.from_user.id, default_target=default_target)
    text, kb = await render_status(m)
    await m.answer(text, reply_markup=kb)


@dp.message(Command("menu"))
async def cmd_menu(m: Message, state: FSMContext):
    await state.clear()
    await db_ensure_user(m.from_user.id)
    text, kb = await render_status(m)
    await m.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "menu:home")
async def menu_home(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db_ensure_user(c.from_user.id)
    # fake Message-like for render
    msg = c.message
    msg.from_user = c.from_user  # type: ignore
    text, kb = await render_status(msg)  # type: ignore
    await c.message.edit_text(text, reply_markup=kb)


@dp.callback_query(F.data == "toggle:anon")
async def toggle_anon(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db_ensure_user(c.from_user.id)
    new_val = await db_toggle_anonymous(c.from_user.id)
    msg = c.message
    msg.from_user = c.from_user  # type: ignore
    text, kb = await render_status(msg)  # type: ignore
    note = "✅ Anonim yoqildi (hide name)" if new_val == 1 else "✅ Profil ko‘rinadi (show name)"
    await c.message.edit_text(note + "\n\n" + text, reply_markup=kb)


@dp.callback_query(F.data == "menu:target")
async def menu_target(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    await state.set_state(Form.waiting_target)
    await c.message.edit_text(
        "🎯 Qabul qiluvchini yuboring:\n"
        "- `me` (siz)\n"
        "- `@username`\n"
        "- `user_id` (raqam)\n\n"
        "✅ Eng ishonchlisi: @username\n"
        "⚠️ user_id ba'zan ishlamasligi mumkin (relayer entity topolmasa).",
        reply_markup=back_menu_kb()
    )


@dp.callback_query(F.data == "menu:comment")
async def menu_comment(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    await state.set_state(Form.waiting_comment)
    await c.message.edit_text(
        "💬 Komment yuboring (ixtiyoriy).\n"
        "O‘chirish uchun: `-` yuboring.\n"
        "Masalan: `Congrats 🎁` yoki `:)`",
        reply_markup=back_menu_kb()
    )


@dp.callback_query(F.data == "menu:gift")
async def menu_gift(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db_ensure_user(c.from_user.id)
    await c.message.edit_text("🎁 Sovg‘a narxini tanlang:", reply_markup=price_kb())


@dp.callback_query(F.data.startswith("price:"))
async def choose_price(c: CallbackQuery):
    await c.answer()
    price = int(c.data.split(":", 1)[1])
    if price not in GIFTS_BY_PRICE:
        return await c.message.edit_text("Bunday narx yo‘q.", reply_markup=price_kb())
    await c.message.edit_text(f"⭐ {price} bo‘yicha sovg‘a tanlang:", reply_markup=gifts_by_price_kb(price))


@dp.callback_query(F.data.startswith("gift:"))
async def choose_gift(c: CallbackQuery):
    await c.answer()
    gift_id = int(c.data.split(":", 1)[1])
    if gift_id not in GIFTS_BY_ID:
        return await c.message.edit_text("Gift topilmadi.", reply_markup=price_kb())
    await db_set_selected_gift(c.from_user.id, gift_id)

    g = GIFTS_BY_ID[gift_id]
    await c.message.edit_text(
        f"✅ Sovg‘a tanlandi:\n{g.label} (⭐{g.stars})\nID: {g.id}\n\n"
        "Endi: 💳 Invoice yarating yoki 🚀 test yuboring.",
        reply_markup=main_menu_kb((await db_get_settings(c.from_user.id))[3])
    )


@dp.message(Form.waiting_target)
async def set_target(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    target_norm = normalize_target(m.text or "")
    await db_set_target(m.from_user.id, target_norm)
    await state.clear()
    text, kb = await render_status(m)
    await m.answer("✅ Qabul qiluvchi saqlandi.\n\n" + text, reply_markup=kb)


@dp.message(Form.waiting_comment)
async def set_comment(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    raw = (m.text or "").strip()
    if raw in ("-",) or raw.lower() in ("off", "none", "null"):
        await db_set_comment(m.from_user.id, None)
        await state.clear()
        text, kb = await render_status(m)
        return await m.answer("✅ Komment o‘chirildi.\n\n" + text, reply_markup=kb)

    comment = safe_comment(raw)
    await db_set_comment(m.from_user.id, comment)
    await state.clear()
    text, kb = await render_status(m)
    await m.answer("✅ Komment saqlandi.\n\n" + text, reply_markup=kb)


# -------------------------
# Payment flow
# -------------------------
@dp.callback_query(F.data == "pay:create")
async def pay_create(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    target_str, comment, sel_gift_id, anonymous = await db_get_settings(c.from_user.id)

    if not sel_gift_id or sel_gift_id not in GIFTS_BY_ID:
        msg = c.message
        msg.from_user = c.from_user  # type: ignore
        text, kb = await render_status(msg)  # type: ignore
        return await c.message.edit_text("❌ Avval sovg‘ani tanlang.\n\n" + text, reply_markup=kb)

    gift = GIFTS_BY_ID[sel_gift_id]

    # Target resolve
    target = resolve_target_for_user(
        stored_target=target_str,
        user_telegram_id=c.from_user.id,
        user_username=c.from_user.username,
    )

    # Price for invoice
    amount = calc_invoice_amount_usd(gift.stars)
    amount_str = f"{amount:.2f}"

    # Build invoice currency config
    if CURRENCY_TYPE == "crypto":
        price_currency = PAY_ASSET
    else:
        price_currency = PAY_FIAT

    order_id = await db_create_order(
        user_id=c.from_user.id,
        target=str(target),
        gift=gift,
        comment=comment,
        anonymous=anonymous,
        price_amount=amount_str,
        price_currency=price_currency,
    )

    await c.message.edit_text(
        "⏳ Invoice yaratilmoqda...\n"
        f"🧾 Buyurtma: #{order_id}\n"
        f"🎁 Gift: {gift.label} (⭐{gift.stars})\n"
        f"🎯 Target: {target}\n"
        f"🔒 Rejim: {'ANONIM' if anonymous == 1 else 'PROFIL'}\n"
        f"💬 Comment: {(comment if comment else '(bo‘sh)')}\n"
        f"💵 To‘lov: {amount_str} {price_currency}",
        reply_markup=None
    )

    # Create invoice via Crypto Pay API
    try:
        bot_username = os.getenv("BOT_USERNAME")  # optional
        paid_btn_url = f"https://t.me/{bot_username}" if bot_username else None

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
            paid_btn_name=("openBot" if paid_btn_url else None),
            paid_btn_url=paid_btn_url,
            hidden_message="✅ To‘lov qabul qilindi. Sovg‘a avtomatik yuboriladi.",
        )

        invoice_id = int(inv["invoice_id"])
        invoice_url = inv.get("bot_invoice_url") or inv.get("pay_url")  # pay_url deprecated, fallback
        if not invoice_url:
            raise RuntimeError(f"Invoice URL not found in response: {inv}")

        await db_attach_invoice(order_id, invoice_id, invoice_url)

        await c.message.edit_text(
            "✅ Invoice tayyor!\n\n"
            f"🧾 Buyurtma: #{order_id}\n"
            f"🎁 Gift: {gift.label} (⭐{gift.stars})\n"
            f"🎯 Target: {target}\n"
            f"💵 To‘lov: {amount_str} {price_currency}\n\n"
            "To‘lang, bot o‘zi tekshiradi va sovg‘ani yuboradi.",
            reply_markup=pay_invoice_kb(invoice_url, order_id)
        )

    except Exception as e:
        await db_mark_status(order_id, "failed", error=str(e))
        await admin_notify(f"❌ Invoice create failed | order #{order_id} | {e}")
        msg = c.message
        msg.from_user = c.from_user  # type: ignore
        text, kb = await render_status(msg)  # type: ignore
        await c.message.edit_text(f"❌ Invoice yaratib bo‘lmadi: {e}\n\n" + text, reply_markup=kb)


@dp.callback_query(F.data.startswith("pay:check:"))
async def pay_check(c: CallbackQuery):
    await c.answer()
    order_id = int(c.data.split(":")[-1])
    order = await db_get_order(order_id)
    if not order or order["user_id"] != c.from_user.id:
        return await c.message.edit_text("❌ Buyurtma topilmadi yoki ruxsat yo‘q.", reply_markup=back_menu_kb())

    if not order["invoice_id"]:
        return await c.message.edit_text("❌ Invoice yo‘q.", reply_markup=back_menu_kb())

    try:
        items = await cryptopay.get_invoices(invoice_ids=str(order["invoice_id"]))
        inv = items[0] if items else None
        if not inv:
            return await c.message.edit_text("❌ Invoice topilmadi (API).", reply_markup=back_menu_kb())

        status = inv.get("status")
        if status == "paid":
            await db_mark_status(order_id, "paid", error=None)
            await c.message.edit_text("✅ Invoice PAID ✅\nSovg‘a yuborish navbatga qo‘shildi.", reply_markup=back_menu_kb())
            return
        if status == "expired":
            await db_mark_status(order_id, "expired", error="Invoice expired")
            return await c.message.edit_text("⌛ Invoice muddati tugagan (expired).", reply_markup=back_menu_kb())

        # active or other
        await c.message.edit_text(
            f"🧾 Buyurtma: #{order_id}\n"
            f"📌 Invoice status: {status}\n\n"
            "Agar to‘lagan bo‘lsangiz, 5-10 soniyada yangilanadi.",
            reply_markup=pay_invoice_kb(order["invoice_url"], order_id) if order["invoice_url"] else back_menu_kb()
        )
    except Exception as e:
        await c.message.edit_text(f"❌ Tekshirish xatoligi: {e}", reply_markup=back_menu_kb())


# -------------------------
# Optional: TEST send (no payment)
# -------------------------
@dp.callback_query(F.data == "send:test")
async def test_send_menu(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    await c.message.edit_text(
        "🚀 TEST yuborish (CryptoBot to‘lovsiz).\n"
        "Bu faqat tekshiruv uchun.\n\n"
        "Davom etasizmi?",
        reply_markup=confirm_test_send_kb()
    )


@dp.callback_query(F.data == "send:go")
async def send_test_now(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    target_str, comment, sel_gift_id, anonymous = await db_get_settings(c.from_user.id)
    if not sel_gift_id or sel_gift_id not in GIFTS_BY_ID:
        msg = c.message
        msg.from_user = c.from_user  # type: ignore
        text, kb = await render_status(msg)  # type: ignore
        return await c.message.edit_text("❌ Avval sovg‘ani tanlang.\n\n" + text, reply_markup=kb)

    gift = GIFTS_BY_ID[sel_gift_id]
    target = resolve_target_for_user(
        stored_target=target_str,
        user_telegram_id=c.from_user.id,
        user_username=c.from_user.username,
    )

    await c.message.edit_text(
        f"⏳ TEST yuborilyapti...\n"
        f"🎯 Target: {target}\n"
        f"🎁 Gift: {gift.label} (⭐{gift.stars})\n"
        f"🔒 Rejim: {'ANONIM' if anonymous == 1 else 'PROFIL'}\n"
        f"💬 Comment: {(comment if comment else '(bo‘sh)')}",
        reply_markup=None
    )

    try:
        comment_attached = await relayer.send_star_gift(
            target=target,
            gift=gift,
            comment=comment,
            hide_name=(anonymous == 1),
        )
        note = "✅ Yuborildi!"
        if comment and not comment_attached:
            note += "\n⚠️ Komment server tomonidan qabul qilinmadi (fallback comment-siz yuborildi)."
        msg = c.message
        msg.from_user = c.from_user  # type: ignore
        text, kb = await render_status(msg)  # type: ignore
        await c.message.edit_text(note + "\n\n" + text, reply_markup=kb)

    except Exception as e:
        await admin_notify(f"❌ TEST send failed | user {c.from_user.id} | {e}")
        msg = c.message
        msg.from_user = c.from_user  # type: ignore
        text, kb = await render_status(msg)  # type: ignore
        await c.message.edit_text(f"❌ Xatolik: {e}\n\n" + text, reply_markup=kb)


# =========================
# Background: invoice watcher
# =========================
async def process_paid_order(order: dict):
    order_id = int(order["order_id"])

    async with _processing_lock:
        if order_id in _processing_orders:
            return
        _processing_orders.add(order_id)

    try:
        await db_mark_status(order_id, "sending", error=None)

        user_id = int(order["user_id"])
        gift = GIFTS_BY_ID.get(int(order["gift_id"]))
        if not gift:
            raise RuntimeError("Gift not found in catalog")

        # resolve target string stored
        stored_target = str(order["target"])
        # if stored is int-like, use int
        target: Union[str, int]
        if stored_target.startswith("@"):
            target = stored_target
        elif stored_target.isdigit():
            target = int(stored_target)
        else:
            target = stored_target

        comment = order.get("comment")
        anonymous = int(order.get("anonymous") or 0)

        comment_attached = await relayer.send_star_gift(
            target=target,
            gift=gift,
            comment=comment,
            hide_name=(anonymous == 1),
        )

        await db_mark_status(order_id, "sent", error=None)

        msg = (
            "✅ Sovg‘a yuborildi!\n"
            f"🧾 Buyurtma: #{order_id}\n"
            f"🎁 {gift.label} (⭐{gift.stars})\n"
            f"🎯 Target: {stored_target}\n"
            f"🔒 Rejim: {'ANONIM' if anonymous == 1 else 'PROFIL'}\n"
        )
        if comment:
            msg += f"💬 Comment: {comment}\n"
            if not comment_attached:
                msg += "⚠️ Komment server tomonidan qabul qilinmadi (fallback comment-siz yuborildi).\n"

        await bot.send_message(user_id, msg)

    except Exception as e:
        await db_mark_status(order_id, "failed", error=str(e))
        await admin_notify(f"❌ Delivery failed | order #{order_id} | {e}")
        try:
            await bot.send_message(
                int(order["user_id"]),
                f"❌ Sovg‘ani yuborib bo‘lmadi.\n🧾 Buyurtma: #{order_id}\nXatolik: {e}"
            )
        except Exception:
            pass
    finally:
        async with _processing_lock:
            _processing_orders.discard(order_id)


async def invoice_watcher():
    """
    Poll Crypto Pay API:
    - fetch active invoices for orders.status='active'
    - when invoice status becomes 'paid' -> mark paid and deliver
    """
    while True:
        try:
            orders = await db_get_active_orders(limit=200)
            active = [o for o in orders if o.get("status") == "active" and o.get("invoice_id")]
            if not active:
                await asyncio.sleep(INVOICE_POLL_INTERVAL)
                continue

            # chunk invoice_ids (avoid too long)
            invoice_map = {int(o["invoice_id"]): o for o in active}
            invoice_ids = list(invoice_map.keys())

            # chunk size
            chunk_size = 80
            for i in range(0, len(invoice_ids), chunk_size):
                chunk = invoice_ids[i:i + chunk_size]
                ids_str = ",".join(str(x) for x in chunk)
                items = await cryptopay.get_invoices(invoice_ids=ids_str)

                for inv in items:
                    inv_id = int(inv.get("invoice_id"))
                    status = inv.get("status")
                    order = invoice_map.get(inv_id)
                    if not order:
                        continue

                    if status == "paid":
                        # mark paid; delivery will be triggered immediately
                        await db_mark_status(int(order["order_id"]), "paid", error=None)
                        await process_paid_order(order)
                    elif status == "expired":
                        await db_mark_status(int(order["order_id"]), "expired", error="Invoice expired")

            await asyncio.sleep(INVOICE_POLL_INTERVAL)

        except asyncio.CancelledError:
            return
        except Exception as e:
            log.error("invoice_watcher error: %s", e)
            await asyncio.sleep(max(5.0, INVOICE_POLL_INTERVAL))


# =========================
# Web server (health)
# =========================
async def web_health(request: web.Request):
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

#----------------------
log.info("BOOT: starting...")
# =========================
# Main
# =========================
async def main():
    await db_init()

    await cryptopay.start()
    me_app = await cryptopay.get_me()
    log.info("CryptoPay OK | app_id=%s name=%s", me_app.get("app_id"), me_app.get("name"))

    rel = await relayer.start()
    log.info("Relayer OK | id=%s username=%s", getattr(rel, "id", None), getattr(rel, "username", None))

    runner = await start_web_server()

    watcher_task = asyncio.create_task(invoice_watcher(), name="invoice_watcher")

    try:
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
