import re
import requests
import cloudscraper
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, filters, CallbackQueryHandler, CommandHandler, ContextTypes

BOT_TOKEN = "8571420841:AAHy2j_GhUMRqOFDixbGhnQ6z3b6NswcU1E"
BASE_SITE = "https://www.hentai.name"
CDN_SITE = "https://pics.hentai.name"

# -------------------- Helper Functions --------------------
def log(msg):
    print(f"[LOG] {msg}")

def slugify(term):
    return re.sub(r"\s+", "-", term.strip())

import cloudscraper

def search_mangas(term, page=1):
    url = f"{BASE_SITE}/search/{slugify(term)}/?p={page}"
    log(f"Qidiruv URL: {url}")

    scraper = cloudscraper.create_scraper()  # Cloudflare bypass
    try:
        r = scraper.get(url, timeout=10)
        r.raise_for_status()
    except Exception as e:
        log(f"Qidiruv xatoligi: {e}")
        return [], None, None

    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for a in soup.select("a.cover"):
        img = a.find("img")
        caption = a.find("div", class_="caption")
        results.append({
            "link": a.get("href"),
            "title": caption.text.strip() if caption else "Noma'lum",
            "poster": img["src"] if img else None
        })

    next_page = page + 1 if soup.select("a.next") else None
    prev_page = page - 1 if page > 1 else None
    log(f"{len(results)} manga topildi. Next page: {next_page}, Prev page: {prev_page}")
    return results, next_page, prev_page
def manga_poster_url(manga_link):
    manga_id = int(manga_link.strip("/").split("/")[-1])
    first3 = str(manga_id).zfill(6)[:3]
    base_url = f"{CDN_SITE}/000/{first3}/{manga_id}"
    poster = f"{base_url}/poster_1.webp"
    log(f"Poster URL: {poster}")
    return poster

def manga_image_url(manga_link, index):
    manga_id = int(manga_link.strip("/").split("/")[-1])
    first3 = str(manga_id).zfill(6)[:3]
    base_url = f"{CDN_SITE}/000/{first3}/{manga_id}"
    url = f"{base_url}/{index+1}.webp"
    log(f"Rasm URL: {url}")
    return url

# -------------------- Sessions --------------------
sessions = {}  # chat_id -> {'results':[], 'index':0, 'page':1, 'term':str, 'message_id':int}

# -------------------- Bot Handlers --------------------
async def start(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Manga qidirish uchun nomini yozing.\n"
        "Masalan: Naruto, One Piece va boshqalar."
    )
    log(f"{update.effective_user.username} start berdi")

async def text_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    term = update.message.text.strip()
    log(f"{update.effective_user.username} qidirmoqda: {term}")
    results, next_page, prev_page = search_mangas(term)
    if not results:
        await update.message.reply_text("Hech narsa topilmadi 😔")
        return
    chat_id = update.message.chat_id
    sessions[chat_id] = {'results': results, 'index': 0, 'page':1, 'term': term}
    await send_search_results(chat_id, context, results, next_page, prev_page)

async def send_search_results(chat_id, context, results, next_page=None, prev_page=None, edit=False):
    keyboard = [[InlineKeyboardButton(r['title'], callback_data=f"select|{r['link']}")] for r in results[:10]]
    nav_buttons = []
    if prev_page: nav_buttons.append(InlineKeyboardButton("Oldingi sahifa", callback_data=f"page|{sessions[chat_id]['term']}|{prev_page}"))
    if next_page: nav_buttons.append(InlineKeyboardButton("Keyingi sahifa", callback_data=f"page|{sessions[chat_id]['term']}|{next_page}"))
    if nav_buttons: keyboard.append(nav_buttons)
    text = "Biror manga tanlang:"
    log(f"Keyboard tayyorlandi, edit={edit}")
    if edit:
        await context.bot.edit_message_text(chat_id=chat_id,
                                            message_id=sessions[chat_id]['message_id'],
                                            text=text,
                                            reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        msg = await context.bot.send_message(chat_id=chat_id, text=text,
                                             reply_markup=InlineKeyboardMarkup(keyboard))
        sessions[chat_id]['message_id'] = msg.message_id
        log(f"Yangi message yuborildi: {msg.message_id}")

async def send_manga_prompt(chat_id, context, edit=False):
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
    if edit:
        await context.bot.edit_message_media(chat_id=chat_id,
                                             message_id=session['message_id'],
                                             media={'type':'photo','media':poster},
                                             reply_markup=InlineKeyboardMarkup(keyboard))
        await context.bot.edit_message_caption(chat_id=chat_id,
                                               message_id=session['message_id'],
                                               caption=caption,
                                               reply_markup=InlineKeyboardMarkup(keyboard))
        log("Manga prompt edit qilindi")
    else:
        msg = await context.bot.send_photo(chat_id=chat_id,
                                           photo=poster,
                                           caption=caption,
                                           reply_markup=InlineKeyboardMarkup(keyboard))
        session['message_id'] = msg.message_id
        log("Manga prompt yuborildi")

async def button_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    session = sessions.get(chat_id)
    if not session:
        await q.edit_message_text("Sessiya tugagan. Iltimos, yangi nom yozing.", reply_markup=None)
        return

    data = q.data.split("|")
    log(f"Callback data: {q.data}")
    if data[0] == "read":
        manga_link = data[1]
        index = int(data[2])
        url = manga_image_url(manga_link, index)
        keyboard = [
            [
                InlineKeyboardButton("Oldingi", callback_data=f"read|{manga_link}|{index-1}" if index>0 else f"read|{manga_link}|0"),
                InlineKeyboardButton("Keyingi", callback_data=f"read|{manga_link}|{index+1}")
            ],
            [InlineKeyboardButton("To‘xtatish", callback_data="stop_reading")]
        ]
        await q.edit_message_media(
            media={'type':'photo','media':url},
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        log(f"Rasm yuborildi: {url}")

    elif data[0] == "stop_reading":
        await q.edit_message_caption("O‘qish to‘xtatildi", reply_markup=None)
        log("O‘qish to‘xtatildi")

    elif data[0] == "next_manga":
        if session['index'] + 1 < len(session['results']):
            session['index'] += 1
            await send_manga_prompt(chat_id, context, edit=True)
            log("Keyingi manga yuborildi")
        else:
            term = session['term']
            next_page = session['page'] + 1
            results, next_page_link, prev_page_link = search_mangas(term, page=next_page)
            if results:
                session['results'] = results
                session['index'] = 0
                session['page'] = next_page
                await send_manga_prompt(chat_id, context, edit=True)
                log(f"Keyingi sahifa manga yuborildi, sahifa {next_page}")
            else:
                await q.edit_message_caption("Ro'yxat tugadi.", reply_markup=None)
                log("Ro'yxat tugadi")

    elif data[0] == "select":
        manga_link = data[1]
        session['index'] = session['results'].index(next(r for r in session['results'] if r['link']==manga_link))
        await send_manga_prompt(chat_id, context, edit=True)
        log(f"Manga tanlandi: {manga_link}")

    elif data[0] == "page":
        term, page = data[1], int(data[2])
        results, next_page, prev_page = search_mangas(term, page)
        if results:
            session['results'] = results
            session['index'] = 0
            session['page'] = page
            await send_search_results(chat_id, context, results, next_page, prev_page, edit=True)
            log(f"Sahifa o'zgartirildi: {page}")
        else:
            await q.edit_message_text("Hech narsa topilmadi 😔", reply_markup=None)
            log(f"Sahifa {page} bo'sh")

# -------------------- Main --------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    log("Bot ishga tushmoqda...")
    app.run_polling()

if __name__ == "__main__":
    main()
