import os
import re
import time
import json
import asyncio
import logging
import secrets
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import aiosqlite
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineQuery,
    InlineKeyboardMarkup, InlineQueryResultArticle,
    InputTextMessageContent
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import RPCError
from telethon.errors.rpcerrorlist import AuthKeyDuplicatedError


# =========================
# IMPORTANT (1 daqiqa o‘qi!)
# =========================
# 1) RELAYER_SESSION faqat 1 joyda ishlasin. Aks holda AuthKeyDuplicatedError bo‘ladi.
# 2) Hostingda 1 ta instance/dyno qoldir.
# 3) Bot admin-only: faqat adminlar foydalanadi.
# 4) Inline ishlashi uchun BotFather’da Inline Mode yoqilgan bo‘lishi kerak.


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

# Owner (bosh admin)
OWNER_ID = int(os.getenv("OWNER_ID", "7440949683"))

DB_PATH = os.getenv("DB_PATH", "bot.db")


# =========================
# Gifts catalog (ID ko‘rsatmaymiz)
# =========================
@dataclass(frozen=True)
class GiftItem:
    gift_id: int
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
    GIFTS_BY_ID[g.gift_id] = g
ALLOWED_PRICES = sorted(GIFTS_BY_PRICE.keys())


# =========================
# Simple i18n (RU default)
# =========================
TEXTS = {
    "ru": {
        "access_denied": "⛔ Доступ запрещён.",
        "start": "✅ Панель администратора.\n\nВыберите действие:",
        "mode_profile": "👤 Профиль (показывать имя)",
        "mode_anon": "🕵️ Аноним (скрыть имя)",
        "comment_none": "(без комментария)",
        "target_none": "(цель не указана)",
        "set_comment_tip": "💬 Отправьте комментарий.\nУдалить: отправьте `-`",
        "set_target_tip": "🎯 Отправьте цель:\n- `@username`\n- `id` (число)\n\n✅ Лучше всего: @username",
        "choose_price": "⭐ Выберите цену:",
        "choose_gift": "🎁 Выберите подарок за ⭐{price}:",
        "confirm_title": "Подтвердите отправку:",
        "confirm_send": "✅ Отправить",
        "confirm_cancel": "❌ Отмена",
        "cancelled": "❌ Отменено.",
        "not_owner": "⚠️ Только создатель команды может подтверждать/отменять.",
        "already_done": "⚠️ Уже обработано.",
        "sending": "⏳ Отправляю...",
        "sent": "✅ Отправлено!",
        "failed": "❌ Ошибка отправки:\n{err}",
        "need_reply_or_target": "⚠️ В группе используйте команду как reply.\nПример: ответьте на человека и напишите /gift 50\n\nИли укажите цель явно: /gift @username 50",
        "admin_added": "✅ Админ добавлен: {uid}",
        "admin_removed": "✅ Админ удалён: {uid}",
        "admins_list": "👥 Админы:\n{list}",
        "lang_set": "✅ Язык установлен: {lang}",
        "inline_usage": "Напишите: `50 @username` (например: `50 @someone`)",
        "inline_pick": "Нажмите и подтвердите отправку.",
    },
    "uz": {
        "access_denied": "⛔ Ruxsat yo‘q.",
        "start": "✅ Admin panel.\n\nTanlang:",
        "mode_profile": "👤 Profil (ism ko‘rinsin)",
        "mode_anon": "🕵️ Anonim (ism yashirilsin)",
        "comment_none": "(komment yo‘q)",
        "target_none": "(target yo‘q)",
        "set_comment_tip": "💬 Komment yuboring.\nO‘chirish: `-` yuboring",
        "set_target_tip": "🎯 Target yuboring:\n- `@username`\n- `id` (raqam)\n\n✅ Eng yaxshi: @username",
        "choose_price": "⭐ Narxni tanlang:",
        "choose_gift": "🎁 ⭐{price} uchun sovg‘ani tanlang:",
        "confirm_title": "Yuborishni tasdiqlang:",
        "confirm_send": "✅ Yuborish",
        "confirm_cancel": "❌ Bekor qilish",
        "cancelled": "❌ Bekor qilindi.",
        "not_owner": "⚠️ Faqat buyruq bergan admin tasdiqlay oladi.",
        "already_done": "⚠️ Allaqachon bajarilgan.",
        "sending": "⏳ Yuborilyapti...",
        "sent": "✅ Yuborildi!",
        "failed": "❌ Xatolik:\n{err}",
        "need_reply_or_target": "⚠️ Guruhda reply qilib ishlating.\nMasalan: odamga reply qiling va yozing: /gift 50\n\nYoki targetni yozing: /gift @username 50",
        "admin_added": "✅ Admin qo‘shildi: {uid}",
        "admin_removed": "✅ Admin o‘chirildi: {uid}",
        "admins_list": "👥 Adminlar:\n{list}",
        "lang_set": "✅ Til o‘rnatildi: {lang}",
        "inline_usage": "Shunday yozing: `50 @username` (masalan: `50 @someone`)",
        "inline_pick": "Tanlang va tasdiqlang.",
    },
    "en": {
        "access_denied": "⛔ Access denied.",
        "start": "✅ Admin panel.\n\nChoose:",
        "mode_profile": "👤 Show profile (show name)",
        "mode_anon": "🕵️ Anonymous (hide name)",
        "comment_none": "(no comment)",
        "target_none": "(no target)",
        "set_comment_tip": "💬 Send comment.\nDelete: send `-`",
        "set_target_tip": "🎯 Send target:\n- `@username`\n- `id` (number)\n\n✅ Best: @username",
        "choose_price": "⭐ Choose price:",
        "choose_gift": "🎁 Choose gift for ⭐{price}:",
        "confirm_title": "Confirm sending:",
        "confirm_send": "✅ Send",
        "confirm_cancel": "❌ Cancel",
        "cancelled": "❌ Cancelled.",
        "not_owner": "⚠️ Only the creator admin can confirm/cancel.",
        "already_done": "⚠️ Already processed.",
        "sending": "⏳ Sending...",
        "sent": "✅ Sent!",
        "failed": "❌ Failed:\n{err}",
        "need_reply_or_target": "⚠️ In groups: reply to a user and type /gift 50\n\nOr provide target: /gift @username 50",
        "admin_added": "✅ Admin added: {uid}",
        "admin_removed": "✅ Admin removed: {uid}",
        "admins_list": "👥 Admins:\n{list}",
        "lang_set": "✅ Language set: {lang}",
        "inline_usage": "Type: `50 @username` (example: `50 @someone`)",
        "inline_pick": "Pick and confirm.",
    },
}

def t(lang: str, key: str, **kwargs) -> str:
    lang = (lang or "ru").lower()
    d = TEXTS.get(lang) or TEXTS["ru"]
    s = d.get(key) or TEXTS["ru"].get(key, key)
    return s.format(**kwargs)


# =========================
# DB: single connection (threads error bo‘lmaydi)
# =========================
class DB:
    def __init__(self, path: str):
        self.path = path
        self.conn: Optional[aiosqlite.Connection] = None
        self.lock = asyncio.Lock()

    async def start(self):
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("PRAGMA synchronous=NORMAL;")
        await self.conn.execute("PRAGMA foreign_keys=ON;")
        await self.conn.execute("PRAGMA busy_timeout=5000;")

        await self.conn.execute("""
        CREATE TABLE IF NOT EXISTS admins(
            user_id INTEGER PRIMARY KEY,
            role TEXT NOT NULL DEFAULT 'admin', -- owner/admin
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        );
        """)
        await self.conn.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            user_id INTEGER PRIMARY KEY,
            anonymous INTEGER NOT NULL DEFAULT 0,
            comment TEXT DEFAULT NULL,
            target TEXT DEFAULT NULL,
            lang TEXT NOT NULL DEFAULT 'ru'
        );
        """)
        await self.conn.execute("""
        CREATE TABLE IF NOT EXISTS actions(
            token TEXT PRIMARY KEY,
            creator_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            msg_id INTEGER NOT NULL,
            target TEXT NOT NULL,
            gift_id INTEGER NOT NULL,
            anonymous INTEGER NOT NULL,
            comment TEXT DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'pending', -- pending/sending/sent/cancelled/failed
            last_error TEXT DEFAULT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        """)
        await self.conn.commit()

        # ensure owner exists
        now = int(time.time())
        await self.conn.execute(
            "INSERT OR IGNORE INTO admins(user_id, role, is_active, created_at) VALUES(?,?,?,?)",
            (OWNER_ID, "owner", 1, now)
        )
        await self.conn.commit()

    async def stop(self):
        if self.conn:
            await self.conn.close()
            self.conn = None

    async def is_admin(self, user_id: int) -> Tuple[bool, str]:
        async with self.lock:
            cur = await self.conn.execute("SELECT role, is_active FROM admins WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
            if not row:
                return False, ""
            if int(row["is_active"]) != 1:
                return False, ""
            return True, str(row["role"])

    async def add_admin(self, user_id: int, role: str = "admin"):
        now = int(time.time())
        async with self.lock:
            await self.conn.execute(
                "INSERT OR REPLACE INTO admins(user_id, role, is_active, created_at) VALUES(?,?,?,?)",
                (user_id, role, 1, now)
            )
            await self.conn.commit()

    async def remove_admin(self, user_id: int):
        async with self.lock:
            await self.conn.execute("UPDATE admins SET is_active=0 WHERE user_id=?", (user_id,))
            await self.conn.commit()

    async def list_admins(self) -> List[Tuple[int, str, int]]:
        async with self.lock:
            cur = await self.conn.execute("SELECT user_id, role, is_active FROM admins ORDER BY role DESC, user_id ASC")
            rows = await cur.fetchall()
            return [(int(r["user_id"]), str(r["role"]), int(r["is_active"])) for r in rows]

    async def ensure_settings(self, user_id: int):
        async with self.lock:
            await self.conn.execute("INSERT OR IGNORE INTO settings(user_id) VALUES(?)", (user_id,))
            await self.conn.commit()

    async def get_settings(self, user_id: int) -> Tuple[int, Optional[str], Optional[str], str]:
        async with self.lock:
            cur = await self.conn.execute(
                "SELECT anonymous, comment, target, lang FROM settings WHERE user_id=?",
                (user_id,)
            )
            r = await cur.fetchone()
            if not r:
                return 0, None, None, "ru"
            return int(r["anonymous"]), r["comment"], r["target"], str(r["lang"] or "ru")

    async def set_lang(self, user_id: int, lang: str):
        async with self.lock:
            await self.conn.execute("UPDATE settings SET lang=? WHERE user_id=?", (lang, user_id))
            await self.conn.commit()

    async def toggle_anonymous(self, user_id: int) -> int:
        async with self.lock:
            cur = await self.conn.execute("SELECT anonymous FROM settings WHERE user_id=?", (user_id,))
            r = await cur.fetchone()
            curv = int(r["anonymous"] or 0) if r else 0
            newv = 0 if curv == 1 else 1
            await self.conn.execute("UPDATE settings SET anonymous=? WHERE user_id=?", (newv, user_id))
            await self.conn.commit()
            return newv

    async def set_comment(self, user_id: int, comment: Optional[str]):
        async with self.lock:
            await self.conn.execute("UPDATE settings SET comment=? WHERE user_id=?", (comment, user_id))
            await self.conn.commit()

    async def set_target(self, user_id: int, target: Optional[str]):
        async with self.lock:
            await self.conn.execute("UPDATE settings SET target=? WHERE user_id=?", (target, user_id))
            await self.conn.commit()

    async def create_action(
        self,
        token: str,
        creator_id: int,
        chat_id: int,
        msg_id: int,
        target: str,
        gift_id: int,
        anonymous: int,
        comment: Optional[str],
    ):
        now = int(time.time())
        async with self.lock:
            await self.conn.execute("""
            INSERT INTO actions(token, creator_id, chat_id, msg_id, target, gift_id, anonymous, comment, status, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """, (token, creator_id, chat_id, msg_id, target, gift_id, anonymous, comment, "pending", now, now))
            await self.conn.commit()

    async def get_action(self, token: str) -> Optional[dict]:
        async with self.lock:
            cur = await self.conn.execute("SELECT * FROM actions WHERE token=?", (token,))
            r = await cur.fetchone()
            if not r:
                return None
            return dict(r)

    async def claim_action_sending(self, token: str, user_id: int) -> Tuple[bool, str]:
        # Atomic: faqat pending bo‘lsa sendingga o‘tadi
        now = int(time.time())
        async with self.lock:
            cur = await self.conn.execute("SELECT creator_id, status FROM actions WHERE token=?", (token,))
            r = await cur.fetchone()
            if not r:
                return False, "missing"
            if int(r["creator_id"]) != user_id:
                return False, "not_owner"
            if str(r["status"]) != "pending":
                return False, "already"
            await self.conn.execute(
                "UPDATE actions SET status='sending', updated_at=? WHERE token=? AND status='pending'",
                (now, token)
            )
            await self.conn.commit()
            return True, "ok"

    async def mark_action(self, token: str, status: str, err: Optional[str] = None):
        now = int(time.time())
        async with self.lock:
            await self.conn.execute(
                "UPDATE actions SET status=?, last_error=?, updated_at=? WHERE token=?",
                (status, err, now, token)
            )
            await self.conn.commit()


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
        self.lock = asyncio.Lock()

    async def start(self):
        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                raise RuntimeError("RELAYER_SESSION invalid. Yangi session oling.")
            return await self.client.get_me()
        except AuthKeyDuplicatedError:
            raise

    async def stop(self):
        await self.client.disconnect()

    @staticmethod
    def _clean_comment(s: Optional[str]) -> Optional[str]:
        if not s:
            return None
        t = s.strip().replace("\r", " ").replace("\n", " ")
        if not t:
            return None
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
        return True  => comment qo‘shildi
        return False => comment qabul qilinmadi, comment-siz yuborildi
        """
        async with self.lock:
            # can send?
            can = await self.client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.gift_id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")

            # resolve entity
            try:
                peer = await self.client.get_input_entity(target)
            except Exception:
                raise RuntimeError(
                    "Target topilmadi. Eng yaxshi yechim: @username ishlating.\n"
                    "Agar username yo‘q bo‘lsa, qabul qiluvchi relayerga 1 marta yozsin."
                )

            cleaned = self._clean_comment(comment)
            msg_obj = None
            if cleaned:
                msg_obj = types.TextWithEntities(text=cleaned, entities=[])

            extra = {}
            # NOTE: Telegram ba’zi holatlarda baribir nom ko‘rsatishi mumkin (Telegram cheklovi).
            if hide_name:
                extra["hide_name"] = True

            async def _try_send(message_obj):
                invoice = types.InputInvoiceStarGift(
                    peer=peer,
                    gift_id=gift.gift_id,
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
                # comment invalid bo‘lsa fallback
                if "STARGIFT_MESSAGE_INVALID" in str(e):
                    await _try_send(None)
                    return False
                raise


# =========================
# Bot UI helpers
# =========================
def kb_main(lang: str, anonymous: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Gift", callback_data="m:gift")
    kb.button(text="🎯 Target", callback_data="m:target")
    kb.button(text="💬 Comment", callback_data="m:comment")
    kb.button(
        text=(t(lang, "mode_anon") if anonymous == 1 else t(lang, "mode_profile")),
        callback_data="m:toggle"
    )
    kb.button(text="🌐 RU/UZ/EN", callback_data="m:lang")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def kb_lang() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="RU", callback_data="lang:ru")
    kb.button(text="UZ", callback_data="lang:uz")
    kb.button(text="EN", callback_data="lang:en")
    kb.button(text="⬅️", callback_data="m:home")
    kb.adjust(3, 1)
    return kb.as_markup()

def kb_prices(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in ALLOWED_PRICES:
        kb.button(text=f"⭐ {p}", callback_data=f"p:{p}")
    kb.button(text="⬅️", callback_data="m:home")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def kb_gifts(lang: str, price: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in GIFTS_BY_PRICE.get(price, []):
        # ID ko‘rsatmaymiz
        kb.button(text=f"{g.label}", callback_data=f"g:{g.gift_id}")
    kb.button(text="⬅️", callback_data="m:gift")
    kb.adjust(1)
    return kb.as_markup()

def kb_confirm(lang: str, token: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "confirm_send"), callback_data=f"a:send:{token}")
    kb.button(text=t(lang, "confirm_cancel"), callback_data=f"a:cancel:{token}")
    kb.adjust(1, 1)
    return kb.as_markup()


async def safe_edit(msg: Message, text: str, reply_markup: Optional[InlineKeyboardMarkup]):
    """
    Telegram: message is not modified xatosini yutib yuboradi.
    """
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise


# =========================
# Target parsing
# =========================
def normalize_target(raw: str) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    if s.startswith("@"):
        return s
    if s.isdigit():
        return s
    # "username" kelsa @ qo‘shamiz
    return "@" + s

def target_from_reply(reply: Message) -> Optional[str]:
    if not reply or not reply.from_user:
        return None
    if reply.from_user.username:
        return "@" + reply.from_user.username
    return str(reply.from_user.id)


# =========================
# App objects
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

db = DB(DB_PATH)
relayer = Relayer()

# Simple “waiting input” holatlari (yengil)
WAITING_COMMENT: set[int] = set()
WAITING_TARGET: set[int] = set()


# =========================
# Admin check wrappers
# =========================
async def require_admin(user_id: int) -> Tuple[bool, str, str]:
    ok, role = await db.is_admin(user_id)
    await db.ensure_settings(user_id)
    anon, comment, target, lang = await db.get_settings(user_id)
    if not ok:
        return False, role, lang
    return True, role, lang


# =========================
# Commands
# =========================
@dp.message(Command("start"))
async def cmd_start(m: Message):
    ok, role, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(lang, "access_denied"))

    anon, comment, target, lang = await db.get_settings(m.from_user.id)
    await m.answer(t(lang, "start"), reply_markup=kb_main(lang, anon))


@dp.message(Command("admins"))
async def cmd_admins(m: Message):
    ok, role, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(lang, "access_denied"))
    if role != "owner":
        return await m.answer(t(lang, "access_denied"))

    rows = await db.list_admins()
    lines = []
    for uid, r, active in rows:
        st = "✅" if active == 1 else "⛔"
        lines.append(f"{st} {uid} ({r})")
    await m.answer(t(lang, "admins_list", list="\n".join(lines) if lines else "-"))


@dp.message(Command("admin_add"))
async def cmd_admin_add(m: Message):
    ok, role, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(lang, "access_denied"))
    if role != "owner":
        return await m.answer(t(lang, "access_denied"))

    parts = (m.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await m.answer("Usage: /admin_add 123456789")
    uid = int(parts[1])
    await db.add_admin(uid, "admin")
    await m.answer(t(lang, "admin_added", uid=uid))


@dp.message(Command("admin_del"))
async def cmd_admin_del(m: Message):
    ok, role, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(lang, "access_denied"))
    if role != "owner":
        return await m.answer(t(lang, "access_denied"))

    parts = (m.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await m.answer("Usage: /admin_del 123456789")
    uid = int(parts[1])
    if uid == OWNER_ID:
        return await m.answer("Owner’ni o‘chira olmaysiz.")
    await db.remove_admin(uid)
    await m.answer(t(lang, "admin_removed", uid=uid))


@dp.message(Command("gift"))
async def cmd_gift(m: Message):
    """
    Guruhda reply qilib ishlatish oson:
    - odamga reply qiling -> /gift 50
    Yoki:
    - /gift @username 50
    """
    ok, role, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(lang, "access_denied"))

    await db.ensure_settings(m.from_user.id)
    anon, comment, target, lang = await db.get_settings(m.from_user.id)

    # /gift @user 50  yoki /gift 50 @user
    raw = (m.text or "").split()
    price = None
    explicit_target = None

    for token in raw[1:]:
        if token.isdigit() and int(token) in ALLOWED_PRICES:
            price = int(token)
        if token.startswith("@") or token.isdigit():
            # bu yerda “price” ham digit bo‘lishi mumkin, shuning uchun price bilan to‘qnashsa keyin tekshiramiz
            pass

    # explicit target qidiramiz
    # (price tokenini target deb qabul qilmaslik uchun)
    for token in raw[1:]:
        if price is not None and token.isdigit() and int(token) == price:
            continue
        if token.startswith("@") or (token.isdigit() and len(token) >= 5):
            explicit_target = normalize_target(token)
            break

    reply_target = target_from_reply(m.reply_to_message) if m.reply_to_message else None

    final_target = explicit_target or reply_target or target  # avval explicit, keyin reply, keyin saqlangan target
    if not final_target:
        return await m.answer(t(lang, "need_reply_or_target"))

    # targetni saqlab qo‘yamiz (keyin menu’dan ham ishlaydi)
    await db.set_target(m.from_user.id, final_target)

    # agar price berilgan bo‘lsa, shu narxni ochib yuboramiz; bo‘lmasa price menu
    if price:
        return await m.answer(t(lang, "choose_gift", price=price), reply_markup=kb_gifts(lang, price))
    return await m.answer(t(lang, "choose_price"), reply_markup=kb_prices(lang))


# =========================
# Menu callbacks
# =========================
@dp.callback_query(F.data.startswith("m:"))
async def cb_menu(c: CallbackQuery):
    ok, role, lang = await require_admin(c.from_user.id)
    if not ok:
        await c.answer(t(lang, "access_denied"), show_alert=True)
        return

    anon, comment, target, lang = await db.get_settings(c.from_user.id)
    action = c.data.split(":", 1)[1]

    await c.answer()

    if action == "home":
        WAITING_COMMENT.discard(c.from_user.id)
        WAITING_TARGET.discard(c.from_user.id)
        await safe_edit(c.message, t(lang, "start"), kb_main(lang, anon))
        return

    if action == "toggle":
        newv = await db.toggle_anonymous(c.from_user.id)
        anon, comment, target, lang = await db.get_settings(c.from_user.id)
        await safe_edit(c.message, t(lang, "start"), kb_main(lang, anon))
        return

    if action == "comment":
        WAITING_TARGET.discard(c.from_user.id)
        WAITING_COMMENT.add(c.from_user.id)
        await safe_edit(c.message, t(lang, "set_comment_tip"), None)
        return

    if action == "target":
        WAITING_COMMENT.discard(c.from_user.id)
        WAITING_TARGET.add(c.from_user.id)
        await safe_edit(c.message, t(lang, "set_target_tip"), None)
        return

    if action == "gift":
        WAITING_COMMENT.discard(c.from_user.id)
        WAITING_TARGET.discard(c.from_user.id)
        await safe_edit(c.message, t(lang, "choose_price"), kb_prices(lang))
        return

    if action == "lang":
        await safe_edit(c.message, "🌐 Choose language:", kb_lang())
        return


@dp.callback_query(F.data.startswith("lang:"))
async def cb_lang(c: CallbackQuery):
    ok, role, lang0 = await require_admin(c.from_user.id)
    if not ok:
        await c.answer(t(lang0, "access_denied"), show_alert=True)
        return
    await c.answer()
    lang = c.data.split(":", 1)[1]
    if lang not in ("ru", "uz", "en"):
        lang = "ru"
    await db.set_lang(c.from_user.id, lang)
    anon, comment, target, lang = await db.get_settings(c.from_user.id)
    await safe_edit(c.message, t(lang, "lang_set", lang=lang.upper()), kb_main(lang, anon))


# =========================
# Comment/Target input
# =========================
@dp.message()
async def any_text_input(m: Message):
    ok, role, lang = await require_admin(m.from_user.id)
    if not ok:
        return

    anon, comment, target, lang = await db.get_settings(m.from_user.id)

    if m.from_user.id in WAITING_COMMENT:
        WAITING_COMMENT.discard(m.from_user.id)
        raw = (m.text or "").strip()
        if raw == "-" or raw.lower() in ("off", "none", "null"):
            await db.set_comment(m.from_user.id, None)
        else:
            # max 250 (bot tarafida), relayerda 120
            await db.set_comment(m.from_user.id, raw[:250])
        anon, comment, target, lang = await db.get_settings(m.from_user.id)
        return await m.answer(t(lang, "start"), reply_markup=kb_main(lang, anon))

    if m.from_user.id in WAITING_TARGET:
        WAITING_TARGET.discard(m.from_user.id)
        trg = normalize_target(m.text or "")
        await db.set_target(m.from_user.id, trg)
        anon, comment, target, lang = await db.get_settings(m.from_user.id)
        return await m.answer(t(lang, "start"), reply_markup=kb_main(lang, anon))


# =========================
# Price/Gift selection
# =========================
@dp.callback_query(F.data.startswith("p:"))
async def cb_price(c: CallbackQuery):
    ok, role, lang = await require_admin(c.from_user.id)
    if not ok:
        await c.answer(t(lang, "access_denied"), show_alert=True)
        return
    await c.answer()
    anon, comment, target, lang = await db.get_settings(c.from_user.id)

    price = int(c.data.split(":", 1)[1])
    if price not in GIFTS_BY_PRICE:
        return await safe_edit(c.message, "No such price.", kb_prices(lang))
    await safe_edit(c.message, t(lang, "choose_gift", price=price), kb_gifts(lang, price))


@dp.callback_query(F.data.startswith("g:"))
async def cb_gift(c: CallbackQuery):
    ok, role, lang = await require_admin(c.from_user.id)
    if not ok:
        await c.answer(t(lang, "access_denied"), show_alert=True)
        return
    await c.answer()

    gift_id = int(c.data.split(":", 1)[1])
    gift = GIFTS_BY_ID.get(gift_id)
    if not gift:
        return await safe_edit(c.message, "Gift not found.", None)

    anon, comment, target, lang = await db.get_settings(c.from_user.id)
    if not target:
        return await safe_edit(c.message, t(lang, "need_reply_or_target"), None)

    # ACTION yaratamiz (token DB’da turadi => 2 marta bosib 2 marta yuborib bo‘lmaydi)
    token = secrets.token_urlsafe(8)
    # Confirm message shu chatda bo‘ladi
    confirm_text = (
        f"🎁 {gift.label}  ⭐{gift.stars}\n"
        f"🎯 {target}\n"
        f"🔒 {(t(lang, 'mode_anon') if anon == 1 else t(lang, 'mode_profile'))}\n"
        f"💬 {comment if comment else t(lang, 'comment_none')}\n\n"
        f"{t(lang, 'confirm_title')}"
    )

    # yangi message jo‘natamiz (edit qilish oson bo‘lishi uchun)
    msg = await c.message.answer(confirm_text, reply_markup=kb_confirm(lang, token))
    await db.create_action(
        token=token,
        creator_id=c.from_user.id,
        chat_id=msg.chat.id,
        msg_id=msg.message_id,
        target=target,
        gift_id=gift.gift_id,
        anonymous=anon,
        comment=comment,
    )


# =========================
# Confirm/Cancel
# =========================
@dp.callback_query(F.data.startswith("a:"))
async def cb_action(c: CallbackQuery):
    ok, role, lang = await require_admin(c.from_user.id)
    if not ok:
        await c.answer(t(lang, "access_denied"), show_alert=True)
        return

    await c.answer()

    parts = c.data.split(":")
    if len(parts) != 3:
        return
    kind, token = parts[1], parts[2]

    action = await db.get_action(token)
    if not action:
        return await c.answer("Missing / expired.", show_alert=True)

    # faqat creator tasdiqlaydi/bekor qiladi
    if int(action["creator_id"]) != c.from_user.id:
        return await c.answer(t(lang, "not_owner"), show_alert=True)

    anon, comment, target, lang = await db.get_settings(c.from_user.id)

    if kind == "cancel":
        if action["status"] in ("sent", "cancelled", "failed"):
            return await c.answer(t(lang, "already_done"), show_alert=True)
        await db.mark_action(token, "cancelled")
        # message "Cancelled" bo‘lsin va tugmalar ketadi
        try:
            await c.message.edit_text(t(lang, "cancelled"), reply_markup=None)
        except TelegramBadRequest:
            pass
        return

    if kind == "send":
        # CLAIM (pending -> sending) => double send yo‘q!
        ok_claim, why = await db.claim_action_sending(token, c.from_user.id)
        if not ok_claim:
            if why == "already":
                return await c.answer(t(lang, "already_done"), show_alert=True)
            if why == "not_owner":
                return await c.answer(t(lang, "not_owner"), show_alert=True)
            return await c.answer("Error.", show_alert=True)

        # UI: "Sending..."
        try:
            await c.message.edit_text(t(lang, "sending"), reply_markup=None)
        except TelegramBadRequest:
            pass

        try:
            gift = GIFTS_BY_ID.get(int(action["gift_id"]))
            if not gift:
                raise RuntimeError("Gift not found in catalog")

            target_str = str(action["target"])
            # Telethon target type
            if target_str.startswith("@"):
                target_t: Union[str, int] = target_str
            elif target_str.isdigit():
                target_t = int(target_str)
            else:
                target_t = target_str

            comment_txt = action["comment"]
            hide_name = int(action["anonymous"]) == 1

            comment_attached = await relayer.send_star_gift(
                target=target_t,
                gift=gift,
                comment=comment_txt,
                hide_name=hide_name,
            )

            await db.mark_action(token, "sent")

            # Final message
            done = t(lang, "sent")
            if comment_txt and not comment_attached:
                done += "\n⚠️ Komment qabul qilinmadi (comment-siz yuborildi)."

            try:
                await c.message.edit_text(done, reply_markup=None)
            except TelegramBadRequest:
                pass

        except Exception as e:
            err = str(e)
            await db.mark_action(token, "failed", err=err)
            try:
                await c.message.edit_text(t(lang, "failed", err=err), reply_markup=None)
            except TelegramBadRequest:
                pass


# =========================
# Inline mode (admin-only)
# Query format: "50 @username"
# =========================
@dp.inline_query()
async def inline_handler(q: InlineQuery):
    ok, role, lang = await require_admin(q.from_user.id)
    if not ok:
        # non-admin => empty
        await q.answer([], cache_time=1, is_personal=True)
        return

    anon, comment, target_saved, lang = await db.get_settings(q.from_user.id)

    text = (q.query or "").strip()
    if not text:
        # show hint
        hint = InlineQueryResultArticle(
            id="help",
            title=t(lang, "inline_usage"),
            input_message_content=InputTextMessageContent(
                message_text=t(lang, "inline_usage")
            )
        )
        await q.answer([hint], cache_time=1, is_personal=True)
        return

    parts = text.split()
    if len(parts) < 2:
        hint = InlineQueryResultArticle(
            id="help2",
            title=t(lang, "inline_usage"),
            input_message_content=InputTextMessageContent(
                message_text=t(lang, "inline_usage")
            )
        )
        await q.answer([hint], cache_time=1, is_personal=True)
        return

    # first: price, second: target
    try:
        price = int(parts[0])
    except ValueError:
        await q.answer([], cache_time=1, is_personal=True)
        return

    if price not in GIFTS_BY_PRICE:
        await q.answer([], cache_time=1, is_personal=True)
        return

    trg = normalize_target(parts[1])
    if not trg:
        await q.answer([], cache_time=1, is_personal=True)
        return

    results = []
    for g in GIFTS_BY_PRICE[price]:
        token = secrets.token_urlsafe(8)

        # Inline message ichida confirm/cancel bo‘ladi
        msg_text = (
            f"🎁 {g.label}  ⭐{g.stars}\n"
            f"🎯 {trg}\n"
            f"🔒 {(t(lang, 'mode_anon') if anon == 1 else t(lang, 'mode_profile'))}\n"
            f"💬 {comment if comment else t(lang, 'comment_none')}\n\n"
            f"{t(lang, 'confirm_title')}"
        )

        # NOTE: Inline result tanlanganda message chatga tushadi,
        # callback bosilganda biz actionni DB’dan topishimiz uchun token kerak.
        # Lekin inline tanlanmasidan oldin message_id yo‘q.
        # Shuning uchun: inline message tushgach callback bosilganda biz token bo‘yicha action yo‘q bo‘lishi mumkin.
        # Yechim: inline message “send/cancel” bosilganda, agar action yo‘q bo‘lsa, uni o‘sha paytda yaratamiz.
        #
        # Buning uchun callback_data ichiga kerakli minimal datani joylaymiz:
        # token|gift_id|anon|target
        pack = {
            "tok": token,
            "gid": g.gift_id,
            "an": anon,
            "t": trg,
        }
        payload = json.dumps(pack, separators=(",", ":"))
        # callback_data 64 bayt limit: json ba’zida uzun bo‘lishi mumkin,
        # shu sabab: uni qisqartirish uchun base64 emas, lekin juda kichik saqlaymiz.
        # Agar username juda uzun bo‘lsa ham limitdan oshmasligi uchun:
        # trg Telegram username max 32 => json hali ham odatda sig‘adi.
        cb_send = f"i:send:{payload}"
        cb_cancel = f"i:cancel:{payload}"

        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "confirm_send"), callback_data=cb_send[:64])
        kb.button(text=t(lang, "confirm_cancel"), callback_data=cb_cancel[:64])
        kb.adjust(1, 1)

        results.append(
            InlineQueryResultArticle(
                id=f"g{g.gift_id}",
                title=f"{g.label} (⭐{g.stars})",
                description=t(lang, "inline_pick"),
                input_message_content=InputTextMessageContent(message_text=msg_text),
                reply_markup=kb.as_markup()
            )
        )

    await q.answer(results, cache_time=1, is_personal=True)


@dp.callback_query(F.data.startswith("i:"))
async def inline_action_callback(c: CallbackQuery):
    ok, role, lang = await require_admin(c.from_user.id)
    if not ok:
        await c.answer(t(lang, "access_denied"), show_alert=True)
        return

    parts = c.data.split(":", 2)
    if len(parts) != 3:
        return
    kind = parts[1]
    raw = parts[2]

    # raw JSON bo‘lishi kerak (kesilib qolgan bo‘lsa ishlamaydi)
    try:
        pack = json.loads(raw)
    except Exception:
        await c.answer("Bad inline data.", show_alert=True)
        return

    token = pack.get("tok")
    gid = int(pack.get("gid"))
    trg = str(pack.get("t"))
    an = int(pack.get("an") or 0)

    await db.ensure_settings(c.from_user.id)
    anon, comment, target_saved, lang = await db.get_settings(c.from_user.id)

    # Inline’da ham faqat creator bosishi kerak:
    # Inline message kim yuborgan bo‘lsa, callbackni ham o‘sha admin bosadi deb hisoblaymiz.
    # (Boshqa admin bosgan bo‘lsa ham, bu yerda uni to‘xtatamiz.)
    # Action DB’da yo‘q bo‘lsa, uni endi yaratamiz (message_id bor).
    existing = await db.get_action(token)

    if kind == "cancel":
        if existing:
            if int(existing["creator_id"]) != c.from_user.id:
                return await c.answer(t(lang, "not_owner"), show_alert=True)
            if existing["status"] in ("sent", "cancelled", "failed"):
                return await c.answer(t(lang, "already_done"), show_alert=True)
            await db.mark_action(token, "cancelled")
        try:
            await c.message.edit_text(t(lang, "cancelled"), reply_markup=None)
        except TelegramBadRequest:
            pass
        return

    if kind == "send":
        if not existing:
            # yaratamiz
            await db.create_action(
                token=token,
                creator_id=c.from_user.id,
                chat_id=c.message.chat.id,
                msg_id=c.message.message_id,
                target=trg,
                gift_id=gid,
                anonymous=an,
                comment=comment,
            )
            existing = await db.get_action(token)

        # owner check + claim
        if int(existing["creator_id"]) != c.from_user.id:
            return await c.answer(t(lang, "not_owner"), show_alert=True)

        ok_claim, why = await db.claim_action_sending(token, c.from_user.id)
        if not ok_claim:
            if why == "already":
                return await c.answer(t(lang, "already_done"), show_alert=True)
            return await c.answer("Error.", show_alert=True)

        try:
            await c.message.edit_text(t(lang, "sending"), reply_markup=None)
        except TelegramBadRequest:
            pass

        try:
            gift = GIFTS_BY_ID.get(gid)
            if not gift:
                raise RuntimeError("Gift not found")

            # target resolve
            target_str = trg
            if target_str.startswith("@"):
                target_t: Union[str, int] = target_str
            elif target_str.isdigit():
                target_t = int(target_str)
            else:
                target_t = target_str

            comment_attached = await relayer.send_star_gift(
                target=target_t,
                gift=gift,
                comment=comment,
                hide_name=(an == 1),
            )
            await db.mark_action(token, "sent")

            done = t(lang, "sent")
            if comment and not comment_attached:
                done += "\n⚠️ Komment qabul qilinmadi (comment-siz yuborildi)."
            try:
                await c.message.edit_text(done, reply_markup=None)
            except TelegramBadRequest:
                pass

        except Exception as e:
            err = str(e)
            await db.mark_action(token, "failed", err=err)
            try:
                await c.message.edit_text(t(lang, "failed", err=err), reply_markup=None)
            except TelegramBadRequest:
                pass


# =========================
# Main
# =========================
async def main():
    log.info("BOOT: starting...")
    await db.start()
    log.info("BOOT: db OK")

    try:
        me = await relayer.start()
        log.info("Relayer OK | id=%s username=%s", getattr(me, "id", None), getattr(me, "username", None))
    except AuthKeyDuplicatedError:
        log.error("RELAYER_SESSION DUPLICATED! Bu session 2ta IP’da ishlatilgan va endi o‘lgan. YANGI session oling va faqat 1 joyda ishlating.")
        raise

    log.info("BOOT: polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await relayer.stop()
        await db.stop()

if __name__ == "__main__":
    asyncio.run(main())
