import os
import re
import time
import json
import asyncio
import logging
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
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import RPCError, SessionPasswordNeededError


# =========================
# Logging
# =========================
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
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

DB_PATH = os.getenv("DB_PATH", "bot.db")

# Bosh admin (owner)
OWNER_ADMIN_ID = int(os.getenv("OWNER_ADMIN_ID", "7440949683"))

# Inline natijalar nechta
INLINE_LIMIT = int(os.getenv("INLINE_LIMIT", "10"))

# Draft action tozalash (sekund)
DRAFT_TTL_SECONDS = int(os.getenv("DRAFT_TTL_SECONDS", "86400"))  # 24h

# Telethon connect timeout
TELETHON_TIMEOUT = int(os.getenv("TELETHON_TIMEOUT", "25"))


# =========================
# LANG
# =========================
T = {
    "ru": {
        "denied": "⛔ Доступ запрещён. Вы не администратор.",
        "need_session": "⚠️ Сначала сделайте /login и сохраните session (Relayer).",
        "start_owner": "✅ Вы — главный админ.\nКоманды: /admin_add /admin_del /admin_list /login /gift\nInline: @Bot 50 @user comment",
        "start_admin": "✅ Вы — админ.\nКоманды: /login /gift\nInline: @Bot 50 @user comment",
        "admin_added": "✅ Вы добавлены как админ. Нажмите /login чтобы привязать relayer session.",
        "admin_removed": "⛔ Ваш доступ удалён админом.",
        "login_phone": "📱 Отправьте номер телефона (пример: +998901234567).",
        "login_code": "🔐 Отправьте код.\nМожно с точками: 1.2.3.4.5 (бот сам уберёт точки).",
        "login_pass": "🔒 Включена 2FA (Cloud Password). Отправьте пароль.",
        "login_ok": "✅ Session сохранена! Теперь можно отправлять подарки.",
        "login_cancel": "❌ Login отменён.",
        "lang_set": "✅ Язык установлен: {lang}",
        "inline_help": "Наберите: @Bot 50 @username комментарий",
        "pick_title": "🎁 Выберите подарок:",
        "confirm_title": "Подтвердите отправку:",
        "sent_ok": "✅ Отправлено!",
        "already_done": "⚠️ Уже обработано (отправлено/отменено).",
        "cancelled": "❌ Отменено.",
        "need_reply_target": "⚠️ Target=reply, но reply не найден.\nНапишите target в inline запросе или используйте /gift reply в группе.",
        "entity_fail": "❌ Не могу найти пользователя.\n✅ Лучше использовать @username или пусть получатель напишет relayer-аккаунту 1 раз.",
        "mode_anon": "🕵️ Анонимно (hide name)",
        "mode_show": "👤 Профиль (show name)",
        "comment_empty": "(без комментария)",
        "btn_send": "✅ Отправить",
        "btn_toggle": "🕵️/👤 Режим",
        "btn_cancel": "❌ Отмена",
        "btn_menu": "⬅️ Меню",
        "menu": "Меню:",
        "set_target": "🎯 Отправьте target: @username или user_id или me",
        "set_comment": "💬 Отправьте комментарий (или '-' чтобы удалить).",
        "saved": "✅ Сохранено.",
        "bad_args": "Формат: /gift 50 [@user|id] [comment...] (в группе можно reply + /gift 50 ...)",
        "admin_list_title": "👮 Admin list:",
        "admin_add_ok": "✅ Admin qo‘shildi: {uid}",
        "admin_del_ok": "✅ Admin o‘chirildi: {uid}",
    },
    "uz": {
        "denied": "⛔ Ruxsat yo‘q. Siz admin emassiz.",
        "need_session": "⚠️ Avval /login qilib relayer session bog‘lang.",
        "start_owner": "✅ Siz bosh adminsiz.\nBuyruqlar: /admin_add /admin_del /admin_list /login /gift\nInline: @Bot 50 @user comment",
        "start_admin": "✅ Siz adminsiz.\nBuyruqlar: /login /gift\nInline: @Bot 50 @user comment",
        "admin_added": "✅ Siz admin bo‘ldingiz. /login qilib relayer session bog‘lang.",
        "admin_removed": "⛔ Sizning ruxsatingiz o‘chirildi.",
        "login_phone": "📱 Telefon raqamingizni yuboring (misol: +998901234567).",
        "login_code": "🔐 Kod yuboring.\nNuqta bilan ham bo‘ladi: 1.2.3.4.5 (bot nuqtani olib tashlaydi).",
        "login_pass": "🔒 2FA bor (Cloud Password). Parolni yuboring.",
        "login_ok": "✅ Session saqlandi! Endi gift yuborishingiz mumkin.",
        "login_cancel": "❌ Login bekor qilindi.",
        "lang_set": "✅ Til o‘rnatildi: {lang}",
        "inline_help": "Yozing: @Bot 50 @username komment",
        "pick_title": "🎁 Sovg‘ani tanlang:",
        "confirm_title": "Yuborishni tasdiqlang:",
        "sent_ok": "✅ Yuborildi!",
        "already_done": "⚠️ Avval ishlangan (yuborilgan/bekor qilingan).",
        "cancelled": "❌ Bekor qilindi.",
        "need_reply_target": "⚠️ Target=reply, lekin reply topilmadi.\nInline’da target yozing yoki guruhda reply + /gift ishlating.",
        "entity_fail": "❌ User topilmadi.\n✅ @username ishlating yoki user relayerga 1 marta yozsin.",
        "mode_anon": "🕵️ Anonim (hide name)",
        "mode_show": "👤 Profil (show name)",
        "comment_empty": "(komment yo‘q)",
        "btn_send": "✅ Yuborish",
        "btn_toggle": "🕵️/👤 Rejim",
        "btn_cancel": "❌ Bekor",
        "btn_menu": "⬅️ Menu",
        "menu": "Menu:",
        "set_target": "🎯 Target yuboring: @username yoki user_id yoki me",
        "set_comment": "💬 Komment yuboring (o‘chirish: '-')",
        "saved": "✅ Saqlandi.",
        "bad_args": "Format: /gift 50 [@user|id] [comment...] (guruhda reply + /gift 50 ...)",
        "admin_list_title": "👮 Adminlar:",
        "admin_add_ok": "✅ Admin qo‘shildi: {uid}",
        "admin_del_ok": "✅ Admin o‘chirildi: {uid}",
    },
    "en": {
        "denied": "⛔ Access denied. You are not an admin.",
        "need_session": "⚠️ Run /login first to attach relayer session.",
        "start_owner": "✅ You are OWNER.\nCommands: /admin_add /admin_del /admin_list /login /gift\nInline: @Bot 50 @user comment",
        "start_admin": "✅ You are admin.\nCommands: /login /gift\nInline: @Bot 50 @user comment",
        "admin_added": "✅ You are now an admin. Use /login to attach relayer session.",
        "admin_removed": "⛔ Your access was removed.",
        "login_phone": "📱 Send your phone number (example: +998901234567).",
        "login_code": "🔐 Send the code.\nDots allowed: 1.2.3.4.5 (bot removes dots).",
        "login_pass": "🔒 2FA enabled (Cloud Password). Send your password.",
        "login_ok": "✅ Session saved! You can send gifts now.",
        "login_cancel": "❌ Login cancelled.",
        "lang_set": "✅ Language set: {lang}",
        "inline_help": "Type: @Bot 50 @username comment",
        "pick_title": "🎁 Pick a gift:",
        "confirm_title": "Confirm sending:",
        "sent_ok": "✅ Sent!",
        "already_done": "⚠️ Already processed.",
        "cancelled": "❌ Cancelled.",
        "need_reply_target": "⚠️ Target=reply but reply not found.\nProvide target in inline query or use /gift reply in group.",
        "entity_fail": "❌ Can't resolve user.\n✅ Use @username or ask target to message relayer once.",
        "mode_anon": "🕵️ Anonymous (hide name)",
        "mode_show": "👤 Show profile (show name)",
        "comment_empty": "(no comment)",
        "btn_send": "✅ Send",
        "btn_toggle": "🕵️/👤 Mode",
        "btn_cancel": "❌ Cancel",
        "btn_menu": "⬅️ Menu",
        "menu": "Menu:",
        "set_target": "🎯 Send target: @username or user_id or me",
        "set_comment": "💬 Send comment (or '-' to remove).",
        "saved": "✅ Saved.",
        "bad_args": "Usage: /gift 50 [@user|id] [comment...] (in groups: reply + /gift 50 ...)",
        "admin_list_title": "👮 Admin list:",
        "admin_add_ok": "✅ Added admin: {uid}",
        "admin_del_ok": "✅ Removed admin: {uid}",
    },
}


def tr(lang: str, key: str) -> str:
    if lang not in T:
        lang = "ru"
    return T[lang].get(key, T["ru"].get(key, key))


def fmt_mode(lang: str, hide_name: int) -> str:
    return tr(lang, "mode_anon") if hide_name == 1 else tr(lang, "mode_show")


# =========================
# Gifts (NO ID in UI)
# =========================
@dataclass(frozen=True)
class GiftItem:
    id: int
    stars: int
    label: str


GIFT_CATALOG: List[GiftItem] = [
    GiftItem(6028601630662853006, 50, "🍾"),
    GiftItem(5170521118301225164, 100, "💎"),
    GiftItem(5170690322832818290, 100, "💍"),
    GiftItem(5168043875654172773, 100, "🏆"),
    GiftItem(5170564780938756245, 50, "🚀"),
    GiftItem(5170314324215857265, 50, "💐"),
    GiftItem(5170144170496491616, 50, "🎂"),
    GiftItem(5168103777563050263, 25, "🌹"),
    GiftItem(5170250947678437525, 25, "🎁"),
    GiftItem(5170233102089322756, 15, "🧸"),
    GiftItem(5170145012310081615, 15, "💝"),
    GiftItem(5922558454332916696, 50, "🎄"),
    GiftItem(5956217000635139069, 50, "🧸🎩"),
]

GIFTS_BY_ID: Dict[int, GiftItem] = {g.id: g for g in GIFT_CATALOG}


def gifts_up_to(max_stars: int) -> List[GiftItem]:
    out = [g for g in GIFT_CATALOG if g.stars <= max_stars]
    out.sort(key=lambda x: (x.stars, x.label))
    return out


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
            role TEXT NOT NULL DEFAULT 'admin', -- 'owner'|'admin'
            lang TEXT NOT NULL DEFAULT 'ru',
            default_hide_name INTEGER NOT NULL DEFAULT 0,
            session_string TEXT DEFAULT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            action_id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL,
            target TEXT NOT NULL, -- '@user' | '123' | '__reply__' | 'me'
            gift_id INTEGER NOT NULL,
            stars INTEGER NOT NULL,
            comment TEXT DEFAULT NULL,
            hide_name INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'draft', -- draft|sending|sent|failed|cancelled
            error TEXT DEFAULT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_actions_creator ON actions(creator_id);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);")
        await db.commit()

    # seed owner
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
        INSERT OR IGNORE INTO admins(user_id, role, lang, created_at, updated_at)
        VALUES(?,?,?,?,?)
        """, (OWNER_ADMIN_ID, "owner", "ru", now, now))
        await db.commit()


async def db_get_admin(user_id: int) -> Optional[dict]:
    async with db_connect() as db:
        cur = await db.execute("""
        SELECT user_id, role, lang, default_hide_name, session_string
        FROM admins WHERE user_id=?
        """, (user_id,))
        r = await cur.fetchone()
        if not r:
            return None
        return {
            "user_id": r[0],
            "role": r[1],
            "lang": r[2],
            "default_hide_name": int(r[3] or 0),
            "session_string": r[4],
        }


async def db_set_lang(user_id: int, lang: str):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
        UPDATE admins SET lang=?, updated_at=? WHERE user_id=?
        """, (lang, now, user_id))
        await db.commit()


async def db_set_default_hide(user_id: int, hide: int):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
        UPDATE admins SET default_hide_name=?, updated_at=? WHERE user_id=?
        """, (hide, now, user_id))
        await db.commit()


async def db_set_session(user_id: int, session_string: Optional[str]):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
        UPDATE admins SET session_string=?, updated_at=? WHERE user_id=?
        """, (session_string, now, user_id))
        await db.commit()


async def db_add_admin(user_id: int):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
        INSERT OR IGNORE INTO admins(user_id, role, lang, created_at, updated_at)
        VALUES(?,?,?,?,?)
        """, (user_id, "admin", "ru", now, now))
        await db.commit()


async def db_del_admin(user_id: int):
    async with db_connect() as db:
        await db.execute("DELETE FROM admins WHERE user_id=? AND role!='owner'", (user_id,))
        await db.commit()


async def db_list_admins() -> List[Tuple[int, str, str]]:
    async with db_connect() as db:
        cur = await db.execute("SELECT user_id, role, lang FROM admins ORDER BY role DESC, user_id ASC")
        rows = await cur.fetchall()
        return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]


async def db_create_action(
    creator_id: int,
    target: str,
    gift: GiftItem,
    comment: Optional[str],
    hide_name: int,
) -> int:
    now = int(time.time())
    async with db_connect() as db:
        cur = await db.execute("""
        INSERT INTO actions(
            creator_id, target, gift_id, stars, comment, hide_name, status, created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """, (creator_id, target, gift.id, gift.stars, comment, hide_name, "draft", now, now))
        await db.commit()
        return int(cur.lastrowid)


async def db_get_action(action_id: int) -> Optional[dict]:
    async with db_connect() as db:
        cur = await db.execute("""
        SELECT action_id, creator_id, target, gift_id, stars, comment, hide_name, status, error
        FROM actions WHERE action_id=?
        """, (action_id,))
        r = await cur.fetchone()
        if not r:
            return None
        return {
            "action_id": int(r[0]),
            "creator_id": int(r[1]),
            "target": str(r[2]),
            "gift_id": int(r[3]),
            "stars": int(r[4]),
            "comment": r[5],
            "hide_name": int(r[6] or 0),
            "status": str(r[7]),
            "error": r[8],
        }


async def db_toggle_action_hide(action_id: int) -> Optional[int]:
    now = int(time.time())
    async with db_connect() as db:
        cur = await db.execute("SELECT hide_name, status FROM actions WHERE action_id=?", (action_id,))
        r = await cur.fetchone()
        if not r:
            return None
        hide = int(r[0] or 0)
        status = str(r[1])
        if status != "draft":
            return None
        new_val = 0 if hide == 1 else 1
        await db.execute("""
        UPDATE actions SET hide_name=?, updated_at=? WHERE action_id=? AND status='draft'
        """, (new_val, now, action_id))
        await db.commit()
        return new_val


async def db_cancel_action(action_id: int) -> bool:
    now = int(time.time())
    async with db_connect() as db:
        cur = await db.execute("""
        UPDATE actions SET status='cancelled', updated_at=? WHERE action_id=? AND status='draft'
        """, (now, action_id))
        await db.commit()
        return cur.rowcount == 1


async def db_try_lock_send(action_id: int) -> bool:
    now = int(time.time())
    async with db_connect() as db:
        cur = await db.execute("""
        UPDATE actions SET status='sending', updated_at=? WHERE action_id=? AND status='draft'
        """, (now, action_id))
        await db.commit()
        return cur.rowcount == 1


async def db_mark_sent(action_id: int):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
        UPDATE actions SET status='sent', error=NULL, updated_at=? WHERE action_id=?
        """, (now, action_id))
        await db.commit()


async def db_mark_failed(action_id: int, err: str):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
        UPDATE actions SET status='failed', error=?, updated_at=? WHERE action_id=?
        """, (err[:500], now, action_id))
        await db.commit()


async def db_cleanup_drafts():
    cutoff = int(time.time()) - DRAFT_TTL_SECONDS
    async with db_connect() as db:
        await db.execute("""
        DELETE FROM actions WHERE status='draft' AND created_at < ?
        """, (cutoff,))
        await db.commit()


# =========================
# Auth helpers
# =========================
async def ensure_admin_or_denied(m: Message) -> bool:
    adm = await db_get_admin(m.from_user.id)
    if not adm:
        await m.reply(T["ru"]["denied"])
        return False
    return True


async def ensure_admin_callback_or_denied(c: CallbackQuery) -> Optional[dict]:
    adm = await db_get_admin(c.from_user.id)
    if not adm:
        try:
            await c.answer(T["ru"]["denied"], show_alert=True)
        except Exception:
            pass
        return None
    return adm


def sanitize_phone(text: str) -> str:
    t = (text or "").strip()
    t = t.replace(" ", "")
    if not t.startswith("+"):
        # allow "998..." -> "+998..."
        if t.isdigit():
            t = "+" + t
    return t


def sanitize_code(text: str) -> str:
    # allow "1.2.3.4.5" -> "12345"
    digits = re.sub(r"\D+", "", text or "")
    return digits


def safe_comment(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = text.strip().replace("\r", " ").replace("\n", " ")
    if not t:
        return None
    if len(t) > 250:
        t = t[:250]
    return t


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


# =========================
# UI
# =========================
def menu_kb(lang: str, hide_default: int, has_session: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 /gift", callback_data="menu:help_gift")
    kb.button(text="🌐 Lang", callback_data="menu:lang")
    kb.button(text=("🕵️ default" if hide_default == 1 else "👤 default"), callback_data="menu:toggle_default")
    if not has_session:
        kb.button(text="🔐 /login", callback_data="menu:help_login")
    kb.adjust(2, 2)
    return kb.as_markup()


def lang_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 RU", callback_data="lang:ru")
    kb.button(text="🇺🇿 UZ", callback_data="lang:uz")
    kb.button(text="🇬🇧 EN", callback_data="lang:en")
    kb.button(text="⬅️", callback_data="menu:home")
    kb.adjust(3, 1)
    return kb.as_markup()


def action_kb(lang: str, action_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=tr(lang, "btn_send"), callback_data=f"a:{action_id}:send")
    kb.button(text=tr(lang, "btn_toggle"), callback_data=f"a:{action_id}:toggle")
    kb.button(text=tr(lang, "btn_cancel"), callback_data=f"a:{action_id}:cancel")
    kb.adjust(2, 1)
    return kb.as_markup()


def pick_kb(lang: str, action_ids: List[int], gifts: List[GiftItem]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for aid, g in zip(action_ids, gifts):
        kb.button(text=f"{g.label} {g.stars}⭐", callback_data=f"a:{aid}:pick")
    kb.adjust(2)
    return kb.as_markup()


async def safe_edit_message(
    bot: Bot,
    c: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
):
    """
    Fix: message is not modified
    Works for normal messages; for inline_message_id edits (no message), it edits inline message.
    """
    try:
        if c.message:
            # normal
            await c.message.edit_text(text, reply_markup=reply_markup)
        else:
            # inline callback
            await bot.edit_message_text(
                inline_message_id=c.inline_message_id,
                text=text,
                reply_markup=reply_markup,
            )
    except Exception as e:
        msg = str(e)
        if "message is not modified" in msg:
            # ignore
            return
        raise


# =========================
# Telethon relayer manager
# =========================
class RelayerPool:
    """
    One Telethon client per admin (cached).
    """
    def __init__(self):
        self._clients: Dict[int, TelegramClient] = {}
        self._locks: Dict[int, asyncio.Lock] = {}

    def _lock(self, admin_id: int) -> asyncio.Lock:
        if admin_id not in self._locks:
            self._locks[admin_id] = asyncio.Lock()
        return self._locks[admin_id]

    async def get_client(self, admin_id: int, session_string: str) -> TelegramClient:
        if admin_id in self._clients:
            return self._clients[admin_id]
        client = TelegramClient(
            StringSession(session_string),
            TG_API_ID,
            TG_API_HASH,
            timeout=TELETHON_TIMEOUT,
            connection_retries=5,
            retry_delay=2,
            auto_reconnect=True,
        )
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError("Session invalid. /login qayta qiling.")
        self._clients[admin_id] = client
        return client

    async def close_all(self):
        for c in list(self._clients.values()):
            try:
                await c.disconnect()
            except Exception:
                pass
        self._clients.clear()

    async def send_star_gift(
        self,
        *,
        admin_id: int,
        session_string: str,
        target: Union[str, int],
        gift: GiftItem,
        comment: Optional[str],
        hide_name: bool,
    ) -> bool:
        """
        returns True if comment used, False if fallback without comment.
        """
        lock = self._lock(admin_id)
        async with lock:
            client = await self.get_client(admin_id, session_string)

            # can send?
            can = await client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")

            # resolve entity
            try:
                peer = await client.get_input_entity(target)
            except Exception:
                raise RuntimeError("ENTITY_NOT_FOUND")

            cleaned = safe_comment(comment)
            msg_obj = None
            if cleaned:
                msg_obj = types.TextWithEntities(text=cleaned[:120], entities=[])

            extra = {}
            if hide_name:
                extra["hide_name"] = True  # only pass if True

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


# =========================
# Login FSM (phone->code->pass)
# =========================
class LoginForm(StatesGroup):
    phone = State()
    code = State()
    password = State()


@dataclass
class LoginFlow:
    client: TelegramClient
    phone: str
    phone_code_hash: str


_login_flows: Dict[int, LoginFlow] = {}  # user_id -> flow


async def login_flow_cleanup(user_id: int):
    flow = _login_flows.pop(user_id, None)
    if flow:
        try:
            await flow.client.disconnect()
        except Exception:
            pass


# =========================
# Bot setup
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
relayers = RelayerPool()


# =========================
# Owner admin tools
# =========================
def is_owner(adm: dict) -> bool:
    return adm.get("role") == "owner"


@dp.message(Command("admin_add"))
async def cmd_admin_add(m: Message):
    adm = await db_get_admin(m.from_user.id)
    if not adm or not is_owner(adm):
        return await m.reply(T["ru"]["denied"])

    # /admin_add 123  or reply
    uid = None
    parts = (m.text or "").split()
    if len(parts) >= 2 and parts[1].isdigit():
        uid = int(parts[1])
    elif m.reply_to_message and m.reply_to_message.from_user:
        uid = m.reply_to_message.from_user.id

    if not uid:
        return await m.reply("Usage: /admin_add <user_id>  (yoki reply bilan)")

    await db_add_admin(uid)
    lang = adm["lang"]
    await m.reply(tr(lang, "admin_add_ok").format(uid=uid))

    # notify new admin (if possible)
    try:
        await bot.send_message(uid, tr("ru", "admin_added"))
    except Exception:
        pass


@dp.message(Command("admin_del"))
async def cmd_admin_del(m: Message):
    adm = await db_get_admin(m.from_user.id)
    if not adm or not is_owner(adm):
        return await m.reply(T["ru"]["denied"])

    uid = None
    parts = (m.text or "").split()
    if len(parts) >= 2 and parts[1].isdigit():
        uid = int(parts[1])
    elif m.reply_to_message and m.reply_to_message.from_user:
        uid = m.reply_to_message.from_user.id

    if not uid:
        return await m.reply("Usage: /admin_del <user_id>  (yoki reply bilan)")

    await db_del_admin(uid)
    lang = adm["lang"]
    await m.reply(tr(lang, "admin_del_ok").format(uid=uid))

    try:
        await bot.send_message(uid, tr("ru", "admin_removed"))
    except Exception:
        pass


@dp.message(Command("admin_list"))
async def cmd_admin_list(m: Message):
    adm = await db_get_admin(m.from_user.id)
    if not adm or not is_owner(adm):
        return await m.reply(T["ru"]["denied"])
    lang = adm["lang"]

    rows = await db_list_admins()
    text = tr(lang, "admin_list_title") + "\n\n"
    for uid, role, lg in rows:
        text += f"- {uid} | {role} | {lg}\n"
    await m.reply(text)


# =========================
# Basic /start /lang /menu
# =========================
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    adm = await db_get_admin(m.from_user.id)
    if not adm:
        return await m.reply(T["ru"]["denied"])

    lang = adm["lang"]
    has_session = bool(adm.get("session_string"))
    if is_owner(adm):
        text = tr(lang, "start_owner")
    else:
        text = tr(lang, "start_admin")

    text += "\n\n" + tr(lang, "inline_help")
    await m.reply(text, reply_markup=menu_kb(lang, adm["default_hide_name"], has_session))


@dp.message(Command("lang"))
async def cmd_lang(m: Message):
    if not await ensure_admin_or_denied(m):
        return
    adm = await db_get_admin(m.from_user.id)
    await m.reply("Choose language:", reply_markup=lang_kb())


@dp.callback_query(F.data.startswith("lang:"))
async def cb_lang(c: CallbackQuery):
    adm = await ensure_admin_callback_or_denied(c)
    if not adm:
        return
    code = c.data.split(":", 1)[1]
    if code not in ("ru", "uz", "en"):
        code = "ru"
    await db_set_lang(c.from_user.id, code)
    await c.answer("OK")
    new_adm = await db_get_admin(c.from_user.id)
    lang = new_adm["lang"]
    has_session = bool(new_adm.get("session_string"))
    await safe_edit_message(
        bot,
        c,
        tr(lang, "lang_set").format(lang=code),
        reply_markup=menu_kb(lang, new_adm["default_hide_name"], has_session)
    )


@dp.callback_query(F.data == "menu:home")
async def cb_menu_home(c: CallbackQuery):
    adm = await ensure_admin_callback_or_denied(c)
    if not adm:
        return
    has_session = bool(adm.get("session_string"))
    lang = adm["lang"]
    text = tr(lang, "menu")
    await c.answer()
    await safe_edit_message(bot, c, text, reply_markup=menu_kb(lang, adm["default_hide_name"], has_session))


@dp.callback_query(F.data == "menu:lang")
async def cb_menu_lang(c: CallbackQuery):
    adm = await ensure_admin_callback_or_denied(c)
    if not adm:
        return
    await c.answer()
    await safe_edit_message(bot, c, "Choose language:", reply_markup=lang_kb())


@dp.callback_query(F.data == "menu:help_gift")
async def cb_help_gift(c: CallbackQuery):
    adm = await ensure_admin_callback_or_denied(c)
    if not adm:
        return
    lang = adm["lang"]
    await c.answer()
    txt = (
        "🧩 /gift examples:\n"
        "1) Private: /gift 50 @username Congrats\n"
        "2) Group: reply to user, then: /gift 50 Congrats\n\n"
        + tr(lang, "inline_help")
    )
    await safe_edit_message(bot, c, txt, reply_markup=menu_kb(lang, adm["default_hide_name"], bool(adm.get("session_string"))))


@dp.callback_query(F.data == "menu:help_login")
async def cb_help_login(c: CallbackQuery):
    adm = await ensure_admin_callback_or_denied(c)
    if not adm:
        return
    lang = adm["lang"]
    await c.answer()
    await safe_edit_message(bot, c, "Use /login to attach relayer session.", reply_markup=menu_kb(lang, adm["default_hide_name"], bool(adm.get("session_string"))))


@dp.callback_query(F.data == "menu:toggle_default")
async def cb_toggle_default(c: CallbackQuery):
    adm = await ensure_admin_callback_or_denied(c)
    if not adm:
        return
    lang = adm["lang"]
    new_val = 0 if adm["default_hide_name"] == 1 else 1
    await db_set_default_hide(c.from_user.id, new_val)
    new_adm = await db_get_admin(c.from_user.id)
    await c.answer("OK")
    await safe_edit_message(
        bot,
        c,
        f"Default mode: {fmt_mode(lang, new_adm['default_hide_name'])}",
        reply_markup=menu_kb(lang, new_adm["default_hide_name"], bool(new_adm.get("session_string")))
    )


# =========================
# /login flow
# =========================
@dp.message(Command("login"))
async def cmd_login(m: Message, state: FSMContext):
    if not await ensure_admin_or_denied(m):
        return
    adm = await db_get_admin(m.from_user.id)
    lang = adm["lang"]

    # cancel old flow if any
    await login_flow_cleanup(m.from_user.id)

    await state.set_state(LoginForm.phone)
    await m.reply(tr(lang, "login_phone"))


@dp.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    if not await ensure_admin_or_denied(m):
        return
    await state.clear()
    await login_flow_cleanup(m.from_user.id)
    adm = await db_get_admin(m.from_user.id)
    await m.reply(tr(adm["lang"], "login_cancel"))


@dp.message(LoginForm.phone)
async def login_phone(m: Message, state: FSMContext):
    adm = await db_get_admin(m.from_user.id)
    lang = adm["lang"]

    phone = sanitize_phone(m.text or "")
    if not phone or len(phone) < 8:
        return await m.reply(tr(lang, "login_phone"))

    client = TelegramClient(StringSession(), TG_API_ID, TG_API_HASH, timeout=TELETHON_TIMEOUT)
    await client.connect()

    try:
        sent = await client.send_code_request(phone)
        _login_flows[m.from_user.id] = LoginFlow(client=client, phone=phone, phone_code_hash=sent.phone_code_hash)
        await state.set_state(LoginForm.code)
        await m.reply(tr(lang, "login_code"))
    except Exception as e:
        await client.disconnect()
        await m.reply(f"❌ send_code error: {e}")


@dp.message(LoginForm.code)
async def login_code(m: Message, state: FSMContext):
    adm = await db_get_admin(m.from_user.id)
    lang = adm["lang"]

    flow = _login_flows.get(m.from_user.id)
    if not flow:
        await state.clear()
        return await m.reply("Flow missing. /login qayta.")

    code = sanitize_code(m.text or "")
    if len(code) < 3:
        return await m.reply(tr(lang, "login_code"))

    try:
        await flow.client.sign_in(flow.phone, code=code, phone_code_hash=flow.phone_code_hash)
        # success
        session_str = flow.client.session.save()
        await db_set_session(m.from_user.id, session_str)
        await state.clear()
        await login_flow_cleanup(m.from_user.id)
        await m.reply(tr(lang, "login_ok"))
    except SessionPasswordNeededError:
        await state.set_state(LoginForm.password)
        await m.reply(tr(lang, "login_pass"))
    except Exception as e:
        await m.reply(f"❌ code error: {e}")


@dp.message(LoginForm.password)
async def login_password(m: Message, state: FSMContext):
    adm = await db_get_admin(m.from_user.id)
    lang = adm["lang"]

    flow = _login_flows.get(m.from_user.id)
    if not flow:
        await state.clear()
        return await m.reply("Flow missing. /login qayta.")

    pwd = (m.text or "").strip()
    if len(pwd) < 2:
        return await m.reply(tr(lang, "login_pass"))

    try:
        await flow.client.sign_in(password=pwd)
        session_str = flow.client.session.save()
        await db_set_session(m.from_user.id, session_str)
        await state.clear()
        await login_flow_cleanup(m.from_user.id)
        await m.reply(tr(lang, "login_ok"))
    except Exception as e:
        await m.reply(f"❌ password error: {e}")


@dp.message(Command("logout"))
async def cmd_logout(m: Message):
    if not await ensure_admin_or_denied(m):
        return
    await db_set_session(m.from_user.id, None)
    await m.reply("✅ Session removed. /login again if needed.")


# =========================
# /gift command (reply-friendly)
# =========================
@dp.message(Command("gift"))
@dp.message(Command("g"))
async def cmd_gift(m: Message):
    if not await ensure_admin_or_denied(m):
        return
    adm = await db_get_admin(m.from_user.id)
    lang = adm["lang"]
    if not adm.get("session_string"):
        return await m.reply(tr(lang, "need_session"))

    parts = (m.text or "").split(maxsplit=3)
    # /gift 50 [target] [comment...]
    if len(parts) < 2 or not parts[1].isdigit():
        return await m.reply(tr(lang, "bad_args"))

    max_stars = int(parts[1])
    target = None
    comment = None

    # group reply -> default target=reply user
    reply_user = None
    if m.reply_to_message and m.reply_to_message.from_user:
        reply_user = m.reply_to_message.from_user

    if len(parts) >= 3:
        # could be target or comment (if reply exists)
        maybe = parts[2].strip()
        if maybe.startswith("@") or maybe.isdigit() or maybe.lower() == "me":
            target = normalize_target(maybe)
            comment = safe_comment(parts[3] if len(parts) >= 4 else None)
        else:
            # treat as comment if target via reply
            comment = safe_comment(" ".join(parts[2:]))
    else:
        comment = None

    if not target:
        if reply_user:
            # use @username if possible else id (may fail if relayer can't resolve)
            if reply_user.username:
                target = "@" + reply_user.username
            else:
                # will try numeric id; may fail if relayer cannot resolve it
                target = str(reply_user.id)
        else:
            # default target is me
            if m.from_user.username:
                target = "@" + m.from_user.username
            else:
                target = str(m.from_user.id)

    gifts = gifts_up_to(max_stars)
    if not gifts:
        return await m.reply("No gifts for this limit.")

    gifts = gifts[:INLINE_LIMIT]
    action_ids: List[int] = []
    for g in gifts:
        aid = await db_create_action(
            creator_id=m.from_user.id,
            target=target,
            gift=g,
            comment=comment,
            hide_name=int(adm["default_hide_name"] or 0),
        )
        action_ids.append(aid)

    cm = comment if comment else tr(lang, "comment_empty")
    mode_txt = fmt_mode(lang, int(adm["default_hide_name"] or 0))

    txt = (
        f"{tr(lang, 'pick_title')}\n\n"
        f"🎯 {target}\n"
        f"🔒 {mode_txt}\n"
        f"💬 {cm}"
    )
    await m.reply(txt, reply_markup=pick_kb(lang, action_ids, gifts))


# =========================
# Inline mode
# Query formats:
#   "50 @user comment"
#   "50"  (target=reply required on send)
# =========================
_inline_cache: Dict[Tuple[int, str], Tuple[float, List[InlineQueryResultArticle]]] = {}


def parse_inline_query(q: str) -> Tuple[Optional[int], str, Optional[str]]:
    """
    returns (max_stars, target, comment)
    target may be '__reply__' if not provided
    """
    q = (q or "").strip()
    if not q:
        return None, "__reply__", None
    parts = q.split()
    if not parts[0].isdigit():
        return None, "__reply__", None
    max_stars = int(parts[0])
    target = "__reply__"
    comment = None
    if len(parts) >= 2:
        if parts[1].startswith("@") or parts[1].isdigit() or parts[1].lower() == "me":
            target = normalize_target(parts[1])
            comment = safe_comment(" ".join(parts[2:]) if len(parts) >= 3 else None)
        else:
            # no target, only comment
            comment = safe_comment(" ".join(parts[1:]))
    return max_stars, target, comment


@dp.inline_query()
async def inline_handler(q: InlineQuery):
    adm = await db_get_admin(q.from_user.id)
    if not adm:
        return await q.answer([], is_personal=True, cache_time=1)

    lang = adm["lang"]
    if not adm.get("session_string"):
        # don't spam results
        return await q.answer([], is_personal=True, cache_time=1, switch_pm_text=tr(lang, "need_session"), switch_pm_parameter="login")

    max_stars, target, comment = parse_inline_query(q.query)
    if not max_stars:
        # show help result
        help_res = InlineQueryResultArticle(
            id="help",
            title=tr(lang, "inline_help"),
            input_message_content=InputTextMessageContent(
                message_text=tr(lang, "inline_help"),
                parse_mode="HTML",
            ),
        )
        return await q.answer([help_res], is_personal=True, cache_time=1)

    cache_key = (q.from_user.id, q.query.strip())
    now = time.time()
    if cache_key in _inline_cache:
        ts, items = _inline_cache[cache_key]
        if now - ts < 8.0:
            return await q.answer(items, is_personal=True, cache_time=1)

    gifts = gifts_up_to(max_stars)[:INLINE_LIMIT]
    results: List[InlineQueryResultArticle] = []

    for g in gifts:
        aid = await db_create_action(
            creator_id=q.from_user.id,
            target=target,
            gift=g,
            comment=comment,
            hide_name=int(adm["default_hide_name"] or 0),
        )
        cm = comment if comment else tr(lang, "comment_empty")
        mode_txt = fmt_mode(lang, int(adm["default_hide_name"] or 0))

        tgt_txt = target if target != "__reply__" else "reply-target"
        msg_text = (
            f"🎁 {g.label}  ⭐{g.stars}\n"
            f"🎯 {tgt_txt}\n"
            f"🔒 {mode_txt}\n"
            f"💬 {cm}\n\n"
            f"{tr(lang, 'confirm_title')}"
        )

        results.append(
            InlineQueryResultArticle(
                id=str(aid),
                title=f"{g.label} {g.stars}⭐",
                description=f"target: {tgt_txt} | mode: {('anon' if int(adm['default_hide_name'] or 0)==1 else 'show')}",
                input_message_content=InputTextMessageContent(
                    message_text=msg_text,
                    parse_mode="HTML",
                ),
                reply_markup=action_kb(lang, aid),
            )
        )

    _inline_cache[cache_key] = (now, results)
    await q.answer(results, is_personal=True, cache_time=1)


# =========================
# Action callbacks
# =========================
@dp.callback_query(F.data.startswith("a:"))
async def action_callback(c: CallbackQuery):
    adm = await ensure_admin_callback_or_denied(c)
    if not adm:
        return
    lang = adm["lang"]

    try:
        _, aid_s, cmd = c.data.split(":", 2)
        action_id = int(aid_s)
    except Exception:
        return await c.answer("bad", show_alert=True)

    act = await db_get_action(action_id)
    if not act:
        return await c.answer("not found", show_alert=True)

    # Only creator or owner can control
    if not is_owner(adm) and act["creator_id"] != c.from_user.id:
        return await c.answer(tr(lang, "denied"), show_alert=True)

    gift = GIFTS_BY_ID.get(act["gift_id"])
    if not gift:
        return await c.answer("gift missing", show_alert=True)

    # PICK -> show confirm with same action
    if cmd == "pick":
        if act["status"] != "draft":
            await c.answer(tr(lang, "already_done"), show_alert=True)
            return

        cm = act["comment"] if act["comment"] else tr(lang, "comment_empty")
        mode_txt = fmt_mode(lang, act["hide_name"])
        txt = (
            f"🎁 {gift.label}  ⭐{gift.stars}\n"
            f"🎯 {act['target']}\n"
            f"🔒 {mode_txt}\n"
            f"💬 {cm}\n\n"
            f"{tr(lang, 'confirm_title')}"
        )
        await c.answer("OK")
        await safe_edit_message(bot, c, txt, reply_markup=action_kb(lang, action_id))
        return

    # TOGGLE
    if cmd == "toggle":
        new_hide = await db_toggle_action_hide(action_id)
        if new_hide is None:
            return await c.answer(tr(lang, "already_done"), show_alert=True)

        act2 = await db_get_action(action_id)
        cm = act2["comment"] if act2["comment"] else tr(lang, "comment_empty")
        mode_txt = fmt_mode(lang, act2["hide_name"])
        tgt_txt = act2["target"]

        txt = (
            f"🎁 {gift.label}  ⭐{gift.stars}\n"
            f"🎯 {tgt_txt}\n"
            f"🔒 {mode_txt}\n"
            f"💬 {cm}\n\n"
            f"{tr(lang, 'confirm_title')}"
        )
        await c.answer("OK")
        await safe_edit_message(bot, c, txt, reply_markup=action_kb(lang, action_id))
        return

    # CANCEL
    if cmd == "cancel":
        ok = await db_cancel_action(action_id)
        await c.answer("OK")
        if not ok:
            return await c.answer(tr(lang, "already_done"), show_alert=True)

        txt = f"{tr(lang, 'cancelled')}\n🎁 {gift.label} ⭐{gift.stars}"
        await safe_edit_message(bot, c, txt, reply_markup=None)
        return

    # SEND
    if cmd == "send":
        if not adm.get("session_string"):
            return await c.answer(tr(lang, "need_session"), show_alert=True)

        locked = await db_try_lock_send(action_id)
        if not locked:
            return await c.answer(tr(lang, "already_done"), show_alert=True)

        # Resolve target
        target_raw = act["target"]
        target: Union[str, int]

        if target_raw == "__reply__":
            # Try find reply target if message exists
            if c.message and c.message.reply_to_message and c.message.reply_to_message.from_user:
                ru = c.message.reply_to_message.from_user
                if ru.username:
                    target = "@" + ru.username
                else:
                    target = int(ru.id)
            else:
                await db_mark_failed(action_id, "reply_target_missing")
                await c.answer(tr(lang, "need_reply_target"), show_alert=True)
                return
        else:
            if target_raw.startswith("@"):
                target = target_raw
            elif target_raw.isdigit():
                target = int(target_raw)
            else:
                target = target_raw

        cm = act["comment"]
        hide_name = (act["hide_name"] == 1)

        # immediate UI feedback
        await c.answer("Sending...")

        try:
            used_comment = await relayers.send_star_gift(
                admin_id=c.from_user.id,
                session_string=adm["session_string"],
                target=target,
                gift=gift,
                comment=cm,
                hide_name=hide_name,
            )
            await db_mark_sent(action_id)

            note = tr(lang, "sent_ok")
            if cm and not used_comment:
                note += "\n⚠️ Comment fallback: sent without comment (Telegram rejected message)."

            txt = f"{note}\n🎁 {gift.label} ⭐{gift.stars}"
            await safe_edit_message(bot, c, txt, reply_markup=None)

        except RuntimeError as e:
            if str(e) == "ENTITY_NOT_FOUND":
                await db_mark_failed(action_id, "ENTITY_NOT_FOUND")
                await safe_edit_message(bot, c, tr(lang, "entity_fail"), reply_markup=None)
            else:
                await db_mark_failed(action_id, str(e))
                await safe_edit_message(bot, c, f"❌ Error: {e}", reply_markup=None)
        except Exception as e:
            await db_mark_failed(action_id, str(e))
            await safe_edit_message(bot, c, f"❌ Error: {e}", reply_markup=None)
        return

    await c.answer("unknown", show_alert=True)


# =========================
# Background cleanup
# =========================
async def cleanup_loop():
    while True:
        try:
            await db_cleanup_drafts()
        except Exception as e:
            log.warning("cleanup error: %s", e)
        await asyncio.sleep(300)  # 5 min


# =========================
# MAIN
# =========================
async def main():
    log.info("BOOT: starting...")
    await db_init()
    log.info("BOOT: db ok")
    asyncio.create_task(cleanup_loop(), name="cleanup_loop")
    log.info("BOOT: polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await relayers.close_all()


if __name__ == "__main__":
    asyncio.run(main())
