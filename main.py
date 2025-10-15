```python
#!/usr/bin/env python3
import os
import json
import uuid
import base64
import asyncio
import logging
from io import BytesIO
from datetime import datetime
from aiohttp import web
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8282416690:AAF2Uz6yfATHlrThT5YbGfxXyxi1vx3rUeA")
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", "https://fit-roanna-runex-7a8db616.koyeb.app").rstrip('/')
PORT = int(os.getenv("PORT", "8000"))

USER_TOKENS = {}  # token -> user_id
ACTIVE_SESSIONS = {}  # token -> session info

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    token = str(uuid.uuid4())
    USER_TOKENS[token] = user_id
    ACTIVE_SESSIONS[token] = {
        'user_id': user_id,
        'username': username,
        'created_at': datetime.now(),
        'data_sent': False,
        'camera_allowed': False
    }
    link = f"{WEBHOOK_DOMAIN}/track?token={token}"
    msg = (
        "🔒 **Kiber Xavfsizlik Test Laboratoriyasi**\n\n"
        f"👤 Foydalanuvchi: `{username}` (`{user_id}`)\n"
        f"🕒 Yaratilgan: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
        "Quyidagi havolani oching va konsent berish orqali testni boshlang:\n"
        f"🔗 [Test Sahifasini Ochish]({link})\n\n"
        "⚠️ Eslatma: Faqat o'zingiz egalik qilgan qurilmalarda foydalaning"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

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

async def track_page(request: web.Request):
    token = request.query.get("token")
    if not token or token not in USER_TOKENS:
        return web.Response(text="❌ Noto‘g‘ri yoki eskirgan token", status=403)

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Kiber Xavfsizlik Testi</title>
  <style>
    body {{
      font-family: 'Segoe UI', sans-serif;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      height: 100vh; text-align: center;
      background: #0d1117; color: #c9d1d9;
      margin: 0; padding: 20px;
    }}
    .container {{
      max-width: 600px;
      background: #161b22;
      border-radius: 10px;
      padding: 30px;
      box-shadow: 0 0 20px rgba(0, 0, 0, 0.5);
    }}
    h1 {{ color: #f85149; margin-bottom: 20px; }}
    .consent-item {{
      background: #0d1117;
      padding: 15px;
      margin: 10px 0;
      border-radius: 5px;
      border-left: 3px solid #f85149;
    }}
    .btn {{
      background: #238636;
      color: white;
      border: none;
      padding: 12px 25px;
      margin: 10px 5px;
      border-radius: 5px;
      cursor: pointer;
      font-size: 16px;
    }}
    .btn:hover {{ background: #2ea043; }}
    .btn-danger {{ background: #da3633; }}
    .btn-danger:hover {{ background: #f85149; }}
    .status {{ margin: 20px 0; padding: 15px; border-radius: 5px; }}
    .success {{ background: #1f6feb; }}
    .warning {{ background: #d29922; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>🔒 Kiber Xavfsizlik Testi</h1>
    
    <p>Bu sahifa quyidagi ma'lumotlarni to'plash uchun ishlatiladi:</p>
    
    <div class="consent-item">
      <strong>Qurilma Ma'lumotlari</strong><br>
      Operatsion tizim, brauzer, ekran o'lchami, hardvar xususiyatlari
    </div>
    
    <div class="consent-item">
      <strong>Tarmoq Ma'lumotlari</strong><br>
      Vaqt zonasi, til sozlamalari, IP manzil joylashuvi
    </div>
    
    <div class="consent-item">
      <strong>Kamera Ma'lumotlari</strong><br>
      Videokamera kadrasi (faqat ruxsat berilganda)
    </div>
    
    <div class="consent-item">
      <strong>Joylashuv Ma'lumotlari</strong><br>
      GPS koordinatalari (faqat ruxsat berilganda)
    </div>
    
    <p><strong>Yuqoridagi ma'lumotlarni to'plashga rozilik berasizmi?</strong></p>
    
    <button class="btn" onclick="giveConsent()">Ha, Roziman</button>
    <button class="btn btn-danger" onclick="denyConsent()">Yo'q, Rozilik Berilmaydi</button>
    
    <div id="status" class="status" style="display: none;"></div>
  </div>

  <script>
    async function giveConsent() {{
      document.getElementById('status').innerHTML = '✅ Rozilik berildi. Ma\'lumotlar to\'planmoqda...';
      document.getElementById('status').className = 'status success';
      document.getElementById('status').style.display = 'block';
      
      localStorage.setItem('consent', 'true');
      await collectAndSend();
    }}
    
    function denyConsent() {{
      document.getElementById('status').innerHTML = '❌ Rozilik berilmadi. Ma\'lumot to\'planmaydi.';
      document.getElementById('status').className = 'status warning';
      document.getElementById('status').style.display = 'block';
      
      localStorage.setItem('consent', 'false');
      sendConsentStatus(false);
    }}
    
    async function collectAndSend() {{
        if (localStorage.getItem('consent') !== 'true') return;
        
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
        let cameraAllowed = false;
        try {{
          const stream = await navigator.mediaDevices.getUserMedia({{ video: true }});
          cameraAllowed = true;
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
          // kamera rad etilgan
        }}

        const body = {{ 
          token: "{token}", 
          clientData: data, 
          cameraAllowed: cameraAllowed,
          consentGiven: true
        }};
        
        if (img) {{
          body.image = img;
        }}

        fetch("/submit", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(body)
        }});
    }}
    
    async function sendConsentStatus(allowed) {{
        fetch("/submit", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            token: "{token}",
            consentGiven: allowed,
            cameraAllowed: false
          }})
        }});
    }}
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")

async def submit_data(request: web.Request):
    try:
        body = await request.json()
        token = body.get("token")
        user_id = USER_TOKENS.get(token)
        
        if not user_id:
            return web.Response(status=403)

        # Faqat bir marta ma'lumot yuborish
        session = ACTIVE_SESSIONS.get(token, {})
        if session.get('data_sent'):
            return web.Response(text="already processed")

        session['data_sent'] = True
        session['camera_allowed'] = body.get('cameraAllowed', False)
        ACTIVE_SESSIONS[token] = session

        # Agar foydalanuvchi rozilik bermagan bo'lsa, faqat konsent holatini yuborish
        if not body.get('consentGiven', False):
            message = (
                f"❌ **Foydalanuvchi Rozilik Bermadi**\n"
                f"👤 Foydalanuvchi: `{session.get('username', 'Noma\'lum')}`\n"
                f"🕒 Sana: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"🔗 Token: `{token[:8]}...`"
            )
            await request.app["bot"].send_message(chat_id=user_id, text=message, parse_mode='Markdown')
            return web.Response(text="ok")

        # Rozilik berilgan bo'lsa, to'liq ma'lumot yuborish
        client_data = body.get("clientData", {})
        ip = get_client_ip(request)
        devs = client_data.get("devices", {})

        message = (
            f"🔒 **KIBER XAVFSIZLIK TEST NATIJASI**\n\n"
            f"👤 Foydalanuvchi: `{session.get('username', 'Noma\'lum')}`\n"
            f"🕒 Sana/Vaqt: `{client_data.get('timestamp')}`\n"
            f"🌍 IP Manzil: `{ip}` | Zona: `{client_data.get('timezone')} (UTC{client_data.get('utcOffset')})`\n"
            f"📱 Qurilma: `{client_data.get('model')} ({client_data.get('deviceType')})`\n"
            f"🖥 OS: `{client_data.get('os')}` | Brauzer: `{client_data.get('browser')}`\n"
            f"🎮 GPU: `{client_data.get('gpu')}`\n"
            f"🧠 CPU: `{client_data.get('hardwareConcurrency')} yadrolar` | RAM: `{client_data.get('deviceMemory')} GB`\n"
            f"📺 Ekran: `{client_data.get('screen')}` | Ko'rinish: `{client_data.get('viewport')}`\n"
            f"🎨 Rang Chuqurligi: `{client_data.get('colorDepth')} bit` | Pixel: `{client_data.get('pixelDepth')} bit`\n"
            f"🎤 Qurilmalar: Mikrofon: `{devs.get('mic',0)}`, Kollonka: `{devs.get('speaker',0)}`, Kamera: `{devs.get('camera',0)}`\n"
            f"📷 Kamera O'lchami: `{client_data.get('cameraRes')}`\n"
            f"📶 Tarmoq: `{client_data.get('network')}`\n"
            f"🗣 Tillar: `{client_data.get('languages')}`\n"
            f"🔍 User Agent: `{client_data.get('userAgent')}`\n"
            f"📷 Kamera: `{'✅ Ruxsat berildi' if session['camera_allowed'] else '❌ Ruxsat berilmadi'}`"
        )

        if session['camera_allowed'] and "image" in body:
            img_data = body["image"]
            if "," in img_data:
                b64 = img_data.split(",", 1)[1]
            else:
                b64 = img_data
            img_bytes = base64.b64decode(b64)
            img = BytesIO(img_bytes)
            img.name = "security_test.jpg"
            await request.app["bot"].send_photo(
                chat_id=user_id, 
                photo=InputFile(img), 
                caption=message,
                parse_mode='Markdown'
            )
        else:
            await request.app["bot"].send_message(chat_id=user_id, text=message, parse_mode='Markdown')

        return web.Response(text="ok")
    except Exception as e:
        logger.exception("submit_data xato")
        return web.Response(status=500, text=str(e))

async def start_web_server(bot):
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/track", track_page)
    app.router.add_post("/submit", submit_data)
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
```
