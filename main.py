import re
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, filters, CallbackQueryHandler, CommandHandler, ContextTypes

BOT_TOKEN = "8571420841:AAHy2j_GhUMRqOFDixbGhnQ6z3b6NswcU1E"
BASE_SITE = "https://www.hentai.name"
CDN_SITE = "https://pics.hentai.name"

# -------------------- Helper Functions --------------------
def slugify(term):
    return re.sub(r"\s+", "-", term.strip())

def search_mangas(term, page=1):
    url = f"{BASE_SITE}/search/{slugify(term)}/?p={page}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception:
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
    return results, next_page, prev_page

def manga_poster_url(manga_link):
    manga_id = int(manga_link.strip("/").split("/")[-1])
    first3 = str(manga_id).zfill(6)[:3]
    base_url = f"{CDN_SITE}/000/{first3}/{manga_id}"
    poster = f"{base_url}/poster_1.webp"
    return poster

def manga_image_url(manga_link, index):
    manga_id = int(manga_link.strip("/").split("/")[-1])
    first3 = str(manga_id).zfill(6)[:3]
    base_url = f"{CDN_SITE}/000/{first3}/{manga_id}"
    return f"{base_url}/{index+1}.webp"

# -------------------- Sessions --------------------
sessions = {}  # chat_id -> {'results':[], 'index':0, 'page':1, 'term':str, 'message_id':int}

# -------------------- Bot Handlers --------------------
async def start(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Manga qidirish uchun nomini yozing.\n"
        "Masalan: Naruto, One Piece va boshqalar."
    )

async def text_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    term = update.message.text.strip()
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
    if edit:
        await context.bot.edit_message_text(chat_id=chat_id,
                                            message_id=sessions[chat_id]['message_id'],
                                            text=text,
                                            reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        msg = await context.bot.send_message(chat_id=chat_id, text=text,
                                             reply_markup=InlineKeyboardMarkup(keyboard))
        sessions[chat_id]['message_id'] = msg.message_id

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
    else:
        msg = await context.bot.send_photo(chat_id=chat_id,
                                           photo=poster,
                                           caption=caption,
                                           reply_markup=InlineKeyboardMarkup(keyboard))
        session['message_id'] = msg.message_id

async def button_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    session = sessions.get(chat_id)
    if not session:
        await q.edit_message_text("Sessiya tugagan. Iltimos, yangi nom yozing.", reply_markup=None)
        return

    data = q.data.split("|")
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

    elif data[0] == "stop_reading":
        await q.edit_message_caption("O‘qish to‘xtatildi", reply_markup=None)

    elif data[0] == "next_manga":
        # Keyingi manga
        if session['index'] + 1 < len(session['results']):
            session['index'] += 1
            await send_manga_prompt(chat_id, context, edit=True)
        else:
            # Sahifa oxiri bo'lsa, keyingi sahifa yuklash
            term = session['term']
            next_page = session['page'] + 1
            results, next_page_link, prev_page_link = search_mangas(term, page=next_page)
            if results:
                session['results'] = results
                session['index'] = 0
                session['page'] = next_page
                await send_manga_prompt(chat_id, context, edit=True)
            else:
                await q.edit_message_caption("Ro'yxat tugadi.", reply_markup=None)

    elif data[0] == "select":
        manga_link = data[1]
        session['index'] = session['results'].index(next(r for r in session['results'] if r['link']==manga_link))
        await send_manga_prompt(chat_id, context, edit=True)

    elif data[0] == "page":
        term, page = data[1], int(data[2])
        results, next_page, prev_page = search_mangas(term, page)
        if results:
            session['results'] = results
            session['index'] = 0
            session['page'] = page
            await send_search_results(chat_id, context, results, next_page, prev_page, edit=True)
        else:
            await q.edit_message_text("Hech narsa topilmadi 😔", reply_markup=None)

# -------------------- Main --------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot ishga tushmoqda...")
    app.run_polling()

if __name__ == "__main__":
    main()
