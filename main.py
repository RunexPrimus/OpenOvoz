import os
import time
import asyncio
import logging
import secrets
from dataclasses import dataclass
from decimal import Decimal, ROUND_UP
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import aiohttp
import aiosqlite

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import RPCError


# ----------------- LOG -----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("gift-ton-bot")


# ----------------- ENV -----------------
def env_required(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v

BOT_TOKEN = env_required("BOT_TOKEN")
TG_API_ID = int(env_required("TG_API_ID"))
TG_API_HASH = env_required("TG_API_HASH")
RELAYER_SESSION = env_required("RELAYER_SESSION")

TONCENTER_API_KEY = env_required("TONCENTER_API_KEY")
TON_DEPOSIT_ADDRESS = env_required("TON_DEPOSIT_ADDRESS")
TON_PRICE_PER_STAR = Decimal(env_required("TON_PRICE_PER_STAR"))  # e.g. 0.01

TONCENTER_BASE = os.environ.get("TONCENTER_BASE", "https://toncenter.com/api/v2").rstrip("/")
TON_POLL_INTERVAL = int(os.environ.get("TON_POLL_INTERVAL", "6"))
TX_FETCH_LIMIT = int(os.environ.get("TX_FETCH_LIMIT", "25"))
MIN_TX_AGE_SEC = int(os.environ.get("MIN_TX_AGE_SEC", "10"))

DB_PATH = os.environ.get("DB_PATH", "bot.db")

NANO = Decimal("1000000000")


# ----------------- Utils -----------------
def ton_to_nano_int(ton_amount: Decimal) -> int:
    a = ton_amount.quantize(Decimal("0.000000001"), rounding=ROUND_UP)
    return int(a * NANO)

def nano_to_ton_str(nano: int) -> str:
    s = (Decimal(nano) / NANO)
    txt = format(s, "f")
    return txt.rstrip("0").rstrip(".") if "." in txt else txt

async def safe_edit(msg, text: str, reply_markup=None):
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise


# ----------------- Gifts -----------------
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

GIFTS_BY_ID: Dict[int, GiftItem] = {g.id: g for g in GIFT_CATALOG}
GIFTS_BY_PRICE: Dict[int, List[GiftItem]] = {}
for g in GIFT_CATALOG:
    GIFTS_BY_PRICE.setdefault(g.stars, []).append(g)
ALLOWED_PRICES = sorted(GIFTS_BY_PRICE.keys())


# ----------------- DB -----------------
class DB:
    def __init__(self, path: str):
        self.path = path
        self.conn: Optional[aiosqlite.Connection] = None

    async def start(self):
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("PRAGMA synchronous=NORMAL;")
        await self.conn.execute("PRAGMA busy_timeout=5000;")
        await self.init_schema()

    async def stop(self):
        if self.conn:
            await self.conn.close()

    async def init_schema(self):
        assert self.conn
        await self.conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings(
            user_id INTEGER PRIMARY KEY,
            receiver TEXT DEFAULT 'me',          -- me | @username
            comment TEXT DEFAULT NULL,
            selected_gift_id INTEGER DEFAULT NULL
        )
        """)
        await self.conn.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            order_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            target TEXT NOT NULL,                -- resolved @username
            gift_id INTEGER NOT NULL,
            stars INTEGER NOT NULL,
            expected_nano INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING/PAID/SENT/FAILED
            tx_hash TEXT,
            tx_lt INTEGER,
            created_at INTEGER NOT NULL,
            paid_at INTEGER,
            sent_at INTEGER,
            fail_reason TEXT
        )
        """)
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        await self.conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_state(
            id INTEGER PRIMARY KEY CHECK(id=1),
            last_lt INTEGER DEFAULT 0
        )
        """)
        await self.conn.execute("INSERT OR IGNORE INTO scan_state(id,last_lt) VALUES(1,0)")
        await self.conn.commit()

    async def ensure_user(self, user_id: int):
        assert self.conn
        await self.conn.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES(?)", (user_id,))
        await self.conn.commit()

    async def get_settings(self, user_id: int) -> Tuple[str, Optional[str], Optional[int]]:
        assert self.conn
        cur = await self.conn.execute(
            "SELECT receiver, comment, selected_gift_id FROM user_settings WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            return ("me", None, None)
        return (row[0] or "me", row[1], row[2])

    async def set_receiver(self, user_id: int, receiver: str):
        assert self.conn
        await self.conn.execute("UPDATE user_settings SET receiver=? WHERE user_id=?", (receiver, user_id))
        await self.conn.commit()

    async def set_comment(self, user_id: int, comment: Optional[str]):
        assert self.conn
        await self.conn.execute("UPDATE user_settings SET comment=? WHERE user_id=?", (comment, user_id))
        await self.conn.commit()

    async def set_gift(self, user_id: int, gift_id: Optional[int]):
        assert self.conn
        await self.conn.execute("UPDATE user_settings SET selected_gift_id=? WHERE user_id=?", (gift_id, user_id))
        await self.conn.commit()

    async def create_order(self, user_id: int, target: str, gift: GiftItem, expected_nano: int) -> str:
        assert self.conn
        order_id = f"order_{secrets.token_hex(8)}"
        now = int(time.time())
        await self.conn.execute(
            "INSERT INTO orders(order_id,user_id,target,gift_id,stars,expected_nano,status,created_at) "
            "VALUES(?,?,?,?,?,?, 'PENDING', ?)",
            (order_id, user_id, target, gift.id, gift.stars, expected_nano, now)
        )
        await self.conn.commit()
        return order_id

    async def get_order(self, order_id: str) -> Optional[dict]:
        assert self.conn
        cur = await self.conn.execute(
            "SELECT order_id,user_id,target,gift_id,stars,expected_nano,status,tx_hash,tx_lt,created_at,paid_at,sent_at,fail_reason "
            "FROM orders WHERE order_id=?",
            (order_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        keys = ["order_id","user_id","target","gift_id","stars","expected_nano","status","tx_hash","tx_lt","created_at","paid_at","sent_at","fail_reason"]
        return dict(zip(keys, row))

    async def recent_orders(self, user_id: int, limit: int = 5) -> List[Tuple[str, str, int, int]]:
        assert self.conn
        cur = await self.conn.execute(
            "SELECT order_id,status,stars,expected_nano FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        return await cur.fetchall()

    async def mark_paid(self, order_id: str, tx_hash: str, tx_lt: int):
        assert self.conn
        now = int(time.time())
        # prevent reusing same tx for multiple orders
        cur = await self.conn.execute("SELECT 1 FROM orders WHERE tx_hash=? AND status IN ('PAID','SENT')", (tx_hash,))
        if await cur.fetchone():
            return

        await self.conn.execute(
            "UPDATE orders SET status='PAID', tx_hash=?, tx_lt=?, paid_at=? "
            "WHERE order_id=? AND status='PENDING'",
            (tx_hash, tx_lt, now, order_id)
        )
        await self.conn.commit()

    async def paid_orders(self) -> List[Tuple[str, int, str, int]]:
        assert self.conn
        cur = await self.conn.execute("SELECT order_id,user_id,target,gift_id FROM orders WHERE status='PAID'")
        return await cur.fetchall()

    async def mark_sent(self, order_id: str):
        assert self.conn
        now = int(time.time())
        await self.conn.execute(
            "UPDATE orders SET status='SENT', sent_at=? WHERE order_id=? AND status='PAID'",
            (now, order_id)
        )
        await self.conn.commit()

    async def mark_failed(self, order_id: str, reason: str):
        assert self.conn
        await self.conn.execute("UPDATE orders SET status='FAILED', fail_reason=? WHERE order_id=?", (reason[:500], order_id))
        await self.conn.commit()

    async def get_last_lt(self) -> int:
        assert self.conn
        cur = await self.conn.execute("SELECT last_lt FROM scan_state WHERE id=1")
        row = await cur.fetchone()
        return int(row[0] or 0)

    async def set_last_lt(self, last_lt: int):
        assert self.conn
        await self.conn.execute("UPDATE scan_state SET last_lt=? WHERE id=1", (int(last_lt),))
        await self.conn.commit()


# ----------------- TON Center watcher (LIVE) -----------------
class TonCenter:
    def __init__(self, api_key: str, base_url: str, deposit_address: str):
        self.api_key = api_key
        self.base_url = base_url
        self.deposit_address = deposit_address
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        timeout = aiohttp.ClientTimeout(total=15)
        self.session = aiohttp.ClientSession(timeout=timeout)

    async def stop(self):
        if self.session:
            await self.session.close()

    def headers(self) -> dict:
        return {"X-API-Key": self.api_key}

    async def get_transactions(self, limit: int) -> List[dict]:
        assert self.session
        url = f"{self.base_url}/getTransactions"
        params = {"address": self.deposit_address, "limit": str(limit)}
        async with self.session.get(url, params=params, headers=self.headers()) as r:
            data = await r.json()
            return data.get("result") or []

    @staticmethod
    def parse(tx: dict) -> Tuple[int, str, int, int, str]:
        """
        returns (lt, tx_hash, utime, amount_nano, memo)
        """
        tid = tx.get("transaction_id") or {}
        lt = int(tid.get("lt") or 0)
        tx_hash = tid.get("hash") or ""

        utime = int(tx.get("utime") or 0)
        in_msg = tx.get("in_msg") or {}
        amount_nano = int(in_msg.get("value") or 0)
        memo = (in_msg.get("message") or "").strip()

        dst = in_msg.get("destination")
        # best-effort filter: only incoming to our deposit address
        if dst and dst != os.environ.get("TON_DEPOSIT_ADDRESS"):
            memo = ""

        return lt, tx_hash, utime, amount_nano, memo

    async def scan_new(self, db: DB) -> int:
        """
        scans newest txs and marks PAID orders.
        returns number of newly paid orders.
        """
        txs = await self.get_transactions(limit=TX_FETCH_LIMIT)
        last_lt = await db.get_last_lt()

        # txs are newest-first typically; process ascending to update checkpoint cleanly
        parsed = []
        now = int(time.time())
        for tx in txs:
            lt, tx_hash, utime, amount_nano, memo = self.parse(tx)
            if lt <= last_lt:
                continue
            if utime and (now - utime) < MIN_TX_AGE_SEC:
                continue
            if not memo.startswith("order_"):
                continue
            parsed.append((lt, tx_hash, amount_nano, memo))

        parsed.sort(key=lambda x: x[0])  # asc by lt
        paid_count = 0
        max_lt = last_lt

        for lt, tx_hash, amount_nano, memo in parsed:
            max_lt = max(max_lt, lt)
            order = await db.get_order(memo)
            if not order or order["status"] != "PENDING":
                continue
            if amount_nano < int(order["expected_nano"]):
                continue

            await db.mark_paid(memo, tx_hash, lt)
            paid_count += 1

        if max_lt > last_lt:
            await db.set_last_lt(max_lt)

        return paid_count

    async def scan_for_order(self, db: DB, order_id: str) -> bool:
        """
        LIVE check for a specific order (button press):
        fetch fresh tx list and try to match order memo immediately.
        """
        txs = await self.get_transactions(limit=TX_FETCH_LIMIT)
        now = int(time.time())
        for tx in txs:
            lt, tx_hash, utime, amount_nano, memo = self.parse(tx)
            if memo != order_id:
                continue
            if utime and (now - utime) < MIN_TX_AGE_SEC:
                continue
            order = await db.get_order(order_id)
            if not order or order["status"] != "PENDING":
                return True  # already handled
            if amount_nano < int(order["expected_nano"]):
                return False
            await db.mark_paid(order_id, tx_hash, lt)
            return True
        return False


# ----------------- Relayer (Telethon) -----------------
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
        log.info("[RELAYER] authorized as id=%s username=%s", me.id, me.username)
        return me

    async def stop(self):
        await self.client.disconnect()

    @staticmethod
    def _clean_comment(s: Optional[str]) -> str:
        if not s:
            return ""
        return s.strip().replace("\r", " ").replace("\n", " ")[:120]

    async def send_gift(self, target: str, gift: GiftItem, comment: Optional[str]) -> None:
        async with self._lock:
            can = await self.client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")

            peer = await self.client.get_input_entity(target)

            txt = self._clean_comment(comment)
            msg_obj = types.TextWithEntities(text=txt, entities=[]) if txt else None

            async def _pay(msg):
                invoice = types.InputInvoiceStarGift(peer=peer, gift_id=gift.id, message=msg)
                form = await self.client(functions.payments.GetPaymentFormRequest(invoice=invoice))
                await self.client(functions.payments.SendStarsFormRequest(form_id=form.form_id, invoice=invoice))

            try:
                await _pay(msg_obj)
            except RPCError as e:
                # if comment rejected, resend without comment + fallback message
                if "STARGIFT_MESSAGE_INVALID" in str(e):
                    await _pay(None)
                    if txt:
                        await self.client.send_message(peer, f"💬 Izoh: {txt}")
                else:
                    raise


# ----------------- Bot UI -----------------
class Form(StatesGroup):
    waiting_receiver = State()
    waiting_comment = State()

def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Sovg'a tanlash", callback_data="menu:gift")
    kb.button(text="🎯 Qabul qiluvchi", callback_data="menu:receiver")
    kb.button(text="💬 Komment", callback_data="menu:comment")
    kb.button(text="🧾 TON bilan sotib olish", callback_data="menu:buy")
    kb.button(text="📦 Buyurtmalarim", callback_data="menu:orders")
    kb.adjust(2, 1, 2)
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

def pay_kb(order_id: str, amount_nano: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    memo = quote(order_id)
    ton_link = f"ton://transfer/{TON_DEPOSIT_ADDRESS}?amount={amount_nano}&text={memo}"
    tk_link = f"https://app.tonkeeper.com/transfer/{TON_DEPOSIT_ADDRESS}?amount={amount_nano}&text={memo}"

    kb.button(text="💳 TON (ton://) to'lash", url=ton_link)
    kb.button(text="💳 Tonkeeper (https) to'lash", url=tk_link)
    kb.button(text="✅ Live tekshirish", callback_data=f"pay:check:{order_id}")
    kb.button(text="⬅️ Menu", callback_data="menu:home")
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()

def normalize_receiver(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "me"
    if t.lower() == "me":
        return "me"
    if t.startswith("@"):
        return t
    return "@" + t

def safe_comment(text: str) -> Optional[str]:
    t = (text or "").strip()
    if t == "-" or t.lower() == "off":
        return None
    return t[:250] if t else None


# ----------------- App instances -----------------
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

db = DB(DB_PATH)
ton = TonCenter(TONCENTER_API_KEY, TONCENTER_BASE, TON_DEPOSIT_ADDRESS)
relayer = Relayer()


# ----------------- Render -----------------
async def render_status(user_id: int) -> str:
    receiver, comment, sel_gift_id = await db.get_settings(user_id)
    gift_txt = "Tanlanmagan"
    if sel_gift_id and sel_gift_id in GIFTS_BY_ID:
        g = GIFTS_BY_ID[sel_gift_id]
        gift_txt = f"{g.label} (⭐{g.stars}) — {g.id}"
    return (
        "📌 Sozlamalar:\n"
        f"🎯 Qabul qiluvchi: {receiver}\n"
        f"💬 Komment: {comment if comment else '(yo‘q)'}\n"
        f"🎁 Sovg‘a: {gift_txt}\n\n"
        "Quyidan tanlang:"
    )


# ----------------- Handlers -----------------
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(m.from_user.id)
    await m.answer(await render_status(m.from_user.id), reply_markup=main_menu_kb())

@dp.message(Command("menu"))
async def cmd_menu(m: Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(m.from_user.id)
    await m.answer(await render_status(m.from_user.id), reply_markup=main_menu_kb())

@dp.callback_query(F.data == "menu:home")
async def cb_home(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db.ensure_user(c.from_user.id)
    await safe_edit(c.message, await render_status(c.from_user.id), reply_markup=main_menu_kb())

@dp.callback_query(F.data == "menu:gift")
async def cb_gift(c: CallbackQuery):
    await c.answer()
    await safe_edit(c.message, "🎁 Sovg‘a narxini tanlang:", reply_markup=price_kb())

@dp.callback_query(F.data == "menu:receiver")
async def cb_receiver(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(Form.waiting_receiver)
    await safe_edit(
        c.message,
        "🎯 Qabul qiluvchi yuboring:\n"
        "- `me` (o‘zingiz)\n"
        "- `@username` (boshqa odam)\n\n"
        "⚠️ Eng ishonchli: @username.",
        reply_markup=back_menu_kb()
    )

@dp.callback_query(F.data == "menu:comment")
async def cb_comment(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(Form.waiting_comment)
    await safe_edit(
        c.message,
        "💬 Komment yuboring (ixtiyoriy).\n"
        "O‘chirish uchun: `-` yuboring.",
        reply_markup=back_menu_kb()
    )

@dp.callback_query(F.data == "menu:orders")
async def cb_orders(c: CallbackQuery):
    await c.answer()
    await db.ensure_user(c.from_user.id)
    rows = await db.recent_orders(c.from_user.id, limit=7)
    if not rows:
        return await safe_edit(c.message, "📦 Sizda hali buyurtma yo‘q.", reply_markup=main_menu_kb())

    lines = ["📦 Oxirgi buyurtmalar:"]
    for oid, st, stars, nano in rows:
        lines.append(f"- `{oid}` — {st} — ⭐{stars} — {nano_to_ton_str(nano)} TON")
    await safe_edit(c.message, "\n".join(lines), reply_markup=main_menu_kb())

@dp.callback_query(F.data.startswith("price:"))
async def cb_price(c: CallbackQuery):
    await c.answer()
    price = int(c.data.split(":", 1)[1])
    await safe_edit(c.message, f"⭐ {price} bo‘yicha sovg‘a tanlang:", reply_markup=gifts_by_price_kb(price))

@dp.callback_query(F.data.startswith("gift:"))
async def cb_pick_gift(c: CallbackQuery):
    await c.answer()
    gid = int(c.data.split(":", 1)[1])
    if gid not in GIFTS_BY_ID:
        return await safe_edit(c.message, "Gift topilmadi.", reply_markup=price_kb())
    await db.set_gift(c.from_user.id, gid)
    g = GIFTS_BY_ID[gid]
    await safe_edit(
        c.message,
        f"✅ Tanlandi: {g.label} (⭐{g.stars})\nID: {g.id}\n\n"
        "Endi 🧾 TON bilan sotib olish ni bosing.",
        reply_markup=main_menu_kb()
    )

@dp.message(Form.waiting_receiver)
async def st_receiver(m: Message, state: FSMContext):
    await db.ensure_user(m.from_user.id)
    await db.set_receiver(m.from_user.id, normalize_receiver(m.text))
    await state.clear()
    await m.answer("✅ Saqlandi.\n\n" + await render_status(m.from_user.id), reply_markup=main_menu_kb())

@dp.message(Form.waiting_comment)
async def st_comment(m: Message, state: FSMContext):
    await db.ensure_user(m.from_user.id)
    await db.set_comment(m.from_user.id, safe_comment(m.text))
    await state.clear()
    await m.answer("✅ Saqlandi.\n\n" + await render_status(m.from_user.id), reply_markup=main_menu_kb())

@dp.callback_query(F.data == "menu:buy")
async def cb_buy(c: CallbackQuery):
    await c.answer()
    await db.ensure_user(c.from_user.id)

    receiver, comment, sel_gift_id = await db.get_settings(c.from_user.id)
    if not sel_gift_id or sel_gift_id not in GIFTS_BY_ID:
        return await safe_edit(c.message, "❌ Avval sovg‘ani tanlang.", reply_markup=main_menu_kb())

    gift = GIFTS_BY_ID[sel_gift_id]

    # resolve target
    if receiver.lower() == "me":
        if not c.from_user.username:
            return await safe_edit(
                c.message,
                "❌ Sizda @username yo‘q.\n\n"
                "`me` ishlashi uchun Telegram Settings -> Username qo‘ying.\n"
                "Yoki receiver sifatida boshqa @username kiriting.",
                reply_markup=main_menu_kb()
            )
        target = "@" + c.from_user.username
    else:
        target = receiver if receiver.startswith("@") else ("@" + receiver)

    amount_ton = Decimal(gift.stars) * TON_PRICE_PER_STAR
    expected_nano = ton_to_nano_int(amount_ton)

    order_id = await db.create_order(c.from_user.id, target, gift, expected_nano)

    text = (
        "🧾 Buyurtma yaratildi.\n\n"
        f"🎁 Gift: {gift.label} (⭐{gift.stars})\n"
        f"🎯 Qabul qiluvchi: {target}\n"
        f"💰 To‘lov: {nano_to_ton_str(expected_nano)} TON\n\n"
        "✅ Tugma orqali to‘lasangiz memo (TEXT) avtomatik qo‘yiladi.\n"
        f"📌 Memo: `{order_id}`\n\n"
        f"🏦 Deposit: `{TON_DEPOSIT_ADDRESS}`"
    )
    await safe_edit(c.message, text, reply_markup=pay_kb(order_id, expected_nano))

@dp.callback_query(F.data.startswith("pay:check:"))
async def cb_pay_check(c: CallbackQuery):
    order_id = c.data.split(":")[-1]
    await c.answer("🔎 Live tekshiryapman...")

    order = await db.get_order(order_id)
    if not order:
        return await c.answer("Order topilmadi.", show_alert=True)

    if order["status"] == "PENDING":
        found = await ton.scan_for_order(db, order_id)
        order = await db.get_order(order_id)  # refresh
        if not found and order and order["status"] == "PENDING":
            await c.answer("⏳ Hali payment topilmadi. 10-20s kutib yana bosing.", show_alert=True)

    # show updated status
    order = await db.get_order(order_id)
    gift = GIFTS_BY_ID.get(order["gift_id"])
    gift_txt = f"{gift.label} (⭐{gift.stars})" if gift else f"id={order['gift_id']}"
    st = order["status"]

    msg = (
        "🧾 Buyurtma holati:\n"
        f"• Order: `{order_id}`\n"
        f"• Status: **{st}**\n"
        f"• Gift: {gift_txt}\n"
        f"• To‘lov: {nano_to_ton_str(order['expected_nano'])} TON\n"
        f"• Target: {order['target']}\n"
    )
    if st == "PENDING":
        msg += "\n⏳ Hali payment topilmadi."
    elif st == "PAID":
        msg += "\n✅ Payment topildi. Gift yuborilyapti..."
    elif st == "SENT":
        msg += "\n✅ Gift yuborildi!"
    elif st == "FAILED":
        msg += f"\n❌ FAILED: {order.get('fail_reason') or 'unknown'}"

    await safe_edit(c.message, msg, reply_markup=pay_kb(order_id, order["expected_nano"]))


# ----------------- Background workers -----------------
async def ton_scan_loop():
    while True:
        try:
            paid = await ton.scan_new(db)
            if paid:
                log.info("[TON] new paid orders: %s", paid)
        except Exception as e:
            log.warning("[TON] scan error: %s", e)
        await asyncio.sleep(TON_POLL_INTERVAL)

async def delivery_loop():
    while True:
        try:
            rows = await db.paid_orders()
            for order_id, user_id, target, gift_id in rows:
                try:
                    gift = GIFTS_BY_ID[gift_id]
                    receiver, comment, _ = await db.get_settings(user_id)
                    final_comment = comment or f"Order: {order_id}"
                    await relayer.send_gift(target=target, gift=gift, comment=final_comment)
                    await db.mark_sent(order_id)
                    try:
                        await bot.send_message(user_id, f"🎁 Gift yuborildi! {gift.label}\nOrder: `{order_id}`")
                    except Exception:
                        pass
                except Exception as e:
                    reason = f"{type(e).__name__}: {e}"
                    await db.mark_failed(order_id, reason)
                    try:
                        await bot.send_message(user_id, f"❌ Gift yuborilmadi.\nOrder: `{order_id}`\nSabab: {reason}")
                    except Exception:
                        pass
        except Exception as e:
            log.warning("[DELIVERY] loop error: %s", e)

        await asyncio.sleep(3)


# ----------------- Main -----------------
async def main():
    await db.start()
    await ton.start()
    await relayer.start()

    t1 = asyncio.create_task(ton_scan_loop())
    t2 = asyncio.create_task(delivery_loop())

    try:
        await dp.start_polling(bot)
    finally:
        for t in (t1, t2):
            t.cancel()
        await ton.stop()
        await relayer.stop()
        await db.stop()

if __name__ == "__main__":
    asyncio.run(main())
