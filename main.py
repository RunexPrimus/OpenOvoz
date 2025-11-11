# bot_cloudscraper.py
import re
import asyncio
import cloudscraper
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, filters,
    CallbackQueryHandler, CommandHandler, ContextTypes
)

# ---------- CONFIG ---------
BOT_TOKEN = "8527838419:AAGIMFOGAYM15BDA8Kk4LFxhrm-kKJC-L38"
BASE_SITE = "https://www.hentai.name"    # yoki https://www.manga.name — kerakiga qarab o'zgartiring
CDN_SITE  = "https://pics.hentai.name"

# OPTIONAL: agar siz brauzerdan olingan cookie'larni ishlatmoqchi bo'lsangiz shu yerga qo'ying.
# Eslatma: cookie'lar vaqt o'tishi bilan yaroqsiz bo'lishi mumkin — yangilang.
DEFAULT_COOKIES = {
    "_pk_id.2.80ff": "87d72b757c3ed68d.1762794922.",
    "_pk_ses.2.80ff": "1",
    "fpestid": "1YfG3OViYhbVVBMnTEmU-tCxiSzFsA_kQwRqNkeTg5lAtAjaJHg_bYElnL932lO5wzouAw"
}

# Kuchli headers (brauzerga o'xshash)
DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/142.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8,uz;q=0.7",
    "Referer": BASE_SITE + "/",
    "Origin": BASE_SITE,
    # sec-ch headers (Cloudflare-aware)
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}

# ---------- Logging helper ----------
def log(msg: str):
    print(f"[LOG] {msg}")

# ---------- Utilities ----------
def slugify(term: str) -> str:
    return re.sub(r"\s+", "-", term.strip())

def manga_poster_url(manga_link: str) -> str:
    manga_id = int(manga_link.strip("/").split("/")[-1])
    first3 = str(manga_id).zfill(6)[:3]
    return f"{CDN_SITE}/000/{first3}/{manga_id}/poster_1.webp"

def manga_image_url(manga_link: str, index: int) -> str:
    manga_id = int(manga_link.strip("/").split("/")[-1])
    first3 = str(manga_id).zfill(6)[:3]
    return f"{CDN_SITE}/000/{first3}/{manga_id}/{index+1}.webp"

# ---------- Network / Scraping (sync) ----------
def _search_mangas_sync(term: str, page: int = 1,
                        headers: dict = None, cookies: dict = None):
    """
    Blocking function that performs HTTP fetch + parsing.
    Returns (results list, next_page_or_None, prev_page_or_None)
    """
    url = f"{BASE_SITE}/search/{slugify(term)}/?p={page}"
    log(f"Qidiruv URL: {url}")
    headers = headers or DEFAULT_HEADERS
    cookies = cookies or DEFAULT_COOKIES

    # cloudscraper create – bypass Cloudflare JS challenges in many cases
    scraper = cloudscraper.create_scraper()  # you can pass browser=... if needed
    try:
        r = scraper.get(url, headers=headers, cookies=cookies, timeout=15)
        # raise_for_status to convert 403/5xx into exceptions we can catch
        r.raise_for_status()
    except Exception as e:
        log(f"Qidiruv xatoligi: {e}")
        return [], None, None

    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    # find anchor elements that represent covers (page-specific; may need adjusting)
    for a in soup.select("a.cover"):
        img = a.find("img")
        caption = a.find("div", class_="caption")
        link = a.get("href")
        # Normalize link: some sites return relative hrefs
        if link and link.startswith("/"):
            link = BASE_SITE.rstrip("/") + link
        results.append({
            "link": link,
            "title": caption.text.strip() if caption else "Noma'lum",
            "poster": img["src"] if img and img.get("src") else None
        })
    # detect pagination buttons (site-specific)
    next_page = page + 1 if soup.select("a.next") else None
    prev_page = page - 1 if page > 1 else None
    log(f"{len(results)} manga topildi. Next page: {next_page}, Prev page: {prev_page}")
    return results, next_page, prev_page

# Async wrapper so we don't block the event loop
async def search_mangas(term: str, page: int = 1, headers: dict = None, cookies: dict = None):
    return await asyncio.to_thread(_search_mangas_sync, term, page, headers, cookies)

# ---------- Bot session store ----------
# sessions: chat_id -> {'results':[], 'index':0, 'page':1, 'term':str, 'message_id':int}
sessions = {}

# ---------- Bot Handlers (async) ----------
async def start(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Manga qidirish uchun nom yozing (masalan: Naruto).\n"
        "Qidiruvni yuborganingizdan so‘ng 5–10 ta natija chiqadi, tanlang."
    )
    log(f"{update.effective_user.id} start berdi")

async def text_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    term = update.message.text.strip()
    chat_id = update.message.chat_id
    log(f"{update.effective_user.id} qidirmoqda: {term}")

    # call blocking search in thread
    results, next_page, prev_page = await search_mangas(term, page=1)
    if not results:
        await update.message.reply_text("Hech narsa topilmadi 😔 (Cloudflare yoki sayt strukturasini tekshiring)")
        return

    sessions[chat_id] = {'results': results, 'index': 0, 'page': 1, 'term': term, 'message_id': None}
    await send_search_results(chat_id, context, results, next_page, prev_page)

async def send_search_results(chat_id: int, context: ContextTypes.DEFAULT_TYPE,
                              results: list, next_page=None, prev_page=None, edit=False):
    # prepare keyboard (first 10)
    keyboard = []
    for r in results[:10]:
        # callback_data include full link (safe because we never eval it) — if too long, use index mapping
        keyboard.append([InlineKeyboardButton(r['title'] or "Noma'lum", callback_data=f"select|{r['link']}")])
    nav_buttons = []
    if prev_page:
        nav_buttons.append(InlineKeyboardButton("Oldingi sahifa", callback_data=f"page|{sessions[chat_id]['term']}|{prev_page}"))
    if next_page:
        nav_buttons.append(InlineKeyboardButton("Keyingi sahifa", callback_data=f"page|{sessions[chat_id]['term']}|{next_page}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    text = "Biror manga tanlang:"
    log(f"Keyboard tayyorlandi, edit={edit}")
    if edit and sessions[chat_id].get('message_id'):
        try:
            await context.bot.edit_message_text(chat_id=chat_id,
                                                message_id=sessions[chat_id]['message_id'],
                                                text=text,
                                                reply_markup=InlineKeyboardMarkup(keyboard))
            log("Search results edited")
        except Exception as e:
            log(f"Edit search results failed: {e}")
    else:
        msg = await context.bot.send_message(chat_id=chat_id, text=text,
                                             reply_markup=InlineKeyboardMarkup(keyboard))
        sessions[chat_id]['message_id'] = msg.message_id
        log(f"Yangi message yuborildi: {msg.message_id}")

async def send_manga_prompt(chat_id: int, context: ContextTypes.DEFAULT_TYPE, edit=False):
    session = sessions[chat_id]
    index = session['index']
    manga = session['results'][index]
    poster = manga_poster_url(manga['link'])
    caption = f"{manga['title']}\nO‘qishni boshlamoqchimisiz?"
    keyboard = [
        [
            InlineKeyboardButton("Ha", callback_data=f"read|{manga['link']}|0"),
            InlineKeyboardButton("Yo'q", callback_data="next_manga")
        ]
    ]
    if edit and session.get('message_id'):
        try:
            await context.bot.edit_message_media(chat_id=chat_id,
                                                 message_id=session['message_id'],
                                                 media={'type': 'photo', 'media': poster},
                                                 reply_markup=InlineKeyboardMarkup(keyboard))
            await context.bot.edit_message_caption(chat_id=chat_id,
                                                   message_id=session['message_id'],
                                                   caption=caption,
                                                   reply_markup=InlineKeyboardMarkup(keyboard))
            log("Manga prompt edit qilindi")
        except Exception as e:
            log(f"Edit manga prompt failed: {e}")
    else:
        msg = await context.bot.send_photo(chat_id=chat_id, photo=poster,
                                           caption=caption, reply_markup=InlineKeyboardMarkup(keyboard))
        session['message_id'] = msg.message_id
        log(f"Manga prompt yuborildi (message_id={msg.message_id})")

async def button_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat.id if q.message else q.from_user.id
    session = sessions.get(chat_id)
    if not session:
        try:
            await q.edit_message_text("Sessiya tugagan. Iltimos, yangi nom yozing.", reply_markup=None)
        except Exception:
            pass
        log("Sessiya topilmadi")
        return

    data = q.data.split("|")
    log(f"Callback data: {q.data}")

    if data[0] == "read":
        manga_link = data[1]
        index = int(data[2])
        url = manga_image_url(manga_link, index)
        keyboard = [
            [
                InlineKeyboardButton("Oldingi", callback_data=f"read|{manga_link}|{index-1}" if index > 0 else f"read|{manga_link}|0"),
                InlineKeyboardButton("Keyingi", callback_data=f"read|{manga_link}|{index+1}")
            ],
            [InlineKeyboardButton("To‘xtatish", callback_data="stop_reading")]
        ]
        try:
            await q.edit_message_media(media={'type': 'photo', 'media': url},
                                       reply_markup=InlineKeyboardMarkup(keyboard))
            log(f"Rasm yuborildi: {url}")
        except Exception as e:
            log(f"edit_message_media failed: {e}")
            await q.edit_message_caption("Rasmni olishda xatolik yuz berdi.", reply_markup=None)

    elif data[0] == "stop_reading":
        try:
            await q.edit_message_caption("O‘qish to‘xtatildi", reply_markup=None)
        except Exception:
            pass
        log("O‘qish to‘xtatildi")

    elif data[0] == "next_manga":
        # agar lokal ro'yxatda yana manga bo'lsa -> ko'rsat
        if session['index'] + 1 < len(session['results']):
            session['index'] += 1
            await send_manga_prompt(chat_id, context, edit=True)
            log("Keyingi manga yuborildi (xuddi ro'yxat ichida)")
            return

        # aks holda sahifa oxiri -> keyingi sahifani yuklash
        term = session['term']
        next_page = session['page'] + 1
        log(f"Sahifa oxiri — keyingi sahifa ({next_page}) yuklanmoqda...")
        results, next_page_link, prev_page_link = await search_mangas(term, page=next_page)
        if results:
            session['results'] = results
            session['index'] = 0
            session['page'] = next_page
            await send_manga_prompt(chat_id, context, edit=True)
            log(f"Keyingi sahifa manga yuborildi, sahifa {next_page}")
        else:
            try:
                await q.edit_message_caption("Ro'yxat tugadi.", reply_markup=None)
            except Exception:
                pass
            log("Ro'yxat tugadi (hech yangi sahifa topilmadi)")

    elif data[0] == "select":
        # user select qildi — topilgan ro'yxatdan linkni tanlab index'ga o'rnatamiz
        manga_link = data[1]
        # normalize link same as stored: ensure we compare consistent strings
        # stored results may contain absolute URLs, ensure comparison matches
        found_index = None
        for i, r in enumerate(session['results']):
            if r.get('link') == manga_link or r.get('link', '').endswith(manga_link):
                found_index = i
                break
        if found_index is None:
            # try to refresh current page results (rare)
            log("Tanlangan manga topilmadi, sahifani qayta yuklaymiz...")
            term = session['term']
            page = session.get('page', 1)
            results, next_page, prev_page = await search_mangas(term, page=page)
            if not results:
                await q.edit_message_text("Hech narsa topilmadi 😔", reply_markup=None)
                return
            session['results'] = results
            # try find again
            for i, r in enumerate(session['results']):
                if r.get('link') == manga_link or r.get('link', '').endswith(manga_link):
                    found_index = i
                    break
        if found_index is None:
            # fallback: set to 0
            found_index = 0
        session['index'] = found_index
        await send_manga_prompt(chat_id, context, edit=True)
        log(f"Manga tanlandi va prompt yuborildi: index={found_index}")

    elif data[0] == "page":
        term, page = data[1], int(data[2])
        results, next_page, prev_page = await search_mangas(term, page)
        if results:
            session['results'] = results
            session['index'] = 0
            session['page'] = page
            await send_search_results(chat_id, context, results, next_page, prev_page, edit=True)
            log(f"Sahifa o'zgartirildi: {page}")
        else:
            try:
                await q.edit_message_text("Hech narsa topilmadi 😔", reply_markup=None)
            except Exception:
                pass
            log(f"Sahifa {page} bo'sh")

# ---------- Main ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    log("Bot ishga tushmoqda...")
    app.run_polling()

if __name__ == "__main__":
    main()
