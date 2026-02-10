import os
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
from contextlib import asynccontextmanager

import aiosqlite
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup,
    InlineQuery, InlineQueryResultArticle,
    InputTextMessageContent,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage

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
RELAYER_SESSION = env_required("RELAYER_SESSION")

DB_PATH = os.getenv("DB_PATH", "bot.db")

# owner admin id (bosh admin)
OWNER_ID = int(os.getenv("OWNER_ID", "7440949683"))

# default language for everyone (siz xohlagan: RU)
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "ru").strip().lower()
if DEFAULT_LANG not in ("uz", "ru", "en"):
    DEFAULT_LANG = "ru"


# =========================
# i18n (minimal, clean)
# =========================
TR = {
    "ru": {
        "no_access": "⛔ Нет доступа.",
        "menu_title": "Выберите действие:",
        "target_set": "✅ Получатель сохранён.",
        "comment_set": "✅ Комментарий сохранён.",
        "comment_removed": "✅ Комментарий удалён.",
        "gift_selected": "✅ Подарок выбран.",
        "mode_show": "👤 Профиль (show name)",
        "mode_hide": "🕵️ Аноним (hide name)",
        "confirm_title": "Подтвердите отправку:",
        "btn_send": "✅ Отправить",
        "btn_cancel": "✖️ Отмена",
        "btn_back": "⬅️ Меню",
        "btn_target": "🎯 Получатель",
        "btn_comment": "💬 Комментарий",
        "btn_gift": "🎁 Подарок",
        "btn_mode": "🔒 Режим",
        "ask_target": "🎯 Укажите получателя:\n- `me`\n- `@username`\n- `user_id`\n\n✅ Надёжнее всего: @username",
        "ask_comment": "💬 Введите комментарий (необязательно).\nУдалить: `-`",
        "pick_price": "🎁 Выберите цену (⭐):",
        "sending": "⏳ Отправляю...",
        "sent": "✅ Отправлено!",
        "cancelled": "❌ Отменено",
        "creator_only": "⛔ Только автор может подтверждать/отменять.",
        "already_done": "⚠️ Уже обработано.",
        "still_sending": "⏳ Уже отправляется...",
        "inline_help_title": "Как использовать inline",
        "inline_help_text": "Формат:\n@{bot} 50 @username комментарий\n\nReply-target в inline недоступен.\nДля reply в группе: ответьте на человека и используйте /gift 50 коммент",
        "reply_target_missing": "⚠️ Target=reply, но reply не найден.\nИспользуйте /gift reply в группе или inline с @username.",
        "admin_added": "✅ Админ добавлен.",
        "admin_removed": "✅ Админ удалён.",
        "admins_list": "👮 Админы:",
        "lang_set": "✅ Язык установлен: {lang}",
        "err": "❌ Ошибка: {e}",
    },
    "uz": {
        "no_access": "⛔ Ruxsat yo‘q.",
        "menu_title": "Tanlang:",
        "target_set": "✅ Qabul qiluvchi saqlandi.",
        "comment_set": "✅ Komment saqlandi.",
        "comment_removed": "✅ Komment o‘chirildi.",
        "gift_selected": "✅ Sovg‘a tanlandi.",
        "mode_show": "👤 Profil (show name)",
        "mode_hide": "🕵️ Anonim (hide name)",
        "confirm_title": "Yuborishni tasdiqlang:",
        "btn_send": "✅ Yuborish",
        "btn_cancel": "✖️ Bekor qilish",
        "btn_back": "⬅️ Menu",
        "btn_target": "🎯 Qabul qiluvchi",
        "btn_comment": "💬 Komment",
        "btn_gift": "🎁 Sovg‘a",
        "btn_mode": "🔒 Rejim",
        "ask_target": "🎯 Qabul qiluvchini yuboring:\n- `me`\n- `@username`\n- `user_id`\n\n✅ Eng ishonchlisi: @username",
        "ask_comment": "💬 Komment yuboring (ixtiyoriy).\nO‘chirish: `-`",
        "pick_price": "🎁 Narx tanlang (⭐):",
        "sending": "⏳ Yuborilyapti...",
        "sent": "✅ Yuborildi!",
        "cancelled": "❌ Bekor qilindi",
        "creator_only": "⛔ Faqat buyruq bergan admin tasdiqlay oladi.",
        "already_done": "⚠️ Allaqachon bajarilgan.",
        "still_sending": "⏳ Allaqachon yuborilyapti...",
        "inline_help_title": "Inline ishlatish",
        "inline_help_text": "Format:\n@{bot} 50 @username komment\n\nInline’da reply-target bo‘lmaydi.\nReply uchun: guruhda odamga reply qilib /gift 50 komment",
        "reply_target_missing": "⚠️ Target=reply topilmadi.\nGuruhda /gift reply ishlating yoki inline’da @username bering.",
        "admin_added": "✅ Admin qo‘shildi.",
        "admin_removed": "✅ Admin olib tashlandi.",
        "admins_list": "👮 Adminlar:",
        "lang_set": "✅ Til o‘zgardi: {lang}",
        "err": "❌ Xatolik: {e}",
    },
    "en": {
        "no_access": "⛔ No access.",
        "menu_title": "Choose:",
        "target_set": "✅ Target saved.",
        "comment_set": "✅ Comment saved.",
        "comment_removed": "✅ Comment removed.",
        "gift_selected": "✅ Gift selected.",
        "mode_show": "👤 Profile (show name)",
        "mode_hide": "🕵️ Anonymous (hide name)",
        "confirm_title": "Confirm sending:",
        "btn_send": "✅ Send",
        "btn_cancel": "✖️ Cancel",
        "btn_back": "⬅️ Menu",
        "btn_target": "🎯 Target",
        "btn_comment": "💬 Comment",
        "btn_gift": "🎁 Gift",
        "btn_mode": "🔒 Mode",
        "ask_target": "🎯 Send target:\n- `me`\n- `@username`\n- `user_id`\n\n✅ Best: @username",
        "ask_comment": "💬 Send comment (optional).\nRemove: `-`",
        "pick_price": "🎁 Choose price (⭐):",
        "sending": "⏳ Sending...",
        "sent": "✅ Sent!",
        "cancelled": "❌ Cancelled",
        "creator_only": "⛔ Only the creator can confirm/cancel.",
        "already_done": "⚠️ Already processed.",
        "still_sending": "⏳ Already sending...",
        "inline_help_title": "How to use inline",
        "inline_help_text": "Format:\n@{bot} 50 @username comment\n\nInline cannot use reply-target.\nFor reply in group: reply to user and use /gift 50 comment",
        "reply_target_missing": "⚠️ Target=reply not found.\nUse /gift reply in group or inline with @username.",
        "admin_added": "✅ Admin added.",
        "admin_removed": "✅ Admin removed.",
        "admins_list": "👮 Admins:",
        "lang_set": "✅ Language set: {lang}",
        "err": "❌ Error: {e}",
    },
}


def tr(lang: str, key: str, **kwargs) -> str:
    lang = (lang or DEFAULT_LANG).lower()
    if lang not in TR:
        lang = DEFAULT_LANG
    s = TR[lang].get(key, TR["ru"].get(key, key))
    if kwargs:
        try:
            return s.format(**kwargs)
        except Exception:
            return s
    return s


# =========================
# Gifts (IDs hidden in UI)
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

GIFTS_BY_PRICE: Dict[int, List[GiftItem]] = {}
GIFTS_BY_ID: Dict[int, GiftItem] = {}
for g in GIFT_CATALOG:
    GIFTS_BY_PRICE.setdefault(g.stars, []).append(g)
    GIFTS_BY_ID[g.id] = g

ALLOWED_PRICES = sorted(GIFTS_BY_PRICE.keys())


def gifts_up_to(max_stars: int) -> List[GiftItem]:
    out: List[GiftItem] = []
    for g in GIFT_CATALOG:
        if g.stars <= max_stars:
            out.append(g)
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
            role TEXT NOT NULL DEFAULT 'admin',   -- owner|admin
            lang TEXT NOT NULL DEFAULT 'ru',
            target TEXT DEFAULT 'me',
            comment TEXT DEFAULT NULL,
            selected_gift_id INTEGER DEFAULT NULL,
            hide_name INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            action_id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL,
            chat_id INTEGER DEFAULT NULL,
            target TEXT NOT NULL,         -- '@user' or '123' or 'reply:chat_id:msg_id:uid:@username?'
            gift_id INTEGER NOT NULL,
            stars INTEGER NOT NULL,
            comment TEXT DEFAULT NULL,
            hide_name INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',  -- pending|sending|sent|cancelled|failed
            error TEXT DEFAULT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_actions_creator ON actions(creator_id);")
        await db.commit()

    # ensure owner exists
    async with db_connect() as db:
        now = int(time.time())
        await db.execute("INSERT OR IGNORE INTO admins(user_id, role, lang, created_at) VALUES(?,?,?,?)",
                         (OWNER_ID, "owner", DEFAULT_LANG, now))
        await db.commit()


async def db_get_admin(user_id: int) -> Optional[dict]:
    async with db_connect() as db:
        cur = await db.execute(
            "SELECT user_id, role, lang, target, comment, selected_gift_id, hide_name FROM admins WHERE user_id=?",
            (user_id,)
        )
        r = await cur.fetchone()
        if not r:
            return None
        return {
            "user_id": r[0],
            "role": r[1],
            "lang": r[2],
            "target": r[3] or "me",
            "comment": r[4],
            "selected_gift_id": r[5],
            "hide_name": int(r[6] or 0),
        }


async def db_is_owner(user_id: int) -> bool:
    a = await db_get_admin(user_id)
    return bool(a and a["role"] == "owner")


async def db_add_admin(user_id: int, role: str = "admin", lang: str = None):
    now = int(time.time())
    lang = (lang or DEFAULT_LANG).lower()
    if lang not in ("uz", "ru", "en"):
        lang = DEFAULT_LANG
    async with db_connect() as db:
        await db.execute(
            "INSERT OR REPLACE INTO admins(user_id, role, lang, created_at) VALUES(?,?,?,?)",
            (user_id, role, lang, now)
        )
        await db.commit()


async def db_remove_admin(user_id: int):
    async with db_connect() as db:
        await db.execute("DELETE FROM admins WHERE user_id=? AND role!='owner'", (user_id,))
        await db.commit()


async def db_list_admins() -> List[dict]:
    async with db_connect() as db:
        cur = await db.execute("SELECT user_id, role, lang FROM admins ORDER BY role DESC, user_id ASC")
        rows = await cur.fetchall()
    return [{"user_id": r[0], "role": r[1], "lang": r[2]} for r in rows]


async def db_set_admin_lang(user_id: int, lang: str):
    lang = (lang or DEFAULT_LANG).lower()
    if lang not in ("uz", "ru", "en"):
        lang = DEFAULT_LANG
    async with db_connect() as db:
        await db.execute("UPDATE admins SET lang=? WHERE user_id=?", (lang, user_id))
        await db.commit()


async def db_set_target(user_id: int, target: str):
    async with db_connect() as db:
        await db.execute("UPDATE admins SET target=? WHERE user_id=?", (target, user_id))
        await db.commit()


async def db_set_comment(user_id: int, comment: Optional[str]):
    async with db_connect() as db:
        await db.execute("UPDATE admins SET comment=? WHERE user_id=?", (comment, user_id))
        await db.commit()


async def db_set_selected_gift(user_id: int, gift_id: Optional[int]):
    async with db_connect() as db:
        await db.execute("UPDATE admins SET selected_gift_id=? WHERE user_id=?", (gift_id, user_id))
        await db.commit()


async def db_toggle_hide_name(user_id: int) -> int:
    async with db_connect() as db:
        cur = await db.execute("SELECT hide_name FROM admins WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        cur_val = int((r[0] if r else 0) or 0)
        new_val = 0 if cur_val == 1 else 1
        await db.execute("UPDATE admins SET hide_name=? WHERE user_id=?", (new_val, user_id))
        await db.commit()
        return new_val


async def db_create_action(
    creator_id: int,
    chat_id: Optional[int],
    target: str,
    gift: GiftItem,
    comment: Optional[str],
    hide_name: int
) -> int:
    now = int(time.time())
    async with db_connect() as db:
        cur = await db.execute("""
            INSERT INTO actions(creator_id, chat_id, target, gift_id, stars, comment, hide_name, status, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (creator_id, chat_id, target, gift.id, gift.stars, comment, hide_name, "pending", now, now))
        await db.commit()
        return int(cur.lastrowid)


async def db_get_action(action_id: int) -> Optional[dict]:
    async with db_connect() as db:
        cur = await db.execute("""
            SELECT action_id, creator_id, chat_id, target, gift_id, stars, comment, hide_name, status, error
            FROM actions WHERE action_id=?
        """, (action_id,))
        r = await cur.fetchone()
        if not r:
            return None
        return {
            "action_id": r[0],
            "creator_id": r[1],
            "chat_id": r[2],
            "target": r[3],
            "gift_id": r[4],
            "stars": r[5],
            "comment": r[6],
            "hide_name": int(r[7] or 0),
            "status": r[8],
            "error": r[9],
        }


async def db_try_lock_sending(action_id: int) -> Tuple[bool, str]:
    """
    atomically switch pending -> sending
    returns (ok, status)
    """
    now = int(time.time())
    async with db_connect() as db:
        cur = await db.execute("SELECT status FROM actions WHERE action_id=?", (action_id,))
        row = await cur.fetchone()
        if not row:
            return False, "missing"
        status = row[0]
        if status == "sending":
            return False, "sending"
        if status != "pending":
            return False, status

        await db.execute("""
            UPDATE actions SET status='sending', updated_at=? 
            WHERE action_id=? AND status='pending'
        """, (now, action_id))
        await db.commit()

        # verify updated
        cur2 = await db.execute("SELECT status FROM actions WHERE action_id=?", (action_id,))
        row2 = await cur2.fetchone()
        new_status = row2[0] if row2 else "missing"
        return (new_status == "sending"), new_status


async def db_mark_action(action_id: int, status: str, error: Optional[str] = None):
    now = int(time.time())
    async with db_connect() as db:
        await db.execute("""
            UPDATE actions SET status=?, error=?, updated_at=? WHERE action_id=?
        """, (status, error, now, action_id))
        await db.commit()


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


def safe_comment(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    t = (text or "").strip()
    if not t:
        return None
    if len(t) > 250:
        t = t[:250]
    return t


def fmt_gift(g: GiftItem) -> str:
    # ID ko'rsatmaymiz
    return f"{g.label}  ⭐{g.stars}"


def fmt_mode(lang: str, hide_name: int) -> str:
    return tr(lang, "mode_hide") if hide_name == 1 else tr(lang, "mode_show")


def parse_inline_query(q: str) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """
    INLINE format (target required):
      "50 @username comment..."
      "50 123456 comment..."
      "50 me comment..."
    """
    q = (q or "").strip()
    if not q:
        return None, None, None

    parts = q.split()
    if not parts[0].isdigit():
        return None, None, None

    max_stars = int(parts[0])
    if len(parts) < 2:
        return max_stars, None, None

    target_raw = parts[1].strip()
    if not (target_raw.startswith("@") or target_raw.isdigit() or target_raw.lower() == "me"):
        return max_stars, None, safe_comment(" ".join(parts[1:]))

    target = normalize_target(target_raw)
    comment = safe_comment(" ".join(parts[2:]) if len(parts) >= 3 else None)
    return max_stars, target, comment


# =========================
# Telethon Relayer
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
        Returns True if comment attached, False if fallback comment-less send happened.
        """
        async with self._lock:
            can = await self.client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")

            try:
                peer = await self.client.get_input_entity(target)
            except Exception:
                # user_id ba'zan ishlamaydi
                raise RuntimeError("Cannot resolve target. Use @username or receiver should message relayer once.")

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
                # comment invalid => retry without comment
                if "STARGIFT_MESSAGE_INVALID" in str(e):
                    await _try_send(None)
                    return False
                raise


# =========================
# Bot UI (inline keyboards)
# =========================
def menu_kb(lang: str, hide_name: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=tr(lang, "btn_target"), callback_data="menu:target")
    kb.button(text=tr(lang, "btn_comment"), callback_data="menu:comment")
    kb.button(text=tr(lang, "btn_gift"), callback_data="menu:gift")
    kb.button(text=f"{tr(lang, 'btn_mode')} · {fmt_mode(lang, hide_name)}", callback_data="menu:mode")
    kb.adjust(2, 2)
    return kb.as_markup()


def back_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=tr(lang, "btn_back"), callback_data="menu:home")
    return kb.as_markup()


def price_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in ALLOWED_PRICES:
        kb.button(text=f"⭐ {p}", callback_data=f"price:{p}")
    kb.button(text=tr(lang, "btn_back"), callback_data="menu:home")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def gifts_kb(lang: str, price: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in GIFTS_BY_PRICE.get(price, []):
        kb.button(text=f"{g.label} ⭐{g.stars}", callback_data=f"gift:{g.id}")
    kb.button(text=tr(lang, "btn_back"), callback_data="menu:gift")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def action_kb(lang: str, action_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=tr(lang, "btn_send"), callback_data=f"act:send:{action_id}")
    kb.button(text=tr(lang, "btn_cancel"), callback_data=f"act:cancel:{action_id}")
    kb.adjust(2)
    return kb.as_markup()


# =========================
# Safe edit (fix “message is not modified” + clear markup)
# =========================
async def safe_edit(c: CallbackQuery, text: str, reply_markup: Optional[InlineKeyboardMarkup]):
    try:
        if c.message:
            await c.message.edit_text(text, reply_markup=reply_markup)
            if reply_markup is None:
                # some clients keep old markup, so clear again
                try:
                    await c.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass
        else:
            await bot.edit_message_text(inline_message_id=c.inline_message_id, text=text, reply_markup=reply_markup)
            if reply_markup is None:
                try:
                    await bot.edit_message_reply_markup(inline_message_id=c.inline_message_id, reply_markup=None)
                except Exception:
                    pass
    except Exception as e:
        if "message is not modified" in str(e):
            return
        raise


# =========================
# Render status
# =========================
async def render_status(admin: dict) -> str:
    lang = admin["lang"]
    target = admin["target"]
    comment = admin["comment"]
    hide_name = admin["hide_name"]
    sel = admin["selected_gift_id"]

    gift_txt = "(not selected)"
    if sel and sel in GIFTS_BY_ID:
        gift_txt = fmt_gift(GIFTS_BY_ID[sel])

    cm = comment if comment else "(no comment)"
    mode_txt = fmt_mode(lang, hide_name)

    return (
        f"{tr(lang, 'menu_title')}\n\n"
        f"🎁 {gift_txt}\n"
        f"🎯 {target}\n"
        f"🔒 {mode_txt}\n"
        f"💬 {cm}\n"
    )


# =========================
# App objects
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
relayer = Relayer()


# =========================
# Access guard
# =========================
async def require_admin(user_id: int) -> Optional[dict]:
    return await db_get_admin(user_id)


# =========================
# Commands
# =========================
@dp.message(Command("start"))
async def cmd_start(m: Message):
    a = await require_admin(m.from_user.id)
    if not a:
        return await m.answer(tr(DEFAULT_LANG, "no_access"))

    text = await render_status(a)
    await m.answer(text, reply_markup=menu_kb(a["lang"], a["hide_name"]))


@dp.message(Command("menu"))
async def cmd_menu(m: Message):
    a = await require_admin(m.from_user.id)
    if not a:
        return await m.answer(tr(DEFAULT_LANG, "no_access"))

    text = await render_status(a)
    await m.answer(text, reply_markup=menu_kb(a["lang"], a["hide_name"]))


@dp.message(Command("lang"))
async def cmd_lang(m: Message):
    a = await require_admin(m.from_user.id)
    if not a:
        return await m.answer(tr(DEFAULT_LANG, "no_access"))

    parts = (m.text or "").split()
    if len(parts) < 2:
        return await m.answer("Usage: /lang uz|ru|en")

    new_lang = parts[1].strip().lower()
    await db_set_admin_lang(m.from_user.id, new_lang)
    a = await db_get_admin(m.from_user.id)
    await m.answer(tr(a["lang"], "lang_set", lang=new_lang))


# Owner admin management
@dp.message(Command("admins"))
async def cmd_admins(m: Message):
    a = await require_admin(m.from_user.id)
    if not a:
        return await m.answer(tr(DEFAULT_LANG, "no_access"))

    rows = await db_list_admins()
    lines = [tr(a["lang"], "admins_list")]
    for r in rows:
        lines.append(f"- {r['user_id']} ({r['role']}, {r['lang']})")
    await m.answer("\n".join(lines))


@dp.message(Command("admin_add"))
async def cmd_admin_add(m: Message):
    if not await db_is_owner(m.from_user.id):
        return await m.answer(tr(DEFAULT_LANG, "no_access"))

    uid = None
    if m.reply_to_message and m.reply_to_message.from_user:
        uid = m.reply_to_message.from_user.id
    else:
        parts = (m.text or "").split()
        if len(parts) >= 2 and parts[1].isdigit():
            uid = int(parts[1])

    if not uid:
        return await m.answer("Usage: reply to user + /admin_add  OR /admin_add <user_id>")

    await db_add_admin(uid, role="admin", lang=DEFAULT_LANG)
    await m.answer(tr(DEFAULT_LANG, "admin_added") + f" ({uid})")


@dp.message(Command("admin_del"))
async def cmd_admin_del(m: Message):
    if not await db_is_owner(m.from_user.id):
        return await m.answer(tr(DEFAULT_LANG, "no_access"))

    uid = None
    if m.reply_to_message and m.reply_to_message.from_user:
        uid = m.reply_to_message.from_user.id
    else:
        parts = (m.text or "").split()
        if len(parts) >= 2 and parts[1].isdigit():
            uid = int(parts[1])

    if not uid:
        return await m.answer("Usage: reply to user + /admin_del  OR /admin_del <user_id>")

    await db_remove_admin(uid)
    await m.answer(tr(DEFAULT_LANG, "admin_removed") + f" ({uid})")


# Group-friendly command: reply to someone and send gift
@dp.message(Command("gift"))
async def cmd_gift(m: Message):
    a = await require_admin(m.from_user.id)
    if not a:
        return

    lang = a["lang"]

    # /gift <max_stars> [target] [comment...]
    parts = (m.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await m.answer("Usage: /gift 50 [@username|id|me] [comment...]")

    max_stars = int(parts[1])
    target: Optional[str] = None
    comment: Optional[str] = None

    if len(parts) >= 3:
        # if 3rd looks like target
        t = parts[2].strip()
        if t.startswith("@") or t.isdigit() or t.lower() == "me":
            target = normalize_target(t)
            comment = safe_comment(" ".join(parts[3:]) if len(parts) >= 4 else None)
        else:
            comment = safe_comment(" ".join(parts[2:]))

    # reply target if no explicit target
    if not target and m.reply_to_message and m.reply_to_message.from_user:
        ru = m.reply_to_message.from_user
        if ru.username:
            target = f"@{ru.username}"
        else:
            target = str(ru.id)

    if not target:
        return await m.answer(tr(lang, "reply_target_missing"))

    gifts = gifts_up_to(max_stars)
    if not gifts:
        return await m.answer("No gifts for that stars limit.")

    # pick cheapest by default (or you can improve: show list)
    gift = gifts[0]

    act_id = await db_create_action(
        creator_id=m.from_user.id,
        chat_id=m.chat.id,
        target=target,
        gift=gift,
        comment=comment,
        hide_name=a["hide_name"],
    )

    cm = comment if comment else "(no comment)"
    msg = (
        f"🎁 {fmt_gift(gift)}\n"
        f"🎯 {target}\n"
        f"🔒 {fmt_mode(lang, a['hide_name'])}\n"
        f"💬 {cm}\n\n"
        f"{tr(lang, 'confirm_title')}"
    )
    await m.answer(msg, reply_markup=action_kb(lang, act_id))


# =========================
# Menu callbacks
# =========================
@dp.callback_query(F.data.startswith("menu:"))
async def menu_router(c: CallbackQuery):
    a = await require_admin(c.from_user.id)
    if not a:
        return await c.answer(tr(DEFAULT_LANG, "no_access"), show_alert=True)

    lang = a["lang"]
    cmd = c.data.split(":", 1)[1]

    await c.answer()

    if cmd == "home":
        await safe_edit(c, await render_status(a), menu_kb(lang, a["hide_name"]))
        return

    if cmd == "target":
        await safe_edit(c, tr(lang, "ask_target"), back_kb(lang))
        return

    if cmd == "comment":
        await safe_edit(c, tr(lang, "ask_comment"), back_kb(lang))
        return

    if cmd == "gift":
        await safe_edit(c, tr(lang, "pick_price"), price_kb(lang))
        return

    if cmd == "mode":
        new_val = await db_toggle_hide_name(c.from_user.id)
        a2 = await db_get_admin(c.from_user.id)
        await safe_edit(c, await render_status(a2), menu_kb(lang, a2["hide_name"]))
        return


# Target/comment input (simple: user writes text after pressing)
@dp.message()
async def any_text_router(m: Message):
    a = await require_admin(m.from_user.id)
    if not a:
        return

    # Heuristic:
    # If message starts with "@" or "me" or digit -> treat as target update
    # If message is "-" -> remove comment
    # Else -> treat as comment update
    txt = (m.text or "").strip()
    lang = a["lang"]

    if not txt:
        return

    if txt == "-":
        await db_set_comment(m.from_user.id, None)
        a2 = await db_get_admin(m.from_user.id)
        return await m.answer(tr(lang, "comment_removed") + "\n\n" + await render_status(a2),
                              reply_markup=menu_kb(lang, a2["hide_name"]))

    if txt.lower() == "me" or txt.startswith("@") or txt.isdigit():
        await db_set_target(m.from_user.id, normalize_target(txt))
        a2 = await db_get_admin(m.from_user.id)
        return await m.answer(tr(lang, "target_set") + "\n\n" + await render_status(a2),
                              reply_markup=menu_kb(lang, a2["hide_name"]))

    await db_set_comment(m.from_user.id, safe_comment(txt))
    a2 = await db_get_admin(m.from_user.id)
    return await m.answer(tr(lang, "comment_set") + "\n\n" + await render_status(a2),
                          reply_markup=menu_kb(lang, a2["hide_name"]))


# =========================
# Price/Gift selection callbacks
# =========================
@dp.callback_query(F.data.startswith("price:"))
async def cb_price(c: CallbackQuery):
    a = await require_admin(c.from_user.id)
    if not a:
        return await c.answer(tr(DEFAULT_LANG, "no_access"), show_alert=True)

    lang = a["lang"]
    await c.answer()
    price = int(c.data.split(":", 1)[1])
    if price not in GIFTS_BY_PRICE:
        return await safe_edit(c, tr(lang, "pick_price"), price_kb(lang))
    await safe_edit(c, f"⭐ {price}", gifts_kb(lang, price))


@dp.callback_query(F.data.startswith("gift:"))
async def cb_gift(c: CallbackQuery):
    a = await require_admin(c.from_user.id)
    if not a:
        return await c.answer(tr(DEFAULT_LANG, "no_access"), show_alert=True)

    lang = a["lang"]
    await c.answer()

    gid = int(c.data.split(":", 1)[1])
    if gid not in GIFTS_BY_ID:
        return await safe_edit(c, tr(lang, "pick_price"), price_kb(lang))

    await db_set_selected_gift(c.from_user.id, gid)
    a2 = await db_get_admin(c.from_user.id)

    g = GIFTS_BY_ID[gid]
    txt = f"{tr(lang, 'gift_selected')}\n\n🎁 {fmt_gift(g)}\n\n{tr(lang, 'menu_title')}"
    await safe_edit(c, txt, menu_kb(lang, a2["hide_name"]))


# =========================
# Inline mode (admins only)
# =========================
INLINE_LIMIT = 30


@dp.inline_query()
async def inline_handler(q: InlineQuery):
    a = await db_get_admin(q.from_user.id)
    if not a:
        return await q.answer([], is_personal=True, cache_time=1)

    lang = a["lang"]
    bot_me = await bot.get_me()

    max_stars, target, comment = parse_inline_query(q.query)

    # target majburiy
    if not max_stars or not target:
        help_res = InlineQueryResultArticle(
            id="help",
            title=tr(lang, "inline_help_title"),
            input_message_content=InputTextMessageContent(
                message_text=tr(lang, "inline_help_text", bot=bot_me.username)
            ),
        )
        return await q.answer([help_res], is_personal=True, cache_time=1)

    gifts = gifts_up_to(max_stars)[:INLINE_LIMIT]
    results: List[InlineQueryResultArticle] = []

    for g in gifts:
        action_id = await db_create_action(
            creator_id=q.from_user.id,
            chat_id=None,
            target=target,
            gift=g,
            comment=comment,
            hide_name=a["hide_name"],
        )

        cm = comment if comment else "(no comment)"
        msg = (
            f"🎁 {fmt_gift(g)}\n"
            f"🎯 {target}\n"
            f"🔒 {fmt_mode(lang, a['hide_name'])}\n"
            f"💬 {cm}\n\n"
            f"{tr(lang, 'confirm_title')}"
        )

        results.append(
            InlineQueryResultArticle(
                id=str(action_id),
                title=f"{g.label} ⭐{g.stars}",
                description=f"target: {target}",
                input_message_content=InputTextMessageContent(message_text=msg),
                reply_markup=action_kb(lang, action_id),
            )
        )

    await q.answer(results, is_personal=True, cache_time=1)


# =========================
# Action callbacks (send/cancel)
# =========================
@dp.callback_query(F.data.startswith("act:"))
async def action_callback(c: CallbackQuery):
    a = await require_admin(c.from_user.id)
    if not a:
        return await c.answer(tr(DEFAULT_LANG, "no_access"), show_alert=True)

    lang = a["lang"]
    await c.answer()

    _, cmd, sid = c.data.split(":", 2)
    action_id = int(sid)

    act = await db_get_action(action_id)
    if not act:
        return await c.answer(tr(lang, "already_done"), show_alert=True)

    # STRICT: only creator can send/cancel
    if act["creator_id"] != c.from_user.id:
        return await c.answer(tr(lang, "creator_only"), show_alert=True)

    gift = GIFTS_BY_ID.get(act["gift_id"])
    if not gift:
        await db_mark_action(action_id, "failed", error="Gift not in catalog")
        return await safe_edit(c, tr(lang, "err", e="Gift not found"), reply_markup=None)

    if cmd == "cancel":
        if act["status"] != "pending":
            return await c.answer(tr(lang, "already_done"), show_alert=True)

        await db_mark_action(action_id, "cancelled", error=None)
        txt = f"{tr(lang, 'cancelled')} ✅\n\n🎁 {fmt_gift(gift)}"
        return await safe_edit(c, txt, reply_markup=None)

    if cmd == "send":
        ok, st = await db_try_lock_sending(action_id)
        if not ok:
            if st == "sending":
                return await c.answer(tr(lang, "still_sending"), show_alert=False)
            return await c.answer(tr(lang, "already_done"), show_alert=True)

        # show sending
        target_str = act["target"]
        cm = act["comment"] if act["comment"] else "(no comment)"
        sending_text = (
            f"{tr(lang, 'sending')}\n\n"
            f"🎁 {fmt_gift(gift)}\n"
            f"🎯 {target_str}\n"
            f"🔒 {fmt_mode(lang, act['hide_name'])}\n"
            f"💬 {cm}"
        )
        await safe_edit(c, sending_text, reply_markup=None)

        # Resolve target
        target_val: Union[str, int]
        if target_str.lower() == "me":
            # fallback
            if c.from_user.username:
                target_val = f"@{c.from_user.username}"
            else:
                target_val = c.from_user.id
        elif target_str.startswith("@"):
            target_val = target_str
        elif target_str.isdigit():
            target_val = int(target_str)
        else:
            target_val = target_str

        try:
            comment_attached = await relayer.send_star_gift(
                target=target_val,
                gift=gift,
                comment=act["comment"],
                hide_name=(act["hide_name"] == 1),
            )
            await db_mark_action(action_id, "sent", error=None)

            final = (
                f"{tr(lang, 'sent')}\n\n"
                f"🎁 {fmt_gift(gift)}\n"
                f"🎯 {target_str}\n"
                f"🔒 {fmt_mode(lang, act['hide_name'])}\n"
            )
            if act["comment"]:
                final += f"💬 {act['comment']}\n"
                if not comment_attached:
                    final += "⚠️ comment rejected by Telegram (sent without comment)\n"

            await safe_edit(c, final, reply_markup=None)

        except Exception as e:
            await db_mark_action(action_id, "failed", error=str(e))
            await safe_edit(c, tr(lang, "err", e=str(e)), reply_markup=None)


# =========================
# Main
# =========================
async def main():
    log.info("BOOT: starting...")
    await db_init()
    log.info("BOOT: db_init OK")

    me = await relayer.start()
    log.info("Relayer OK | id=%s username=%s", getattr(me, "id", None), getattr(me, "username", None))

    try:
        log.info("Polling...")
        await dp.start_polling(bot)
    finally:
        await relayer.stop()


if __name__ == "__main__":
    asyncio.run(main())
