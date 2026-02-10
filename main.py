import os
import time
import json
import uuid
import asyncio
import logging
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
from contextlib import asynccontextmanager

import aiosqlite
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import RPCError


# =========================
# ENV + Logging
# =========================
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("giftbot")


def env_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


BOT_TOKEN = env_required("BOT_TOKEN")
TG_API_ID = int(env_required("TG_API_ID"))
TG_API_HASH = env_required("TG_API_HASH")

# Global fallback relayer (optional but recommended)
DEFAULT_RELAYER_SESSION = os.getenv("RELAYER_SESSION", "").strip()

DB_PATH = os.getenv("DB_PATH", "bot.db")

# Owner (main admin)
OWNER_ID = int(os.getenv("OWNER_ID", "7440949683"))

# Web/hosting keep-alive (optional)
PORT = int(os.getenv("PORT", "8080"))
WEB_BIND = os.getenv("WEB_BIND", "0.0.0.0")

# Inline context TTL
INLINE_CTX_TTL_SEC = int(os.getenv("INLINE_CTX_TTL_SEC", "600"))

# Default language for everyone (you asked RU)
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "ru").lower().strip()


# =========================
# Gifts catalog (STATIC)
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

GIFTS_BY_ID: Dict[int, GiftItem] = {g.id: g for g in GIFT_CATALOG}


# =========================
# i18n (UZ/RU/EN)
# =========================
T = {
    "ru": {
        "access_denied": "⛔ Доступ запрещён.\nЭтот бот только для админов.",
        "start_admin": "✅ Доступ разрешён.\n\nИспользование inline:\n`@{bot} 50 @username | комментарий | anon/show`\n\nПример:\n`@{bot} 50 @vremenniy_uzer | :) | anon`",
        "help": (
            "🛠 Команды:\n"
            "/admin_add <id|@user> — добавить админа (owner)\n"
            "/admin_remove <id|@user> — отключить админа (owner)\n"
            "/admin_list — список админов\n"
            "/session_set <SESSION_STRING> — сохранить вашу сессию (relayer)\n"
            "/session_clear — убрать вашу сессию\n"
            "/lang <ru|uz|en> — язык\n"
            "/set_target <me|@user|id> — дефолтный получатель\n"
            "/set_comment <text|off> — дефолтный комментарий\n"
            "/mode <anon|show> — дефолтный режим\n"
        ),
        "need_session": "❌ У вас нет relayer-сессии. Используйте /session_set <SESSION_STRING> (QR-сессия).",
        "owner_only": "❌ Только owner может это делать.",
        "admin_added": "✅ Админ добавлен: {uid}",
        "admin_removed": "✅ Админ отключён: {uid}",
        "admin_list": "👮 Админы:\n{rows}",
        "session_saved": "✅ Сессия сохранена.",
        "session_cleared": "✅ Сессия удалена.",
        "lang_set": "✅ Язык: {lang}",
        "target_set": "✅ Получатель по умолчанию: {target}",
        "comment_set": "✅ Комментарий по умолчанию сохранён.",
        "comment_cleared": "✅ Комментарий удалён.",
        "mode_set": "✅ Режим по умолчанию: {mode}",
        "inline_bad": "Напишите так: `@{bot} 50 @username | comment | anon/show`",
        "inline_need_target": "⚠️ Нет получателя. Укажите `@username` или задайте /set_target",
        "inline_title": "{label} (⭐{stars})",
        "inline_desc": "Кому: {target} | Режим: {mode}",
        "msg_preview": "🎁 Подарок: {label} (⭐{stars})\n👤 Кому: {target}\n🔒 Режим: {mode}\n💬 Коммент: {comment}",
        "btn_send": "✅ Отправить",
        "btn_cancel": "❌ Отмена",
        "btn_toggle": "🕵️/👤 Режим",
        "sending": "⏳ Отправляю...",
        "sent": "✅ Отправлено!",
        "cancelled": "❌ Отменено.",
        "already_done": "⚠️ Уже обработано (повторно нельзя).",
        "fail": "❌ Ошибка: {e}",
        "note_anon": "ℹ️ Важно: hide_name может скрывать имя в деталях подарка, но Telegram всё равно может показывать отправителя в чате.",
    },
    "uz": {
        "access_denied": "⛔ Ruxsat yo‘q.\nBu bot faqat adminlar uchun.",
        "start_admin": "✅ Ruxsat bor.\n\nInline ishlatish:\n`@{bot} 50 @username | komment | anon/show`\n\nMisol:\n`@{bot} 50 @vremenniy_uzer | :) | anon`",
        "help": (
            "🛠 Buyruqlar:\n"
            "/admin_add <id|@user> — admin qo‘shish (owner)\n"
            "/admin_remove <id|@user> — adminni o‘chirish (owner)\n"
            "/admin_list — adminlar ro‘yxati\n"
            "/session_set <SESSION_STRING> — relayer sessiya saqlash\n"
            "/session_clear — sessiyani o‘chirish\n"
            "/lang <ru|uz|en> — til\n"
            "/set_target <me|@user|id> — default qabul qiluvchi\n"
            "/set_comment <text|off> — default komment\n"
            "/mode <anon|show> — default rejim\n"
        ),
        "need_session": "❌ Sizda relayer sessiya yo‘q. /session_set <SESSION_STRING> qiling (QR sessiya).",
        "owner_only": "❌ Faqat owner qila oladi.",
        "admin_added": "✅ Admin qo‘shildi: {uid}",
        "admin_removed": "✅ Admin o‘chirildi: {uid}",
        "admin_list": "👮 Adminlar:\n{rows}",
        "session_saved": "✅ Sessiya saqlandi.",
        "session_cleared": "✅ Sessiya o‘chirildi.",
        "lang_set": "✅ Til: {lang}",
        "target_set": "✅ Default target: {target}",
        "comment_set": "✅ Default komment saqlandi.",
        "comment_cleared": "✅ Komment o‘chirildi.",
        "mode_set": "✅ Default rejim: {mode}",
        "inline_bad": "Shunday yozing: `@{bot} 50 @username | comment | anon/show`",
        "inline_need_target": "⚠️ Target yo‘q. `@username` yozing yoki /set_target qo‘ying",
        "inline_title": "{label} (⭐{stars})",
        "inline_desc": "Kimga: {target} | Rejim: {mode}",
        "msg_preview": "🎁 Sovg‘a: {label} (⭐{stars})\n👤 Kimga: {target}\n🔒 Rejim: {mode}\n💬 Komment: {comment}",
        "btn_send": "✅ Yuborish",
        "btn_cancel": "❌ Bekor",
        "btn_toggle": "🕵️/👤 Rejim",
        "sending": "⏳ Yuborilyapti...",
        "sent": "✅ Yuborildi!",
        "cancelled": "❌ Bekor qilindi.",
        "already_done": "⚠️ Oldin ishlangan (qayta bo‘lmaydi).",
        "fail": "❌ Xatolik: {e}",
        "note_anon": "ℹ️ Eslatma: hide_name gift detail’da ismni yashirishi mumkin, lekin chatda Telegram baribir yuboruvchini ko‘rsatishi mumkin.",
    },
    "en": {
        "access_denied": "⛔ Access denied. Admin-only bot.",
        "start_admin": "✅ Access granted.\n\nInline usage:\n`@{bot} 50 @username | comment | anon/show`\n\nExample:\n`@{bot} 50 @vremenniy_uzer | :) | anon`",
        "help": (
            "🛠 Commands:\n"
            "/admin_add <id|@user> — add admin (owner)\n"
            "/admin_remove <id|@user> — disable admin (owner)\n"
            "/admin_list — list admins\n"
            "/session_set <SESSION_STRING> — save your relayer session\n"
            "/session_clear — remove your session\n"
            "/lang <ru|uz|en> — language\n"
            "/set_target <me|@user|id> — default receiver\n"
            "/set_comment <text|off> — default comment\n"
            "/mode <anon|show> — default mode\n"
        ),
        "need_session": "❌ You have no relayer session. Use /session_set <SESSION_STRING> (QR session).",
        "owner_only": "❌ Owner-only.",
        "admin_added": "✅ Admin added: {uid}",
        "admin_removed": "✅ Admin disabled: {uid}",
        "admin_list": "👮 Admins:\n{rows}",
        "session_saved": "✅ Session saved.",
        "session_cleared": "✅ Session cleared.",
        "lang_set": "✅ Language: {lang}",
        "target_set": "✅ Default target: {target}",
        "comment_set": "✅ Default comment saved.",
        "comment_cleared": "✅ Comment cleared.",
        "mode_set": "✅ Default mode: {mode}",
        "inline_bad": "Use: `@{bot} 50 @username | comment | anon/show`",
        "inline_need_target": "⚠️ Missing target. Provide `@username` or set /set_target",
        "inline_title": "{label} (⭐{stars})",
        "inline_desc": "To: {target} | Mode: {mode}",
        "msg_preview": "🎁 Gift: {label} (⭐{stars})\n👤 To: {target}\n🔒 Mode: {mode}\n💬 Comment: {comment}",
        "btn_send": "✅ Send",
        "btn_cancel": "❌ Cancel",
        "btn_toggle": "🕵️/👤 Mode",
        "sending": "⏳ Sending...",
        "sent": "✅ Sent!",
        "cancelled": "❌ Cancelled.",
        "already_done": "⚠️ Already processed (no duplicate).",
        "fail": "❌ Error: {e}",
        "note_anon": "ℹ️ Note: hide_name may hide your name in gift details, but Telegram can still show the sender in chat.",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    lang = (lang or DEFAULT_LANG).lower()
    pack = T.get(lang, T["ru"])
    s = pack.get(key, T["ru"].get(key, key))
    return s.format(**kwargs)


# =========================
# DB
# =========================
@asynccontextmanager
async def db_connect():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute("PRAGMA busy_timeout=5000;")
        yield db


async def db_init():
    async with db_connect() as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            role TEXT NOT NULL DEFAULT 'admin', -- owner|admin
            is_active INTEGER NOT NULL DEFAULT 1,
            added_by INTEGER,
            added_at INTEGER NOT NULL
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS admin_prefs (
            user_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT NULL,
            default_target TEXT DEFAULT NULL,
            default_comment TEXT DEFAULT NULL,
            default_anonymous INTEGER NOT NULL DEFAULT 0
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            user_id INTEGER PRIMARY KEY,
            session_string TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at INTEGER NOT NULL
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS inline_ctx (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            target TEXT NOT NULL,
            comment TEXT DEFAULT NULL,
            anonymous INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS sent_guard (
            message_key TEXT PRIMARY KEY,
            created_at INTEGER NOT NULL
        );
        """)
        await db.commit()

    # ensure owner exists
    await db_ensure_owner()


async def db_ensure_owner():
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
            INSERT OR IGNORE INTO admins(user_id, role, is_active, added_by, added_at)
            VALUES(?, 'owner', 1, NULL, ?)
        """, (OWNER_ID, now))
        await db.execute("""
            INSERT OR IGNORE INTO admin_prefs(user_id, lang, default_target, default_comment, default_anonymous)
            VALUES(?, ?, NULL, NULL, 0)
        """, (OWNER_ID, DEFAULT_LANG))
        await db.commit()


async def db_is_admin(user_id: int) -> Tuple[bool, str]:
    async with db_connect() as db:
        cur = await db.execute("SELECT role, is_active FROM admins WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return False, "none"
        role, is_active = row[0], int(row[1])
        return (is_active == 1), (role or "admin")


async def db_add_admin(by_user: int, user_id: int):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
            INSERT OR REPLACE INTO admins(user_id, role, is_active, added_by, added_at)
            VALUES(?, 'admin', 1, ?, ?)
        """, (user_id, by_user, now))
        await db.execute("""
            INSERT OR IGNORE INTO admin_prefs(user_id, lang, default_target, default_comment, default_anonymous)
            VALUES(?, ?, NULL, NULL, 0)
        """, (user_id, DEFAULT_LANG))
        await db.commit()


async def db_remove_admin(user_id: int):
    async with db_connect() as db:
        await db.execute("UPDATE admins SET is_active=0 WHERE user_id=? AND role!='owner'", (user_id,))
        await db.commit()


async def db_list_admins() -> List[Tuple[int, str, int]]:
    async with db_connect() as db:
        cur = await db.execute("SELECT user_id, role, is_active FROM admins ORDER BY role DESC, user_id ASC")
        rows = await cur.fetchall()
        return [(int(r[0]), r[1], int(r[2])) for r in rows]


async def db_get_prefs(user_id: int) -> Tuple[str, Optional[str], Optional[str], int]:
    async with db_connect() as db:
        cur = await db.execute("""
            SELECT lang, default_target, default_comment, default_anonymous
            FROM admin_prefs
            WHERE user_id=?
        """, (user_id,))
        row = await cur.fetchone()
        if not row:
            return DEFAULT_LANG, None, None, 0
        return (row[0] or DEFAULT_LANG, row[1], row[2], int(row[3] or 0))


async def db_set_lang(user_id: int, lang: str):
    async with db_connect() as db:
        await db.execute("UPDATE admin_prefs SET lang=? WHERE user_id=?", (lang, user_id))
        await db.commit()


async def db_set_target(user_id: int, target: Optional[str]):
    async with db_connect() as db:
        await db.execute("UPDATE admin_prefs SET default_target=? WHERE user_id=?", (target, user_id))
        await db.commit()


async def db_set_comment(user_id: int, comment: Optional[str]):
    async with db_connect() as db:
        await db.execute("UPDATE admin_prefs SET default_comment=? WHERE user_id=?", (comment, user_id))
        await db.commit()


async def db_set_mode(user_id: int, anonymous: int):
    async with db_connect() as db:
        await db.execute("UPDATE admin_prefs SET default_anonymous=? WHERE user_id=?", (anonymous, user_id))
        await db.commit()


async def db_set_session(user_id: int, session_string: str):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
            INSERT OR REPLACE INTO admin_sessions(user_id, session_string, enabled, updated_at)
            VALUES(?, ?, 1, ?)
        """, (user_id, session_string.strip(), now))
        await db.commit()


async def db_clear_session(user_id: int):
    async with db_connect() as db:
        await db.execute("DELETE FROM admin_sessions WHERE user_id=?", (user_id,))
        await db.commit()


async def db_get_session(user_id: int) -> Optional[str]:
    async with db_connect() as db:
        cur = await db.execute("SELECT session_string, enabled FROM admin_sessions WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return None
        if int(row[1]) != 1:
            return None
        return row[0]


async def db_put_inline_ctx(token: str, user_id: int, target: str, comment: Optional[str], anonymous: int):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
            INSERT OR REPLACE INTO inline_ctx(token, user_id, target, comment, anonymous, created_at)
            VALUES(?,?,?,?,?,?)
        """, (token, user_id, target, comment, int(anonymous), now))
        await db.commit()


async def db_get_inline_ctx(token: str) -> Optional[dict]:
    async with db_connect() as db:
        cur = await db.execute("""
            SELECT token, user_id, target, comment, anonymous, created_at
            FROM inline_ctx WHERE token=?
        """, (token,))
        row = await cur.fetchone()
        if not row:
            return None
        return {
            "token": row[0],
            "user_id": int(row[1]),
            "target": row[2],
            "comment": row[3],
            "anonymous": int(row[4]),
            "created_at": int(row[5]),
        }


async def db_update_inline_mode(token: str, anonymous: int):
    async with db_connect() as db:
        await db.execute("UPDATE inline_ctx SET anonymous=? WHERE token=?", (int(anonymous), token))
        await db.commit()


async def db_cleanup_inline_ctx():
    cutoff = int(time.time()) - INLINE_CTX_TTL_SEC
    async with db_connect() as db:
        await db.execute("DELETE FROM inline_ctx WHERE created_at < ?", (cutoff,))
        await db.commit()


async def db_guard_once(message_key: str) -> bool:
    now = int(time.time())
    try:
        async with db_connect() as db:
            await db.execute("INSERT INTO sent_guard(message_key, created_at) VALUES(?,?)", (message_key, now))
            await db.commit()
        return True
    except Exception:
        return False


# =========================
# Helpers
# =========================
def normalize_target(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    if s.lower() == "me":
        return "me"
    if s.startswith("@"):
        return s
    if s.isdigit():
        return s
    return "@" + s


def clean_comment(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip().replace("\r", " ").replace("\n", " ")
    if not s:
        return None
    if len(s) > 120:
        s = s[:120]
    return s


def mode_text(lang: str, anonymous: int) -> str:
    if (anonymous or 0) == 1:
        return "anon" if lang == "en" else ("anon" if lang == "ru" else "anon")
    return "show" if lang == "en" else ("show" if lang == "ru" else "show")


def parse_inline_query(q: str, prefs_target: Optional[str], prefs_comment: Optional[str], prefs_anon: int):
    """
    Format:
      "<max_stars> [target] | comment | anon/show"
    Examples:
      "50"
      "50 @user"
      "50 @user | :)"
      "50 @user | hello | anon"
      "50 | hi | show"   (uses default target)
    """
    q = (q or "").strip()
    if not q:
        return None

    parts = [p.strip() for p in q.split("|")]
    head = parts[0]
    head_tokens = head.split()
    if not head_tokens or not head_tokens[0].isdigit():
        return None

    max_stars = int(head_tokens[0])
    target = None
    if len(head_tokens) >= 2:
        target = normalize_target(head_tokens[1])

    comment = None
    if len(parts) >= 2:
        comment = clean_comment(parts[1])
    if comment is None:
        comment = clean_comment(prefs_comment)

    mode = None
    if len(parts) >= 3:
        mode = parts[2].strip().lower()

    anonymous = prefs_anon
    if mode in ("anon", "anonymous", "hide"):
        anonymous = 1
    elif mode in ("show", "profile", "name"):
        anonymous = 0

    if target is None:
        target = normalize_target(prefs_target)

    return max_stars, target, comment, anonymous


def make_inline_token(user_id: int) -> str:
    # short token
    rnd = uuid.uuid4().hex[:10]
    return f"{user_id:x}{rnd}"


# =========================
# Telethon relayer pool
# =========================
class RelayerPool:
    def __init__(self):
        self._clients: Dict[str, TelegramClient] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._start_lock = asyncio.Lock()

    @staticmethod
    def _key(session_string: str) -> str:
        h = hashlib.sha256(session_string.encode("utf-8")).hexdigest()
        return h[:16]

    async def _get_client(self, session_string: str) -> TelegramClient:
        k = self._key(session_string)
        if k in self._clients:
            return self._clients[k]

        async with self._start_lock:
            if k in self._clients:
                return self._clients[k]

            client = TelegramClient(
                StringSession(session_string),
                TG_API_ID,
                TG_API_HASH,
                timeout=25,
                connection_retries=5,
                retry_delay=2,
                auto_reconnect=True,
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                raise RuntimeError("Session invalid / expired. Re-generate SESSION_STRING.")
            self._clients[k] = client
            self._locks[k] = asyncio.Lock()
            return client

    async def send_star_gift(
        self,
        *,
        session_string: str,
        target: Union[str, int],
        gift: GiftItem,
        comment: Optional[str],
        hide_name: bool,
    ) -> bool:
        client = await self._get_client(session_string)
        k = self._key(session_string)
        lock = self._locks[k]

        async with lock:
            can = await client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")

            try:
                peer = await client.get_input_entity(target)
            except Exception:
                if isinstance(target, int):
                    raise RuntimeError(
                        "user_id orqali entity topilmadi. Eng yaxshisi @username ishlating "
                        "(yoki qabul qiluvchi relayerga 1 marta yozsin)."
                    )
                raise

            cleaned = clean_comment(comment)
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
                form = await client(functions.payments.GetPaymentFormRequest(invoice=invoice))
                await client(functions.payments.SendStarsFormRequest(form_id=form.form_id, invoice=invoice))

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

    async def stop_all(self):
        for c in list(self._clients.values()):
            try:
                await c.disconnect()
            except Exception:
                pass
        self._clients.clear()
        self._locks.clear()


# =========================
# Bot + UI
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
pool = RelayerPool()


def inline_kb(lang: str, token: str, gift_id: int, anonymous: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_send"), callback_data=f"act:send:{token}:{gift_id}")
    kb.button(text=t(lang, "btn_toggle"), callback_data=f"act:toggle:{token}:{gift_id}")
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"act:cancel:{token}:{gift_id}")
    kb.adjust(1, 2)
    return kb.as_markup()


async def safe_edit_inline(callback: CallbackQuery, text: str, reply_markup: Optional[InlineKeyboardMarkup]):
    try:
        if callback.inline_message_id:
            await bot.edit_message_text(
                inline_message_id=callback.inline_message_id,
                text=text,
                reply_markup=reply_markup,
            )
        else:
            await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        # Fix: "message is not modified"
        if "message is not modified" in str(e).lower():
            return
        raise


async def require_admin(user_id: int) -> Tuple[bool, str, str]:
    ok, role = await db_is_admin(user_id)
    lang, _, _, _ = await db_get_prefs(user_id)
    return ok, role, lang


def resolve_target_for_send(target: str, from_user: Message) -> Union[str, int]:
    # target is stored as "me" or "@x" or digits
    if target == "me":
        if from_user.from_user.username:
            return "@" + from_user.from_user.username
        return int(from_user.from_user.id)
    if target.startswith("@"):
        return target
    if target.isdigit():
        return int(target)
    return target


# =========================
# Commands (admin-only)
# =========================
@dp.message(Command("start"))
async def cmd_start(m: Message):
    ok, _, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(DEFAULT_LANG, "access_denied"))

    await db_cleanup_inline_ctx()
    await m.answer(t(lang, "start_admin", bot=(await bot.get_me()).username))


@dp.message(Command("help"))
async def cmd_help(m: Message):
    ok, _, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(DEFAULT_LANG, "access_denied"))
    await m.answer(t(lang, "help"))


@dp.message(Command("lang"))
async def cmd_lang(m: Message):
    ok, _, _ = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(DEFAULT_LANG, "access_denied"))
    parts = (m.text or "").split()
    if len(parts) < 2:
        lang, _, _, _ = await db_get_prefs(m.from_user.id)
        return await m.answer(f"lang={lang} (ru|uz|en)")
    new_lang = parts[1].lower().strip()
    if new_lang not in ("ru", "uz", "en"):
        return await m.answer("ru|uz|en")
    await db_set_lang(m.from_user.id, new_lang)
    await m.answer(t(new_lang, "lang_set", lang=new_lang))


@dp.message(Command("set_target"))
async def cmd_set_target(m: Message):
    ok, _, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(DEFAULT_LANG, "access_denied"))
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await m.answer("Usage: /set_target me | @username | user_id")
    target = normalize_target(parts[1])
    await db_set_target(m.from_user.id, target)
    await m.answer(t(lang, "target_set", target=target))


@dp.message(Command("set_comment"))
async def cmd_set_comment(m: Message):
    ok, _, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(DEFAULT_LANG, "access_denied"))
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await m.answer("Usage: /set_comment off | текст")
    raw = parts[1].strip()
    if raw.lower() in ("off", "none", "-"):
        await db_set_comment(m.from_user.id, None)
        return await m.answer(t(lang, "comment_cleared"))
    await db_set_comment(m.from_user.id, clean_comment(raw))
    await m.answer(t(lang, "comment_set"))


@dp.message(Command("mode"))
async def cmd_mode(m: Message):
    ok, _, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(DEFAULT_LANG, "access_denied"))
    parts = (m.text or "").split()
    if len(parts) < 2:
        _, _, _, anon = await db_get_prefs(m.from_user.id)
        return await m.answer(f"mode={'anon' if anon==1 else 'show'} (anon|show)")
    v = parts[1].lower().strip()
    if v not in ("anon", "show"):
        return await m.answer("anon|show")
    await db_set_mode(m.from_user.id, 1 if v == "anon" else 0)
    await m.answer(t(lang, "mode_set", mode=v))


@dp.message(Command("session_set"))
async def cmd_session_set(m: Message):
    ok, _, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(DEFAULT_LANG, "access_denied"))
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await m.answer("Usage: /session_set <SESSION_STRING>")
    session_string = parts[1].strip()

    # Quick sanity check: try connect
    try:
        # will raise if invalid
        await pool._get_client(session_string)
    except Exception as e:
        return await m.answer(t(lang, "fail", e=str(e)))

    await db_set_session(m.from_user.id, session_string)
    await m.answer(t(lang, "session_saved"))


@dp.message(Command("session_clear"))
async def cmd_session_clear(m: Message):
    ok, _, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(DEFAULT_LANG, "access_denied"))
    await db_clear_session(m.from_user.id)
    await m.answer(t(lang, "session_cleared"))


@dp.message(Command("admin_add"))
async def cmd_admin_add(m: Message):
    ok, role, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(DEFAULT_LANG, "access_denied"))
    if role != "owner":
        return await m.answer(t(lang, "owner_only"))

    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await m.answer("Usage: /admin_add <user_id>")
    raw = parts[1].strip()
    if raw.startswith("@"):
        # bots can't reliably resolve user_id by username unless user interacted.
        return await m.answer("❌ @username bo‘yicha qo‘shish uchun user_id kerak. Masalan: /admin_add 123456789")
    if not raw.isdigit():
        return await m.answer("user_id (digits) required")
    uid = int(raw)

    await db_add_admin(m.from_user.id, uid)
    await m.answer(t(lang, "admin_added", uid=uid))


@dp.message(Command("admin_remove"))
async def cmd_admin_remove(m: Message):
    ok, role, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(DEFAULT_LANG, "access_denied"))
    if role != "owner":
        return await m.answer(t(lang, "owner_only"))

    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await m.answer("Usage: /admin_remove <user_id>")
    raw = parts[1].strip()
    if not raw.isdigit():
        return await m.answer("user_id (digits) required")
    uid = int(raw)

    await db_remove_admin(uid)
    await m.answer(t(lang, "admin_removed", uid=uid))


@dp.message(Command("admin_list"))
async def cmd_admin_list(m: Message):
    ok, _, lang = await require_admin(m.from_user.id)
    if not ok:
        return await m.answer(t(DEFAULT_LANG, "access_denied"))
    rows = await db_list_admins()
    lines = []
    for uid, role, active in rows:
        lines.append(f"- {uid} | {role} | {'ON' if active==1 else 'OFF'}")
    await m.answer(t(lang, "admin_list", rows="\n".join(lines)))


# =========================
# Inline mode
# =========================
@dp.inline_query()
async def inline_handler(q: InlineQuery):
    ok, _, lang = await require_admin(q.from_user.id)
    if not ok:
        return await q.answer([], is_personal=True, cache_time=1)

    bot_me = await bot.get_me()
    bot_username = bot_me.username or "YourBot"

    prefs_lang, prefs_target, prefs_comment, prefs_anon = await db_get_prefs(q.from_user.id)

    parsed = parse_inline_query(q.query, prefs_target, prefs_comment, prefs_anon)
    if not parsed:
        hint = t(prefs_lang, "inline_bad", bot=bot_username)
        res = InlineQueryResultArticle(
            id="help",
            title="Usage",
            description=hint,
            input_message_content=InputTextMessageContent(message_text=hint),
        )
        return await q.answer([res], is_personal=True, cache_time=1)

    max_stars, target, comment, anonymous = parsed
    if not target:
        hint = t(prefs_lang, "inline_need_target", bot=bot_username)
        res = InlineQueryResultArticle(
            id="need_target",
            title="Target required",
            description=hint,
            input_message_content=InputTextMessageContent(message_text=hint),
        )
        return await q.answer([res], is_personal=True, cache_time=1)

    token = make_inline_token(q.from_user.id)
    await db_put_inline_ctx(token, q.from_user.id, target, comment, anonymous)

    gifts = [g for g in GIFT_CATALOG if g.stars <= max_stars]
    if not gifts:
        res = InlineQueryResultArticle(
            id="none",
            title="No gifts",
            description=f"<= {max_stars}★ not found",
            input_message_content=InputTextMessageContent(message_text="No gifts for this price."),
        )
        return await q.answer([res], is_personal=True, cache_time=1)

    results = []
    comment_text = comment if comment else "(none)" if prefs_lang == "en" else ("(yo‘q)" if prefs_lang == "uz" else "(нет)")
    mode = "anon" if anonymous == 1 else "show"

    for g in gifts[:30]:
        title = t(prefs_lang, "inline_title", label=g.label, stars=g.stars)
        desc = t(prefs_lang, "inline_desc", target=target, mode=mode)

        preview = t(
            prefs_lang,
            "msg_preview",
            label=g.label,
            stars=g.stars,
            target=target,
            mode=mode,
            comment=comment_text,
        ) + "\n\n" + t(prefs_lang, "note_anon")

        results.append(
            InlineQueryResultArticle(
                id=f"{token}:{g.id}",
                title=title,
                description=desc,
                input_message_content=InputTextMessageContent(message_text=preview),
                reply_markup=inline_kb(prefs_lang, token, g.id, anonymous),
            )
        )

    await q.answer(results, is_personal=True, cache_time=1)


@dp.callback_query(F.data.startswith("act:"))
async def inline_actions(c: CallbackQuery):
    ok, _, lang = await require_admin(c.from_user.id)
    if not ok:
        return await c.answer("DENIED", show_alert=True)

    parts = c.data.split(":")
    if len(parts) < 4:
        return await c.answer("BAD", show_alert=True)

    action = parts[1]
    token = parts[2]
    gift_id = int(parts[3])

    ctx = await db_get_inline_ctx(token)
    if not ctx or ctx["user_id"] != c.from_user.id:
        return await c.answer("CTX expired", show_alert=True)

    gift = GIFTS_BY_ID.get(gift_id)
    if not gift:
        return await c.answer("Gift not found", show_alert=True)

    # message key for idempotency
    if c.inline_message_id:
        msg_key = f"inline:{c.inline_message_id}:{gift_id}"
    else:
        msg_key = f"msg:{c.message.chat.id}:{c.message.message_id}:{gift_id}"

    target = ctx["target"]
    comment = ctx["comment"]
    anonymous = int(ctx["anonymous"] or 0)
    mode = "anon" if anonymous == 1 else "show"

    comment_text = comment if comment else "(none)" if lang == "en" else ("(yo‘q)" if lang == "uz" else "(нет)")
    preview = t(
        lang,
        "msg_preview",
        label=gift.label,
        stars=gift.stars,
        target=target,
        mode=mode,
        comment=comment_text,
    ) + "\n\n" + t(lang, "note_anon")

    if action == "toggle":
        new_anon = 0 if anonymous == 1 else 1
        await db_update_inline_mode(token, new_anon)
        new_mode = "anon" if new_anon == 1 else "show"
        new_preview = t(
            lang,
            "msg_preview",
            label=gift.label,
            stars=gift.stars,
            target=target,
            mode=new_mode,
            comment=comment_text,
        ) + "\n\n" + t(lang, "note_anon")

        await c.answer("OK")
        return await safe_edit_inline(c, new_preview, inline_kb(lang, token, gift_id, new_anon))

    if action == "cancel":
        # mark as done so it can't be used later
        await db_guard_once(msg_key)
        await c.answer("OK")
        return await safe_edit_inline(c, t(lang, "cancelled"), None)

    if action == "send":
        # idempotency
        allowed = await db_guard_once(msg_key)
        if not allowed:
            return await c.answer(t(lang, "already_done"), show_alert=True)

        # pick relayer session: admin's own -> fallback default
        session = await db_get_session(c.from_user.id)
        if not session:
            session = DEFAULT_RELAYER_SESSION or None
        if not session:
            return await c.answer(t(lang, "need_session"), show_alert=True)

        await c.answer("OK")
        await safe_edit_inline(c, t(lang, "sending"), None)

        try:
            hide_name = (anonymous == 1)
            # NOTE: Telegram may still show sender in chat; hide_name often affects gift details.
            comment_attached = await pool.send_star_gift(
                session_string=session,
                target=(target if target != "me" else ("@" + c.from_user.username if c.from_user.username else int(c.from_user.id))),
                gift=gift,
                comment=comment,
                hide_name=hide_name,
            )

            done_text = t(lang, "sent")
            if comment and not comment_attached:
                done_text += "\n⚠️ Comment ignored by Telegram (fallback without comment)."
            await safe_edit_inline(c, done_text, None)

        except Exception as e:
            await safe_edit_inline(c, t(lang, "fail", e=str(e)), None)

        return


# =========================
# Minimal health server (optional)
# =========================
async def run_health_server():
    # optional (if your host needs a port)
    from aiohttp import web

    async def health(_):
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_BIND, PORT)
    await site.start()
    log.info("Health server on %s:%s", WEB_BIND, PORT)
    return runner


# =========================
# Main
# =========================
async def main():
    log.info("BOOT...")
    await db_init()

    # make sure bot sees inline username for hint
    me = await bot.get_me()
    log.info("Bot: @%s", me.username)

    # if default relayer exists, validate once (optional)
    if DEFAULT_RELAYER_SESSION:
        try:
            await pool._get_client(DEFAULT_RELAYER_SESSION)
            log.info("Default relayer session OK")
        except Exception as e:
            log.warning("Default relayer invalid: %s", e)

    runner = None
    try:
        runner = await run_health_server()
    except Exception as e:
        log.warning("Health server not started: %s", e)

    try:
        log.info("Polling...")
        await dp.start_polling(bot)
    finally:
        await pool.stop_all()
        if runner:
            try:
                await runner.cleanup()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
