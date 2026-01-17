import os
import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

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


# ===================== ENV (NO .env) =====================
def env_required(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v

BOT_TOKEN = env_required("BOT_TOKEN")
TG_API_ID = int(env_required("TG_API_ID"))
TG_API_HASH = env_required("TG_API_HASH")
RELAYER_SESSION = env_required("RELAYER_SESSION")

# Only this user can use the bot
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "7440949683"))

DB_PATH = os.environ.get("DB_PATH", "bot.db")


def is_allowed(user_id: int) -> bool:
    return int(user_id) == ALLOWED_USER_ID


async def deny_message(obj: Union[Message, CallbackQuery]):
    text = "⛔️ Access denied."
    if isinstance(obj, Message):
        await obj.answer(text)
    else:
        await obj.answer(text, show_alert=True)


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

GIFTS_BY_PRICE: Dict[int, List[GiftItem]] = {}
GIFTS_BY_ID: Dict[int, GiftItem] = {}

for g in GIFT_CATALOG:
    GIFTS_BY_PRICE.setdefault(g.stars, []).append(g)
    GIFTS_BY_ID[g.id] = g

ALLOWED_PRICES = sorted(GIFTS_BY_PRICE.keys())


# ===================== DB =====================
async def db_init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            target TEXT DEFAULT 'me',
            comment TEXT DEFAULT NULL,
            selected_gift_id INTEGER DEFAULT NULL
        )
        """)
        await db.commit()

async def db_ensure_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES(?)", (user_id,))
        await db.commit()

async def db_get_settings(user_id: int) -> Tuple[str, Optional[str], Optional[int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT target, comment, selected_gift_id FROM user_settings WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            return ("me", None, None)
        return (row[0] or "me", row[1], row[2])

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

    def _clean_comment(self, s: Optional[str]) -> str:
        if not s:
            return ""
        s = s.strip().replace("\r", " ").replace("\n", " ")
        if len(s) > 120:
            s = s[:120]
        return s

    async def send_gift(
        self,
        target: Union[str, int],
        gift: GiftItem,
        comment: Optional[str] = None,
        show_profile: bool = True,
    ):
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

            txt = self._clean_comment(comment)
            msg_obj = None if not txt else types.TextWithEntities(text=txt, entities=[])

            # show_profile=True => hide_name OMIT => anonim emas
            extra = {}
            if not show_profile:
                extra["hide_name"] = True

            async def _try_send(msg):
                invoice = types.InputInvoiceStarGift(
                    peer=peer,
                    gift_id=gift.id,
                    message=msg,
                    **extra
                )
                form = await self.client(functions.payments.GetPaymentFormRequest(invoice=invoice))
                await self.client(functions.payments.SendStarsFormRequest(form_id=form.form_id, invoice=invoice)

            try:
                await _try_send(msg_obj)
            except RPCError as e:
                if "STARGIFT_MESSAGE_INVALID" in str(e):
                    await _try_send(None)
                else:
                    raise


# ===================== Bot UI =====================
def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎯 Qabul qiluvchi", callback_data="menu:target")
    kb.button(text="💬 Komment", callback_data="menu:comment")
    kb.button(text="🎁 Sovg'a tanlash", callback_data="menu:gift")
    kb.button(text="🚀 Yuborish", callback_data="menu:send")
    kb.adjust(2, 2)
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

def confirm_send_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tasdiqlab yuborish", callback_data="send:go")
    kb.button(text="🎯 Qabul qiluvchi", callback_data="menu:target")
    kb.button(text="💬 Komment", callback_data="menu:comment")
    kb.button(text="🎁 Sovg'a", callback_data="menu:gift")
    kb.button(text="⬅️ Menu", callback_data="menu:home")
    kb.adjust(1, 2, 2)
    return kb.as_markup()


class Form(StatesGroup):
    waiting_target = State()
    waiting_comment = State()


def normalize_target(text: str) -> Union[str, int]:
    t = (text or "").strip()
    if not t:
        return "me"
    if t.lower() == "me":
        return "me"
    if t.startswith("@"):
        return t
    if t.isdigit():
        return int(t)
    return "@" + t


def safe_comment(text: str) -> str:
    t = (text or "").strip()
    if len(t) > 250:
        t = t[:250]
    return t


async def render_status(user_id: int) -> str:
    target, comment, sel_gift_id = await db_get_settings(user_id)
    gift_txt = "Tanlanmagan"
    if sel_gift_id and sel_gift_id in GIFTS_BY_ID:
        g = GIFTS_BY_ID[sel_gift_id]
        gift_txt = f"{g.label} (⭐{g.stars}) — {g.id}"
    comment_txt = comment if comment else "(yo‘q)"
    return (
        "📌 Hozirgi sozlamalar:\n"
        f"🎯 Qabul qiluvchi: {target}\n"
        f"💬 Komment: {comment_txt}\n"
        f"🎁 Sovg‘a: {gift_txt}\n\n"
        "Quyidan tanlang:"
    )


bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
relayer = Relayer()


@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    if not is_allowed(m.from_user.id):
        return await deny_message(m)
    await state.clear()
    await db_ensure_user(m.from_user.id)
    await m.answer(await render_status(m.from_user.id), reply_markup=main_menu_kb())

@dp.message(Command("menu"))
async def menu_cmd(m: Message, state: FSMContext):
    if not is_allowed(m.from_user.id):
        return await deny_message(m)
    await state.clear()
    await db_ensure_user(m.from_user.id)
    await m.answer(await render_status(m.from_user.id), reply_markup=main_menu_kb())


@dp.callback_query(F.data.startswith("menu:"))
async def menu_router(c: CallbackQuery, state: FSMContext):
    if not is_allowed(c.from_user.id):
        return await deny_message(c)

    await c.answer()
    await db_ensure_user(c.from_user.id)

    action = c.data.split(":", 1)[1]

    if action == "home":
        await state.clear()
        await c.message.edit_text(await render_status(c.from_user.id), reply_markup=main_menu_kb())
        return

    if action == "target":
        await state.set_state(Form.waiting_target)
        await c.message.edit_text(
            "🎯 Qabul qiluvchini yuboring:\n- `me`\n- `@username`\n- `user_id` (raqam)\n\n"
            "⚠️ user_id ba'zan ishlamasligi mumkin. Username eng yaxshi.",
            reply_markup=back_menu_kb()
        )
        return

    if action == "comment":
        await state.set_state(Form.waiting_comment)
        await c.message.edit_text(
            "💬 Komment yuboring (ixtiyoriy).\nO‘chirish uchun: `-` yuboring.\nMasalan: `:)`",
            reply_markup=back_menu_kb()
        )
        return

    if action == "gift":
        await state.clear()
        await c.message.edit_text("🎁 Sovg‘a narxini tanlang:", reply_markup=price_kb())
        return

    if action == "send":
        await state.clear()
        await c.message.edit_text("🚀 Yuborishni tasdiqlang:", reply_markup=confirm_send_kb())
        return


@dp.message(Form.waiting_target)
async def set_target(m: Message, state: FSMContext):
    if not is_allowed(m.from_user.id):
        return await deny_message(m)

    await db_ensure_user(m.from_user.id)
    target_norm = normalize_target(m.text.strip())
    await db_set_target(m.from_user.id, str(target_norm))
    await state.clear()
    await m.answer("✅ Qabul qiluvchi saqlandi.\n\n" + await render_status(m.from_user.id), reply_markup=main_menu_kb())


@dp.message(Form.waiting_comment)
async def set_comment(m: Message, state: FSMContext):
    if not is_allowed(m.from_user.id):
        return await deny_message(m)

    await db_ensure_user(m.from_user.id)
    raw = (m.text or "").strip()
    if raw == "-" or raw.lower() == "off":
        await db_set_comment(m.from_user.id, None)
        await state.clear()
        return await m.answer("✅ Komment o‘chirildi.\n\n" + await render_status(m.from_user.id), reply_markup=main_menu_kb())

    comment = safe_comment(raw)
    await db_set_comment(m.from_user.id, comment)
    await state.clear()
    await m.answer("✅ Komment saqlandi.\n\n" + await render_status(m.from_user.id), reply_markup=main_menu_kb())


@dp.callback_query(F.data.startswith("price:"))
async def choose_price(c: CallbackQuery):
    if not is_allowed(c.from_user.id):
        return await deny_message(c)

    await c.answer()
    price = int(c.data.split(":", 1)[1])
    if price not in GIFTS_BY_PRICE:
        return await c.message.edit_text("Bunday narx yo‘q.", reply_markup=price_kb())

    await c.message.edit_text(f"⭐ {price} bo‘yicha sovg‘a tanlang:", reply_markup=gifts_by_price_kb(price))


@dp.callback_query(F.data.startswith("gift:"))
async def choose_gift(c: CallbackQuery):
    if not is_allowed(c.from_user.id):
        return await deny_message(c)

    await c.answer()
    gift_id = int(c.data.split(":", 1)[1])
    if gift_id not in GIFTS_BY_ID:
        return await c.message.edit_text("Gift topilmadi.", reply_markup=price_kb())

    await db_set_selected_gift(c.from_user.id, gift_id)
    g = GIFTS_BY_ID[gift_id]
    await c.message.edit_text(
        f"✅ Sovg‘a tanlandi:\n{g.label} (⭐{g.stars})\nID: {g.id}\n\nEndi yuborishni tasdiqlang:",
        reply_markup=confirm_send_kb()
    )


@dp.callback_query(F.data == "send:go")
async def send_go(c: CallbackQuery):
    if not is_allowed(c.from_user.id):
        return await deny_message(c)

    await c.answer()
    await db_ensure_user(c.from_user.id)

    target_str, comment, sel_gift_id = await db_get_settings(c.from_user.id)
    if not sel_gift_id or sel_gift_id not in GIFTS_BY_ID:
        return await c.message.edit_text("❌ Avval sovg‘ani tanlang.", reply_markup=main_menu_kb())

    gift = GIFTS_BY_ID[sel_gift_id]

    t = (target_str or "me").strip()
    if t.lower() == "me":
        target: Union[str, int] = "me"
    elif t.startswith("@"):
        target = t
    elif t.isdigit():
        target = int(t)
    else:
        target = "@" + t

    msg = (comment or "").strip()

    await c.message.edit_text(
        f"⏳ Yuborilyapti...\n🎯 Target: {target_str}\n🎁 Gift: {gift.label} (⭐{gift.stars})\n💬 Comment: {(msg if msg else '(bo‘sh)')}",
        reply_markup=None
    )

    try:
        await relayer.send_gift(target=target, gift=gift, comment=msg, show_profile=True)
        await c.message.edit_text("✅ Yuborildi!\n\n" + await render_status(c.from_user.id), reply_markup=main_menu_kb())
    except RPCError as e:
        await c.message.edit_text(f"❌ Telegram RPCError: {e.__class__.__name__}: {e}\n\n" + await render_status(c.from_user.id),
                                  reply_markup=main_menu_kb())
    except Exception as e:
        await c.message.edit_text(f"❌ Xatolik: {e}\n\n" + await render_status(c.from_user.id),
                                  reply_markup=main_menu_kb())


async def main():
    await db_init()
    me = await relayer.start()
    print(f"[RELAYER] authorized as: id={me.id} username={me.username}")

    try:
        await dp.start_polling(bot)
    finally:
        await relayer.stop()

if __name__ == "__main__":
    asyncio.run(main())
