import os
import asyncio
import time
import secrets
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
from decimal import Decimal, ROUND_UP
from urllib.parse import quote

import aiohttp
import aiosqlite

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


# ===================== ENV (Secrets only) =====================
def env_required(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v

BOT_TOKEN = env_required("BOT_TOKEN")
TG_API_ID = int(env_required("TG_API_ID"))
TG_API_HASH = env_required("TG_API_HASH")
RELAYER_SESSION = env_required("RELAYER_SESSION")

TON_DEPOSIT_ADDRESS = env_required("TON_DEPOSIT_ADDRESS")
TONCENTER_API_KEY = env_required("TONCENTER_API_KEY")

TONCENTER_BASE = os.environ.get("TONCENTER_BASE", "https://toncenter.com/api/v2")
TON_POLL_INTERVAL = int(os.environ.get("TON_POLL_INTERVAL", "6"))
MIN_TX_AGE_SEC = int(os.environ.get("MIN_TX_AGE_SEC", "10"))

RELAYER_CONTACT = os.environ.get("RELAYER_CONTACT", "").strip()  # optional

# TON per 1 star (e.g. 0.01)
TON_PRICE_PER_STAR = Decimal(env_required("TON_PRICE_PER_STAR"))

DB_PATH = os.environ.get("DB_PATH", "bot.db")


# ===================== Helpers =====================
NANO = Decimal("1000000000")

def ton_to_nano_int(ton_amount: Decimal) -> int:
    # round up to avoid underpayment due to decimals
    a = ton_amount.quantize(Decimal("0.000000001"), rounding=ROUND_UP)
    return int(a * NANO)

def nano_to_ton_str(nano: int) -> str:
    s = (Decimal(nano) / NANO).normalize()
    # normalize() sometimes outputs scientific; force plain:
    return format(s, "f").rstrip("0").rstrip(".") if "." in format(s, "f") else format(s, "f")


# ===================== STATIC GIFT CATALOG =====================
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


# ===================== DB =====================
async def db_init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            receiver TEXT DEFAULT 'me',          -- me | @username
            comment TEXT DEFAULT NULL,
            selected_gift_id INTEGER DEFAULT NULL
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            tg_user_id INTEGER NOT NULL,
            buyer_username TEXT,
            receiver TEXT NOT NULL,              -- resolved receiver string (me/@username)
            gift_id INTEGER NOT NULL,
            stars INTEGER NOT NULL,
            amount_nano INTEGER NOT NULL,        -- expected amount in nanotons
            status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/PAID/SENT/FAILED
            tx_hash TEXT,
            created_at INTEGER NOT NULL,
            paid_at INTEGER,
            sent_at INTEGER,
            fail_reason TEXT
        )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        await db.commit()

async def db_ensure_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES(?)", (user_id,))
        await db.commit()

async def db_get_settings(user_id: int) -> Tuple[str, Optional[str], Optional[int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT receiver, comment, selected_gift_id FROM user_settings WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            return ("me", None, None)
        return (row[0] or "me", row[1], row[2])

async def db_set_receiver(user_id: int, receiver: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE user_settings SET receiver=? WHERE user_id=?", (receiver, user_id))
        await db.commit()

async def db_set_comment(user_id: int, comment: Optional[str]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE user_settings SET comment=? WHERE user_id=?", (comment, user_id))
        await db.commit()

async def db_set_selected_gift(user_id: int, gift_id: Optional[int]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE user_settings SET selected_gift_id=? WHERE user_id=?", (gift_id, user_id))
        await db.commit()

async def db_create_order(
    tg_user_id: int,
    buyer_username: Optional[str],
    receiver: str,
    gift: GiftItem,
    amount_nano: int
) -> str:
    order_id = f"order_{secrets.token_hex(8)}"
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO orders(order_id, tg_user_id, buyer_username, receiver, gift_id, stars, amount_nano, status, created_at) "
            "VALUES(?,?,?,?,?,?,?, 'PENDING', ?)",
            (order_id, tg_user_id, buyer_username, receiver, gift.id, gift.stars, amount_nano, now)
        )
        await db.commit()
    return order_id

async def db_get_order(order_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT order_id, tg_user_id, buyer_username, receiver, gift_id, stars, amount_nano, status, tx_hash, created_at, paid_at, sent_at, fail_reason "
            "FROM orders WHERE order_id=?",
            (order_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        keys = ["order_id","tg_user_id","buyer_username","receiver","gift_id","stars","amount_nano","status","tx_hash","created_at","paid_at","sent_at","fail_reason"]
        return dict(zip(keys, row))

async def db_mark_paid(order_id: str, tx_hash: str):
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status='PAID', tx_hash=?, paid_at=? WHERE order_id=? AND status='PENDING'",
            (tx_hash, now, order_id)
        )
        await db.commit()

async def db_get_paid_unsent() -> List[Tuple[str, int, str, int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT order_id, tg_user_id, receiver, gift_id FROM orders WHERE status='PAID'")
        return await cur.fetchall()

async def db_mark_sent(order_id: str):
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status='SENT', sent_at=? WHERE order_id=? AND status='PAID'", (now, order_id))
        await db.commit()

async def db_mark_failed(order_id: str, reason: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status='FAILED', fail_reason=? WHERE order_id=?", (reason[:500], order_id))
        await db.commit()

async def db_recent_orders(user_id: int, limit: int = 5) -> List[Tuple[str, str, int, int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT order_id, status, stars, amount_nano FROM orders WHERE tg_user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        return await cur.fetchall()


# ===================== Relayer (Telethon) =====================
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
    def _clean_comment(s: Optional[str]) -> str:
        if not s:
            return ""
        s = s.strip().replace("\r", " ").replace("\n", " ")
        return s[:120]

    async def send_gift(self, target: str, gift: GiftItem, comment: Optional[str] = None) -> None:
        """
        show_profile=True default: hide_name OMIT (profil ko'rinadi).
        comment attach ko'p holatda STARGIFT_MESSAGE_INVALID bo'ladi, shuning uchun fallback chat message qo'yilgan.
        """
        async with self._lock:
            # 1) can send gift id?
            can = await self.client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")

            # 2) resolve peer (username recommended)
            peer = await self.client.get_input_entity(target)

            # 3) build message
            txt = self._clean_comment(comment)
            msg_obj = None
            if txt:
                msg_obj = types.TextWithEntities(text=txt, entities=[])

            async def _pay(msg):
                invoice = types.InputInvoiceStarGift(peer=peer, gift_id=gift.id, message=msg)
                form = await self.client(functions.payments.GetPaymentFormRequest(invoice=invoice))
                await self.client(
                    functions.payments.SendStarsFormRequest(
                        form_id=form.form_id,
                        invoice=invoice
                    )
                )

            try:
                await _pay(msg_obj)
            except RPCError as e:
                # comment reject bo'lsa, comment'siz yuboramiz va commentni chatga tashlaymiz
                if "STARGIFT_MESSAGE_INVALID" in str(e):
                    await _pay(None)
                    if txt:
                        await self.client.send_message(peer, f"💬 Izoh: {txt}")
                else:
                    raise


# ===================== TON Watcher =====================
class TonCenterWatcher:
    def __init__(self, deposit_address: str, api_key: str, base_url: str):
        self.addr = deposit_address
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session: Optional[aiohttp.ClientSession] = None
        self.seen_hashes = set()

    async def start(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))

    async def stop(self):
        if self.session:
            await self.session.close()

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key}

    async def fetch_transactions(self, limit: int = 50) -> List[dict]:
        url = f"{self.base_url}/getTransactions"
        params = {"address": self.addr, "limit": str(limit)}
        async with self.session.get(url, params=params, headers=self._headers()) as r:
            data = await r.json()
            return data.get("result") or []

    def parse_tx(self, tx: dict) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[int], Optional[str]]:
        """
        Returns: (memo, amount_nano, tx_hash, utime, dst)
        """
        tid = tx.get("transaction_id") or {}
        tx_hash = tid.get("hash") or tx.get("hash")

        utime = tx.get("utime")  # seconds
        in_msg = tx.get("in_msg") or {}

        memo = (in_msg.get("message") or "").strip()
        dst = in_msg.get("destination")
        val = in_msg.get("value")

        amount_nano = None
        if val is not None:
            try:
                amount_nano = int(val)
            except Exception:
                amount_nano = None

        return (memo or None, amount_nano, tx_hash, utime, dst)

    async def scan_once(self) -> List[Tuple[str, int, str]]:
        """
        returns list of matched payments: [(order_id, amount_nano, tx_hash), ...]
        """
        txs = await self.fetch_transactions(limit=60)
        matches = []
        now = int(time.time())

        for tx in txs:
            memo, amount_nano, tx_hash, utime, dst = self.parse_tx(tx)
            if not memo or amount_nano is None or not tx_hash:
                continue

            # only incoming to deposit address (best effort)
            if dst and dst != self.addr:
                continue

            # avoid too-fresh tx
            if isinstance(utime, int) and (now - utime) < MIN_TX_AGE_SEC:
                continue

            if tx_hash in self.seen_hashes:
                continue

            # memo must be order_id exact (we generate order_...)
            if memo.startswith("order_"):
                matches.append((memo, amount_nano, tx_hash))
                self.seen_hashes.add(tx_hash)

        return matches


# ===================== Bot UI =====================
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

    # Universal TON deep-link
    ton_link = f"ton://transfer/{TON_DEPOSIT_ADDRESS}?amount={amount_nano}&text={memo}"

    # Tonkeeper app link (also works for many users)
    tk_link = f"https://app.tonkeeper.com/transfer/{TON_DEPOSIT_ADDRESS}?amount={amount_nano}&text={memo}"

    kb.button(text="💳 TON (ton://) to'lash", url=ton_link)
    kb.button(text="💳 Tonkeeper (https) to'lash", url=tk_link)
    kb.button(text="✅ To'lovni tekshirish", callback_data=f"pay:check:{order_id}")
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
    if t.isdigit():
        # for safety: do not accept numeric user_id as receiver in MVP
        return "@" + t  # will likely fail, but keep as username-like
    return "@" + t

def safe_comment(text: str) -> str:
    t = (text or "").strip()
    if t == "-" or t.lower() == "off":
        return ""
    return t[:250]

async def render_status(user_id: int) -> str:
    receiver, comment, sel_gift_id = await db_get_settings(user_id)
    gift_txt = "Tanlanmagan"
    if sel_gift_id and sel_gift_id in GIFTS_BY_ID:
        g = GIFTS_BY_ID[sel_gift_id]
        gift_txt = f"{g.label} (⭐{g.stars}) — {g.id}"

    comment_txt = comment if comment else "(yo‘q)"
    return (
        "📌 Sozlamalar:\n"
        f"🎯 Qabul qiluvchi: {receiver}\n"
        f"💬 Komment: {comment_txt}\n"
        f"🎁 Sovg‘a: {gift_txt}\n\n"
        "Quyidan tanlang:"
    )


# ===================== App =====================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
relayer = Relayer()
watcher = TonCenterWatcher(TON_DEPOSIT_ADDRESS, TONCENTER_API_KEY, TONCENTER_BASE)


# -------- Commands --------
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await db_ensure_user(m.from_user.id)
    await m.answer(await render_status(m.from_user.id), reply_markup=main_menu_kb())

@dp.message(Command("menu"))
async def cmd_menu(m: Message, state: FSMContext):
    await state.clear()
    await db_ensure_user(m.from_user.id)
    await m.answer(await render_status(m.from_user.id), reply_markup=main_menu_kb())


# -------- Menu callbacks --------
@dp.callback_query(F.data == "menu:home")
async def cb_home(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await db_ensure_user(c.from_user.id)
    await c.message.edit_text(await render_status(c.from_user.id), reply_markup=main_menu_kb())

@dp.callback_query(F.data == "menu:gift")
async def cb_gift(c: CallbackQuery):
    await c.answer()
    await c.message.edit_text("🎁 Sovg‘a narxini tanlang:", reply_markup=price_kb())

@dp.callback_query(F.data == "menu:receiver")
async def cb_receiver(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(Form.waiting_receiver)
    hint = ""
    if RELAYER_CONTACT:
        hint = f"\n\n⚠️ Agar yuborishda muammo bo'lsa, {RELAYER_CONTACT} akkauntga 1 marta 'hi' yozib qo'ying."
    await c.message.edit_text(
        "🎯 Qabul qiluvchi yuboring:\n"
        "- `me` (o‘zingiz)\n"
        "- `@username` (boshqa odam)\n\n"
        "✅ Eng ishonchli: `me` yoki @username.\n"
        + hint,
        reply_markup=back_menu_kb()
    )

@dp.callback_query(F.data == "menu:comment")
async def cb_comment(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(Form.waiting_comment)
    await c.message.edit_text(
        "💬 Komment yuboring (ixtiyoriy).\n"
        "O‘chirish uchun: `-` yuboring.\n"
        "Masalan: `Congrats 🎁`",
        reply_markup=back_menu_kb()
    )

@dp.callback_query(F.data == "menu:orders")
async def cb_orders(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    rows = await db_recent_orders(c.from_user.id, limit=5)
    if not rows:
        return await c.message.edit_text("📦 Sizda hali buyurtma yo‘q.", reply_markup=main_menu_kb())

    lines = ["📦 Oxirgi buyurtmalar:"]
    for order_id, status, stars, amount_nano in rows:
        lines.append(f"- `{order_id}` — {status} — ⭐{stars} — {nano_to_ton_str(amount_nano)} TON")
    await c.message.edit_text("\n".join(lines), reply_markup=main_menu_kb())

@dp.callback_query(F.data == "menu:buy")
async def cb_buy(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    receiver, comment, sel_gift_id = await db_get_settings(c.from_user.id)

    if not sel_gift_id or sel_gift_id not in GIFTS_BY_ID:
        return await c.message.edit_text("❌ Avval sovg‘ani tanlang.", reply_markup=main_menu_kb())

    gift = GIFTS_BY_ID[sel_gift_id]
    buyer_username = c.from_user.username

    # receiver resolve: if "me" => needs buyer username
    if receiver.lower() == "me":
        if not buyer_username:
            hint = ""
            if RELAYER_CONTACT:
                hint = f"\n\nAgar username qo'ymasangiz, kamida {RELAYER_CONTACT} akkauntga 1 marta yozib qo'ying (keyin hammasi osonlashadi)."
            return await c.message.edit_text(
                "❌ Sizda @username yo‘q.\n\n"
                "MVP uchun `me` ishlashi uchun @username kerak.\n"
                "Telegram Settings -> Username qo‘ying, keyin qayta urinib ko‘ring."
                + hint,
                reply_markup=main_menu_kb()
            )
        target = "@" + buyer_username
    else:
        target = receiver if receiver.startswith("@") else ("@" + receiver)

    # amount compute
    amount_ton = (Decimal(gift.stars) * TON_PRICE_PER_STAR)
    amount_nano = ton_to_nano_int(amount_ton)

    # Create order
    order_id = await db_create_order(
        tg_user_id=c.from_user.id,
        buyer_username=buyer_username,
        receiver=receiver,
        gift=gift,
        amount_nano=amount_nano,
    )

    await c.message.edit_text(
        "🧾 Buyurtma yaratildi.\n\n"
        f"🎁 Gift: {gift.label} (⭐{gift.stars})\n"
        f"🎯 Qabul qiluvchi: {target}\n"
        f"💰 To‘lov: {nano_to_ton_str(amount_nano)} TON\n\n"
        "✅ Tugma orqali to‘lasangiz COMMENT/TEXT avtomatik qo‘yiladi.\n"
        f"📌 Memo (TEXT): `{order_id}`\n\n"
        f"🏦 Deposit address: `{TON_DEPOSIT_ADDRESS}`",
        reply_markup=pay_kb(order_id, amount_nano)
    )


# -------- States: receiver/comment text input --------
@dp.message(Form.waiting_receiver)
async def st_receiver(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    r = normalize_receiver(m.text)
    await db_set_receiver(m.from_user.id, r)
    await state.clear()
    await m.answer("✅ Qabul qiluvchi saqlandi.\n\n" + await render_status(m.from_user.id), reply_markup=main_menu_kb())

@dp.message(Form.waiting_comment)
async def st_comment(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    txt = safe_comment(m.text or "")
    await db_set_comment(m.from_user.id, txt if txt else None)
    await state.clear()
    await m.answer("✅ Komment saqlandi.\n\n" + await render_status(m.from_user.id), reply_markup=main_menu_kb())


# -------- Price / Gift selection --------
@dp.callback_query(F.data.startswith("price:"))
async def cb_price(c: CallbackQuery):
    await c.answer()
    price = int(c.data.split(":", 1)[1])
    await c.message.edit_text(f"⭐ {price} bo‘yicha sovg‘a tanlang:", reply_markup=gifts_by_price_kb(price))

@dp.callback_query(F.data.startswith("gift:"))
async def cb_gift_pick(c: CallbackQuery):
    await c.answer()
    gid = int(c.data.split(":", 1)[1])
    if gid not in GIFTS_BY_ID:
        return await c.message.edit_text("Gift topilmadi.", reply_markup=price_kb())
    await db_set_selected_gift(c.from_user.id, gid)
    g = GIFTS_BY_ID[gid]
    await c.message.edit_text(
        f"✅ Tanlandi: {g.label} (⭐{g.stars})\nID: {g.id}\n\n"
        "Endi 🧾 TON bilan sotib olish ni bosing.",
        reply_markup=main_menu_kb()
    )


# -------- Payment check button --------
@dp.callback_query(F.data.startswith("pay:check:"))
async def cb_pay_check(c: CallbackQuery):
    await c.answer()
    order_id = c.data.split(":")[-1]
    order = await db_get_order(order_id)
    if not order:
        return await c.answer("Order topilmadi.", show_alert=True)

    st = order["status"]
    if st == "PENDING":
        return await c.answer("⏳ Hali payment topilmadi. 10-20 soniya kutib qayta bosing.", show_alert=True)
    if st == "PAID":
        return await c.answer("✅ Payment topildi! Gift yuborilyapti...", show_alert=True)
    if st == "SENT":
        return await c.answer("✅ Gift yuborildi!", show_alert=True)
    if st == "FAILED":
        return await c.answer(f"❌ FAILED: {order.get('fail_reason') or 'unknown'}", show_alert=True)
    return await c.answer(f"Status: {st}", show_alert=True)


# ===================== Background loops =====================
async def ton_watcher_loop():
    await watcher.start()
    try:
        while True:
            try:
                matches = await watcher.scan_once()
                for order_id, amount_nano, tx_hash in matches:
                    order = await db_get_order(order_id)
                    if not order or order["status"] != "PENDING":
                        continue

                    expected = int(order["amount_nano"])
                    if amount_nano < expected:
                        continue

                    await db_mark_paid(order_id, tx_hash)
                    # notify user
                    try:
                        await bot.send_message(order["tg_user_id"], f"✅ TON payment topildi: `{order_id}`\nGift yuborilishini kuting.")
                    except Exception:
                        pass
            except Exception as e:
                print(f"[TON] scan error: {e}")

            await asyncio.sleep(TON_POLL_INTERVAL)
    finally:
        await watcher.stop()

async def delivery_loop():
    while True:
        paid = await db_get_paid_unsent()
        for order_id, tg_user_id, receiver, gift_id in paid:
            try:
                gift = GIFTS_BY_ID[gift_id]
                # resolve target
                order = await db_get_order(order_id)
                buyer_username = (order.get("buyer_username") or "").strip()
                comment = None

                # load user comment
                rcv, usr_comment, _ = await db_get_settings(tg_user_id)
                if usr_comment:
                    comment = usr_comment
                else:
                    comment = f"Order: {order_id}"

                if receiver.lower() == "me":
                    if not buyer_username:
                        raise RuntimeError("Buyer has no username; cannot deliver to me.")
                    target = "@" + buyer_username
                else:
                    target = receiver if receiver.startswith("@") else ("@" + receiver)

                await relayer.send_gift(target=target, gift=gift, comment=comment)
                await db_mark_sent(order_id)
                try:
                    await bot.send_message(tg_user_id, f"🎁 Gift yuborildi! {gift.label}\nOrder: `{order_id}`")
                except Exception:
                    pass
            except Exception as e:
                reason = f"{type(e).__name__}: {e}"
                await db_mark_failed(order_id, reason)
                try:
                    await bot.send_message(tg_user_id, f"❌ Gift yuborilmadi.\nOrder: `{order_id}`\nSabab: {reason}\n\nAgar kerak bo'lsa sizga refund/manual yordam qilamiz.")
                except Exception:
                    pass

        await asyncio.sleep(4)


# ===================== RUN =====================
async def main():
    await db_init()

    me = await relayer.start()
    print(f"[RELAYER] authorized as: id={me.id} username={me.username}")

    # background tasks
    asyncio.create_task(ton_watcher_loop())
    asyncio.create_task(delivery_loop())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
